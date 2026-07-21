"""Tests for agentic routing helpers, KG relevance, and prompt hygiene."""
from __future__ import annotations

from backend.app.models import EvidenceBundle, GraphTriple, RetrievalHit, SearchDocument
from backend.app.prompts import FEW_SHOT_EXAMPLE, MULTIMODAL_SYSTEM_PROMPT, ROUTE_GUIDANCE, build_evidence_prompt
from backend.app.services.agent_orchestrator import AgentOrchestrator
from backend.app.services.agent_tools import (
    AgentState,
    extract_ready_payload,
    parse_tool_arguments,
    status_for_tool,
)
from backend.app.services.disease_scope import (
    detect_disease_scope,
    parse_source_scope,
    triple_sources_in_scope,
)
from backend.app.services.kg_retriever import KnowledgeGraphRetriever
from backend.app.services.knowledge_graph import KnowledgeGraphBundle
from backend.app.services.qa import QAService
from backend.app.services.qwen import _fallback_indices


def test_few_shot_does_not_leak_double_expressor() -> None:
    assert "双表达" not in FEW_SHOT_EXAMPLE
    assert "双表达" not in MULTIMODAL_SYSTEM_PROMPT


def test_route_guidance_not_force_next_page() -> None:
    text = ROUTE_GUIDANCE["flowchart"]
    assert "下一步页码" in text or "页码" in text
    # Soft guidance only — must not force filling empty next-page fields.
    assert "无后续页码" not in text


def test_status_for_tool_labels() -> None:
    event = status_for_tool("search_guidelines", {"query": "DLBCL 一线", "kind": "flowchart"})
    assert event["type"] == "status"
    assert "检索指南" in event["label"]
    assert "DLBCL" in event["label"]

    view = status_for_tool("view_pages", {"page_codes": ["BCEL-3", "BCEL-C 1 OF 7"]})
    assert "BCEL-3" in view["label"]


def test_parse_tool_arguments_and_ready() -> None:
    assert parse_tool_arguments('{"query":"x","kind":"any"}')["kind"] == "any"
    assert extract_ready_payload('ok\n{"ready": true, "route": "flowchart"}')["route"] == "flowchart"
    assert extract_ready_payload("not json") is None


def _triple(
    subject: str,
    relation: str,
    obj: str,
    evidence: str,
    tid: str,
    object_type: str = "Therapy",
    source_ids: tuple[str, ...] = ("disc-1",),
) -> GraphTriple:
    return GraphTriple(
        triple_id=tid,
        subject_id=f"disease:{subject.lower()}",
        subject_name=subject,
        subject_type="Disease",
        relation=relation,
        object_id=f"concept:{obj.lower().replace(' ', '_')}",
        object_name=obj,
        object_type=object_type,
        confidence=0.86,
        validation_status="trusted",
        evidence_source_ids=list(source_ids),
        evidence_text=evidence,
        evidence_kind="discussion",
    )


def test_kg_therapy_query_filters_unrelated_edges() -> None:
    bundle = KnowledgeGraphBundle(
        triples=[
            _triple(
                "DLBCL",
                "RECOMMENDS",
                "Biopsy",
                "Biopsy is recommended to rule out DLBCL.",
                "t1",
                object_type="Procedure",
            ),
            _triple(
                "DLBCL",
                "RECOMMENDS",
                "R-CHOP",
                "R-CHOP is preferred first-line therapy for DLBCL.",
                "t2",
            ),
            _triple(
                "DLBCL",
                "RECOMMENDS",
                "Pola-R-CHP",
                "Pola-R-CHP is recommended for first-line therapy when IPI is high.",
                "t3",
            ),
        ]
    )
    retriever = KnowledgeGraphRetriever(bundle)
    # Force entity seed via ontology-less fallback path: put DLBCL in query text.
    hits = retriever.retrieve("DLBCL 一线治疗推荐", top_k=5, hops=1, min_relevance=0.12)
    objects = {h.triple.object_name for h in hits}
    assert "Biopsy" not in objects
    assert objects & {"R-CHOP", "Pola-R-CHP"}


