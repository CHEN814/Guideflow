"""Download MedQA jsonl from hf-mirror and filter B-cell lymphoma items."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

# 所有下载/缓存只写 D 盘，禁止落到 C:\Users\...\.cache
_CACHE = Path(r"D:\Project\guideflow\.cache")
_TMP = Path(r"D:\Project\guideflow\.tmp")
for p in (_CACHE / "huggingface" / "hub", _CACHE / "huggingface" / "transformers", _CACHE / "huggingface" / "datasets", _TMP):
    p.mkdir(parents=True, exist_ok=True)

os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
os.environ["HF_HOME"] = str(_CACHE / "huggingface")
os.environ["HF_HUB_CACHE"] = str(_CACHE / "huggingface" / "hub")
os.environ["HUGGINGFACE_HUB_CACHE"] = str(_CACHE / "huggingface" / "hub")
os.environ["TRANSFORMERS_CACHE"] = str(_CACHE / "huggingface" / "transformers")
os.environ["HF_DATASETS_CACHE"] = str(_CACHE / "huggingface" / "datasets")
os.environ["TMP"] = str(_TMP)
os.environ["TEMP"] = str(_TMP)

from huggingface_hub import hf_hub_download

OUT = Path(__file__).resolve().parent
RAW = OUT / "raw"
RAW.mkdir(exist_ok=True)

INCLUDE = re.compile(
    r"\b(?:lymphoma|dlbcl|burkitt|follicular\s+lymph|mantle\s+cell|"
    r"marginal\s+zone|malt\s+lymph|rituximab|r-?chop|r-?cvp|"
    r"chronic\s+lymphocytic\s+leukemia|\bcll\b|\bsll\b|"
    r"waldenstr|lymphoplasmacytic|hairy\s+cell|primary\s+cns\s+lymph|"
    r"testicular\s+lymph|double[- ]hit|double[- ]express|"
    r"polatuzumab|car-?t\b|cd20\s+monoclonal|"
    r"ann\s+arbor|lugano\s+(?:stag|classif)|international\s+prognostic\s+index|\bipi\b)"
    r"|淋巴瘤|滤泡性|套细胞|边缘区|伯基特|利妥昔|弥漫大B|慢性淋巴细胞",
    re.I,
)

# Keep Hodgkin only if B-cell / NHL / rituximab also present
HODGKIN_ONLY = re.compile(r"hodgkin", re.I)
B_SIGNAL = re.compile(
    r"non-?hodgkin|b-cell|dlbcl|rituximab|follicular|mantle|marginal|burkitt|cll|sll",
    re.I,
)


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def text_of(row: dict) -> str:
    parts = [str(row.get("question") or row.get("sent1") or row.get("stem") or "")]
    opts = row.get("options") or {}
    if isinstance(opts, dict):
        parts.extend(str(v) for v in opts.values())
    for k in ("ending0", "ending1", "ending2", "ending3", "A", "B", "C", "D", "E"):
        if k in row and row[k]:
            parts.append(str(row[k]))
    return "\n".join(parts)


def gold_letter(row: dict) -> str | None:
    ans = row.get("answer") or row.get("answer_idx") or row.get("label")
    if isinstance(ans, str) and ans.strip().upper()[:1] in "ABCDE":
        # "C" or "C: foo"
        m = re.search(r"[A-E]", ans.upper())
        return m.group(0) if m else None
    if isinstance(ans, int):
        return "ABCDE"[ans] if 0 <= ans < 5 else None
    return None


def options_map(row: dict) -> dict:
    opts = row.get("options")
    if isinstance(opts, dict) and opts:
        return {str(k).upper()[:1]: str(v) for k, v in opts.items() if str(k).upper()[:1] in "ABCDE"}
    out = {}
    for i, k in enumerate(("ending0", "ending1", "ending2", "ending3", "ending4")):
        if row.get(k):
            out["ABCDE"[i]] = str(row[k])
    return out


def disease_tag(text: str) -> str:
    t = text.lower()
    if re.search(r"diffuse large|dlbcl|弥漫大", t):
        return "DLBCL"
    if re.search(r"follicular", t):
        return "FL"
    if re.search(r"mantle cell", t):
        return "MCL"
    if re.search(r"burkitt", t):
        return "其他 B-NHL"
    if re.search(r"marginal|malt", t):
        return "其他 B-NHL"
    if re.search(r"\bcll\b|chronic lymphocytic|\bsll\b", t):
        return "其他 B-NHL"
    return "跨病种"


def topic_tag(text: str) -> str:
    t = text.lower()
    if re.search(r"rituximab|r-?chop|treat|chemotherap|regimen|radiation", t):
        return "一线"
    if re.search(r"relaps|refract|salvage|second-line|car-?t", t):
        return "复发难治"
    if re.search(r"stag|ipi|prognos|ann arbor|lugano", t):
        return "分期预后"
    if re.search(r"cns|testicular|primary|gastric|brain", t):
        return "特殊部位"
    if re.search(r"diagnos|biopsy|translocation|cd20|cd5|cyclin|myc|bcl", t):
        return "诊断"
    return "诊断"


def keep(row: dict) -> bool:
    text = text_of(row)
    if not INCLUDE.search(text):
        return False
    if HODGKIN_ONLY.search(text) and not B_SIGNAL.search(text):
        return False
    if gold_letter(row) is None:
        return False
    if not options_map(row):
        return False
    return True


def main() -> None:
    files = {}
    for name in ("phrases_no_exclude_test.jsonl", "phrases_no_exclude_train.jsonl"):
        path = hf_hub_download(
            repo_id="GBaker/MedQA-USMLE-4-options",
            filename=name,
            repo_type="dataset",
            cache_dir=str(_CACHE / "huggingface" / "hub"),
            local_dir=str(RAW / "medqa"),
        )
        files[name] = Path(path)
        print("got", path, Path(path).stat().st_size)

    items = []
    seen = set()
    for split, path in files.items():
        rows = load_jsonl(path)
        print(split, "rows", len(rows))
        # peek first
        print("sample keys", list(rows[0].keys()) if rows else None)
        for i, row in enumerate(rows):
            if not keep(row):
                continue
            stem = str(row.get("question") or row.get("sent1") or "")
            key = re.sub(r"\s+", " ", stem)[:180]
            if key in seen:
                continue
            seen.add(key)
            opts = options_map(row)
            letter = gold_letter(row)
            text = text_of(row)
            items.append(
                {
                    "id": f"P1-{len(items)+1:03d}",
                    "source": "MedQA-USMLE-4-options",
                    "split": "test" if "test" in split else "train",
                    "original_id": str(row.get("id") or row.get("meta_info") or f"{split}:{i}"),
                    "lang": "en",
                    "disease": disease_tag(text),
                    "topic": topic_tag(text),
                    "n_options": len(opts),
                    "gold": letter,
                    "include": "Y",
                    "question": stem,
                    "options": opts,
                    "meta": {k: row.get(k) for k in ("meta_info", "answer_idx", "label") if k in row},
                }
            )
    dest = OUT / "part1_questions.json"
    dest.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    from collections import Counter

    print("kept", len(items), "->", dest)
    print("disease", Counter(x["disease"] for x in items))
    print("topic", Counter(x["topic"] for x in items))
    print("split", Counter(x["split"] for x in items))


if __name__ == "__main__":
    main()
