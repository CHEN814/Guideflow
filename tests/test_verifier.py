from __future__ import annotations

from backend.app.services.answer_formatter import format_answer
from backend.app.models import RetrievalHit, SearchDocument
from backend.app.services.verifier import verify_answer


def _hit(text: str) -> RetrievalHit:
    return RetrievalHit(
        document=SearchDocument(
            source_id="s1",
            page_type="discussion",
            pdf_page=10,
            text=text,
        ),
        score=1.0,
        retriever="test",
        rank=1,
    )


def test_verifier_accepts_cited_answer() -> None:
    result = verify_answer(
        "TP53 在 DLBCL 中的意义是什么？",
        "指南讨论了 TP53 mutation in DLBCL 的相关证据 [S1]。",
        [_hit("TP53 mutation in DLBCL")],
    )

    assert result["ok"] is True
    assert result["citation_count"] == 1


def test_verifier_requires_boundary_for_uncovered_entity() -> None:
    result = verify_answer(
        "TP53 R248Q 在 DLBCL 中的意义是什么？",
        "指南讨论了 TP53 mutation in DLBCL 的相关证据 [S1]。",
        [_hit("TP53 mutation in DLBCL")],
    )

    assert result["ok"] is False
    assert "uncovered_entities_without_boundary_statement" in result["issues"]


def test_verifier_allows_boundary_statement_for_uncovered_entity() -> None:
    result = verify_answer(
        "TP53 R248Q 在 DLBCL 中的意义是什么？",
        "指南未直接提及 R248Q，仅讨论 TP53 mutation in DLBCL [S1]。",
        [_hit("TP53 mutation in DLBCL")],
    )

    assert result["ok"] is True


def test_verifier_deduplicates_citation_count() -> None:
    result = verify_answer(
        "TP53 在 DLBCL 中的意义是什么？",
        "证据 [S1] 与 [S1] 重复引用同一来源。",
        [_hit("TP53 mutation in DLBCL")],
    )

    assert result["citation_count"] == 1
    assert result["raw_citation_count"] == 2


def test_format_answer_strips_inline_sources_and_internal_ids() -> None:
    answer = (
        "## 结论\n指南未直接提及 R248Q [S1]。\n\n"
        "来源：\n[S1] ref-dlbcl-27 | discussion\n"
        "disc-dlbcl-p140-c0"
    )

    cleaned = format_answer(answer)

    assert "来源：" not in cleaned
    assert "ref-dlbcl" not in cleaned
    assert "disc-dlbcl" not in cleaned
    assert "[S1]" in cleaned
