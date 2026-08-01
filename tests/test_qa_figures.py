from __future__ import annotations

from unittest.mock import MagicMock

from backend.app.models import NormalizedQuery
from backend.app.models import RetrievalHit, SearchDocument
from backend.app.services.qa import QAService
from backend.app.settings import Settings
from pathlib import Path


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        root_dir=tmp_path,
        pdf_path=tmp_path / "dummy.pdf",
        knowledge_base_path=tmp_path / "kb.json",
        bm25_index_path=tmp_path / "bm25.pkl",
        logs_dir=tmp_path / "logs",
        qwen_api_key=None,
        qwen_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        qwen_model="qwen-plus",
        reranker_model="lexical",
        bm25_top_k=10,
        rerank_top_k=5,
        final_top_k=3,
        max_attached_refs=6,
        vlm_api_key=None,
        vlm_base_url="https://example.com",
        vlm_model="qwen-vl-max",
        page_image_dir=tmp_path / "images",
        page_image_dpi=150,
        summary_cache_path=tmp_path / "summaries.json",
        max_images=4,
        figure_ceiling=4,
        routing_mode="linear",
        agent_max_steps=4,
        graph_fanout=2,
        graph_depth=1,
        graph_reserve=2,
        enable_evidence_gating=False,
        crop_enabled=False,
        crop_dpi=None,
        crop_padding=0.02,
        crop_min_area=0.05,
        crop_prefer="vlm",
        display_max_figures=2,
        crop_vlm_max_area=0.8,
        crop_vlm_dedup_guard=True,
        knowledge_graph_path=tmp_path / "knowledge_graph.json",
        neo4j_uri="bolt://localhost:7687",
        neo4j_user="neo4j",
        neo4j_password=None,
        neo4j_database="neo4j",
        neo4j_clear=False,
        neo4j_batch_size=500,
        chunk_index_path=tmp_path / "knowledge_chunks.json",
        chunk_embedding_model="bge-m3",
        chunk_embedding_index_path=tmp_path / "knowledge_chunks.faiss",
        chunk_embedding_meta_path=tmp_path / "knowledge_chunks_meta.json",
    )


def test_gather_figures_seed_first_budget(tmp_path, monkeypatch) -> None:
    """Navigation neighbours must run even when many guideline hits exist."""
    from backend.app.models import GuidelinePage, PageLink, StructuredKnowledgeBase
    from backend.app.services.graph_navigator import GraphNavigator

    kb = StructuredKnowledgeBase(
        guideline_pages=[
            GuidelinePage(
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
                    )
                ],
            ),
            GuidelinePage(
                page_id="p64",
                pdf_page=64,
                page_type="clinical_guideline",
                clean_text="FIRST-LINE",
                printed_page_code="BCEL-3",
                module_code="BCEL",
                outgoing_links=[],
            ),
        ],
        discussion_chunks=[],
        reference_entries=[],
    )
    nav = GraphNavigator(kb)

    settings = _settings(tmp_path)
    service = object.__new__(QAService)
    service.settings = settings
    service.graph_navigator = nav
    service.summary_cache = MagicMock(all_summaries=lambda: {})
    service.page_renderer = MagicMock(
        render=lambda pdf_page: tmp_path / f"p{pdf_page}.png"
    )

    hits = [
        RetrievalHit(
            document=SearchDocument(
                source_id="page-c1",
                page_type="clinical_guideline",
                pdf_page=71,
                text="regimen table",
                printed_page_code="BCEL-C 1 OF 7",
                module_code="BCEL",
            ),
            score=9.0,
            retriever="test",
            rank=1,
        ),
        RetrievalHit(
            document=SearchDocument(
                source_id="page-2",
                page_type="clinical_guideline",
                pdf_page=63,
                text="workup",
                printed_page_code="BCEL-2",
                module_code="BCEL",
            ),
            score=5.0,
            retriever="test",
            rank=2,
        ),
    ]

    trace = MagicMock()
    normalized = NormalizedQuery(
        original="初治DLBCL要做什么检查？",
        entities=["DLBCL"],
        expanded_queries=[],
        search_queries=["workup"],
    )
    figures, meta = service._gather_figures(
        hits=hits,
        route="flowchart",
        question="初治DLBCL要做什么检查？",
        normalized=normalized,
        trace=trace,
    )
    codes = [fig.page_code for fig in figures]
    assert meta["seed_page_code"] == "BCEL-2"
    assert "BCEL-C 1 OF 7" in codes
    assert "BCEL-3" in codes
    assert len(figures) <= settings.max_images
    bcel2_fig = next(fig for fig in figures if fig.page_code == "BCEL-2")
    assert bcel2_fig.source_index == 2


def test_gather_figures_seed_not_crowded_out_by_budget_one(tmp_path, monkeypatch) -> None:
    """With figure_ceiling=1, seed decision page must win over regimen tables."""
    from backend.app.models import GuidelinePage, StructuredKnowledgeBase
    from backend.app.services.graph_navigator import GraphNavigator

    kb = StructuredKnowledgeBase(
        guideline_pages=[
            GuidelinePage(
                page_id="p64",
                pdf_page=64,
                page_type="clinical_guideline",
                clean_text="FIRST-LINE THERAPY",
                printed_page_code="BCEL-3",
                module_code="BCEL",
                outgoing_links=[],
            ),
        ],
        discussion_chunks=[],
        reference_entries=[],
    )
    nav = GraphNavigator(kb)
    base = _settings(tmp_path)
    settings = Settings(
        **{
            **base.__dict__,
            "max_images": 1,
            "figure_ceiling": 1,
        }
    )
    service = object.__new__(QAService)
    service.settings = settings
    service.graph_navigator = nav
    service.summary_cache = MagicMock(all_summaries=lambda: {})
    service.page_renderer = MagicMock(render=lambda pdf_page: tmp_path / f"p{pdf_page}.png")

    hits = [
        RetrievalHit(
            document=SearchDocument(
                source_id="page-c1",
                page_type="clinical_guideline",
                pdf_page=77,
                text="FIRST-LINE THERAPY regimen",
                printed_page_code="BCEL-C 1 OF 7",
                module_code="BCEL",
            ),
            score=19.0,
            retriever="test",
            rank=1,
        ),
        RetrievalHit(
            document=SearchDocument(
                source_id="page-3",
                page_type="clinical_guideline",
                pdf_page=64,
                text="FIRST-LINE decision",
                printed_page_code="BCEL-3",
                module_code="BCEL",
            ),
            score=13.0,
            retriever="test",
            rank=4,
        ),
    ]
    figures, meta = service._gather_figures(
        hits=hits,
        route="flowchart",
        question="DLBCL 一线治疗推荐？",
        normalized=NormalizedQuery(
            original="DLBCL 一线治疗推荐？",
            entities=["DLBCL"],
            expanded_queries=[],
            search_queries=["first-line therapy"],
        ),
        trace=MagicMock(),
    )
    assert meta["seed_page_code"] == "BCEL-3"
    assert [fig.page_code for fig in figures] == ["BCEL-3"]
