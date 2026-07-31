from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.settings import load_settings, source_paths
from backend.app.services.knowledge_graph import KnowledgeGraphBuilder, save_knowledge_graph_bundle
from backend.app.services.store import load_knowledge_base


def main() -> None:
    settings = load_settings()
    parser = argparse.ArgumentParser(description="Build the medical knowledge graph bundle from the structured knowledge base.")
    parser.add_argument(
        "--source",
        choices=("nccn", "csco"),
        default="nccn",
        help="Which guideline source to build (default: nccn).",
    )
    parser.add_argument("--kb", type=Path, default=None, help="Structured knowledge base JSON path.")
    parser.add_argument("--out", type=Path, default=None, help="Output knowledge graph JSON path.")
    args = parser.parse_args()

    paths = source_paths(args.source, settings)
    kb_path = args.kb or paths["knowledge_base"]
    out_path = args.out or paths["knowledge_graph"]

    kb = load_knowledge_base(kb_path)
    kb.source = args.source
    for page in kb.guideline_pages:
        page.source = args.source
    for chunk in kb.discussion_chunks:
        chunk.source = args.source
    for ref in kb.reference_entries:
        ref.source = args.source
    bundle = KnowledgeGraphBuilder().build(kb)
    save_knowledge_graph_bundle(out_path, bundle)

    print(f"Knowledge graph written to: {out_path}")
    print(f"Source: {args.source}")
    for key, value in bundle.stats.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
