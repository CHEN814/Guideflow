"""用已有 raw 作答重算 Part 2 引用 P/R（同一页只计一次）。不重新调用模型。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_eval import (  # noqa: E402
    EVAL_DIR,
    RESULT_DIR,
    RAW_DIR,
    cited_indices,
    extract_page_codes,
    match_gold,
    source_units,
    summarize_part2,
    uniq_units,
)


def save_json(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def score_row(item: dict, rec: dict, payload: dict | None) -> dict:
    src_key = item["data_source"]
    answer = (payload or {}).get("answer_markdown") or ""
    sources = (payload or {}).get("sources") or []
    if sources:
        r_units = []
        for src in sources:
            r_units.extend(source_units(src, src_key))
        idxs = cited_indices(answer)
        c_units = []
        for i in sorted(idxs):
            if 1 <= i <= len(sources):
                c_units.extend(source_units(sources[i - 1], src_key))
        for code in extract_page_codes(answer):
            c_units.append(f"{src_key}:{code}")
        r_units, c_units = uniq_units(r_units), uniq_units(c_units)
    else:
        r_units = uniq_units(rec.get("R") or [])
        c_units = uniq_units(rec.get("C") or [])
    gold = item.get("G") or rec.get("G") or []
    inter = match_gold(gold, c_units)
    g_n = len(gold)
    c_n = len(c_units)
    rec_q = (len(inter) / g_n) if g_n else None
    prec_q = (len(inter) / c_n) if c_n else (0.0 if g_n else None)
    out = dict(rec)
    out.update(
        {
            "R": r_units,
            "C": c_units,
            "G": gold,
            "hit": sorted(inter),
            "hit_n": len(inter),
            "g_n": g_n,
            "c_n": c_n,
            "recall_q": rec_q,
            "precision_q": prec_q,
            "metric_note": "v2_one_unit_per_page",
        }
    )
    return out


def micro(rows: list[dict]) -> dict:
    pos = [r for r in rows if not r.get("negative")]
    hit = sum(r["hit_n"] for r in pos)
    g = sum(r["g_n"] for r in pos)
    c = sum(r["c_n"] for r in pos)
    p = (hit / c) if c else 0.0
    r = (hit / g) if g else 0.0
    f1 = (2 * p * r / (p + r)) if (p + r) else 0.0
    return {"n_pos": len(pos), "hit": hit, "g": g, "c": c, "P": round(p, 4), "R": round(r, 4), "F1": round(f1, 4)}


def main() -> None:
    items = json.loads((EVAL_DIR / "part2_questions.json").read_text(encoding="utf-8"))
    by_item = {x["id"]: x for x in items}
    old_rows = json.loads((RESULT_DIR / "part2_rows.json").read_text(encoding="utf-8"))
    old_sum = json.loads((RESULT_DIR / "part2_summary.json").read_text(encoding="utf-8"))
    save_json(RESULT_DIR / "part2_summary_before_unit_fix.json", old_sum)
    save_json(RESULT_DIR / "part2_rows_before_unit_fix.json", old_rows)

    new_rows = []
    for rec in old_rows:
        item = by_item[rec["id"]]
        raw_path = RAW_DIR / f"p2_{rec['system']}_{rec['id']}.json"
        payload = None
        if raw_path.exists():
            payload = json.loads(raw_path.read_text(encoding="utf-8")).get("payload") or {}
        new_rows.append(score_row(item, rec, payload))

    save_json(RESULT_DIR / "part2_rows.json", new_rows)
    summarize_part2(items, new_rows)

    print("BEFORE (guideflow ALL)", next(s for s in old_sum if s["system"] == "guideflow" and s["data_source"] == "ALL"))
    new_sum = json.loads((RESULT_DIR / "part2_summary.json").read_text(encoding="utf-8"))
    print("AFTER  (guideflow ALL)", next(s for s in new_sum if s["system"] == "guideflow" and s["data_source"] == "ALL"))
    gf = [r for r in new_rows if r["system"] == "guideflow"]
    print("guideflow micro by source:")
    for src in ("nccn", "csco", "eha"):
        print(" ", src, micro([r for r in gf if r["data_source"] == src]))
    print("mean |C| before", sum(r["c_n"] for r in old_rows if r["system"] == "guideflow" and not r["negative"]) / 45)
    print("mean |C| after ", sum(r["c_n"] for r in gf if not r["negative"]) / 45)


if __name__ == "__main__":
    main()
