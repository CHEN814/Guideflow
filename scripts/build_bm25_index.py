from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.settings import load_settings
from backend.app.services.bm25_store import build_bm25_store
from backend.app.services.store import load_knowledge_base


def main() -> None:
    settings = load_settings()
    parser = argparse.ArgumentParser(description="Build BM25 index from local knowledge base.")
    parser.add_argument("--kb", type=Path, default=settings.knowledge_base_path)
    parser.add_argument("--out", type=Path, default=settings.bm25_index_path)
    args = parser.parse_args()

    kb = load_knowledge_base(args.kb)
    docs = kb.to_search_documents()
    store = build_bm25_store(docs)
    store.save(args.out)
    print(f"BM25 index written to: {args.out}")
    print(f"Indexed documents: {len(store.documents)}")


if __name__ == "__main__":
    main()
