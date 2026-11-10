"""Retrieval/generation policy hooks used by QA and experiment arms."""
from __future__ import annotations

import re
from typing import List, Optional, Sequence

from backend.app.models import RetrievalHit
from backend.app.services.disease_scope import DiseaseScope, is_kb_uncovered

_REF_PAGE_RE = re.compile(
    r"SUGGESTED TREATMENT REGIMENS REFERENCES|REFERENCES\s*$|参考文献",
    re.I,
)


def is_reference_list_page(hit: RetrievalHit) -> bool:
    doc = hit.document
    text = (doc.text or "")[:800]
    page = str(doc.printed_page_code or "")
    if _REF_PAGE_RE.search(text):
        return True
    if re.search(r"\bREFERENCES\b", page, re.I):
        return True
    return False


def penalize_reference_pages(
    hits: Sequence[RetrievalHit],
    *,
    factor: float = 0.15,
) -> List[RetrievalHit]:
    out = list(hits)
    for hit in out:
        if is_reference_list_page(hit):
            hit.details["reference_page_penalty"] = factor
            hit.score = float(hit.score) * factor
    out.sort(reverse=True, key=lambda item: item.score)
    for rank, hit in enumerate(out, start=1):
        hit.rank = rank
    return out


def apply_gate_min_keep(
    pre_gate: Sequence[RetrievalHit],
    kept: Sequence[RetrievalHit],
    min_keep: int,
) -> List[RetrievalHit]:
    if min_keep <= 0 or len(kept) >= min_keep:
        return list(kept)
    kept_ids = {id(h) for h in kept}
    extras = [h for h in pre_gate if id(h) not in kept_ids]
    extras.sort(reverse=True, key=lambda item: item.score)
    merged = list(kept) + extras[: max(0, min_keep - len(kept))]
    for rank, hit in enumerate(merged, start=1):
        hit.rank = rank
    return merged


def max_relevance_score(hits: Sequence[RetrievalHit]) -> float:
    scores = []
    for hit in hits:
        raw = hit.details.get("rerank_score")
        if raw is None:
            raw = hit.score
        try:
            scores.append(float(raw))
        except (TypeError, ValueError):
            continue
    return max(scores) if scores else 0.0


def parametric_fallback_reason(
    *,
    allow_labeled: bool,
    disease_scope: DiseaseScope,
    hits: Sequence[RetrievalHit],
    threshold: float,
) -> Optional[str]:
    if not allow_labeled:
        return None
    if is_kb_uncovered(disease_scope):
        return f"kb_uncovered:{disease_scope.key}"
    if threshold > 0:
        score = max_relevance_score(hits)
        if not hits or score < threshold:
            return f"relevance_gate:{score:.3f}<{threshold:.3f}"
    return None