def test_parse_source_scope_conventions() -> None:
    assert parse_source_scope("disc-dlbcl-p248-c0") == ("dlbcl", None)
    assert parse_source_scope("ref-mzl-29") == ("mzl", None)
    assert parse_source_scope("page-BCEL-A_1_OF_3") == (None, "BCEL")
    assert parse_source_scope("page-NHODG-A_6_OF_8") == (None, "NHODG")
    assert parse_source_scope("822") == (None, None)


def test_triple_sources_in_scope_verdicts() -> None:
    scope = detect_disease_scope("DLBCL 分型")
    assert triple_sources_in_scope(["disc-dlbcl-p248-c0"], scope) is True
    assert triple_sources_in_scope(["page-BCEL-1"], scope) is True
    # Common supportive-care module is in-scope for any specific disease.
    assert triple_sources_in_scope(["page-NHODG-A_6_OF_8"], scope) is True
    # Another disease's chapter is rejected.
    assert triple_sources_in_scope(["disc-mzl-p197-c4"], scope) is False
    # Unresolvable (bare Neo4j edge id).
    assert triple_sources_in_scope(["822"], scope) is None


def test_kg_retrieve_scope_drops_other_disease_sources() -> None:
    bundle = KnowledgeGraphBundle(
        triples=[
            _triple("DLBCL", "SUBTYPE", "GCB", "GCB is a DLBCL subtype.", "d1",
                    object_type="Concept", source_ids=("disc-dlbcl-p248-c0",)),
            _triple("DLBCL", "RECOMMENDS", "Biopsy", "Biopsy to rule out DLBCL.", "m1",
                    object_type="Procedure", source_ids=("disc-mzl-p197-c4",)),
            _triple("DLBCL", "RECOMMENDS", "BCL6", "HGBL similar to DLBCL-NOS.", "h1",
                    object_type="Gene", source_ids=("disc-hgbl-p303-c0",)),
        ]
    )
    retriever = KnowledgeGraphRetriever(bundle)
    scope = detect_disease_scope("DLBCL 中 GCB 与 ABC 有何差异")
    hits = retriever.retrieve(
        "DLBCL 中 GCB 与 ABC 有何差异", top_k=10, hops=1, min_relevance=0.0, disease_scope=scope
    )
    sources = {sid for hit in hits for sid in hit.triple.evidence_source_ids}
    assert "disc-mzl-p197-c4" not in sources
    assert "disc-hgbl-p303-c0" not in sources

    triples = retriever.expand_subgraph(["disease:dlbcl"], hops=1, top_k=10, disease_scope=scope)
    exp_sources = {sid for t in triples for sid in t.evidence_source_ids}
    assert "disc-dlbcl-p248-c0" in exp_sources
    assert "disc-mzl-p197-c4" not in exp_sources
    assert "disc-hgbl-p303-c0" not in exp_sources


def test_filter_graph_for_prompt_scopes_and_denoises() -> None:
    svc = QAService.__new__(QAService)
    scope = detect_disease_scope("DLBCL 中 GCB 与 ABC 有何差异")
    in_scope = _triple("DLBCL", "SUBTYPE", "GCB", "GCB is a DLBCL subtype.", "d1",
                       object_type="Concept", source_ids=("disc-dlbcl-p248-c0",))
    other_disease = _triple("DLBCL", "RECOMMENDS", "Biopsy", "Biopsy to rule out DLBCL.", "m1",
                            object_type="Procedure", source_ids=("disc-mzl-p197-c4",))
    synth = GraphTriple(
        triple_id="synth:1:x:y", subject_id="synth:x", subject_name="DLBCL",
        subject_type="QuerySeed", relation="MENTIONS", object_id="synth:y",
        object_name="page", object_type="SourcePage", confidence=0.6,
        validation_status="fallback", evidence_text="", evidence_source_ids=["disc-dlbcl-p248-c0"],
        evidence_kind="retrieval", review_status="synthetic",
    )
    neo4j_empty = GraphTriple(
        triple_id="neo4j:822", subject_id="822", subject_name="", subject_type="Node",
        relation="SUBJECT_OF", object_id="823", object_name="", object_type="Node",
        confidence=0.8, validation_status="trusted", evidence_text="edge",
        evidence_source_ids=["822"], evidence_kind="neo4j",
    )
    subset = svc._filter_graph_for_prompt([in_scope, other_disease, synth, neo4j_empty], scope,
                                          "DLBCL 中 GCB 与 ABC 有何差异")
    ids = {t.triple_id for t in subset}
    assert ids == {"d1"}


