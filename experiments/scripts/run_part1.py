"""Part 1 MCQ runner: hybrid system, concurrent workers."""
from __future__ import annotations

import argparse
import subprocess
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from datetime import date
from pathlib import Path

from common.paths import CODE_ROOT, DATASETS, RUNS, pin_caches_to_d, ensure_sys_path

pin_caches_to_d()
ensure_sys_path()
sys.path.insert(0, str(CODE_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from common.io import load_json, save_json
from common.scoring import format_mcq, parse_mcq_letter
from common.settings_override import apply_arm, load_arm_yaml
from common.stats import mcnemar_exact, wilson_ci

from backend.app.services.qa import QAService
from backend.app.services.qwen import QwenClient
from backend.app.settings import load_settings

LINEAR_MODELS = {"deepseek-r1-distill-qwen-1.5b", "qwen2-7b-instruct"}
MCQ_TEMPERATURE = 0.0


def git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=str(CODE_ROOT.parent), text=True
        ).strip()
    except Exception:
        return "unknown"


def default_questions() -> Path:
    v2 = DATASETS / "part1" / "v2_all.json"
    if v2.exists():
        return v2
    v2_test = DATASETS / "part1" / "v2_test.json"
    if v2_test.exists():
        return v2_test
    return DATASETS / "part1" / "v1_questions.json"


class Part1Runner:
    def __init__(self, arm: dict, source: str = "nccn") -> None:
        self.arm = arm
        self.source = source
        base = load_settings()
        self.settings = apply_arm(base, arm, source=source)
        self.settings = replace(
            self.settings,
            generate_temperature=MCQ_TEMPERATURE,
            enable_vlm=False,
            penalize_reference_pages=bool(arm.get("penalize_reference_pages", True)),
        )
        model = arm.get("qwen_model") or self.settings.qwen_model
        if model in LINEAR_MODELS:
            self.settings = replace(self.settings, routing_mode="linear")
        self._qa: QAService | None = None
        self._client: QwenClient | None = None

    def qa(self) -> QAService:
        if self._qa is None:
            self._qa = QAService(self.settings)
        return self._qa

    def client(self) -> QwenClient:
        if self._client is None:
            s = self.settings
            self._client = QwenClient(
                api_key=s.qwen_api_key,
                base_url=s.qwen_base_url,
                model=s.qwen_model,
                source_key=self.source,
                generate_temperature=MCQ_TEMPERATURE,
                answer_policy=str(getattr(s, "answer_policy", "guideline_only") or "guideline_only"),
            )
        return self._client

    def ask_system(self, question: str) -> dict:
        t0 = time.time()
        result = self.qa().ask(question, trace_enabled=True, enable_literature=False)
        payload = result.to_web_payload()
        payload["elapsed_s"] = round(time.time() - t0, 2)
        return payload

    def ask_baseline(self, question: str) -> dict:
        t0 = time.time()
        answer = self.client()._chat_text(
            [
                {
                    "role": "system",
                    "content": (
                        "你是医学考试助手。只根据自身知识作答，不要编造指南页码。\n"
                        "允许简要推理，但最后一行必须写成：最终答案: X"
                    ),
                },
                {"role": "user", "content": question},
            ],
            temperature=MCQ_TEMPERATURE,
            timeout=90,
        )
        return {
            "answer_markdown": answer,
            "sources": [],
            "elapsed_s": round(time.time() - t0, 2),
            "answer_kind": "baseline_llm",
            "degraded": [],
        }


def summarize(items: list[dict], rows: list[dict]) -> list[dict]:
    by_id = {x["id"]: x for x in items}
    summary = []
    for sys_name in sorted({r["system"] for r in rows}):
        sub = [r for r in rows if r["system"] == sys_name]
        n = len(sub)
        k = sum(r["correct"] for r in sub)
        lo, hi = wilson_ci(k, n)
        by_dz: dict[str, list] = {}
        for r in sub:
            dz = by_id.get(r["id"], {}).get("disease") or "未知"
            by_dz.setdefault(dz, []).append(r)
        summary.append(
            {
                "system": sys_name,
                "n": n,
                "strict_acc": round(k / n, 4) if n else None,
                "ci95": [round(lo, 4), round(hi, 4)],
                "valid_rate": round(sum(r["parse_step"] != "invalid" for r in sub) / n, 4) if n else None,
                "by_disease": {
                    dz: {
                        "n": len(rs),
                        "acc": round(sum(x["correct"] for x in rs) / len(rs), 4),
                    }
                    for dz, rs in sorted(by_dz.items())
                },
            }
        )
    baselines = [s["system"] for s in summary if str(s["system"]).startswith("baseline")]
    pairs = [s["system"] for s in summary if s["system"] not in baselines]
    if baselines and pairs:
        base_name = baselines[0]
        base = {r["id"]: r["correct"] for r in rows if r["system"] == base_name}
        for sys_name in pairs:
            b = c = 0
            for r in rows:
                if r["system"] != sys_name or r["id"] not in base:
                    continue
                if r["correct"] and not base[r["id"]]:
                    b += 1
                if (not r["correct"]) and base[r["id"]]:
                    c += 1
            for s in summary:
                if s["system"] == sys_name:
                    s["mcnemar_vs_baseline"] = {
                        "system_only": b,
                        "baseline_only": c,
                        "p": round(mcnemar_exact(b, c), 4),
                    }
    return summary


def _eval_one(runner: Part1Runner, kind: str, item: dict) -> tuple[dict, dict]:
    q = format_mcq(item)
    try:
        payload = runner.ask_system(q) if kind == "guideflow" else runner.ask_baseline(q)
        err = None
    except Exception:
        payload = {"answer_markdown": "", "sources": [], "elapsed_s": None}
        err = traceback.format_exc()
    letter, step = parse_mcq_letter(payload.get("answer_markdown") or "")
    rec = {
        "id": item["id"],
        "gold": item["gold"],
        "parsed": letter,
        "parse_step": step,
        "correct": int(letter == item["gold"]),
        "elapsed_s": payload.get("elapsed_s"),
        "answer_kind": payload.get("answer_kind"),
        "error": err,
    }
    return rec, payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--arm", help="experiments/configs/*.yaml")
    parser.add_argument("--model", default="qwen-plus")
    parser.add_argument("--system", choices=["guideflow", "baseline", "both"], default="guideflow")
    parser.add_argument("--label", default="", help="写入 rows 的系统名，默认用 arm.name")
    parser.add_argument("--questions", type=Path, default=None)
    parser.add_argument("--run-name", default="")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    arm = load_arm_yaml(Path(args.arm)) if args.arm else {}
    arm.setdefault("qwen_model", args.model)
    arm.setdefault("enable_vlm", False)
    arm.setdefault("generate_temperature", MCQ_TEMPERATURE)

    run_name = args.run_name or f"{date.today().isoformat()}_part1_{arm.get('name') or args.model}"
    run_dir = RUNS / run_name
    raw_dir = run_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    qpath = args.questions or default_questions()
    items = load_json(qpath)
    if args.limit:
        items = items[: args.limit]

    rows_path = run_dir / "part1_rows.json"
    rows = load_json(rows_path) if args.resume and rows_path.exists() else []
    have = {(r["system"], r["id"]) for r in rows}
    runner = Part1Runner(arm)
    arm_label = args.label or arm.get("name") or "guideflow"
    systems = []
    if args.system in {"guideflow", "both"}:
        systems.append(("guideflow", arm_label))
    if args.system in {"baseline", "both"}:
        systems.append(("baseline", f"baseline_{arm.get('qwen_model') or args.model}"))

    save_json(
        run_dir / "meta.json",
        {
            "part": 1,
            "git_commit": git_commit(),
            "arm": arm,
            "questions": str(qpath),
            "n": len(items),
            "qwen_model": runner.settings.qwen_model,
            "reranker_model": runner.settings.reranker_model,
            "answer_policy": getattr(runner.settings, "answer_policy", "guideline_only"),
            "allow_labeled_parametric": runner.settings.allow_labeled_parametric,
            "relevance_gate_threshold": runner.settings.relevance_gate_threshold,
            "enable_vlm": runner.settings.enable_vlm,
            "routing_mode": runner.settings.routing_mode,
            "generate_temperature": runner.settings.generate_temperature,
            "date": date.today().isoformat(),
        },
    )

    pending = [
        (item, kind, sys_name)
        for item in items
        for kind, sys_name in systems
        if (sys_name, item["id"]) not in have
    ]
    lock = threading.Lock()

    def work(task: tuple[dict, str, str]) -> dict:
        item, kind, sys_name = task
        print(f"[P1] {sys_name} {item['id']}", flush=True)
        rec, payload = _eval_one(runner, kind, item)
        rec["system"] = sys_name
        with lock:
            save_json(raw_dir / f"p1_{sys_name}_{item['id']}.json", {"item": item, "payload": payload, "rec": rec})
            rows.append(rec)
            save_json(rows_path, rows)
        return rec

    if pending and args.system in {"guideflow", "both"}:
        runner.qa()
    workers = max(1, int(args.workers or 1))
    if workers == 1 or len(pending) <= 1:
        for task in pending:
            work(task)
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = [pool.submit(work, task) for task in pending]
            for fut in as_completed(futs):
                fut.result()

    summary = summarize(items, rows)
    save_json(run_dir / "part1_summary.json", summary)
    print("PART1", summary, flush=True)


if __name__ == "__main__":
    main()
