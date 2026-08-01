from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.services.knowledge_graph import KnowledgeGraphBuilder, save_knowledge_graph_bundle
from backend.app.services.neo4j_graph_service import Neo4jGraphService
from backend.app.services.store import (
    load_knowledge_base,
    save_knowledge_chunks,
)
from backend.app.settings import load_settings


def build_pipeline(*, with_embeddings: bool = False, skip_neo4j: bool = False) -> None:
    settings = load_settings()
    kb_path = settings.knowledge_base_path
    chunk_path = settings.chunk_index_path
    graph_path = settings.knowledge_graph_path

    print(f"[1/4] Loading knowledge base: {kb_path}")
    kb = load_knowledge_base(kb_path)

    print("[2/4] Exporting unified chunks")
    save_knowledge_chunks(chunk_path, kb)
    chunks = kb.to_chunks()
    print(f"      chunks: {len(chunks)} -> {chunk_path}")

    if with_embeddings:
        from backend.app.services.chunk_embedding_index import ChunkEmbeddingIndex

        print("[3/4] Building chunk embeddings")
        index = ChunkEmbeddingIndex(model_name=settings.chunk_embedding_model)
        index.build(chunks)
        index.save(settings.chunk_embedding_index_path, settings.chunk_embedding_meta_path)
        print(f"      embedding index -> {settings.chunk_embedding_index_path}")
        print(f"      embedding meta  -> {settings.chunk_embedding_meta_path}")
    else:
        print("[3/4] Building chunk embeddings — skipped (default; pass --with-embeddings to enable)")

    print("[4/4] Building knowledge graph from chunks")
    graph_bundle = KnowledgeGraphBuilder().build_from_chunks(chunks)
    save_knowledge_graph_bundle(graph_path, graph_bundle)
    print(f"      triples: {len(graph_bundle.triples)} -> {graph_path}")

    if skip_neo4j:
        print("[+] Neo4j import — skipped (--skip-neo4j)")
    elif settings.neo4j_password:
        print("[+] Importing triples into Neo4j")
        neo4j = Neo4jGraphService(settings)
        try:
            result = neo4j.import_triples(graph_bundle.triples)
            print(f"      imported: {result.get('imported', 0)}")
        finally:
            neo4j.close()
    else:
        print("[+] Neo4j import — skipped: NEO4J_PASSWORD not set")

    print("Pipeline finished successfully.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build knowledge chunks / graph (and optionally embeddings + Neo4j import)."
    )
    parser.add_argument("--dry-run", action="store_true", help="Load inputs and report planned outputs without writing.")
    parser.add_argument(
        "--with-embeddings",
        action="store_true",
        help="Build FAISS chunk embeddings (requires sentence-transformers + faiss-cpu). Disabled by default.",
    )
    parser.add_argument("--skip-neo4j", action="store_true", help="Do not import triples into Neo4j even if configured.")
    args = parser.parse_args()

    if args.dry_run:
        settings = load_settings()
        print(f"knowledge_base_path={settings.knowledge_base_path}")
        print(f"chunk_index_path={settings.chunk_index_path}")
        print(f"chunk_embedding_index_path={settings.chunk_embedding_index_path}")
        print(f"chunk_embedding_meta_path={settings.chunk_embedding_meta_path}")
        print(f"knowledge_graph_path={settings.knowledge_graph_path}")
        print(f"with_embeddings={args.with_embeddings}")
        print(f"skip_neo4j={args.skip_neo4j}")
        return

    build_pipeline(with_embeddings=args.with_embeddings, skip_neo4j=args.skip_neo4j)


if __name__ == "__main__":
    main()
