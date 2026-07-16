"""Unit tests for pdf_extractor helpers (no real PDF required)."""
from __future__ import annotations

import re
from typing import Optional

import pytest

from backend.app.services.pdf_extractor import (
    _FOOTER_CODE_RE,
    _chapter_label,
    _clean_text,
    _extract_inline_ref_ids,
    _extract_ms_code,
    _is_toc_page,
    _looks_like_reference_page,
    _module_code_from,
    _parse_reference_entries,
    _parse_toc,
    _segment_discussion,
    _slugify,
    _split_into_chunks,
)


# ── _clean_text ────────────────────────────────────────────────────────────

def test_clean_text_removes_nccn_noise() -> None:
    raw = "National Comprehensive Cancer Network\nActual clinical text.\nVersion 3.2026"
    cleaned = _clean_text(raw)
    assert "National Comprehensive Cancer Network" not in cleaned
    assert "Version 3.2026" not in cleaned
    assert "Actual clinical text." in cleaned


def test_clean_text_removes_printed_by() -> None:
    raw = "Printed by Dr. Smith on 2026-01-01\nReal guideline content."
    cleaned = _clean_text(raw)
    assert "Printed by" not in cleaned
    assert "Real guideline content." in cleaned


def test_clean_text_preserves_medical_content() -> None:
    raw = "R-CHOP is the standard first-line therapy for DLBCL.\nBCL2 rearrangement indicates double-hit lymphoma."
    cleaned = _clean_text(raw)
    assert "R-CHOP" in cleaned
    assert "BCL2" in cleaned


# ── _FOOTER_CODE_RE ────────────────────────────────────────────────────────

@pytest.mark.parametrize("code,expected", [
    ("BCEL-1", True),
    ("BCEL-6B", True),
    ("MANT-A", True),
    ("BCEL-A 1 OF 3", True),
    ("MANT-A 1 OF 5", True),
    ("NHODG-B 4 OF 5", True),
    ("FOLL-2", True),
    ("Some random text", False),
    ("MS-116", False),
    ("B-Cell Lymphomas", False),
    ("", False),
])
def test_footer_code_re(code: str, expected: bool) -> None:
    assert bool(_FOOTER_CODE_RE.match(code)) == expected


def test_module_code_from_simple() -> None:
    assert _module_code_from("BCEL-1") == "BCEL"


def test_module_code_from_compound() -> None:
    assert _module_code_from("BCEL-A 1 OF 3") == "BCEL"


def test_module_code_from_mant() -> None:
    assert _module_code_from("MANT-6B") == "MANT"


# ── _extract_ms_code ────────────────────────────────────────────────────────

def test_extract_ms_code_found() -> None:
    text = "B-Cell Lymphomas\nMS-116\nSome discussion content."
    assert _extract_ms_code(text) == "MS-116"


def test_extract_ms_code_not_found() -> None:
    text = "BCEL-1\nWorkup and diagnosis."
    assert _extract_ms_code(text) is None


# ── TOC parsing / detection ─────────────────────────────────────────────────

_SAMPLE_TOC = (
    "B-Cell Lymphomas\n"
    "Discussion\n"
    "Overview .................................................. 2\n"
    "Sensitive/Inclusive Language Usage ....................... 3\n"
    "Supportive Care .......................................... 7\n"
    "Follicular Lymphoma ...................................... 22\n"
    "Marginal Zone Lymphomas .................................. 54\n"
    "Mantle Cell Lymphoma ..................................... 80\n"
    "Diffuse Large B-Cell Lymphomas ........................... 109\n"
    "Burkitt Lymphoma ......................................... 172\n"
    "Post-Transplant Lymphoproliferative Disorders ........... 198\n"
)


def test_is_toc_page_true() -> None:
    assert _is_toc_page(_SAMPLE_TOC) is True


def test_is_toc_page_false_on_body() -> None:
    body = (
        "B-Cell Lymphomas\nOverview\n"
        "Non-Hodgkin lymphomas (NHL) are a heterogeneous group of\n"
        "lymphoproliferative disorders originating in B lymphocytes.\n"
    )
    assert _is_toc_page(body) is False


def test_parse_toc_extracts_ordered_titles() -> None:
    entries = _parse_toc(_SAMPLE_TOC)
    titles = [t for t, _ in entries]
    assert ("Follicular Lymphoma", 22) in entries
    assert ("Diffuse Large B-Cell Lymphomas", 109) in entries
    # order preserved
    assert titles.index("Overview") < titles.index("Follicular Lymphoma")


# ── _slugify ─────────────────────────────────────────────────────────────────

def test_slugify_generic() -> None:
    assert _slugify("Histologic Transformation to DLBCL") == "histologic-transformation-to-dlbcl"


# ── _chapter_label ───────────────────────────────────────────────────────────

