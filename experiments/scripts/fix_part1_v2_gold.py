"""Repair v2 gold letters in place. IDs stay unchanged so existing runs can be rescored."""
from __future__ import annotations

import sys
from pathlib import Path

from common.paths import DATASETS, RUNS, pin_caches_to_d, ensure_sys_path

pin_caches_to_d()
ensure_sys_path()
sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_part1_v2 import gold_letter, load_jsonl
from common.io import load_json, save_json
from common.stats import wilson_ci
from run_part1 import summarize


def _norm(q: str) -> str:
    return " ".join((q or "").lower().split())


def load_source() -> dict[str, dict]:
    src_dir = DATASETS / "sources" / "v1_raw" / "medqa"
    by_q: dict[str, dict] = {}
    for name in ("phrases_no_exclude_test.jsonl", "phrases_no_exclude_train.jsonl"):
        path = src_dir / name
        if not path.exists():
            continue
        for row in load_jsonl(path):
            q = _norm(str(row.get("question") or ""))
            if q:
                by_q[q] = row
    return by_q


def patch_items(items: list[dict], source: dict[str, dict], v1_gold: dict[str, str]) -> dict:
    changed = missing = still_bad = 0
    for it in items:
        key = _norm(it.get("question") or "")
        old = it.get("gold")
        new = None
        row = source.get(key)
        if row:
            new = gold_letter(row, it.get("options") or {})
        if not new:
            new = v1_gold.get(key)
        if not new:
            missing += 1
            continue
        if new != old:
            it["gold"] = new
            changed += 1
        if new not in (it.get("options") or {}):
            still_bad += 1
    return {"n": len(items), "changed": changed, "missing": missing, "still_bad": still_bad}


def rescore_run(run_dir: Path, items: list[dict]) -> None:
    rows_path = run_dir / "part1_rows.json"
    if not rows_path.exists():
        return
    gold = {it["id"]: it["gold"] for it in items}
    rows = load_json(rows_path)
    for rec in rows:
        gid = gold.get(rec["id"])
        if not gid:
            continue
        rec["gold"] = gid
        rec["correct"] = int(rec.get("parsed") == gid)
    save_json(rows_path, rows)
    save_json(run_dir / "part1_summary.json", summarize(items, rows))
    print("rescored", run_dir, flush=True)


def main() -> None:
    source = load_source()
    v1 = load_json(DATASETS / "part1" / "v1_questions.json")
    v1_gold = {_norm(x["question"]): x["gold"] for x in v1}
    print(f"source_q={len(source)} v1={len(v1_gold)}", flush=True)

    out_dir = DATASETS / "part1"
    stats = {}
    all_items = load_json(out_dir / "v2_all.json")
    stats["v2_all"] = patch_items(all_items, source, v1_gold)
    save_json(out_dir / "v2_all.json", all_items)
    by_id = {it["id"]: it for it in all_items}
    for name in ("v2_dev.json", "v2_test.json"):
        subset = load_json(out_dir / name)
        for it in subset:
            if it["id"] in by_id:
                it["gold"] = by_id[it["id"]]["gold"]
        save_json(out_dir / name, subset)
        stats[name] = {
            "n": len(subset),
            "gold_not_in_options": sum(1 for it in subset if it["gold"] not in it["options"]),
        }
    print(stats, flush=True)

    overlap_diff = 0
    for x in v1:
        y = next((it for it in all_items if _norm(it["question"]) == _norm(x["question"])), None)
        if y and y["gold"] != x["gold"]:
            overlap_diff += 1
            print("STILL_DIFF", x["id"], x["gold"], y["id"], y["gold"], flush=True)
    print("overlap_gold_diff", overlap_diff, flush=True)

    for run in (RUNS / "2026-10-13_v3", RUNS / "2026-10-13_v3_smoke"):
        rescore_run(run, all_items)


if __name__ == "__main__":
    main()
