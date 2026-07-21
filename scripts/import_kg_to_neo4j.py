from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.services.knowledge_graph import load_knowledge_graph_bundle
from backend.app.services.neo4j_graph_service import Neo4jGraphService
from backend.app.settings import load_settings


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import knowledge_graph.json triples into Neo4j using the frontend neighborhood schema "
        "(OntologyConcept + TrustedTriple + APOC dynamic relations)."
    )
    parser.add_argument("--kg", default=None, help="Path to knowledge_graph.json (default: settings.knowledge_graph_path).")
    parser.add_argument("--no-clear", action="store_true", help="Do not wipe the database before importing.")
    args = parser.parse_args()

    settings = load_settings()
    if not settings.neo4j_password:
        raise SystemExit("NEO4J_PASSWORD is not set. Add it to .env before importing.")

    kg_path = Path(args.kg) if args.kg else settings.knowledge_graph_path
    bundle = load_knowledge_graph_bundle(kg_path)
    print(f"Loaded {len(bundle.triples)} triples from {kg_path}")

    service = Neo4jGraphService(settings)
    try:
        result = service.import_triples(bundle.triples, clear=not args.no_clear)
        print(f"Imported {result.get('imported', 0)} triples into Neo4j at {settings.neo4j_uri}")
    finally:
        service.close()


if __name__ == "__main__":
    main()
