"""Cohen's kappa between two Part 2 gold annotation JSON files."""
from __future__ import annotations

import argparse
import json

from common.io import load_json
from common.stats import cohen_kappa


def labels(rows: list[dict]) -> dict[str, str]:
    out = {}
    for r in rows:
        out[r["id"]] = json.dumps(r.get("G"), ensure_ascii=False, sort_keys=True)
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("annotator_a")
    parser.add_argument("annotator_b")
    args = parser.parse_args()
    a, b = labels(load_json(args.annotator_a)), labels(load_json(args.annotator_b))
    ids = sorted(set(a) & set(b))
    k = cohen_kappa([a[i] for i in ids], [b[i] for i in ids])
    print(json.dumps({"n": len(ids), "kappa": round(k, 4)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
