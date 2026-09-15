"""Part 1 / Part 2 真实评测。全部输出写到 D:\\Project\\guideflow\\code\\eval\\results。"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import traceback
from pathlib import Path

# 禁止把缓存/临时文件写到 C 盘
ROOT = Path(__file__).resolve().parents[1]
TMP = Path(r"D:\Project\guideflow\.tmp")
HF = Path(r"D:\Project\guideflow\.cache\huggingface")
TMP.mkdir(parents=True, exist_ok=True)
HF.mkdir(parents=True, exist_ok=True)
os.environ["TMP"] = str(TMP)
os.environ["TEMP"] = str(TMP)
os.environ["TMPDIR"] = str(TMP)
os.environ["HF_HOME"] = str(HF)
os.environ["HF_HUB_CACHE"] = str(HF / "hub")
os.environ["HUGGINGFACE_HUB_CACHE"] = str(HF / "hub")
os.environ["TRANSFORMERS_CACHE"] = str(HF / "transformers")
os.environ["HF_DATASETS_CACHE"] = str(HF / "datasets")

sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from backend.app.services.qa import QAService
from backend.app.services.qwen import QwenClient
from backend.app.settings import load_settings, settings_for_source

EVAL_DIR = Path(__file__).resolve().parent
RESULT_DIR = EVAL_DIR / "results"
RAW_DIR = RESULT_DIR / "raw"
STATE_PATH = RESULT_DIR / "state.json"

MCQ_SUFFIX = (
    "\n\n以上为单选题。允许简要推理，但最后一行必须写成：\n最终答案: X\n"
    "其中 X 仅为 A、B、C、D 或 E 之一。"
)


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def load_state() -> dict:
    if STATE_PATH.exists():
        return load_json(STATE_PATH)
    return {"done": []}


def mark_done(state: dict, key: str) -> None:
    if key not in state["done"]:
        state["done"].append(key)
    save_json(STATE_PATH, state)


def format_mcq(item: dict) -> str:
    lines = [item["question"].strip(), "", "选项："]
    for k in sorted(item["options"].keys()):
        lines.append(f"{k}. {item['options'][k]}")
    lines.append(MCQ_SUFFIX)
    return "\n".join(lines)


def parse_mcq_letter(text: str) -> tuple[str, str]:
    if not text:
        return "invalid", "invalid"
    m = list(re.finditer(r"最终答案\s*[:：]\s*([A-Ea-e])", text))
    if m:
        return m[-1].group(1).upper(), "1"
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    hits = []
    for ln in lines:
        if re.fullmatch(r"[A-Ea-e]", ln):
            hits.append(ln.upper())
        elif re.fullmatch(r"(?:答案|选项)\s*[:：]?\s*[A-Ea-e]", ln):
            hits.append(ln[-1].upper())
    if len(set(hits[-2:])) == 1 and hits:
        return hits[-1], "2"
    if hits:
        return hits[-1], "2"
    return "invalid", "invalid"


def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n <= 0:
        return (0.0, 0.0)
    p = k / n
    den = 1 + z * z / n
    center = (p + z * z / (2 * n)) / den
    half = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / den
    return (max(0.0, center - half), min(1.0, center + half))


_PAGE_PREFIX = re.compile(r"^PAGE[-_]", re.I)


def normalize_unit(u: str) -> str:
    """同一物理单元只保留一个 ID。

    ``nccn:DIAG-1`` / ``nccn:page-DIAG-1`` / ``NCCN:PAGE-DIAG-1`` → ``NCCN:DIAG-1``。
    禁止把 page_code 与 source_id 计成两个 C，否则 Precision 分母被系统性放大。
    """
    raw = (u or "").strip()
    if not raw:
        return ""
    if ":" in raw:
        src, rest = raw.split(":", 1)
    else:
        src, rest = "", raw
    src = src.strip().upper()
    rest = re.sub(r"\s+", " ", rest.strip())
    rest = _PAGE_PREFIX.sub("", rest)
    rest = rest.replace("_", " ")
    rest = re.sub(r"\s+", " ", rest).upper()
    if not rest:
        return ""
    return f"{src}:{rest}" if src else rest


def unit_from_source(src: dict, data_source: str) -> str:
    page = str(src.get("printed_page_code") or "").strip()
    if page and not page.lower().startswith("p."):
        return normalize_unit(f"{data_source}:{page}")
    sid = str(src.get("source_id") or "").strip()
    if sid:
        return normalize_unit(f"{data_source}:{sid}")
    cite = str(src.get("citation_label") or "").strip()
    if cite and not cite.lower().startswith("p."):
        return normalize_unit(f"{data_source}:{cite}")
    return ""


def source_units(src: dict, data_source: str) -> list[str]:
    u = unit_from_source(src, data_source)
    return [u] if u else []


def uniq_units(xs: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in xs:
        n = normalize_unit(x)
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def cited_indices(answer: str) -> set[int]:
    found = set()
    for m in re.finditer(r"\[S(\d+)\]", answer or "", flags=re.I):
        found.add(int(m.group(1)))
    return found


def extract_page_codes(answer: str) -> list[str]:
    pats = [
        r"\b((?:BCEL|FOLL|MANT|BURK|DIAG|ST|NHODG|MZL|EMZL)[A-Z\-]*\s*\d+(?:\s+OF\s+\d+)?)",
        r"\b(MS-\d+)\b",
    ]
    found = []
    for pat in pats:
        for m in re.finditer(pat, answer or "", flags=re.I):
            found.append(normalize_unit(m.group(1)))
    return found


def match_gold(gold: list[str], pred_units: list[str]) -> set[str]:
    gold_n = {normalize_unit(g) for g in gold if normalize_unit(g)}
    pred_n = {normalize_unit(p) for p in pred_units if normalize_unit(p)}
    hit = set()
    for g in gold_n:
        if g in pred_n:
            hit.add(g)
            continue
        g_suffix = g.split(":", 1)[-1]
        for p in pred_n:
            p_suffix = p.split(":", 1)[-1]
            if g_suffix and g_suffix == p_suffix:
                hit.add(g)
                break
            if g_suffix and (p_suffix.endswith(g_suffix) or g_suffix.endswith(p_suffix)) and min(len(g_suffix), len(p_suffix)) >= 6:
                hit.add(g)
                break
    return hit


def negative_label(answer: str) -> str:
    text = answer or ""
    refuse = bool(
        re.search(
            r"未覆盖|未提及|没有给出|无法给出|不能编造|拒绝编造|超出指南|指南未",
            text,
        )
    )
    halluc_cite = bool(re.search(r"BCEL-\d+|FOLL-|MANT-|\[S\d+\]", text)) and not refuse
    dose = bool(re.search(r"\d+\s*mg", text, flags=re.I))
    if refuse and not dose:
        return "拒绝"
    if dose and not refuse:
        return "过度"
    if halluc_cite:
        return "幻觉"
    if refuse:
        return "拒绝"
    return "过度"


def conclusion_label(item: dict, answer: str) -> str:
    if item.get("negative"):
        lab = negative_label(answer)
        return {"拒绝": "支持", "幻觉": "不支持", "过度": "不支持"}.get(lab, "部分支持")
    expected = item.get("expected_conclusion") or ""
    keys = [w for w in re.split(r"[，。；、/（）()\s]+", expected) if len(w) >= 2]
    if not answer:
        return "不支持"
    hits = sum(1 for w in keys if w.lower() in answer.lower())
    if hits >= max(2, len(keys) // 3):
        return "支持"
    if hits >= 1:
        return "部分支持"
    return "不支持"


class Runner:
    def __init__(self) -> None:
        self.settings = load_settings()
        self.services: dict[str, QAService] = {}
        self.baseline_client: QwenClient | None = None

    def guideflow(self, source: str) -> QAService:
        if source not in self.services:
            print(f"[init] QAService({source})", flush=True)
            self.services[source] = QAService(settings_for_source(source, self.settings))
        return self.services[source]

    def baseline(self) -> QwenClient:
        if self.baseline_client is None:
            s = self.settings
            self.baseline_client = QwenClient(
                api_key=s.qwen_api_key,
                base_url=s.qwen_base_url,
                model=s.qwen_model,
                source_key="nccn",
            )
        return self.baseline_client

    def ask_guideflow(self, question: str, source: str) -> dict:
        t0 = time.time()
        result = self.guideflow(source).ask(question, trace_enabled=True, enable_literature=False)
        elapsed = round(time.time() - t0, 2)
        payload = result.to_web_payload()
        payload["elapsed_s"] = elapsed
        return payload

    def ask_baseline(self, question: str) -> dict:
        t0 = time.time()
        client = self.baseline()
        answer = client._chat_text(
            [
                {
                    "role": "system",
                    "content": "你是医学考试助手。只根据自身知识作答，不要编造指南页码。",
                },
                {"role": "user", "content": question},
            ],
            temperature=0.0,
            timeout=90,
        )
        return {
            "answer_markdown": answer,
            "sources": [],
            "elapsed_s": round(time.time() - t0, 2),
            "answer_kind": "baseline_llm",
            "degraded": [],
        }


def run_part1(runner: Runner, systems: list[str], resume: bool) -> None:
    items = load_json(EVAL_DIR / "part1_questions.json")
    state = load_state()
    rows_path = RESULT_DIR / "part1_rows.json"
    rows = load_json(rows_path) if rows_path.exists() else []
    have = {(r["system"], r["id"]) for r in rows}

    for item in items:
        q = format_mcq(item)
        for sys_name in systems:
            key = f"p1:{sys_name}:{item['id']}"
            if resume and ((sys_name, item["id"]) in have or key in state["done"]):
                continue
            print(f"[P1] {sys_name} {item['id']}", flush=True)
            try:
                if sys_name == "guideflow":
                    payload = runner.ask_guideflow(q, "nccn")
                else:
                    payload = runner.ask_baseline(q)
                err = None
            except Exception as exc:
                payload = {"answer_markdown": "", "sources": [], "elapsed_s": None, "degraded": [str(exc)]}
                err = traceback.format_exc()
            answer = payload.get("answer_markdown") or ""
            letter, step = parse_mcq_letter(answer)
            gold = item["gold"]
            correct = int(letter == gold)
            rec = {
                "batch": "EVAL-20260914",
                "system": sys_name,
                "id": item["id"],
                "gold": gold,
                "parsed": letter,
                "parse_step": step,
                "correct": correct,
                "elapsed_s": payload.get("elapsed_s"),
                "answer_kind": payload.get("answer_kind"),
                "tail": answer.replace("\n", " ")[-200:],
                "error": err,
            }
            save_json(RAW_DIR / f"p1_{sys_name}_{item['id']}.json", {"item": item, "payload": payload, "rec": rec})
            rows.append(rec)
            save_json(rows_path, rows)
            mark_done(state, key)

    summarize_part1(items, rows)


def summarize_part1(items: list[dict], rows: list[dict]) -> None:
    by_id = {x["id"]: x for x in items}
    summary = []
    for sys_name in sorted({r["system"] for r in rows}):
        sub = [r for r in rows if r["system"] == sys_name]
        n = len(sub)
        k = sum(r["correct"] for r in sub)
        valid = sum(r["parse_step"] != "invalid" for r in sub)
        lo, hi = wilson_ci(k, n)
        dlbcl = [r for r in sub if by_id.get(r["id"], {}).get("disease") == "DLBCL"]
        other = [r for r in sub if by_id.get(r["id"], {}).get("disease") != "DLBCL"]
        summary.append(
            {
                "system": sys_name,
                "n": n,
                "strict_acc": round(k / n, 4) if n else None,
                "ci95": [round(lo, 4), round(hi, 4)],
                "valid_rate": round(valid / n, 4) if n else None,
                "dlbcl_n": len(dlbcl),
                "dlbcl_acc": round(sum(r["correct"] for r in dlbcl) / len(dlbcl), 4) if dlbcl else None,
                "other_n": len(other),
                "other_acc": round(sum(r["correct"] for r in other) / len(other), 4) if other else None,
            }
        )
    save_json(RESULT_DIR / "part1_summary.json", summary)
    print("PART1 summary", json.dumps(summary, ensure_ascii=False), flush=True)


def run_part2(runner: Runner, systems: list[str], resume: bool) -> None:
    items = load_json(EVAL_DIR / "part2_questions.json")
    state = load_state()
    rows_path = RESULT_DIR / "part2_rows.json"
    rows = load_json(rows_path) if rows_path.exists() else []
    have = {(r["system"], r["id"]) for r in rows}

    for item in items:
        for sys_name in systems:
            key = f"p2:{sys_name}:{item['id']}"
            if resume and ((sys_name, item["id"]) in have or key in state["done"]):
                continue
            print(f"[P2] {sys_name} {item['id']} {item['data_source']}", flush=True)
            try:
                if sys_name == "guideflow":
                    payload = runner.ask_guideflow(item["question"], item["data_source"])
                else:
                    payload = runner.ask_baseline(item["question"])
                err = None
            except Exception as exc:
                payload = {"answer_markdown": "", "sources": [], "elapsed_s": None, "degraded": [str(exc)]}
                err = traceback.format_exc()
            answer = payload.get("answer_markdown") or ""
            sources = payload.get("sources") or []
            r_units = []
            for src in sources:
                r_units.extend(source_units(src, item["data_source"]))
            idxs = cited_indices(answer)
            c_units = []
            for i in sorted(idxs):
                if 1 <= i <= len(sources):
                    c_units.extend(source_units(sources[i - 1], item["data_source"]))
            for code in extract_page_codes(answer):
                c_units.append(f"{item['data_source']}:{code}")
            r_units, c_units = uniq_units(r_units), uniq_units(c_units)
            gold = item.get("G") or []
            inter = match_gold(gold, c_units)
            g_n = len(gold)
            c_n = len(c_units)
            rec_q = (len(inter) / g_n) if g_n else None
            prec_q = (len(inter) / c_n) if c_n else (0.0 if g_n else None)
            rec = {
                "batch": "EVAL-20260914",
                "system": sys_name,
                "id": item["id"],
                "data_source": item["data_source"],
                "negative": bool(item.get("negative")),
                "R": r_units,
                "C": c_units,
                "G": gold,
                "hit": sorted(inter),
                "hit_n": len(inter),
                "g_n": g_n,
                "c_n": c_n,
                "recall_q": rec_q,
                "precision_q": prec_q,
                "conclusion": conclusion_label(item, answer),
                "neg_label": negative_label(answer) if item.get("negative") else "",
                "elapsed_s": payload.get("elapsed_s"),
                "answer_kind": payload.get("answer_kind"),
                "tail": answer.replace("\n", " ")[-200:],
                "error": err,
            }
            save_json(RAW_DIR / f"p2_{sys_name}_{item['id']}.json", {"item": item, "payload": payload, "rec": rec})
            rows.append(rec)
            save_json(rows_path, rows)
            mark_done(state, key)

    summarize_part2(items, rows)


def summarize_part2(items: list[dict], rows: list[dict]) -> None:
    summary = []
    for sys_name in sorted({r["system"] for r in rows}):
        for src in ["nccn", "csco", "eha", "ALL"]:
            sub = [r for r in rows if r["system"] == sys_name and (src == "ALL" or r["data_source"] == src)]
            pos = [r for r in sub if not r["negative"]]
            neg = [r for r in sub if r["negative"]]
            hit = sum(r["hit_n"] for r in pos)
            g = sum(r["g_n"] for r in pos)
            c = sum(r["c_n"] for r in pos)
            p = (hit / c) if c else 0.0
            rcall = (hit / g) if g else 0.0
            f1 = (2 * p * rcall / (p + rcall)) if (p + rcall) else 0.0
            recs = [r["recall_q"] for r in pos if r["recall_q"] is not None]
            precs = [r["precision_q"] for r in pos if r["precision_q"] is not None]
            summary.append(
                {
                    "system": sys_name,
                    "data_source": src,
                    "n_pos": len(pos),
                    "recall_micro": round(rcall, 4),
                    "precision_micro": round(p, 4),
                    "f1_micro": round(f1, 4),
                    "recall_macro": round(sum(recs) / len(recs), 4) if recs else None,
                    "precision_macro": round(sum(precs) / len(precs), 4) if precs else None,
                    "n_neg": len(neg),
                    "neg_refuse_rate": round(sum(r["neg_label"] == "拒绝" for r in neg) / len(neg), 4) if neg else None,
                    "neg_halluc_rate": round(sum(r["neg_label"] == "幻觉" for r in neg) / len(neg), 4) if neg else None,
                }
            )
    save_json(RESULT_DIR / "part2_summary.json", summary)
    print("PART2 summary", json.dumps(summary, ensure_ascii=False), flush=True)


def write_meta() -> None:
    import subprocess

    commit = ""
    try:
        commit = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=str(ROOT), text=True).strip()
    except Exception:
        commit = "unknown"
    s = load_settings()
    meta = {
        "batch_id": "EVAL-20260914",
        "date": "2026-09-14",
        "git_commit": commit,
        "qwen_model": s.qwen_model,
        "temperature_note": "baseline chat temperature=0.0；DLBCL-Evidence 沿用线上 generate 默认（约 0.1）",
        "nccn_pdf": "（2026.V3）NCCN临床 实践指南：B细胞淋巴瘤.pdf",
        "csco_pdf": "3.2025CSCO淋巴瘤诊疗指南(OCR).pdf",
        "eha_pdf": "2025 EHA临床实践指南：大B细胞淋巴瘤的诊断、治疗和随访.pdf",
        "retrieval": {"bm25_top_k": s.bm25_top_k, "rerank_top_k": s.rerank_top_k, "final_top_k": s.final_top_k},
        "systems": ["guideflow", "baseline_llm"],
        "download_cache": r"D:\Project\guideflow\code\eval\raw 与 D:\Project\guideflow\.tmp",
    }
    save_json(RESULT_DIR / "meta.json", meta)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--part", choices=["1", "2", "all"], default="all")
    parser.add_argument("--system", choices=["guideflow", "baseline", "both"], default="both")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    write_meta()
    systems = ["guideflow", "baseline"] if args.system == "both" else [args.system]
    runner = Runner()
    if args.part in {"1", "all"}:
        run_part1(runner, systems, args.resume)
    if args.part in {"2", "all"}:
        run_part2(runner, systems, args.resume)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
