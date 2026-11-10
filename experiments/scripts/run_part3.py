"""Part 3 C-01 regression. Writes to experiments/runs."""
from __future__ import annotations

import argparse
import sys
import traceback
from datetime import date
from pathlib import Path

from common.paths import CODE_ROOT, DATASETS, RUNS, pin_caches_to_d, ensure_sys_path

pin_caches_to_d()
ensure_sys_path()
sys.path.insert(0, str(CODE_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from common.io import load_json, save_json
from common.part3_score import build_prompt, load_deidentified_note, score_answer
from common.settings_override import load_arm_yaml
from run_part1 import Part1Runner


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--arm")
    parser.add_argument("--system", choices=["guideflow", "baseline", "both"], default="both")
    parser.add_argument("--run-name", default="")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    items = load_json(DATASETS / "part3" / "v1_questions.json")
    note = load_deidentified_note()
    arm = load_arm_yaml(Path(args.arm)) if args.arm else {}
    runner = Part1Runner(arm)
    run_name = args.run_name or f"{date.today().isoformat()}_part3_c01"
    run_dir = RUNS / run_name
    raw_dir = run_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    rows_path = run_dir / "part3_rows.json"
    rows = load_json(rows_path) if args.resume and rows_path.exists() else []
    have = {(r["system"], r["id"]) for r in rows}
    systems = ["guideflow", "baseline"] if args.system == "both" else [args.system]
    save_json(run_dir / "meta.json", {"part": 3, "arm": arm, "n": len(items)})

    for item in items:
        prompt = build_prompt(note, item["question"])
        for sys_name in systems:
            if (sys_name, item["id"]) in have:
                continue
            print(f"[P3] {sys_name} {item['id']}", flush=True)
            try:
                payload = runner.ask_system(prompt) if sys_name == "guideflow" else runner.ask_baseline(prompt)
                err = None
            except Exception:
                payload = {"answer_markdown": ""}
                err = traceback.format_exc()
            scored = score_answer(item, payload.get("answer_markdown") or "")
            rec = {
                "system": sys_name,
                "id": item["id"],
                "quota": item.get("quota"),
                "point_n": len(item.get("points") or []),
                **scored,
                "elapsed_s": payload.get("elapsed_s"),
                "error": err,
            }
            save_json(raw_dir / f"p3_{sys_name}_{item['id']}.json", {"item": item, "payload": payload, "rec": rec})
            rows.append(rec)
            save_json(rows_path, rows)

    summary = []
    for sys_name in sorted({r["system"] for r in rows}):
        sub = [r for r in rows if r["system"] == sys_name]
        n = len(sub)
        hit_n = sum(len(r["hit"]) for r in sub)
        tot = sum(r["point_n"] for r in sub)
        summary.append(
            {
                "system": sys_name,
                "n": n,
                "pass_n": sum(1 for r in sub if r["passed"]),
                "pass_rate": round(sum(1 for r in sub if r["passed"]) / n, 4) if n else None,
                "point_recall": round(hit_n / tot, 4) if tot else None,
                "safety_fail_n": sum(1 for r in sub if r["safety"] != "ok"),
            }
        )
    save_json(run_dir / "part3_summary.json", summary)
    print("PART3", summary, flush=True)


if __name__ == "__main__":
    main()
