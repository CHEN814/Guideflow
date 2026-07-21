"""Filter retrieval hits / refs to those actually cited in the answer."""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Sequence, Tuple

from backend.app.models import FigureReference, ReferenceEntry, RetrievalHit
from backend.app.services.figure_selection import extract_cited_source_indices

_SN_RE = re.compile(r"\[S(\d+)\]", re.IGNORECASE)


def filter_cited_hits(
    answer: str,
    hits: Sequence[RetrievalHit],
    figures: Sequence[FigureReference],
) -> Tuple[str, List[RetrievalHit], List[FigureReference], Dict[int, int]]:
    """Keep only hits cited via [Sn], renumber citations, remap figure indices.

    If the answer contains no valid [Sn] citations, keep all hits unchanged
    (fallback so References is never empty for guideline answers that forgot
    to cite).
    """
    hit_list = list(hits)
    if not hit_list:
        return answer, [], list(figures), {}

    cited = {
        idx
        for idx in extract_cited_source_indices(answer)
        if 1 <= idx <= len(hit_list)
    }
    if not cited:
        return answer, hit_list, list(figures), {}

    kept_old = sorted(cited)
    remap: Dict[int, int] = {old: new for new, old in enumerate(kept_old, start=1)}
    kept_hits = [hit_list[old - 1] for old in kept_old]

    def _replace(match: re.Match) -> str:
        old = int(match.group(1))
        new = remap.get(old)
        if new is None:
            return ""
        return f"[S{new}]"

    new_answer = _SN_RE.sub(_replace, answer)
    # Collapse accidental double spaces left by removed markers.
    new_answer = re.sub(r"[ \t]{2,}", " ", new_answer)
    new_answer = re.sub(r" +([,.;:!?])", r"\1", new_answer)

    remapped_figures: List[FigureReference] = []
    for fig in figures:
        new_idx: Optional[int] = None
        if fig.source_index is not None:
            new_idx = remap.get(fig.source_index)
        remapped_figures.append(
            FigureReference(
                page_code=fig.page_code,
                pdf_page=fig.pdf_page,
                image_path=fig.image_path,
                caption=fig.caption,
                source_index=new_idx,
                crop_image_path=fig.crop_image_path,
                crop_full_image_path=fig.crop_full_image_path,
                anchor_paragraph=fig.anchor_paragraph,
                anchor_key=fig.anchor_key,
                crop_method=fig.crop_method,
                bbox_quality=fig.bbox_quality,
            )
        )
    return new_answer, kept_hits, remapped_figures, remap


def filter_attached_references(
    hits: Sequence[RetrievalHit],
    attached_references: Sequence[ReferenceEntry],
    reference_links: Dict[str, List[str]],
    answer: Optional[str] = None,
) -> Tuple[List[ReferenceEntry], Dict[str, List[str]]]:
    """Keep attached refs only when their discussion source is cited as evidence.

    A reference may surface only when its discussion chunk was retained *and* the
    body actually cites evidence via ``[Sn]``. If the answer carries no ``[Sn]``
    marker at all, no discussion sentence was listed as evidence, so no reference
    is shown.
    """
    if answer is not None and not _SN_RE.search(answer):
        return [], {}
    kept_ids = {hit.document.source_id for hit in hits}
    filtered_links: Dict[str, List[str]] = {
        sid: nums
        for sid, nums in (reference_links or {}).items()
        if sid in kept_ids and nums
    }
    allowed_numbers = {str(n) for nums in filtered_links.values() for n in nums}
    if not allowed_numbers:
        return [], filtered_links

    # Preserve original order of attached_references.
    filtered_refs = [
        entry
        for entry in attached_references
        if str(entry.ref_number) in allowed_numbers
    ]
    return filtered_refs, filtered_links
