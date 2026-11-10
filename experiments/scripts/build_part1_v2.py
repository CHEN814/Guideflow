"""Build Part 1 v2: relaxed MedQA + optional CMExam / MedMCQA lymphoma subsets."""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
from pathlib import Path

from common.paths import DATASETS, pin_caches_to_d, ensure_sys_path

pin_caches_to_d()
ensure_sys_path()

from common.io import load_json, load_jsonl, save_json

INCLUDE = re.compile(
    r"\b(?:lymphoma|dlbcl|burkitt|follicular\s+lymph|mantle\s+cell|"
    r"marginal\s+zone|malt\s+lymph|rituximab|r-?chop|r-?cvp|"
    r"chronic\s+lymphocytic\s+leukemia|\bcll\b|\bsll\b|"
    r"waldenstr|lymphoplasmacytic|hairy\s+cell|primary\s+cns\s+lymph|"
    r"testicular\s+lymph|double[- ]hit|double[- ]express|"
    r"polatuzumab|car-?t\b|cd20\s+monoclonal|"
    r"ann\s+arbor|lugano\s+(?:stag|classif)|international\s+prognostic\s+index|\bipi\b)"
    r"|淋巴瘤|滤泡性|套细胞|边缘区|伯基特|利妥昔|弥漫大B|慢性淋巴细胞|华氏|毛细胞",
    re.I,
)
HODGKIN_ONLY = re.compile(r"hodgkin", re.I)
B_SIGNAL = re.compile(
    r"non-?hodgkin|b-cell|dlbcl|rituximab|follicular|mantle|marginal|burkitt|cll|sll|淋巴瘤",
    re.I,
)

DISEASE_RULES = [
    ("DLBCL", re.compile(r"dlbcl|diffuse\s+large|弥漫大", re.I)),
    ("FL", re.compile(r"follicular|滤泡", re.I)),
    ("MCL", re.compile(r"mantle\s+cell|套细胞", re.I)),
    ("MZL", re.compile(r"marginal\s+zone|malt|边缘区", re.I)),
    ("Burkitt", re.compile(r"burkitt|伯基特", re.I)),
    ("CLL", re.compile(r"chronic\s+lymphocytic|\bcll\b|\bsll\b|慢性淋巴", re.I)),
    ("WM", re.compile(r"waldenstr|华氏|lymphoplasmacytic", re.I)),
    ("HCL", re.compile(r"hairy\s+cell|毛细胞", re.I)),
]


def text_of(row: dict) -> str:
    parts = [str(row.get("question") or row.get("sent1") or row.get("stem") or "")]
    opts = row.get("options") or {}
    if isinstance(opts, dict):
        parts.extend(str(v) for v in opts.values())
    elif isinstance(opts, list):
        parts.extend(str(v) for v in opts)
    for k in ("ending0", "ending1", "ending2", "ending3", "A", "B", "C", "D", "E"):
        if k in row and row[k]:
            parts.append(str(row[k]))
    return "\n".join(parts)


def gold_letter(row: dict, opts: dict | None = None) -> str | None:
    """Prefer MedQA answer_idx; never take the first A–E letter out of answer text."""
    opts = opts or options_of(row)
    idx = str(row.get("answer_idx") or "").strip().upper()
    if idx in opts:
        return idx
    label = row.get("label")
    if isinstance(label, str) and label.strip().upper()[:1] in opts:
        return label.strip().upper()[:1]
    raw = row.get("answer")
    if isinstance(raw, int) and 0 <= raw < 5:
        letter = "ABCDE"[raw]
        return letter if letter in opts else None
    ans = str(raw or row.get("gold") or "").strip()
    if ans.upper()[:1] in opts and len(ans) == 1:
        return ans.upper()[:1]
    for k, v in opts.items():
        if ans.lower() == v.lower() or (ans and (ans.lower() in v.lower() or v.lower() in ans.lower())):
            return k
    return None


def options_of(row: dict) -> dict[str, str]:
    opts = row.get("options")
    if isinstance(opts, dict) and opts:
        return {str(k).upper()[:1]: str(v) for k, v in opts.items()}
    out = {}
    for i, k in enumerate("ABCDE"):
        val = row.get(k) or row.get(f"ending{i}")
        if val:
            out[k] = str(val)
    return out


def disease_of(text: str) -> str:
    hits = [name for name, pat in DISEASE_RULES if pat.search(text)]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        return "跨病种"
    return "跨病种"


def keep_row(row: dict, relaxed: bool) -> bool:
    text = text_of(row)
    if not INCLUDE.search(text):
        return False
    if HODGKIN_ONLY.search(text) and not B_SIGNAL.search(text):
        return False
    if not relaxed:
        q = str(row.get("question") or row.get("sent1") or "")
        return bool(INCLUDE.search(q))
    return True


