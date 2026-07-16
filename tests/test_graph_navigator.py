from __future__ import annotations

from backend.app.models import GuidelinePage, PageLink, StructuredKnowledgeBase
from backend.app.services.dlbcl_flow_map import (
    is_decision_flow_page,
    pick_seed_page_code,
    resolve_entry_page,
)
from backend.app.models import RetrievalHit, SearchDocument
from backend.app.services.graph_navigator import GraphNavigator


def _hit(page_code: str, page_type: str = "clinical_guideline", rank: int = 1) -> RetrievalHit:
    return RetrievalHit(
        document=SearchDocument(
            source_id=f"page-{page_code.replace(' ', '_')}",
            page_type=page_type,
            pdf_page=60 + rank,
            text="sample",
            printed_page_code=page_code,
            module_code="BCEL",
        ),
        score=1.0,
        retriever="test",
        rank=rank,
    )


def test_is_decision_flow_page() -> None:
    assert is_decision_flow_page("BCEL-3")
    assert is_decision_flow_page("bcel-7")
    assert not is_decision_flow_page("BCEL-C 3 OF 7")
    assert not is_decision_flow_page("BCEL-A 1 OF 3")
    assert not is_decision_flow_page(None)


def test_resolve_entry_page_first_line_therapy() -> None:
    assert resolve_entry_page("弥漫大B细胞淋巴瘤患者的一线治疗策略是什么？") == "BCEL-3"


def test_resolve_entry_page_workup() -> None:
    assert resolve_entry_page("初治DLBCL患者要做什么检查？") == "BCEL-2"


def test_pick_seed_prefers_intent_over_hits() -> None:
    hits = [_hit("BCEL-C 3 OF 7", rank=1), _hit("BCEL-2", rank=2)]
    seed, source = pick_seed_page_code("一线治疗策略是什么？", hits)
    assert seed == "BCEL-3"
    assert source == "intent_map"


def test_pick_seed_fallback_to_decision_hit() -> None:
    hits = [_hit("BCEL-C 6 OF 7", rank=1), _hit("BCEL-2", rank=2)]
    seed, source = pick_seed_page_code("DLBCL 相关信息", hits)
    assert seed == "BCEL-2"
    assert source == "hit_fallback"


def _kb_with_links() -> StructuredKnowledgeBase:
    bcel2 = GuidelinePage(
        page_id="p63",
        pdf_page=63,
        page_type="clinical_guideline",
        clean_text="WORKUP",
        printed_page_code="BCEL-2",
        module_code="BCEL",
        outgoing_links=[
            PageLink(
                source_page_code="BCEL-2",
                target_pdf_page=64,
                target_page_code="BCEL-3",
                anchor_text="First-line therapy",
                edge_type="flow",
            ),
            PageLink(
                source_page_code="BCEL-2",
                target_pdf_page=79,
                target_page_code="BCEL-C 3 OF 7",
                anchor_text="Suggested Regimens",
                edge_type="flow",
            ),
        ],
    )
    bcel3 = GuidelinePage(
        page_id="p64",
        pdf_page=64,
        page_type="clinical_guideline",
        clean_text="FIRST-LINE THERAPY stage",
        printed_page_code="BCEL-3",
        module_code="BCEL",
        outgoing_links=[
            PageLink(
                source_page_code="BCEL-3",
                target_pdf_page=65,
                target_page_code="BCEL-4",
                anchor_text="Stage I II nonbulky",
                edge_type="flow",
            ),
            PageLink(
                source_page_code="BCEL-3",
                target_pdf_page=66,
                target_page_code="BCEL-5",
                anchor_text="Bulky disease",
                edge_type="flow",
            ),
        ],
    )
    bcel4 = GuidelinePage(
        page_id="p65",
        pdf_page=65,
        page_type="clinical_guideline",
        clean_text="RESTAGING",
        printed_page_code="BCEL-4",
        module_code="BCEL",
        outgoing_links=[],
    )
    bcel5 = GuidelinePage(
        page_id="p66",
        pdf_page=66,
        page_type="clinical_guideline",
        clean_text="RESTAGING bulky",
        printed_page_code="BCEL-5",
        module_code="BCEL",
        outgoing_links=[],
    )
    regimen = GuidelinePage(
        page_id="p79",
        pdf_page=79,
        page_type="clinical_guideline",
        clean_text="SUGGESTED REGIMENS",
        printed_page_code="BCEL-C 3 OF 7",
        module_code="BCEL",
        outgoing_links=[],
    )
    return StructuredKnowledgeBase(
        guideline_pages=[bcel2, bcel3, bcel4, bcel5, regimen],
        discussion_chunks=[],
        reference_entries=[],
    )


def test_graph_expand_prefers_query_relevant_branch() -> None:
    nav = GraphNavigator(_kb_with_links())
    neighbours = nav.expand(
        "BCEL-3",
        query="大包块 bulky disease 一线治疗",
        page_summaries={},
        fanout=1,
        depth=1,
        budget=1,
    )
    assert neighbours == [(66, "BCEL-5")]


def test_graph_expand_from_bcel2_includes_bcel3() -> None:
    nav = GraphNavigator(_kb_with_links())
    neighbours = nav.expand(
        "BCEL-2",
        query="一线治疗 first-line therapy",
        page_summaries={},
        fanout=2,
        depth=1,
        budget=2,
    )
    codes = [code for _page, code in neighbours]
    assert "BCEL-3" in codes
