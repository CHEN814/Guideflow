"""Tests for agentic routing helpers, KG relevance, and prompt hygiene."""
from __future__ import annotations

from backend.app.models import GraphTriple
from backend.app.prompts import FEW_SHOT_EXAMPLE, MULTIMODAL_SYSTEM_PROMPT, ROUTE_GUIDANCE
from backend.app.services.agent_tools import (
    extract_ready_payload,
    parse_tool_arguments,
    status_for_tool,
)
from backend.app.services.kg_retriever import KnowledgeGraphRetriever
from backend.app.services.knowledge_graph import KnowledgeGraphBundle


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
        evidence_source_ids=["disc-1"],
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
