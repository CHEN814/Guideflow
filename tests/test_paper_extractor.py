from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.services.paper_extractor import (
    EHA_PROFILE,
    build_paper_knowledge_base,
    get_paper_profile,
)

ROOT = Path(__file__).resolve().parents[1]
EHA_PDF = ROOT / "2025 EHA临床实践指南：大B细胞淋巴瘤的诊断、治疗和随访.pdf"


def _fake_tables(targets):
    """Inject one Markdown table per unique caption page (no VLM in unit tests)."""
    by_page = {}
    for pdf_page, caption in targets:
        page = int(pdf_page)
        if page in by_page:
            continue
        by_page[page] = [
            f"**{caption or f'TABLE p{page}'}**\n\n"
            f"| Col A | Col B |\n| --- | --- |\n| cell | [I, A] |\n"
        ]
    return by_page


@pytest.mark.skipif(not EHA_PDF.exists(), reason="EHA PDF not present in workspace")
def test_eha_paper_extractor_structure():
    kb = build_paper_knowledge_base(
        EHA_PDF,
        EHA_PROFILE,
        table_provider=_fake_tables,
        skip_vlm=True,
    )
    assert kb.source == "eha"
    assert kb.stats.get("pdf_page_count") == 19

    sections = set(kb.stats.get("sections") or [])
    # Core clinical sections should be present (title-cased).
    joined = " | ".join(sorted(sections)).lower()
    assert "staging" in joined or "prognostic" in joined
    assert "management" in joined or "1l" in joined
    assert len(sections) >= 6

    table_chunks = [c for c in kb.discussion_chunks if c.content_type == "table"]
    # EHA has tables on distinct pages (TABLE 1–7 + A1); fake provider emits one per page.
    assert len(table_chunks) >= 7
    assert all(c.source == "eha" for c in table_chunks)

    assert kb.stats.get("reference_entry_count", 0) >= 100
    assert any(e.ref_number == "1" for e in kb.reference_entries)

    # Superscript citations harvested into reference_ids on some narrative chunks.
    with_refs = [c for c in kb.discussion_chunks if c.content_type == "text" and c.reference_ids]
    assert with_refs, "expected span-level superscript citations on narrative chunks"
    assert any(rid.isdigit() for c in with_refs for rid in c.reference_ids)

    docs = kb.to_search_documents()
    assert docs
    assert all(d.source == "eha" for d in docs)
    assert any(d.content_type == "table" for d in docs)


def test_get_paper_profile():
    p = get_paper_profile("eha")
    assert p.source_key == "eha"
    assert p.article_id == "eha-lbcl"
    with pytest.raises(ValueError):
        get_paper_profile("unknown-source")
