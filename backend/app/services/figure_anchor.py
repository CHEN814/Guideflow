"""Paragraph-boundary anchoring for inline figure placement."""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Sequence

from backend.app.models import FigureReference, RetrievalHit
from backend.app.services.figure_selection import normalize_page_code

_SN_RE = re.compile(r"\[S(\d+)\]", re.IGNORECASE)
_PAGE_CODE_RE = re.compile(
    r"\b([A-Z]+-[A-Z0-9]+(?:\s+\d+\s+OF\s+\d+)?)\b",
    re.IGNORECASE,
)


def split_answer_paragraphs(answer: str) -> List[str]:
    """Split markdown answer into paragraph blocks (blank-line separated)."""
    if not answer.strip():
        return []
    blocks: List[str] = []
    current: List[str] = []
    for line in answer.split("\n"):
        if line.strip() == "" and current:
            blocks.append("\n".join(current).strip())
            current = []
        else:
            current.append(line)
    if current:
        blocks.append("\n".join(current).strip())
    return blocks


def _paragraph_mentions_figure(
    paragraph: str,
    fig: FigureReference,
    hit_by_index: Dict[int, RetrievalHit],
) -> Optional[str]:
    if fig.source_index is not None:
        marker = f"[S{fig.source_index}]"
        if marker.lower() in paragraph.lower():
            return f"S{fig.source_index}"

    fig_code = normalize_page_code(fig.page_code)
    if fig_code and fig_code in paragraph.upper():
        return fig_code

    if fig.source_index is not None:
        hit = hit_by_index.get(fig.source_index)
        if hit and hit.document.printed_page_code:
            hit_code = normalize_page_code(hit.document.printed_page_code)
            if hit_code and hit_code in paragraph.upper():
                return hit_code

    for match in _PAGE_CODE_RE.findall(paragraph):
        code = normalize_page_code(match)
        if fig_code and code == fig_code:
            return fig_code
    return None


def compute_anchors(
    answer: str,
    figures: Sequence[FigureReference],
    hits: Sequence[RetrievalHit],
) -> List[FigureReference]:
    """Assign anchor_paragraph / anchor_key for each figure."""
    paragraphs = split_answer_paragraphs(answer)
    hit_by_index = {idx: hit for idx, hit in enumerate(hits, start=1)}
    anchored: List[FigureReference] = []

    for fig in figures:
        anchor_paragraph: Optional[int] = None
        anchor_key: Optional[str] = None
        for idx, paragraph in enumerate(paragraphs):
            key = _paragraph_mentions_figure(paragraph, fig, hit_by_index)
            if key:
                anchor_paragraph = idx
                anchor_key = key
                break
        anchored.append(
            FigureReference(
                page_code=fig.page_code,
                pdf_page=fig.pdf_page,
                image_path=fig.image_path,
                caption=fig.caption,
                source_index=fig.source_index,
                crop_image_path=fig.crop_image_path,
                anchor_paragraph=anchor_paragraph,
                anchor_key=anchor_key,
                crop_method=fig.crop_method,
                bbox_quality=fig.bbox_quality,
            )
        )
    return anchored
