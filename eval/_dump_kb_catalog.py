"""Dump searchable guideline unit catalogs for Part 2 gold annotation."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.services.store import load_knowledge_base


def snippet(text: str, n: int = 220) -> str:
    return " ".join((text or "").split())[:n]


def dump_one(name: str, path: Path) -> dict:
    kb = load_knowledge_base(path)
    pages = []
    for p in kb.guideline_pages:
        if p.page_type != "clinical_guideline":
            continue
        pages.append(
            {
                "unit_id": f"{name}:{p.printed_page_code or p.page_id}",
                "source_id": p.page_id,
                "page_code": p.printed_page_code,
                "pdf_page": p.pdf_page,
                "module": p.module_code,
                "snippet": snippet(p.clean_text),
            }
        )
    chunks = []
    for c in kb.discussion_chunks:
        chunks.append(
            {
                "unit_id": f"{name}:{c.chunk_id}",
                "source_id": c.chunk_id,
                "ms_page": c.ms_page_code,
                "article": c.article_id,
                "section": c.section,
                "content_type": getattr(c, "content_type", "text"),
                "pdf_page": c.pdf_page,
                "snippet": snippet(c.clean_text),
            }
        )
    return {
        "source": name,
        "n_pages": len(pages),
        "n_chunks": len(chunks),
        "pages": pages,
        "chunks": chunks,
    }


def main() -> None:
    out_dir = Path(__file__).resolve().parent / "catalogs"
    out_dir.mkdir(parents=True, exist_ok=True)
    mapping = {
        "nccn": ROOT / "data/processed/dlbcl_knowledge_base.json",
        "csco": ROOT / "data/processed/csco_knowledge_base.json",
        "eha": ROOT / "data/processed/eha_knowledge_base.json",
    }
    for name, path in mapping.items():
        data = dump_one(name, path)
        dest = out_dir / f"{name}_catalog.json"
        dest.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{name}: pages={data['n_pages']} chunks={data['n_chunks']} -> {dest}")


if __name__ == "__main__":
    main()
