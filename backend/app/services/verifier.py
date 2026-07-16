from __future__ import annotations

import re
from typing import Dict, List, Optional, Sequence

from backend.app.models import FigureReference, RetrievalHit
from backend.app.services.query_normalizer import extract_entities


SOURCE_CITATION_RE = re.compile(r"\[S\d+\]")
INLINE_SOURCE_SECTION_RE = re.compile(r"(?:来源|参考文献|引用来源)\s*[:：]")


def verify_answer(
    question: str,
    answer: str,
    hits: List[RetrievalHit],
    figures: Optional[Sequence[FigureReference]] = None,
) -> Dict[str, object]:
    figures = list(figures or [])
    image_grounded = bool(figures)

    citations = SOURCE_CITATION_RE.findall(answer)
    unique_citations = sorted(set(citations), key=lambda item: int(item[2:-1]))
    entities = extract_entities(question)
    # Captions of attached figures also count as grounded evidence text: an
    # image-grounded answer can legitimately rely on a flowchart whose page text
    # is scrambled, so we widen coverage to avoid false boundary-statement flags.
    evidence_parts = [hit.document.text for hit in hits]
    evidence_parts.extend(fig.caption for fig in figures if fig.caption)
    evidence_text = "\n".join(evidence_parts).lower()
    uncovered_entities = [entity for entity in entities if entity.lower() not in evidence_text]
    mentions_not_direct = "未直接提及" in answer or "没有直接提及" in answer
    # When the answer is grounded on figure images (whose content we cannot
    # text-match here), an uncovered entity is not automatically a violation.
    requires_boundary_statement = bool(uncovered_entities) and not image_grounded

    issues = []
    if not unique_citations:
        issues.append("answer_missing_source_citations")
    if requires_boundary_statement and not mentions_not_direct:
        issues.append("uncovered_entities_without_boundary_statement")
    if not hits and not figures:
        issues.append("no_retrieved_evidence")
    if INLINE_SOURCE_SECTION_RE.search(answer):
        issues.append("answer_contains_inline_sources")

    return {
        "ok": not issues,
        "issues": issues,
        "citation_count": len(unique_citations),
        "raw_citation_count": len(citations),
        "retrieved_source_count": len(hits),
        "figure_count": len(figures),
        "image_grounded": image_grounded,
        "question_entities": entities,
        "uncovered_entities": uncovered_entities,
        "requires_boundary_statement": requires_boundary_statement,
    }
