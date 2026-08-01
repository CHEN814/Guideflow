"""Tests for cited-only evidence filtering and display metadata."""
from __future__ import annotations

from backend.app.models import (
    FigureReference,
    QAResult,
    ReferenceEntry,
    RetrievalHit,
    SearchDocument,
)
from backend.app.services.citation_filter import (
    filter_attached_references,
    filter_cited_hits,
)
from backend.app.services.source_display import (
    build_cite_context_payload,
    clean_reference_text,
    enrich_reference_dict,
    enrich_source_dict,
    extract_author_year,
    extract_guideline_title,
    parse_reference_citation,
)


def _doc(
    source_id: str,
    text: str = "text",
    *,
    page_type: str = "clinical_guideline",
    printed_page_code: str | None = None,
    pdf_page: int = 1,
    section: str | None = None,
    article_id: str | None = None,
    reference_ids: list | None = None,
) -> SearchDocument:
    return SearchDocument(
        source_id=source_id,
        page_type=page_type,
        pdf_page=pdf_page,
        text=text,
        printed_page_code=printed_page_code,
        section=section,
        article_id=article_id,
        reference_ids=list(reference_ids or []),
    )


def _hit(doc: SearchDocument, rank: int = 1) -> RetrievalHit:
    return RetrievalHit(document=doc, score=1.0, retriever="test", rank=rank)


def test_filter_cited_hits_keeps_and_renumbers() -> None:
    hits = [
        _hit(_doc("page-A", printed_page_code="BCEL-A 1 OF 3"), rank=1),
        _hit(_doc("page-B", printed_page_code="BCEL-1"), rank=2),
        _hit(_doc("page-C", printed_page_code="ABBR-1"), rank=3),
    ]
    figures = [
        FigureReference(page_code="BCEL-A 1 OF 3", pdf_page=72, image_path="a.png", source_index=1),
        FigureReference(page_code="ABBR-1", pdf_page=137, image_path="c.png", source_index=3),
        FigureReference(page_code="BCEL-1", pdf_page=62, image_path="b.png", source_index=2),
    ]
    answer = "依据 [S1] 与 [S3] 判断；未引用中间来源。"

    new_answer, kept, figs, remap = filter_cited_hits(answer, hits, figures)

    assert [h.document.source_id for h in kept] == ["page-A", "page-C"]
    assert remap == {1: 1, 3: 2}
    assert "[S1]" in new_answer
    assert "[S2]" in new_answer
    assert "[S3]" not in new_answer
    assert figs[0].source_index == 1  # old 1 -> 1
    assert figs[1].source_index == 2  # old 3 -> 2
    assert figs[2].source_index is None  # old 2 dropped


def test_filter_cited_hits_fallback_keeps_all_when_no_citations() -> None:
    hits = [_hit(_doc("page-A")), _hit(_doc("page-B"), rank=2)]
    answer = "没有引用标记的回答。"
    new_answer, kept, _figs, remap = filter_cited_hits(answer, hits, [])
    assert new_answer == answer
    assert len(kept) == 2
    assert remap == {}


def test_filter_attached_references_gates_on_kept_sources() -> None:
    hits = [
        _hit(_doc("page-BCEL-1", printed_page_code="BCEL-1")),
        # discussion not kept → its refs must drop
    ]
    refs = [
        ReferenceEntry(
            entry_id="ref-dlbcl-1",
            article_id="dlbcl",
            ref_number="1",
            text="Al-Hamadani M, et al. Non-Hodgkin lymphoma. Am J Hematol 2015.",
            pmid="26096944",
            url="https://www.ncbi.nlm.nih.gov/pubmed/26096944",
        )
    ]
    links = {"disc-dlbcl-p248-c0": ["1"]}
    filtered_refs, filtered_links = filter_attached_references(hits, refs, links)
    assert filtered_refs == []
    assert filtered_links == {}


