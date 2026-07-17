"""Figure selection helpers: lexical overlap, answer-driven pruning."""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Sequence, Set, Tuple

from backend.app.models import FigureReference, RetrievalHit

_SN_RE = re.compile(r"\[S(\d+)\]", re.IGNORECASE)
_PAGE_CODE_RE = re.compile(
    r"\b([A-Z]+-[A-Z0-9]+(?:\s+\d+\s+OF\s+\d+)?)\b",
    re.IGNORECASE,
)
_TOKEN_RE = re.compile(r"[a-zA-Z0-9]+|[\u4e00-\u9fff]+")


def tokenize(text: str) -> Set[str]:
    return {m.group(0).lower() for m in _TOKEN_RE.finditer(text or "")}


def lexical_overlap(query: str, *texts: str) -> float:
    """Fraction of query tokens found in the combined corpus texts."""
    q_tokens = tokenize(query)
    if not q_tokens:
        return 0.0
    corpus: Set[str] = set()
    for text in texts:
        corpus |= tokenize(text)
    if not corpus:
        return 0.0
    return len(q_tokens & corpus) / len(q_tokens)


def extract_cited_source_indices(answer: str) -> Set[int]:
    return {int(m) for m in _SN_RE.findall(answer)}


def extract_cited_page_codes(answer: str) -> Set[str]:
    codes: Set[str] = set()
    for match in _PAGE_CODE_RE.findall(answer):
        codes.add(normalize_page_code(match))
    return codes


def normalize_page_code(page_code: Optional[str]) -> str:
    if not page_code:
        return ""
    return " ".join(str(page_code).upper().split())


def _evidence_page_codes(hits: Sequence[RetrievalHit]) -> Set[str]:
    codes: Set[str] = set()
    for hit in hits:
        code = normalize_page_code(hit.document.printed_page_code)
        if code:
            codes.add(code)
    return codes


def _classify_figure_match(
    fig: FigureReference,
    cited_indices: Set[int],
    cited_pages: Set[str],
    evidence_pages: Set[str],
    hit_by_index: Dict[int, RetrievalHit],
) -> Optional[str]:
    """Return 'primary', 'secondary', or None."""
    fig_code = normalize_page_code(fig.page_code)
    if fig.source_index is not None and fig.source_index in cited_indices:
        return "primary"
    if fig_code and fig_code in cited_pages:
        if fig_code in evidence_pages:
            return "primary"
        return "secondary"
    if fig.source_index is not None:
        hit = hit_by_index.get(fig.source_index)
        if hit:
            hit_code = normalize_page_code(hit.document.printed_page_code)
            if hit_code and hit_code in cited_pages:
                return "primary"
    return None


def _fallback_figure(
    figures: Sequence[FigureReference],
    hits: Sequence[RetrievalHit],
    cited_indices: Set[int],
    seed_page_code: Optional[str],
) -> List[FigureReference]:
    """Prefer cited-hit figure, then seed, then first figure."""
    hit_by_index = {idx: hit for idx, hit in enumerate(hits, start=1)}
    for idx in sorted(cited_indices):
        hit = hit_by_index.get(idx)
        if not hit:
            continue
        hit_code = normalize_page_code(hit.document.printed_page_code)
        for fig in figures:
            if fig.source_index == idx:
                return [fig]
            if hit_code and normalize_page_code(fig.page_code) == hit_code:
                return [fig]
            if fig.pdf_page == hit.document.pdf_page:
                return [fig]

    seed_norm = normalize_page_code(seed_page_code)
    if seed_norm:
        for fig in figures:
            if normalize_page_code(fig.page_code) == seed_norm:
                return [fig]

    return [figures[0]]


def prune_figures_by_answer(
    answer: str,
    figures: Sequence[FigureReference],
    hits: Sequence[RetrievalHit],
    seed_page_code: Optional[str] = None,
    display_max: int = 2,
) -> List[FigureReference]:
    """Keep figures cited via [Sn] or page code, with primary/secondary tiers."""
    if not figures:
        return []

    cited_indices = extract_cited_source_indices(answer)
    cited_pages = extract_cited_page_codes(answer)
    evidence_pages = _evidence_page_codes(hits)
    hit_by_index = {idx: hit for idx, hit in enumerate(hits, start=1)}

    primary: List[FigureReference] = []
    secondary: List[FigureReference] = []
    for fig in figures:
        tier = _classify_figure_match(
            fig, cited_indices, cited_pages, evidence_pages, hit_by_index
        )
        if tier == "primary":
            primary.append(fig)
        elif tier == "secondary":
            secondary.append(fig)

    if not primary and not secondary:
        kept = _fallback_figure(figures, hits, cited_indices, seed_page_code)
    else:
        kept = list(primary)
        for fig in secondary:
            if len(kept) >= display_max:
                break
            kept.append(fig)

    # Keep the intent seed decision page when display budget allows more than one.
    seed_norm = normalize_page_code(seed_page_code)
    if seed_norm and display_max > 1 and len(kept) < display_max:
        already = {normalize_page_code(f.page_code) for f in kept}
        if seed_norm not in already:
            for fig in figures:
                if normalize_page_code(fig.page_code) == seed_norm:
                    kept.append(fig)
                    break

    if len(kept) > display_max:
        kept = kept[:display_max]
    return kept


def backfill_source_indices(
    figures: Sequence[FigureReference],
    hits: Sequence[RetrievalHit],
) -> List[FigureReference]:
    """Match figures to retrieval hits by page code or pdf_page."""
    hit_by_code: Dict[str, int] = {}
    hit_by_pdf: Dict[int, int] = {}
    for idx, hit in enumerate(hits, start=1):
        code = normalize_page_code(hit.document.printed_page_code)
        if code:
            hit_by_code[code] = idx
        if hit.document.pdf_page:
            hit_by_pdf[hit.document.pdf_page] = idx

    updated: List[FigureReference] = []
    for fig in figures:
        source_index = fig.source_index
        if source_index is None:
            code = normalize_page_code(fig.page_code)
            if code and code in hit_by_code:
                source_index = hit_by_code[code]
            elif fig.pdf_page in hit_by_pdf:
                source_index = hit_by_pdf[fig.pdf_page]
        updated.append(
            FigureReference(
                page_code=fig.page_code,
                pdf_page=fig.pdf_page,
                image_path=fig.image_path,
                caption=fig.caption,
                source_index=source_index,
                crop_image_path=fig.crop_image_path,
                anchor_paragraph=fig.anchor_paragraph,
                anchor_key=fig.anchor_key,
                crop_method=fig.crop_method,
                bbox_quality=fig.bbox_quality,
            )
        )
    return updated
