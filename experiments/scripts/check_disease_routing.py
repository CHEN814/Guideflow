"""Offline disease-routing diagnostics. No paid API calls."""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

from common.paths import CODE_ROOT, DATASETS, RUNS, pin_caches_to_d, ensure_sys_path

pin_caches_to_d()
ensure_sys_path()
sys.path.insert(0, str(CODE_ROOT))

from common.io import load_json, save_json
from backend.app.services.disease_scope import detect_disease_scope, is_kb_uncovered


def label_gold_disease(item: dict) -> str:
    return item.get("disease") or item.get("topic") or "未知"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--part1", type=Path, default=DATASETS / "part1" / "v1_questions.json")
    parser.add_argument("--part2", type=Path, default=DATASETS / "part2" / "v1_questions.json")
    parser.add_argument("--source", default="nccn")
    args = parser.parse_args()

    rows = []
    for part, path in (("part1", args.part1), ("part2", args.part2)):
        if not path.exists():
            continue
        for it in load_json(path):
            q = it.get("question") or ""
            scope = detect_disease_scope(q, source=args.source)
            rows.append(
                {
                    "part": part,
                    "id": it.get("id"),
                    "gold_disease": label_gold_disease(it),
                    "detected": scope.key,
                    "kb_covered": not is_kb_uncovered(scope),
                    "label": scope.label,
                    "modules": list(scope.module_codes),
                }
            )

    conf = collections.Counter((r["gold_disease"], r["detected"]) for r in rows)
    uncovered = [r for r in rows if not r["kb_covered"]]
    out_dir = RUNS / "offline_disease_routing"
    out_dir.mkdir(parents=True, exist_ok=True)
    save_json(out_dir / "rows.json", rows)
    save_json(
        out_dir / "summary.json",
        {
            "n": len(rows),
            "confusion": [ {"gold": a, "detected": b, "n": n} for (a, b), n in sorted(conf.items()) ],
            "uncovered_n": len(uncovered),
            "uncovered_ids": [r["id"] for r in uncovered],
            "malt_demo": detect_disease_scope("A 60-year-old with MALT lymphoma of the stomach", source=args.source).key,
            "cll_demo": {
                "key": detect_disease_scope("chronic lymphocytic leukemia first-line", source=args.source).key,
                "covered": not is_kb_uncovered(detect_disease_scope("chronic lymphocytic leukemia first-line", source=args.source)),
            },
        },
    )
    print(json.dumps(load_json(out_dir / "summary.json"), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
