"""Download public MedQA / MedMCQA and filter B-cell lymphoma items."""
from __future__ import annotations

import json
import re
from pathlib import Path

import os

_CACHE = Path(r"D:\Project\guideflow\.cache\huggingface")
_TMP = Path(r"D:\Project\guideflow\.tmp")
(_CACHE / "hub").mkdir(parents=True, exist_ok=True)
_TMP.mkdir(parents=True, exist_ok=True)
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
os.environ["HF_HOME"] = str(_CACHE)
os.environ["HF_HUB_CACHE"] = str(_CACHE / "hub")
os.environ["HUGGINGFACE_HUB_CACHE"] = str(_CACHE / "hub")
os.environ["TMP"] = str(_TMP)
os.environ["TEMP"] = str(_TMP)

from huggingface_hub import hf_hub_download, list_repo_files

OUT = Path(__file__).resolve().parent / "raw"
OUT.mkdir(parents=True, exist_ok=True)

KEYWORDS = re.compile(
    r"lymphoma|dlbcl|burkitt|follicular|mantle\s+cell|marginal\s+zone|malt\b|"
    r"rituximab|r-chop|rchop|cll\b|sll\b|waldenstr|hairy\s+cell|"
    r"lymphoplasmacytic|primary\s+cns|testicular\s+lymph|"
    r"淋巴瘤|滤泡|套细胞|边缘区|伯基特|利妥昔|弥漫大",
    re.I,
)

EXCLUDE = re.compile(
    r"\bhodgkin\b(?!.*non-hodgkin)|霍奇金(?!.*非)",
    re.I,
)


def try_list(repo: str) -> list[str]:
    try:
        files = list_repo_files(repo, repo_type="dataset")
        print(f"{repo}: {len(files)} files")
        for f in files[:40]:
            print(" ", f)
        return files
    except Exception as exc:
        print(f"{repo} list failed: {exc}")
        return []


def main() -> None:
    repos = [
        "GBaker/MedQA-USMLE-4-options",
        "openlifescienceai/medmcqa",
        "FreedomIntelligence/CMB",
        "bigbio/med_qa",
    ]
    all_files = {}
    for repo in repos:
        all_files[repo] = try_list(repo)
    (OUT / "repo_files.json").write_text(
        json.dumps(all_files, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Prefer small json/jsonl over parquet
    wanted = []
    for repo, files in all_files.items():
        for f in files:
            low = f.lower()
            if low.endswith((".json", ".jsonl", ".csv")) and "parquet" not in low:
                wanted.append((repo, f))
    print("json-like files:", wanted[:30], "count", len(wanted))

    for repo, f in wanted[:20]:
        try:
            path = hf_hub_download(repo_id=repo, filename=f, repo_type="dataset", local_dir=OUT / repo.replace("/", "_"))
            print("downloaded", path)
        except Exception as exc:
            print("download fail", repo, f, exc)


if __name__ == "__main__":
    main()