_TOC_TITLES = [t for t, _ in _parse_toc(_SAMPLE_TOC)]


def test_chapter_label_dlbcl_canonical_id() -> None:
    text = "B-Cell Lymphomas\nDiffuse Large B-Cell Lymphomas\nDLBCL is the most common subtype."
    art_id, art_title = _chapter_label(text, running_header="B-Cell Lymphomas", toc_titles=_TOC_TITLES)
    assert art_id == "dlbcl"
    assert "Diffuse Large B-Cell Lymphoma" in art_title


def test_chapter_label_overview_via_toc() -> None:
    text = (
        "B-Cell Lymphomas\nOverview\n"
        "Non-Hodgkin lymphomas (NHL) are a heterogeneous group, including "
        "diffuse large B-cell lymphoma (DLBCL) and follicular lymphoma (FL)."
    )
    art_id, art_title = _chapter_label(text, running_header="B-Cell Lymphomas", toc_titles=_TOC_TITLES)
    # Heading is "Overview" -> must NOT be mislabelled dlbcl despite prose mentions.
    assert art_id == "overview"
    assert art_title == "Overview"


# ── _looks_like_reference_page ─────────────────────────────────────────────

def test_reference_page_detected_with_urls() -> None:
    text = (
        "1. Smith J, Jones A. A study on DLBCL. J Clin Oncol 2020;38:123-130. "
        "Available at: https://www.ncbi.nlm.nih.gov/pubmed/11111111.\n"
        "2. Brown K, et al. CAR-T outcomes. Blood 2021;137:456-467. "
        "Available at: https://www.ncbi.nlm.nih.gov/pubmed/22222222.\n"
        "3. Lee C, et al. Rituximab in lymphoma. NEJM 2019;380:789-801. "
        "Available at: https://www.ncbi.nlm.nih.gov/pubmed/33333333.\n"
    )
    assert _looks_like_reference_page(text) is True


def test_reference_page_detected_with_header() -> None:
    text = (
        "References\n"
        "1. Smith J, Jones A. A study on DLBCL. J Clin Oncol 2020;38:123-130.\n"
        "2. Brown K, et al. CAR-T outcomes. Blood 2021;137:456-467.\n"
        "3. Lee C, et al. Rituximab in lymphoma. NEJM 2019;380:789-801.\n"
    )
    assert _looks_like_reference_page(text) is True


def test_numbered_body_list_not_a_reference_page() -> None:
    # A numbered treatment list in body text must NOT be treated as references,
    # otherwise it would trigger a spurious chapter boundary.
    text = (
        "First-line therapy options for DLBCL include the following regimens:\n"
        "1. R-CHOP for 6 cycles in most patients.\n"
        "2. Dose-adjusted EPOCH-R for high-grade disease.\n"
        "3. Pola-R-CHP for selected patients with IPI 2-5.\n"
    )
    assert _looks_like_reference_page(text) is False


def test_non_reference_page_not_detected() -> None:
    text = (
        "First-line therapy for DLBCL includes R-CHOP.\n"
        "Patients with stage I-II disease may receive 3-4 cycles.\n"
    )
    assert _looks_like_reference_page(text) is False


# ── _extract_inline_ref_ids ────────────────────────────────────────────────

def test_extract_inline_ref_ids_range() -> None:
    text = "As shown in studies.45-47 and confirmed by.48"
    ids = _extract_inline_ref_ids(text)
    assert "45" in ids
    assert "46" in ids
    assert "47" in ids


def test_extract_inline_ref_ids_bracket() -> None:
    text = "This was demonstrated [12] and replicated [13]."
    ids = _extract_inline_ref_ids(text)
    assert "12" in ids
    assert "13" in ids


# ── _split_into_chunks ─────────────────────────────────────────────────────

def test_split_into_chunks_basic() -> None:
    text = (
        "Introduction\n\n"
        "This section describes the diagnosis of DLBCL. "
        "Immunophenotyping is essential for subclassification.\n\n"
        "Treatment\n\n"
        "R-CHOP is the standard first-line regimen for most patients."
    )
    counter = [0]
    chunks = _split_into_chunks(
        [(255, text)],
        article_id="dlbcl",
        article_title="DLBCL",
        chunk_counter=counter,
    )
    assert len(chunks) >= 1
    assert all(c.article_id == "dlbcl" for c in chunks)
    assert all(c.pdf_page == 255 for c in chunks)


# ── _parse_reference_entries ───────────────────────────────────────────────

