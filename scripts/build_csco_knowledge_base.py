from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.settings import load_settings
from backend.app.services.csco_extractor import build_csco_knowledge_base
from backend.app.services.store import save_knowledge_base


def _default_csco_pdf(root: Path) -> Path:
    matches = sorted(root.glob("*CSCO*.pdf"))
    if matches:
        return matches[0]
    return root / "2025CSCO淋巴瘤诊疗指南(OCR).pdf"


def main() -> None:
    settings = load_settings()
    default_out = settings.root_dir / "data" / "processed" / "csco_knowledge_base.json"
    parser = argparse.ArgumentParser(
        description="Build CSCO lymphoma structured knowledge base from PDF."
    )
    parser.add_argument("--pdf", type=Path, default=_default_csco_pdf(settings.root_dir))
    parser.add_argument("--out", type=Path, default=default_out)
    args = parser.parse_args()

    kb = build_csco_knowledge_base(args.pdf)
    save_knowledge_base(args.out, kb)

    s = kb.stats
    print(f"CSCO knowledge base written to: {args.out}")
    print(f"  PDF pages        : {s.get('pdf_page_count', 0)}")
    print(f"  Printed offset   : {s.get('printed_page_offset', '?')}")
    print(f"  Front pages      : {s.get('guideline_page_count', 0)}")
    print(f"  Discussion chunks: {s.get('discussion_chunk_count', 0)}")
    print(f"    table chunks   : {s.get('table_chunk_count', 0)}")
    print(f"  Reference entries: {s.get('reference_entry_count', 0)}")
    print(f"  Chapters         : {len(s.get('chapters', []))}")
    search_docs = kb.to_search_documents()
    print(f"  Search documents : {len(search_docs)}")


if __name__ == "__main__":
    main()
