from __future__ import annotations

import re
from typing import Dict, List

from backend.app.models import NormalizedQuery


TRANSLATION_HINTS: Dict[str, str] = {
    "预后": "prognosis prognostic significance outcome",
    "治疗": "therapy treatment regimen",
    "一线": "first-line therapy initial therapy",
    "二线": "second-line therapy subsequent therapy",
    "复发": "relapsed disease",
    "难治": "refractory disease",
    "诊断": "diagnosis diagnostic workup",
    "检查": "workup testing evaluation",
    "分期": "staging",
    "随访": "follow-up surveillance",
    "突变": "mutation",
    "重排": "rearrangement",
    "双打击": "double-hit high-grade B-cell lymphoma",
    "弥漫大B细胞淋巴瘤": "diffuse large B-cell lymphoma DLBCL",
    "大B细胞淋巴瘤": "large B-cell lymphoma LBCL",
}

ENTITY_RE = re.compile(
    r"\b(?:[A-Z]{2,}[A-Z0-9-]*|[A-Z][a-z]?[0-9]{1,4}[A-Z][a-z]?|R-CHOP|Pola-R-CHP|CAR[- ]?T)\b"
)


def extract_entities(question: str) -> List[str]:
    entities = set(ENTITY_RE.findall(question))
    for term in ["TP53", "MYC", "BCL2", "BCL6", "CD19", "CD20", "DLBCL", "IPI", "FISH", "PET", "CT"]:
        if term.lower() in question.lower():
            entities.add(term)
    return sorted(entities)


def normalize_query(question: str) -> NormalizedQuery:
    question = question.strip()
    entities = extract_entities(question)
    expanded: List[str] = []

    for zh, en in TRANSLATION_HINTS.items():
        if zh in question:
            expanded.append(en)

    if "DLBCL" in question.upper() and "diffuse large B-cell lymphoma DLBCL" not in expanded:
        expanded.append("diffuse large B-cell lymphoma DLBCL")

    if entities:
        expanded.append(" ".join(entities))

    entity_contexts = []
    for entity in entities:
        if entity.upper() in {"TP53", "MYC", "BCL2", "BCL6"}:
            entity_contexts.append(f"{entity} DLBCL mutation rearrangement prognosis")
        elif re.match(r"^[A-Z][a-z]?[0-9]{1,4}[A-Z][a-z]?$", entity):
            entity_contexts.append(f"{entity} variant mutation DLBCL")

    search_queries = [question]
    search_queries.extend(expanded)
    search_queries.extend(entity_contexts)
    search_queries = _dedupe([query.strip() for query in search_queries if query.strip()])

    return NormalizedQuery(
        original=question,
        entities=entities,
        expanded_queries=_dedupe(expanded + entity_contexts),
        search_queries=search_queries,
    )


def _dedupe(items: List[str]) -> List[str]:
    seen = set()
    output = []
    for item in items:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output
