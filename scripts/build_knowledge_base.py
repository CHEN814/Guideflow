from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.settings import load_settings
from backend.app.services.pdf_extractor import build_knowledge_base
from backend.app.services.store import save_knowledge_base


def main() -> None:
    settings = load_settings()
    parser = argparse.ArgumentParser(
        description="Build NCCN B-Cell Lymphoma structured knowledge base from PDF."
    )
    parser.add_argument("--pdf", type=Path, default=settings.pdf_path)
    parser.add_argument("--out", type=Path, default=settings.knowledge_base_path)
    args = parser.parse_args()

    kb = build_knowledge_base(args.pdf)
    save_knowledge_base(args.out, kb)

    s = kb.stats
    print(f"Knowledge base written to: {args.out}")
    print(f"  Guideline pages  : {s.get('guideline_page_count', 0)}")
    print(f"    front_matter   : {s.get('front_matter_count', 0)}")
    print(f"    clinical_guide : {s.get('clinical_guideline_count', 0)}")
    print(f"    discussion_text: {s.get('discussion_text_count', 0)}")
    print(f"    disc_refs      : {s.get('discussion_ref_count', 0)}")
    print(f"  Discussion chunks: {s.get('discussion_chunk_count', 0)}")
    print(f"  Reference entries: {s.get('reference_entry_count', 0)}")
    print(f"  Needs review     : {s.get('needs_review_count', 0)}")
    search_docs = kb.to_search_documents()
    print(f"  Search documents : {len(search_docs)}")


if __name__ == "__main__":
    main()
