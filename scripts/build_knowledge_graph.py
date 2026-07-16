from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.settings import load_settings
from backend.app.services.knowledge_graph import KnowledgeGraphBuilder, save_knowledge_graph_bundle
from backend.app.services.store import load_knowledge_base


def main() -> None:
    settings = load_settings()
    parser = argparse.ArgumentParser(description="Build the medical knowledge graph bundle from the structured knowledge base.")
    parser.add_argument("--kb", type=Path, default=settings.knowledge_base_path, help="Structured knowledge base JSON path.")
    parser.add_argument("--out", type=Path, default=settings.knowledge_graph_path, help="Output knowledge graph JSON path.")
    args = parser.parse_args()

    kb = load_knowledge_base(args.kb)
    bundle = KnowledgeGraphBuilder().build(kb)
    save_knowledge_graph_bundle(args.out, bundle)

    print(f"Knowledge graph written to: {args.out}")
    for key, value in bundle.stats.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
