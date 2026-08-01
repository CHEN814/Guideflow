from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.settings import load_settings, source_paths
from backend.app.services.bm25_store import build_bm25_store
from backend.app.services.store import load_knowledge_base


def main() -> None:
    settings = load_settings()
    parser = argparse.ArgumentParser(description="Build BM25 index from a local knowledge base.")
    parser.add_argument(
        "--source",
        choices=("nccn", "csco"),
        default="nccn",
        help="Which guideline source to index (default: nccn).",
    )
    parser.add_argument("--kb", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    paths = source_paths(args.source, settings)
    kb_path = args.kb or paths["knowledge_base"]
    out_path = args.out or paths["bm25_index"]

    kb = load_knowledge_base(kb_path)
    docs = kb.to_search_documents()
    # Stamp source on docs if missing (legacy NCCN JSON)
    for doc in docs:
        if not getattr(doc, "source", None):
            doc.source = args.source
        elif doc.source == "nccn" and args.source == "csco":
            doc.source = "csco"
    store = build_bm25_store(docs)
    store.save(out_path)
    print(f"BM25 index written to: {out_path}")
    print(f"Source: {args.source}")
    print(f"Indexed documents: {len(store.documents)}")


if __name__ == "__main__":
    main()
