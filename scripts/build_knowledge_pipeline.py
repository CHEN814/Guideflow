from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.settings import load_settings, source_paths
from backend.app.services.bm25_store import build_bm25_store
from backend.app.services.csco_extractor import build_csco_knowledge_base
from backend.app.services.pdf_extractor import build_knowledge_base as build_nccn_knowledge_base
from backend.app.services.store import save_knowledge_base


def build_source(source: str, *, pdf: Path | None = None, kb_out: Path | None = None, bm25_out: Path | None = None) -> None:
    settings = load_settings()
    paths = source_paths(source, settings)
    pdf_path = pdf or paths["pdf"]
    kb_path = kb_out or paths["knowledge_base"]
    bm25_path = bm25_out or paths["bm25_index"]

    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found for {source}: {pdf_path}")

    if source == "csco":
        kb = build_csco_knowledge_base(pdf_path)
    elif source == "nccn":
        kb = build_nccn_knowledge_base(pdf_path)
    else:
        raise ValueError(f"Unknown source: {source}")

    save_knowledge_base(kb_path, kb)
    docs = kb.to_search_documents()
    for doc in docs:
        doc.source = source
    store = build_bm25_store(docs)
    store.save(bm25_path)

    stats = kb.stats
    print(f"Source          : {source}")
    print(f"PDF             : {pdf_path}")
    print(f"Knowledge base  : {kb_path}")
    print(f"BM25 index      : {bm25_path}")
    print(f"Search documents: {len(store.documents)}")
    print(f"Discussion chunks: {stats.get('discussion_chunk_count', 0)}")
    print(f"Reference entries: {stats.get('reference_entry_count', 0)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build guideline knowledge base and BM25 index.")
    parser.add_argument("--source", choices=("nccn", "csco"), default="csco")
    parser.add_argument("--pdf", type=Path, default=None)
    parser.add_argument("--kb-out", type=Path, default=None)
    parser.add_argument("--bm25-out", type=Path, default=None)
    args = parser.parse_args()
    build_source(args.source, pdf=args.pdf, kb_out=args.kb_out, bm25_out=args.bm25_out)


if __name__ == "__main__":
    main()
