from __future__ import annotations

import re

SOURCE_SECTION_RE = re.compile(
    r"\n(?:来源|参考文献|引用来源)\s*[:：].*$",
    re.IGNORECASE | re.DOTALL,
)
INTERNAL_ID_RE = re.compile(
    r"\b(?:ref|disc|page)-[a-z0-9_-]+\b",
    re.IGNORECASE,
)
CITATION_SPACE_RE = re.compile(r"\[S\s+(\d+)\]")


def format_answer(answer: str) -> str:
    """Normalize model output without changing medical content."""
    cleaned = answer.strip()
    cleaned = SOURCE_SECTION_RE.sub("", cleaned).strip()
    cleaned = INTERNAL_ID_RE.sub("", cleaned)
    cleaned = CITATION_SPACE_RE.sub(r"[S\1]", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()