def test_parse_reference_entries_basic() -> None:
    text = (
        "1. Coiffier B, et al. CHOP chemotherapy plus rituximab compared with CHOP alone. "
        "N Engl J Med 2002;346:235-242. Available at: "
        "https://www.ncbi.nlm.nih.gov/pubmed/11807147.\n"
        "2. Sehn LH, et al. The revised International Prognostic Index. "
        "Blood 2007;109:1857-1861. Available at: "
        "https://www.ncbi.nlm.nih.gov/pubmed/17105812.\n"
    )
    entries = _parse_reference_entries(text, article_id="dlbcl", raw_links=[], page_blocks=[])
    assert len(entries) == 2
    assert entries[0].ref_number == "1"
    assert entries[0].pmid == "11807147"
    assert entries[1].ref_number == "2"
    assert entries[1].pmid == "17105812"
    assert all(e.article_id == "dlbcl" for e in entries)


def test_parse_reference_entries_with_doi() -> None:
    text = (
        "1. Author A, et al. Some study. J Med 2023. "
        "Available at: https://doi.org/10.1182/blood-2023-12345.\n"
    )
    entries = _parse_reference_entries(text, article_id="test", raw_links=[], page_blocks=[])
    assert len(entries) == 1
    assert entries[0].doi is not None
    assert "10.1182" in entries[0].doi


# ── _segment_discussion (structure-driven boundaries) ──────────────────────

def _page(pdf_page: int, clean: str):
    """Build a discussion-page tuple (raw_links/blocks empty for unit tests)."""
    return (pdf_page, clean, [], [])


def test_segment_discussion_keeps_overview_refs_out_of_dlbcl() -> None:
    """The general/overview chapter (and its references) must not be mislabelled
    as dlbcl just because the prose mentions DLBCL/FL. References stay grouped
    with the chapter whose body physically precedes them."""
    overview_body = (
        "B-Cell Lymphomas\nOverview\n"
        "Non-Hodgkin lymphomas (NHL) are a heterogeneous group, including "
        "diffuse large B-cell lymphoma (DLBCL; 32%), follicular lymphoma (FL; 17%), "
        "marginal zone lymphoma (MZL) and mantle cell lymphoma (MCL).\n"
    )
    overview_refs = (
        "B-Cell Lymphomas\nReferences\n"
        "1. Siegel RL, et al. Cancer statistics, 2025. CA Cancer J Clin 2025. "
        "Available at: https://www.ncbi.nlm.nih.gov/pubmed/39817679.\n"
        "2. Al-Hamadani M, et al. NHL subtype distribution. Am J Hematol 2015. "
        "Available at: https://www.ncbi.nlm.nih.gov/pubmed/26096944.\n"
        "3. Mafra A, et al. Global patterns of NHL. Int J Cancer 2022. "
        "Available at: https://www.ncbi.nlm.nih.gov/pubmed/35695282.\n"
    )
    fl_body = (
        "B-Cell Lymphomas\nFollicular Lymphoma\n"
        "Follicular lymphoma is the most common indolent B-cell lymphoma and "
        "frequently presents with advanced-stage disease.\n"
    )
    fl_refs = (
        "B-Cell Lymphomas\nReferences\n"
        "1. Author A, et al. FL outcomes. Blood 2020. "
        "Available at: https://www.ncbi.nlm.nih.gov/pubmed/44444444.\n"
        "2. Author B, et al. FL therapy. JCO 2021. "
        "Available at: https://www.ncbi.nlm.nih.gov/pubmed/55555555.\n"
        "3. Author C, et al. FL biology. NEJM 2019. "
        "Available at: https://www.ncbi.nlm.nih.gov/pubmed/66666666.\n"
    )

    pages = [
        _page(140, _SAMPLE_TOC),
        _page(141, overview_body),
        _page(151, overview_refs),
        _page(161, fl_body),
        _page(171, fl_refs),
    ]
    chunks, refs, page_records = _segment_discussion(pages)

    # No disease misattribution: nothing should be labelled dlbcl here.
    assert all(c.article_id != "dlbcl" for c in chunks)
    assert all(r.article_id != "dlbcl" for r in refs)

    # The TOC page is recorded but never produces disease chunks.
    toc_pages = [p for p in page_records if p.page_type == "discussion_toc"]
    assert len(toc_pages) == 1
    assert all(c.pdf_page != 140 for c in chunks)

    # Overview body + overview references share the same article_id.
    overview_chunks = [c for c in chunks if c.article_id == "overview"]
    overview_refs_out = [r for r in refs if r.article_id == "overview"]
    assert overview_chunks, "overview chapter should have body chunks"
    assert {r.ref_number for r in overview_refs_out} == {"1", "2", "3"}

    # FL body + FL references share article_id 'fl' and do not leak into overview.
    fl_chunks = [c for c in chunks if c.article_id == "fl"]
    fl_refs_out = [r for r in refs if r.article_id == "fl"]
    assert fl_chunks, "FL chapter should have body chunks"
    assert {r.ref_number for r in fl_refs_out} == {"1", "2", "3"}
