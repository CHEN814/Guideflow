from __future__ import annotations

from backend.app.models import FigureReference, RetrievalHit, SearchDocument
from backend.app.services.figure_selection import (
    lexical_overlap,
    prune_figures_by_answer,
)
from backend.app.services.dlbcl_flow_map import resolve_entry_page


def test_lexical_overlap() -> None:
    score = lexical_overlap("一线治疗 R-CHOP", "First-line therapy with R-CHOP")
    assert score > 0


def test_prune_figures_by_sn_citation() -> None:
    hits = [
        RetrievalHit(
            document=SearchDocument(
                source_id="a",
                page_type="clinical_guideline",
                pdf_page=79,
                text="regimen",
                printed_page_code="BCEL-C 3 OF 7",
            ),
            score=1.0,
            retriever="test",
            rank=1,
        ),
        RetrievalHit(
            document=SearchDocument(
                source_id="b",
                page_type="clinical_guideline",
                pdf_page=63,
                text="workup",
                printed_page_code="BCEL-2",
            ),
            score=1.0,
            retriever="test",
            rank=2,
        ),
    ]
    figures = [
        FigureReference(
            page_code="BCEL-C 3 OF 7",
            pdf_page=79,
            image_path="/tmp/a.png",
            caption="regimen",
            source_index=1,
        ),
        FigureReference(
            page_code="BCEL-2",
            pdf_page=63,
            image_path="/tmp/b.png",
            caption="workup",
            source_index=2,
        ),
    ]
    answer = "## 结论\n初始评估后进入 BCEL-3 流程 [S2]。"
    pruned = prune_figures_by_answer(answer, figures, hits, seed_page_code="BCEL-3")
    assert len(pruned) == 1
    assert pruned[0].page_code == "BCEL-2"


def test_prune_figures_keeps_seed_when_no_citation() -> None:
    figures = [
        FigureReference(
            page_code="BCEL-3",
            pdf_page=64,
            image_path="/tmp/c.png",
            caption="first-line",
            source_index=None,
        ),
        FigureReference(
            page_code="BCEL-C 6 OF 7",
            pdf_page=82,
            image_path="/tmp/d.png",
            caption="regimen",
            source_index=1,
        ),
    ]
    pruned = prune_figures_by_answer("## 结论\n暂无引用。", figures, [], seed_page_code="BCEL-3")
    assert len(pruned) == 1
    assert pruned[0].page_code == "BCEL-3"


def test_resolve_entry_regressions() -> None:
    assert resolve_entry_page("复发难治 DLBCL 下一步") == "BCEL-7"
    assert resolve_entry_page("再分期 interim restaging") == "BCEL-4"
