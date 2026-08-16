"""Smoke PubMed literature search against docs/测试问题.md samples."""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from backend.app.services.literature_query import build_pubmed_query, extract_concepts_rule
from backend.app.services.literature_service import LiteratureSearchService
from backend.app.services.pubmed_client import PubmedClient

QUESTIONS = [
    "TP53突变类型与DLBCL预后关系",
    "CART治疗rrDLBCL的无复发生存率是多少",
    "DLBCL分子分型LymphoGEN和LymphPlex有什么区别？",
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--top", type=int, default=3)
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    client = PubmedClient(
        email="guideflow-smoke@example.com",
        cache_dir=root / "data" / "cache" / "pubmed",
        esearch_timeout_s=8,
        efetch_timeout_s=12,
    )
    svc = LiteratureSearchService(
        pubmed=client,
        qwen_client=None,
        candidate_k=20,
        final_top_k=args.top,
        recent_years=5,
    )

    for q in QUESTIONS:
        concepts = extract_concepts_rule(q)
        term = build_pubmed_query(concepts, level=1)
        print("=" * 72)
        print("Q:", q)
        print("concepts:", {
            "biomarker": concepts.biomarker,
            "intervention": concepts.intervention,
            "outcome": concepts.outcome,
        })
        print("L1:", term)
        t0 = time.time()
        result = svc.search(q)
        dt = time.time() - t0
        print(
            f"count={result.diagnostics.get('count')} "
            f"hits={len(result.hits)} degraded={result.degraded} {dt:.2f}s"
        )
        print("final_term:", result.diagnostics.get("final_term"))
        for hit in result.hits:
            print(
                f"  [L{hit.rank}] PMID {hit.pmid} ({hit.year}) "
                f"score={hit.score:.3f} | {hit.title}"
            )


if __name__ == "__main__":
    main()
