from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from backend.app.services.bm25_store import BM25Store
from backend.app.services.embeddings import load_embedding_model
from backend.app.services.query_normalizer import normalize_query
from backend.app.services.reranker import load_reranker
from backend.app.services.retrieval import HybridRetriever, route_query
from backend.app.services.tracing import TraceLogger
from backend.app.services.vector_store import create_vector_store
from backend.app.settings import EMBEDDING_PROFILES, apply_profile, load_settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect retrieval for a DLBCL question without calling Qwen.")
    parser.add_argument("question")
    parser.add_argument("--trace", action="store_true")
    parser.add_argument(
        "--embedding",
        choices=sorted(EMBEDDING_PROFILES),
        help="Embedding profile to use (overrides .env). e.g. hash (fast) or bge-m3 (quality).",
    )
    args = parser.parse_args()

    settings = load_settings()
    if args.embedding:
        settings = apply_profile(settings, args.embedding)
    normalized = normalize_query(args.question)
    route, filters, triggers = route_query(normalized)

    print("Query normalization")
    print(f"- original: {normalized.original}")
    print(f"- entities: {normalized.entities}")
    print(f"- expanded: {normalized.expanded_queries}")
    print(f"- route: {route}")
    print(f"- triggers: {triggers}")
    print(f"- filters: {filters.to_dict()}")

    trace = TraceLogger(settings.logs_dir, enabled=args.trace)
    if args.trace:
        trace.log("query_received", {"question": args.question})
        trace.log("query_normalized", normalized.__dict__)

    bm25 = BM25Store.load(settings.bm25_index_path)
    vector_store = create_vector_store(settings.vector_index_dir, load_embedding_model(settings.embedding_model))
    vector_store.load()
    retriever = HybridRetriever(
        bm25=bm25,
        vector_store=vector_store,
        reranker=load_reranker(settings.reranker_model),
        bm25_top_k=settings.bm25_top_k,
        vector_top_k=settings.vector_top_k,
        rerank_top_k=settings.rerank_top_k,
        final_top_k=settings.final_top_k,
    )
    hits, diagnostics = retriever.retrieve(normalized, trace if args.trace else None)

    print("\nFinal evidence")
    for hit in hits:
        doc = hit.document
        snippet = doc.text.replace("\n", " ")[:220]
        page_info = doc.printed_page_code or f"pdf_page={doc.pdf_page}"
        print(f"{hit.rank}. score={hit.score:.4f} | {doc.source_id} | {page_info} | {doc.page_type}")
        print(f"   {snippet}")

    if diagnostics.get("degraded"):
        print("\nDegraded:")
        for item in sorted(set(diagnostics["degraded"])):
            print(f"- {item}")

    if args.trace:
        print(f"\nTrace: {trace.path}")


if __name__ == "__main__":
    main()
