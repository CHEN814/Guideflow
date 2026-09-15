"""Re-filter local MedQA jsonl (D: only). Prefer answer_idx. Stricter inclusion."""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

RAW = Path(__file__).resolve().parent / "raw" / "medqa"
OUT = Path(__file__).resolve().parent / "part1_questions.json"

CORE_STEM = re.compile(
    r"\b(?:lymphoma|dlbcl|burkitt|follicular\s+lymph|mantle\s+cell|"
    r"marginal\s+zone|malt\b|rituximab|r-?chop|r-?cvp|"
    r"chronic\s+lymphocytic|hairy\s+cell|waldenstr|lymphoplasmacytic|"
    r"primary\s+cns|testicular\s+lymph|double[- ]hit|polatuzumab|"
    r"cd20|cd5\b|cyclin\s*d1|t\(14;18\)|t\(11;14\)|t\(8;14\))",
    re.I,
)
BIOSTAT = re.compile(
    r"\b(?:RR\s*=|p\s*=|odds ratio|confidence interval|stratify|effect modification|"
    r"generalizability|selection bias|confound)\b",
    re.I,
)
DISTRACTOR_ONLY = re.compile(
    r"increased risk for which of the following|most likely to develop",
    re.I,
)


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def options_map(row: dict) -> dict:
    opts = row.get("options") or {}
    if isinstance(opts, dict):
        return {str(k).upper()[:1]: str(v) for k, v in opts.items() if str(k).upper()[:1] in "ABCDE"}
    return {}


def gold_letter(row: dict, opts: dict) -> str | None:
    idx = str(row.get("answer_idx") or "").strip().upper()
    if idx in opts:
        return idx
    ans = str(row.get("answer") or "").strip()
    for k, v in opts.items():
        if ans.lower() == v.lower() or ans.lower() in v.lower() or v.lower() in ans.lower():
            return k
    return None


def disease_tag(text: str) -> str:
    t = text.lower()
    if re.search(r"diffuse large|dlbcl", t):
        return "DLBCL"
    if re.search(r"follicular", t):
        return "FL"
    if re.search(r"mantle cell", t):
        return "MCL"
    if re.search(r"burkitt|marginal|malt|\bcll\b|chronic lymphocytic|\bsll\b|hairy cell|waldenstr", t):
        return "其他 B-NHL"
    return "跨病种"


def topic_tag(text: str) -> str:
    t = text.lower()
    if re.search(r"relaps|refract|salvage|second-line|car-?t", t):
        return "复发难治"
    if re.search(r"rituximab|r-?chop|treat|chemotherap|regimen|radiation", t):
        return "一线"
    if re.search(r"stag|ipi|prognos|ann arbor|lugano", t):
        return "分期预后"
    if re.search(r"cns|testicular|gastric|brain", t):
        return "特殊部位"
    return "诊断"


def keep(row: dict) -> bool:
    stem = str(row.get("question") or "")
    opts = options_map(row)
    if not opts or gold_letter(row, opts) is None:
        return False
    if not CORE_STEM.search(stem):
        return False
    if BIOSTAT.search(stem):
        return False
    if DISTRACTOR_ONLY.search(stem) and not re.search(r"lymphoma|cll|rituximab|r-chop", stem, re.I):
        return False
    # Hodgkin-only stem
    if re.search(r"\bhodgkin\b", stem, re.I) and not re.search(r"non-?hodgkin|b-cell|rituximab|dlbcl", stem, re.I):
        return False
    return True


def main() -> None:
    items = []
    seen = set()
    for split, name in (("test", "phrases_no_exclude_test.jsonl"), ("train", "phrases_no_exclude_train.jsonl")):
        rows = load_jsonl(RAW / name)
        for i, row in enumerate(rows):
            if not keep(row):
                continue
            stem = str(row.get("question") or "")
            key = re.sub(r"\s+", " ", stem)[:200]
            if key in seen:
                continue
            seen.add(key)
            opts = options_map(row)
            letter = gold_letter(row, opts)
            blob = stem + " " + " ".join(opts.values())
            items.append(
                {
                    "id": f"P1-{len(items)+1:03d}",
                    "source": "MedQA-USMLE-4-options",
                    "split": split,
                    "original_id": f"{row.get('meta_info','')}:{split}:{i}",
                    "lang": "en",
                    "disease": disease_tag(blob),
                    "topic": topic_tag(blob),
                    "n_options": len(opts),
                    "gold": letter,
                    "include": "Y",
                    "question": stem,
                    "options": opts,
                }
            )
    OUT.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    print("kept", len(items))
    print("disease", Counter(x["disease"] for x in items))
    print("topic", Counter(x["topic"] for x in items))
    print("gold", Counter(x["gold"] for x in items))


if __name__ == "__main__":
    main()