def test_filter_attached_references_keeps_when_discussion_cited() -> None:
    hits = [
        _hit(
            _doc(
                "disc-dlbcl-p248-c0",
                page_type="discussion",
                section="Discussion",
                article_id="dlbcl",
                reference_ids=["1"],
            )
        )
    ]
    refs = [
        ReferenceEntry(
            entry_id="ref-dlbcl-1",
            article_id="dlbcl",
            ref_number="1",
            text="Al-Hamadani M, et al. Study. 2015.",
            pmid="26096944",
        )
    ]
    links = {"disc-dlbcl-p248-c0": ["1"]}
    filtered_refs, filtered_links = filter_attached_references(hits, refs, links)
    assert len(filtered_refs) == 1
    assert filtered_refs[0].ref_number == "1"
    assert filtered_links == links


def test_filter_attached_references_drops_when_answer_has_no_citation() -> None:
    hits = [
        _hit(
            _doc(
                "disc-dlbcl-p248-c0",
                page_type="discussion",
                section="Discussion",
                article_id="dlbcl",
                reference_ids=["1"],
            )
        )
    ]
    refs = [
        ReferenceEntry(
            entry_id="ref-dlbcl-1",
            article_id="dlbcl",
            ref_number="1",
            text="Al-Hamadani M, et al. Study. 2015.",
            pmid="26096944",
        )
    ]
    links = {"disc-dlbcl-p248-c0": ["1"]}
    filtered_refs, filtered_links = filter_attached_references(
        hits, refs, links, answer="回答正文没有任何来源引用标记。"
    )
    assert filtered_refs == []
    assert filtered_links == {}


def test_filter_attached_references_keeps_when_answer_cites_source() -> None:
    hits = [
        _hit(
            _doc(
                "disc-dlbcl-p248-c0",
                page_type="discussion",
                section="Discussion",
                article_id="dlbcl",
                reference_ids=["1"],
            )
        )
    ]
    refs = [
        ReferenceEntry(
            entry_id="ref-dlbcl-1",
            article_id="dlbcl",
            ref_number="1",
            text="Al-Hamadani M, et al. Study. 2015.",
            pmid="26096944",
        )
    ]
    links = {"disc-dlbcl-p248-c0": ["1"]}
    filtered_refs, filtered_links = filter_attached_references(
        hits, refs, links, answer="依据 [S1] 判断。"
    )
    assert len(filtered_refs) == 1
    assert filtered_links == links


def test_extract_guideline_title_strips_boilerplate() -> None:
    text = (
        "Note: All recommendations are category 2A unless otherwise indicated. "
        "Diffuse Large B-Cell Lymphoma Table of Contents Discussion "
        "BCEL-A 1 OF 3 CLINICAL UTILITY OF GENOMIC ALTERATIONS IN DLBCL "
        "GENE CLINICAL ASSOCIATION ACTB, BCL2"
    )
    title = extract_guideline_title(text, fallback="BCEL-A 1 OF 3")
    assert "CLINICAL UTILITY" in title.upper()
    assert "Note:" not in title
    assert "Table of Contents" not in title


def test_clean_reference_and_author_year() -> None:
    raw = (
        "Al-Hamadani M, Habermann TM, Cerhan JR, et al. Non-Hodgkin\n"
        "lymphoma subtype distribution. Am J Hematol 2015;90:790–795.\n"
        "Available at:\nhttps://www.ncbi.nlm.nih.gov/pubmed/26096944."
    )
    cleaned = clean_reference_text(raw)
    assert "Available at" not in cleaned
    assert "\n" not in cleaned
    assert extract_author_year(cleaned) == "Al-Hamadani 2015"


