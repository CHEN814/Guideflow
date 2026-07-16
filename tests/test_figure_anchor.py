from __future__ import annotations

from backend.app.models import FigureReference, RetrievalHit, SearchDocument
from backend.app.services.figure_anchor import compute_anchors, split_answer_paragraphs
from backend.app.services.figure_selection import backfill_source_indices


def test_split_answer_paragraphs() -> None:
    answer = "## 结论\n进入 BCEL-C [S1]。\n\n## 依据\n详见流程图。"
    paragraphs = split_answer_paragraphs(answer)
    assert len(paragraphs) == 2
    assert "[S1]" in paragraphs[0]


def test_compute_anchors_by_sn() -> None:
    answer = "## 结论\n依据 [S1] 进入一线治疗。\n\n## 备注\n无图。"
    hits = [
        RetrievalHit(
            document=SearchDocument(
                source_id="a",
                page_type="clinical_guideline",
                pdf_page=79,
                text="regimen",
                printed_page_code="BCEL-C 1 OF 7",
            ),
            score=1.0,
            retriever="test",
            rank=1,
        )
    ]
    figures = [
        FigureReference(
            page_code="BCEL-C 1 OF 7",
            pdf_page=79,
            image_path="/tmp/a.png",
            source_index=1,
        )
    ]
    anchored = compute_anchors(answer, figures, hits)
    assert anchored[0].anchor_paragraph == 0
    assert anchored[0].anchor_key == "S1"


def test_backfill_source_index_for_neighbor_hit() -> None:
    """Bug A regression: neighbor figure must inherit [S1] from matching hit."""
    hits = [
        RetrievalHit(
            document=SearchDocument(
                source_id="a",
                page_type="clinical_guideline",
                pdf_page=79,
                text="regimen",
                printed_page_code="BCEL-C 1 OF 7",
            ),
            score=1.0,
            retriever="test",
            rank=1,
        )
    ]
    figures = [
        FigureReference(
            page_code="BCEL-C 1 OF 7",
            pdf_page=79,
            image_path="/tmp/a.png",
            source_index=None,
        )
    ]
    updated = backfill_source_indices(figures, hits)
    assert updated[0].source_index == 1