def to_item(row: dict, *, source: str, split: str, idx: int, lang: str) -> dict | None:
    q = str(row.get("question") or row.get("sent1") or row.get("stem") or "").strip()
    opts = options_of(row)
    gold = gold_letter(row, opts)
    if not q or len(opts) < 4 or not gold:
        return None
    blob = text_of(row)
    digest = hashlib.md5((source + q + gold).encode("utf-8")).hexdigest()[:10]
    return {
        "id": f"P1V2-{source[:6]}-{idx:04d}-{digest}",
        "source": source,
        "split": split,
        "original_id": str(row.get("id") or row.get("original_id") or ""),
        "lang": lang,
        "disease": disease_of(blob),
        "kb_coverage": "unlabeled",
        "topic": "auto",
        "n_options": len(opts),
        "gold": gold,
        "include": "Y",
        "question": q,
        "options": opts,
    }


def load_medqa(src_dir: Path) -> list[dict]:
    items = []
    for split, name in (("train", "phrases_no_exclude_train.jsonl"), ("test", "phrases_no_exclude_test.jsonl")):
        path = src_dir / name
        if not path.exists():
            continue
        for i, row in enumerate(load_jsonl(path)):
            if keep_row(row, relaxed=True):
                item = to_item(row, source="MedQA-USMLE", split=split, idx=i, lang="en")
                if item:
                    items.append(item)
    return items


def try_hf_subset(repo: str, filename: str, source: str, lang: str) -> list[dict]:
    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        print(f"[skip] huggingface_hub missing, cannot fetch {source}", flush=True)
        return []
    dest = DATASETS / "sources" / source.lower()
    dest.mkdir(parents=True, exist_ok=True)
    try:
        path = hf_hub_download(repo_id=repo, filename=filename, local_dir=str(dest))
    except Exception as exc:
        print(f"[skip] {source}: {exc}", flush=True)
        return []
    items = []
    p = Path(path)
    if p.suffix == ".jsonl":
        rows = load_jsonl(p)
    else:
        raw = json.loads(p.read_text(encoding="utf-8"))
        rows = raw if isinstance(raw, list) else raw.get("data") or raw.get("questions") or []
    for i, row in enumerate(rows):
        if keep_row(row, relaxed=True):
            item = to_item(row, source=source, split="unknown", idx=i, lang=lang)
            if item:
                items.append(item)
    return items


def stratified_split(items: list[dict], seed: int = 13, dev_frac: float = 0.4) -> tuple[list[dict], list[dict]]:
    rng = random.Random(seed)
    buckets: dict[str, list] = {}
    for it in items:
        buckets.setdefault(it["disease"], []).append(it)
    dev, test = [], []
    for rows in buckets.values():
        rng.shuffle(rows)
        n_dev = max(1, int(round(len(rows) * dev_frac))) if len(rows) > 1 else 0
        if len(rows) == 1:
            test.extend(rows)
        else:
            dev.extend(rows[:n_dev])
            test.extend(rows[n_dev:])
    return dev, test


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--medqa-dir", type=Path, default=DATASETS / "sources" / "v1_raw" / "medqa")
    parser.add_argument("--skip-hf", action="store_true")
    args = parser.parse_args()

    items = load_medqa(args.medqa_dir)
    print(f"MedQA relaxed: {len(items)}", flush=True)
    if not args.skip_hf:
        items += try_hf_subset("fzkuji/CMExam", "data/test.jsonl", "CMExam", "zh")
        items += try_hf_subset("openlifescienceai/medmcqa", "data/test-00000-of-00001.parquet", "MedMCQA", "en")

    seen = set()
    uniq = []
    for it in items:
        key = (it["question"][:200], it["gold"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(it)

    rules = {
        "include": "题干或选项匹配淋巴瘤/B细胞相关关键词",
        "exclude_hodgkin_only": True,
        "disease_tag": "规则标注，跨病种=0或>1个病名",
        "kb_coverage": "unlabeled；需两人盲标后再冻结覆盖子集",
        "split": "按病种分层 40% dev / 60% test, seed=13",
    }
    out_dir = DATASETS / "part1"
    save_json(out_dir / "v2_all.json", uniq)
    save_json(out_dir / "v2_inclusion_rules.json", rules)
    dev, test = stratified_split(uniq)
    for it in dev:
        it["eval_split"] = "dev"
    for it in test:
        it["eval_split"] = "test"
    save_json(out_dir / "v2_dev.json", dev)
    save_json(out_dir / "v2_test.json", test)
    save_json(
        out_dir / "v2_coverage_template.json",
        [{"id": it["id"], "kb_coverage": "", "annotator": ""} for it in uniq],
    )
    print(f"v2 unique={len(uniq)} dev={len(dev)} test={len(test)}", flush=True)


if __name__ == "__main__":
    main()
