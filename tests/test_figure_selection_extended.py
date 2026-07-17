from __future__ import annotations

from backend.app.models import FigureReference, RetrievalHit, SearchDocument
from backend.app.services.figure_selection import (
    extract_cited_page_codes,
    prune_figures_by_answer,
)


def test_extract_cited_page_codes_supports_letter_suffix() -> None:
    answer = "参见 BCEL-C 与 BCEL-A 2 OF 3 分支。"
    codes = extract_cited_page_codes(answer)
    assert "BCEL-C" in codes
    assert "BCEL-A 2 OF 3" in codes


def test_prune_fallback_prefers_cited_hit_over_seed() -> None:
    """Bug C regression: fallback should keep cited [S1] hit, not seed."""
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
            page_code="BCEL-3",
            pdf_page=64,
            image_path="/tmp/seed.png",
            source_index=None,
        ),
        FigureReference(
            page_code="BCEL-C 1 OF 7",
            pdf_page=79,
            image_path="/tmp/c.png",
            source_index=1,
        ),
    ]
    answer = "## 结论\n依据 [S1] 决策。"
    pruned = prune_figures_by_answer(
        answer, figures, hits, seed_page_code="BCEL-3", display_max=2
    )
    # Cited [S1] must come first; seed decision page may be kept as secondary.
    assert pruned[0].page_code == "BCEL-C 1 OF 7"
    assert any(fig.page_code == "BCEL-C 1 OF 7" for fig in pruned)
    codes = [fig.page_code for fig in pruned]
    assert codes[0] == "BCEL-C 1 OF 7"
    if len(pruned) > 1:
        assert "BCEL-3" in codes


def test_prune_secondary_next_step_respects_display_max() -> None:
    hits = [
        RetrievalHit(
            document=SearchDocument(
                source_id="a",
                page_type="clinical_guideline",
                pdf_page=63,
                text="workup",
                printed_page_code="BCEL-2",
            ),
            score=1.0,
            retriever="test",
            rank=1,
        )
    ]
    figures = [
        FigureReference(
            page_code="BCEL-2",
            pdf_page=63,
            image_path="/tmp/a.png",
            source_index=1,
        ),
        FigureReference(
            page_code="BCEL-3",
            pdf_page=64,
            image_path="/tmp/b.png",
            source_index=None,
        ),
    ]
    answer = "## 结论\n依据 [S1] 评估后进入一线治疗（BCEL-3）。"
    pruned = prune_figures_by_answer(
        answer, figures, hits, seed_page_code="BCEL-2", display_max=1
    )
    assert len(pruned) == 1
    assert pruned[0].page_code == "BCEL-2"