def test_prompt_omits_graph_block_when_subset_empty() -> None:
    svc = QAService.__new__(QAService)
    scope = detect_disease_scope("DLBCL 中 GCB 与 ABC 有何差异")
    only_other = [
        _triple("DLBCL", "RECOMMENDS", "Biopsy", "Biopsy to rule out DLBCL.", "m1",
                object_type="Procedure", source_ids=("disc-mzl-p197-c4",))
    ]
    subset = svc._filter_graph_for_prompt(only_other, scope, "DLBCL 中 GCB 与 ABC 有何差异")
    assert subset == []
    prompt = build_evidence_prompt(
        "DLBCL 中 GCB 与 ABC 有何差异", EvidenceBundle(primary_hits=[], graph_triples=subset)
    )
    assert "[G1]" not in prompt
    assert "可用知识图谱证据" not in prompt


def _hit(
    source_id: str,
    page_code: str | None,
    text: str,
    *,
    page_type: str = "clinical_guideline",
    rank: int = 1,
) -> RetrievalHit:
    return RetrievalHit(
        document=SearchDocument(
            source_id=source_id,
            page_type=page_type,
            pdf_page=1,
            text=text,
            printed_page_code=page_code,
        ),
        score=1.0,
        retriever="test",
        rank=rank,
    )


def test_fallback_indices_drops_decision_pages_when_unprotected() -> None:
    hits = [
        _hit("disc-1", None, "DLBCL GCB versus ABC subtype discussion", page_type="discussion", rank=1),
        _hit("page-BCEL-1", "BCEL-1", "Diffuse Large B-Cell Lymphoma BCEL-1 DLBCL", rank=2),
        _hit("page-ABBR-1", "ABBR-1", "abbreviations DLBCL", rank=3),
    ]
    question = "DLBCL 中 GCB 与 ABC 有何差异"
    dropped = _fallback_indices(question, hits, set(), protect_decision_pages=False)
    assert 1 in dropped
    assert 2 not in dropped  # BCEL-1 is a decision page

    kept = _fallback_indices(question, hits, {2}, protect_decision_pages=True)
    assert 2 in kept


def test_fallback_indices_keeps_all_when_only_decision_pages() -> None:
    hits = [
        _hit("page-BCEL-1", "BCEL-1", "DLBCL decision flow", rank=1),
        _hit("page-BCEL-2", "BCEL-2", "DLBCL workup", rank=2),
    ]
    indices = _fallback_indices(
        "DLBCL first-line", hits, set(), protect_decision_pages=False
    )
    # Stripping would empty the set → keep original lexical set.
    assert indices


def test_should_upgrade_only_on_genuine_flowchart_intent() -> None:
    # Low-rank decision page alone must NOT upgrade.
    state = AgentState()
    state.route = "evidence"
    state.seed_page_code = None
    state.hits = [
        _hit("disc-1", None, "discussion GCB ABC", page_type="discussion", rank=1),
        _hit("page-BCEL-1", "BCEL-1", "decision flow", rank=2),
    ]
    assert AgentOrchestrator._should_upgrade_to_flowchart(state) is False

    # Rank-1 decision page → upgrade.
    state.hits = [
        _hit("page-BCEL-1", "BCEL-1", "decision flow", rank=1),
        _hit("disc-1", None, "discussion", page_type="discussion", rank=2),
    ]
    assert AgentOrchestrator._should_upgrade_to_flowchart(state) is True

    # Intent-map seed is a decision page → upgrade even if rank-1 is prose.
    state.hits = [
        _hit("disc-1", None, "discussion", page_type="discussion", rank=1),
        _hit("page-BCEL-1", "BCEL-1", "decision flow", rank=2),
    ]
    state.seed_page_code = "BCEL-3"
    assert AgentOrchestrator._should_upgrade_to_flowchart(state) is True

    # Non-evidence route → no upgrade from this helper.
    state.route = "hybrid"
    state.seed_page_code = "BCEL-3"
    assert AgentOrchestrator._should_upgrade_to_flowchart(state) is False