def test_enrich_source_and_reference_payload() -> None:
    doc = _doc(
        "page-BCEL-A_1_OF_3",
        text=(
            "Note: All recommendations are category 2A unless otherwise indicated. "
            "Diffuse Large B-Cell Lymphoma Table of Contents Discussion "
            "BCEL-A 1 OF 3 CLINICAL UTILITY OF GENOMIC ALTERATIONS IN DLBCL"
        ),
        printed_page_code="BCEL-A 1 OF 3",
        pdf_page=72,
    )
    src = enrich_source_dict(doc)
    assert src["citation_label"] == "BCEL-A 1 OF 3"
    assert src["display_title"] == "BCEL-A 1 OF 3"
    assert "CLINICAL UTILITY" in (src.get("subtitle") or "").upper()
    assert "NCCN" in src["source_label"]
    assert src["locator"] == "p.72"
    assert src["badge"] == "指南"

    entry = ReferenceEntry(
        entry_id="ref-dlbcl-1",
        article_id="dlbcl",
        ref_number="1",
        text="Al-Hamadani M, et al. Non-Hodgkin lymphoma. Am J Hematol 2015;90:790-795.",
        pmid="26096944",
        url="https://www.ncbi.nlm.nih.gov/pubmed/26096944",
    )
    ref = enrich_reference_dict(entry)
    assert ref["display_title"] == "Non-Hodgkin lymphoma"
    assert ref["journal"] == "Am J Hematol"
    assert ref["year"] == "2015"
    assert ref["author_year"] == "Al-Hamadani 2015"
    assert ref["badge"] == "文献"
    assert "Am J Hematol" in ref["source_label"]


def test_parse_reference_citation_splits_vancouver() -> None:
    raw = (
        "Al-Hamadani M, Habermann TM, Cerhan JR, et al. Non-Hodgkin lymphoma "
        "subtype distribution. Am J Hematol 2015;90:790-795."
    )
    parsed = parse_reference_citation(raw)
    assert parsed["authors"] and "Al-Hamadani" in parsed["authors"]
    assert "Non-Hodgkin lymphoma" in (parsed["paper_title"] or "")
    assert parsed["journal"] == "Am J Hematol"
    assert parsed["year"] == "2015"


def test_build_cite_context_payload() -> None:
    hits = [
        _hit(
            _doc(
                "page-BCEL-1",
                text="Diffuse Large B-Cell Lymphoma BCEL-1 WORKUP",
                printed_page_code="BCEL-1",
                pdf_page=62,
            )
        )
    ]
    refs = [
        ReferenceEntry(
            entry_id="ref-1",
            article_id="dlbcl",
            ref_number="1",
            text="Smith A, et al. Fancy Title Here. Blood 2020;1:1.",
            pmid="123",
        )
    ]
    payload = build_cite_context_payload(hits, refs)
    assert payload["sources"][0]["citation_label"] == "BCEL-1"
    assert payload["sources"][0]["display_title"] == "BCEL-1"
    assert payload["attached_references"][0]["display_title"] == "Fancy Title Here"


def test_to_web_payload_includes_display_fields() -> None:
    result = QAResult(
        question="q",
        answer="依据 [S1]。",
        sources=[
            _doc(
                "page-BCEL-1",
                text="Diffuse Large B-Cell Lymphoma BCEL-1 DIAGNOSIS WORKUP",
                printed_page_code="BCEL-1",
                pdf_page=62,
            )
        ],
        verification={"ok": True},
        run_id="t",
        trace_path="",
        attached_references=[
            ReferenceEntry(
                entry_id="ref-1",
                article_id="dlbcl",
                ref_number="1",
                text="Smith A, et al. Title. Blood 2020;1:1.",
                pmid="123",
            )
        ],
    )
    payload = result.to_web_payload()
    assert payload["sources"][0]["citation_label"] == "BCEL-1"
    assert payload["sources"][0]["display_title"] == "BCEL-1"
    assert payload["attached_references"][0]["author_year"].startswith("Smith")
    assert payload["attached_references"][0]["display_title"] == "Title"
    assert "[" not in payload["attached_references"][0]["display_title"][:3]
