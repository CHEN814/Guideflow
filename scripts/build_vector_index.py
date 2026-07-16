from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.settings import EMBEDDING_PROFILES, apply_profile, load_settings
from backend.app.services.embeddings import load_embedding_model
from backend.app.services.store import load_knowledge_base
from backend.app.services.vector_store import create_vector_store


def main() -> None:
    settings = load_settings()
    parser = argparse.ArgumentParser(description="Build local vector index from knowledge base.")
    parser.add_argument(
        "--embedding",
        choices=sorted(EMBEDDING_PROFILES),
        help="Embedding profile to build for (overrides .env model and output dir).",
    )
    parser.add_argument("--kb", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    if args.embedding:
        settings = apply_profile(settings, args.embedding)
    kb_path = args.kb or settings.knowledge_base_path
    out_dir = args.out or settings.vector_index_dir

    kb = load_knowledge_base(kb_path)
    docs = kb.to_search_documents()
    embedding_model = load_embedding_model(settings.embedding_model)
    vector_store = create_vector_store(out_dir, embedding_model)
    degraded = vector_store.build(docs)
    print(f"Vector index written to: {out_dir}")
    print(f"Indexed documents: {len(vector_store.documents)}")
    if degraded:
        print(f"Degraded: {', '.join(degraded)}")


if __name__ == "__main__":
    main()
