"""Part 2 citation / retrieval runner with stage-aware R and gold groups."""
from __future__ import annotations

import argparse
import subprocess
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path
import re

from common.paths import CODE_ROOT, DATASETS, RUNS, pin_caches_to_d, ensure_sys_path

pin_caches_to_d()
ensure_sys_path()
sys.path.insert(0, str(CODE_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from common.io import load_json, save_json
from common.scoring import (
    conclusion_label,
    disease_from_units,
    flatten_gold_units,
    gold_size,
    match_gold_groups,
    negative_label,
    retrieval_units_from_payload,
    sentence_label_stats,
    unit_kind_from_units,
)
from common.stats import bootstrap_ci
from common.settings_override import apply_arm, load_arm_yaml

from backend.app.services.qa import QAService
from backend.app.services.qwen import QwenClient
from backend.app.settings import load_settings


def git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=str(CODE_ROOT.parent), text=True
        ).strip()
    except Exception:
        return "unknown"


def default_question_paths() -> list[Path]:
    v3 = DATASETS / "part2" / "v3_nccn_questions.json"
    v2 = DATASETS / "part2" / "v2_questions.json"
    if v3.exists():
        paths = [v3]
        safety = DATASETS / "part2" / "v3_nccn_safety.json"
    else:
        paths = [v2 if v2.exists() else DATASETS / "part2" / "v1_questions.json"]
        safety = DATASETS / "part2" / "safety_refusal.json"
    if safety.exists():
        paths.append(safety)
    return paths


def load_question_sets(paths: list[Path] | None) -> tuple[list[dict], list[str]]:
    used = paths or default_question_paths()
    items: list[dict] = []
    seen: set[str] = set()
    for path in used:
        for item in load_json(path):
            key = str(item.get("id") or "")
            if not key or key in seen:
                continue
            seen.add(key)
            items.append(item)
    return items, [str(p) for p in used]


class Part2Runner:
    def __init__(self, arm: dict) -> None:
        self.arm = arm
        self.base = load_settings()
        self._services: dict[str, QAService] = {}
        self._client: QwenClient | None = None

    def qa(self, source: str) -> QAService:
        if source not in self._services:
            settings = apply_arm(self.base, self.arm, source=source)
            self._services[source] = QAService(settings)
        return self._services[source]

    def warmup(self, sources: list[str]) -> None:
        for source in sources:
            self.qa(source)

    def client(self) -> QwenClient:
        if self._client is None:
            s = apply_arm(self.base, self.arm, source="nccn")
            self._client = QwenClient(
                api_key=s.qwen_api_key,
                base_url=s.qwen_base_url,
                model=s.qwen_model,
                source_key="nccn",
                generate_temperature=float(getattr(s, "generate_temperature", 0.0) or 0.0),
                answer_policy=str(getattr(s, "answer_policy", "guideline_only") or "guideline_only"),
            )
        return self._client

    def ask_system(self, question: str, source: str) -> dict:
        t0 = time.time()
        result = self.qa(source).ask(question, trace_enabled=True, enable_literature=False)
        payload = result.to_web_payload()
        payload["elapsed_s"] = round(time.time() - t0, 2)
        return payload

    def ask_baseline(self, question: str) -> dict:
        t0 = time.time()
        answer = self.client()._chat_text(
            [
                {"role": "system", "content": "你是医学指南助手。只根据自身知识作答，不要编造页码。"},
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
        }


def _loose_gold(item: dict) -> list:
    gold = list(item.get("G") or [])
    extra = item.get("G_opt") or []
    return gold + extra


def score_item(item: dict, payload: dict) -> dict:
    stages = retrieval_units_from_payload(payload, item["data_source"])
    gold = item.get("G") or []
    gold_loose = _loose_gold(item)
    c_units = stages.get("cited") or []
    stage_units = {
        "raw": stages.get("raw") or [],
        "rerank": stages.get("rerank") or [],
        "final": stages.get("final") or [],
        "gated": stages.get("gated") or stages.get("final") or [],
        "cited": c_units,
    }
    hits = {name: match_gold_groups(gold, units) for name, units in stage_units.items()}
    hit_loose = match_gold_groups(gold_loose, c_units)
    g_n = gold_size(gold)
    g_loose_n = gold_size(gold_loose)
    c_n = len(c_units)
    labels = sentence_label_stats(payload.get("answer_markdown") or "")
    disease = item.get("disease") or disease_from_units(flatten_gold_units(gold))
    return {
        "R_raw": stage_units["raw"],
        "R_rerank": stage_units["rerank"],
        "R_final": stage_units["final"],
        "R_gated": stage_units["gated"],
        "R": stage_units["raw"] or stage_units["final"],
        "C": c_units,
        "G": gold,
        "hit": sorted(hits["cited"]),
        "hit_n": len(hits["cited"]),
        "hit_loose_n": len(hit_loose),
        "hit_raw_n": len(hits["raw"]),
        "hit_rerank_n": len(hits["rerank"]),
        "hit_final_n": len(hits["final"]),
        "hit_gated_n": len(hits["gated"]),
        "hit_retrieval_n": len(hits["raw"] or hits["final"]),
        "g_n": g_n,
        "g_loose_n": g_loose_n,
        "c_n": c_n,
        "recall_q": (len(hits["cited"]) / g_n) if g_n else None,
        "precision_q": (len(hits["cited"]) / c_n) if c_n else (0.0 if g_n else None),
        "precision_loose_q": (len(hit_loose) / c_n) if c_n else (0.0 if g_loose_n else None),
        "recall_raw_q": (len(hits["raw"]) / g_n) if g_n else None,
        "recall_rerank_q": (len(hits["rerank"]) / g_n) if g_n else None,
        "recall_final_q": (len(hits["final"]) / g_n) if g_n else None,
        "recall_gated_q": (len(hits["gated"]) / g_n) if g_n else None,
        "recall_retrieval_q": (len(hits["raw"] or hits["final"]) / g_n) if g_n else None,
        "conclusion": conclusion_label(item, payload.get("answer_markdown") or ""),
        "neg_label": negative_label(payload.get("answer_markdown") or "") if item.get("negative") else "",
        "disease": disease,
        "unit_kind": item.get("unit_kind") or unit_kind_from_units(flatten_gold_units(gold)),
        "item_set": item.get("item_set")
        or (
            "v1"
            if re.fullmatch(r"P2-N(?:0\d|1[0-6])", str(item.get("id") or ""))
            else "v3_new"
        ),
        **labels,
    }


def _mean(xs: list[float | None]) -> float | None:
    vals = [x for x in xs if x is not None]
    if not vals:
        return None
    return round(sum(vals) / len(vals), 4)


def _slice_metrics(pos: list[dict], neg: list[dict], extra: dict) -> dict:
    hit = sum(r.get("hit_n") or 0 for r in pos)
    hit_loose = sum(r.get("hit_loose_n") or 0 for r in pos)
    g = sum(r.get("g_n") or 0 for r in pos)
    g_loose = sum(r.get("g_loose_n") or 0 for r in pos)
    c = sum(r.get("c_n") or 0 for r in pos)
    p = (hit / c) if c else 0.0
    p_loose = (hit_loose / c) if c else 0.0
    rcall = (hit / g) if g else 0.0
    f1 = (2 * p * rcall / (p + rcall)) if (p + rcall) else 0.0
    recs = [r["recall_q"] for r in pos if r.get("recall_q") is not None]
    precs = [r["precision_q"] for r in pos if r.get("precision_q") is not None]
    funnel = {}
    for name, key in (
        ("raw", "hit_raw_n"),
        ("rerank", "hit_rerank_n"),
        ("final", "hit_final_n"),
        ("gated", "hit_gated_n"),
        ("cited", "hit_n"),
    ):
        h = sum(r.get(key) or 0 for r in pos)
        funnel[f"recall_{name}_micro"] = round((h / g) if g else 0.0, 4)
    return {
        **extra,
        "n_pos": len(pos),
        "recall_cite_micro": round(rcall, 4),
        "recall_cite_ci": list(bootstrap_ci(recs)),
        "recall_raw_micro": funnel["recall_raw_micro"],
        "recall_rerank_micro": funnel["recall_rerank_micro"],
        "recall_final_micro": funnel["recall_final_micro"],
        "recall_gated_micro": funnel["recall_gated_micro"],
        "precision_micro": round(p, 4),
        "precision_loose_micro": round(p_loose, 4),
        "f1_micro": round(f1, 4),
        "recall_macro": round(sum(recs) / len(recs), 4) if recs else None,
        "precision_macro": round(sum(precs) / len(precs), 4) if precs else None,
        "g_loose_n": g_loose,
        "generic_rate": _mean([r.get("generic_rate") for r in pos]),
        "unlabeled_rate": _mean([r.get("unlabeled_rate") for r in pos]),
        "n_neg": len(neg),
        "neg_refuse_rate": round(sum(r["neg_label"] == "拒绝" for r in neg) / len(neg), 4) if neg else None,
        "neg_halluc_rate": round(sum(r["neg_label"] == "幻觉" for r in neg) / len(neg), 4) if neg else None,
        "neg_over_rate": round(sum(r["neg_label"] == "过度" for r in neg) / len(neg), 4) if neg else None,
    }


def summarize(rows: list[dict]) -> list[dict]:
    summary = []
    for sys_name in sorted({r["system"] for r in rows}):
        sys_rows = [r for r in rows if r["system"] == sys_name]
        for src in ["nccn", "csco", "eha", "ALL"]:
            sub = [r for r in sys_rows if src == "ALL" or r["data_source"] == src]
            pos = [r for r in sub if not r.get("negative")]
            neg = [r for r in sub if r.get("negative")]
            if not sub:
                continue
            summary.append(_slice_metrics(pos, neg, {"system": sys_name, "slice": "source", "key": src}))
        pos_all = [r for r in sys_rows if not r.get("negative")]
        neg_all = [r for r in sys_rows if r.get("negative")]
        for field in ("disease", "unit_kind", "item_set"):
            keys = sorted({str(r.get(field) or "") for r in pos_all if r.get(field)})
            for key in keys:
                pos = [r for r in pos_all if r.get(field) == key]
                summary.append(_slice_metrics(pos, [], {"system": sys_name, "slice": field, "key": key}))
        if neg_all:
            summary.append(_slice_metrics([], neg_all, {"system": sys_name, "slice": "safety", "key": "ALL"}))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--arm")
    parser.add_argument("--system", choices=["guideflow", "baseline", "both"], default="guideflow")
    parser.add_argument("--questions", type=Path, nargs="*", default=None)
    parser.add_argument("--run-name", default="")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--enable-vlm", action="store_true")
    args = parser.parse_args()

    arm = load_arm_yaml(Path(args.arm)) if args.arm else {}
    if not args.enable_vlm:
        arm.setdefault("enable_vlm", False)

    run_name = args.run_name or f"{date.today().isoformat()}_part2_{arm.get('name') or 'default'}"
    run_dir = RUNS / run_name
    raw_dir = run_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    items, qpaths = load_question_sets(args.questions)
    if args.limit:
        items = items[: args.limit]
    rows_path = run_dir / "part2_rows.json"
    rows = load_json(rows_path) if args.resume and rows_path.exists() else []
    have = {(r["system"], r["id"]) for r in rows}
    runner = Part2Runner(arm)
    systems = ["guideflow", "baseline"] if args.system == "both" else [args.system]
    save_json(
        run_dir / "meta.json",
        {
            "part": 2,
            "git_commit": git_commit(),
            "arm": arm,
            "questions": qpaths,
            "n": len(items),
        },
    )

    pending = [
        (item, sys_name)
        for item in items
        for sys_name in systems
        if (sys_name, item["id"]) not in have
    ]
    lock = threading.Lock()

    def work(task: tuple[dict, str]) -> dict:
        item, sys_name = task
        print(f"[P2] {sys_name} {item['id']}", flush=True)
        try:
            if sys_name == "guideflow":
                payload = runner.ask_system(item["question"], item["data_source"])
            else:
                payload = runner.ask_baseline(item["question"])
            err = None
        except Exception:
            payload = {"answer_markdown": "", "sources": []}
            err = traceback.format_exc()
        rec = {
            "system": sys_name,
            "id": item["id"],
            "data_source": item["data_source"],
            "negative": bool(item.get("negative")),
            "disease": item.get("disease") or "",
            **score_item(item, payload),
            "elapsed_s": payload.get("elapsed_s"),
            "error": err,
        }
        with lock:
            save_json(raw_dir / f"p2_{sys_name}_{item['id']}.json", {"item": item, "payload": payload, "rec": rec})
            rows.append(rec)
            save_json(rows_path, rows)
        return rec

    if pending and "guideflow" in systems:
        runner.warmup(sorted({item["data_source"] for item, sys_name in pending if sys_name == "guideflow"}))
    workers = max(1, int(args.workers or 1))
    if workers == 1 or len(pending) <= 1:
        for task in pending:
            work(task)
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = [pool.submit(work, task) for task in pending]
            for fut in as_completed(futs):
                fut.result()

    summary = summarize(rows)
    save_json(run_dir / "part2_summary.json", summary)
    print("PART2", summary, flush=True)


if __name__ == "__main__":
    main()
