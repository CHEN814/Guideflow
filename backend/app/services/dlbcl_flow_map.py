"""DLBCL-specific hardcoded flow entry points for the NCCN BCEL module.

This branch prioritises accuracy for NCCN DLBCL over multi-disease generalisation.
Intent → entry decision page mapping is deterministic lookup, not BM25 guesswork.
"""
from __future__ import annotations

import re
from typing import List, Optional, Sequence

from backend.app.models import RetrievalHit

# BCEL-1..9 are decision flowchart pages; BCEL-A/B/C are tables/regimens.
DECISION_PAGE_RE = re.compile(r"^[A-Z]+-\d+$", re.IGNORECASE)

# (keywords, entry page). Earlier rules win when multiple match.
INTENT_RULES: List[tuple[tuple[str, ...], str]] = [
    (
        ("复发", "难治", "relapse", "refractory", "复发/难治", "复发难治"),
        "BCEL-7",
    ),
    (
        ("随访", "follow-up", "follow up", "surveillance", "followup"),
        "BCEL-9",
    ),
    (
        (
            "再分期",
            "restaging",
            "interim restaging",
            "interim",
            "追加治疗",
            "end-of-treatment",
            "end of treatment",
        ),
        "BCEL-4",
    ),
    (
        (
            "检查",
            "workup",
            "评估",
            "诊断",
            "essential",
            "体格",
            "work-up",
            "要做什么",
        ),
        "BCEL-2",
    ),
    (
        (
            "一线",
            "first-line",
            "first line",
            "initial therapy",
            "first line therapy",
            "一线治疗",
        ),
        "BCEL-3",
    ),
    (
        ("分子", "基因", "genomic", "mutation", "分型", "myc", "bcl2"),
        "BCEL-1",
    ),
]


def normalize_page_code(page_code: Optional[str]) -> Optional[str]:
    if not page_code:
        return None
    return " ".join(page_code.split()).upper()


def is_decision_flow_page(page_code: Optional[str]) -> bool:
    """True for numeric BCEL decision pages (BCEL-3), not regimen tables (BCEL-C)."""
    normalized = normalize_page_code(page_code)
    if not normalized or " OF " in normalized:
        return False
    return bool(DECISION_PAGE_RE.match(normalized))


def resolve_entry_page(query: str, entities: Optional[Sequence[str]] = None) -> Optional[str]:
    """Map query intent to a hardcoded BCEL entry decision page, or None."""
    parts = [query.lower()]
    if entities:
        parts.extend(str(e).lower() for e in entities)
    text = " ".join(parts)
    for keywords, page_code in INTENT_RULES:
        if any(kw.lower() in text for kw in keywords):
            return page_code
    return None


def pick_highest_decision_page_from_hits(hits: Sequence[RetrievalHit]) -> Optional[str]:
    """Fallback seed: highest-ranked retrieval hit that is a numeric decision page."""
    for hit in hits:
        doc = hit.document
        if doc.page_type != "clinical_guideline":
            continue
        code = doc.printed_page_code
        if is_decision_flow_page(code):
            return normalize_page_code(code)
    return None


def pick_seed_page_code(
    query: str,
    hits: Sequence[RetrievalHit],
    entities: Optional[Sequence[str]] = None,
) -> tuple[Optional[str], str]:
    """Return (seed_page_code, source) where source is intent_map or hit_fallback."""
    intent_page = resolve_entry_page(query, entities)
    if intent_page:
        return intent_page, "intent_map"
    fallback = pick_highest_decision_page_from_hits(hits)
    if fallback:
        return fallback, "hit_fallback"
    return None, "none"
