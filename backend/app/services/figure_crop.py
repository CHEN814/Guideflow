"""Flowchart region detection and bbox helpers for cropped display images."""
from __future__ import annotations

from typing import List, Optional, Tuple

try:
    import fitz  # PyMuPDF
except ImportError:  # pragma: no cover
    fitz = None

_CHROME_HEADER_RATIO = 0.08
_CHROME_FOOTER_RATIO = 0.08
_NAV_KEYWORDS = frozenset(
    {
        "TABLE OF CONTENTS",
        "DISCUSSION",
        "INDEX",
        "NOTE: ALL RECOMMENDATIONS",
    }
)
_FLOWCHART_HEAD_RATIO = 0.12
_FLOWCHART_FOOT_RATIO = 0.91
_FLOWCHART_VEC_MARGIN = 0.03
_FLOWCHART_MIN_TEXT_AREA = 0.003
_CLUSTER_TOLERANCE = 10


def normalize_page_code(page_code: Optional[str]) -> Optional[str]:
    if not page_code:
        return None
    return " ".join(page_code.upper().split())


def validate_bbox(bbox: Optional[List[float]]) -> Optional[List[float]]:
    if not bbox or len(bbox) != 4:
        return None
    try:
        x0, y0, x1, y1 = [float(v) for v in bbox]
    except (TypeError, ValueError):
        return None
    if not all(0.0 <= v <= 1.0 for v in (x0, y0, x1, y1)):
        return None
    if x1 <= x0 or y1 <= y0:
        return None
    return [x0, y0, x1, y1]


def _normalize_rect(rect: "fitz.Rect", page_rect: "fitz.Rect") -> List[float]:
    return [
        max(0.0, min(1.0, (rect.x0 - page_rect.x0) / page_rect.width)),
        max(0.0, min(1.0, (rect.y0 - page_rect.y0) / page_rect.height)),
        max(0.0, min(1.0, (rect.x1 - page_rect.x0) / page_rect.width)),
        max(0.0, min(1.0, (rect.y1 - page_rect.y0) / page_rect.height)),
    ]


def _rect_center_y_norm(rect: "fitz.Rect", page_rect: "fitz.Rect") -> float:
    center_y = (rect.y0 + rect.y1) / 2.0
    return (center_y - page_rect.y0) / page_rect.height


def _is_chrome_zone(center_y_norm: float) -> bool:
    return center_y_norm < _CHROME_HEADER_RATIO or center_y_norm > (1.0 - _CHROME_FOOTER_RATIO)


def _union_rects(rects: List["fitz.Rect"]) -> Optional["fitz.Rect"]:
    if not rects:
        return None
    union = fitz.Rect(rects[0])
    for rect in rects[1:]:
        union |= rect
    return union


def detect_table_bbox(page, clip: Optional["fitz.Rect"] = None) -> Optional[List[float]]:
    """Detect table regions using PyMuPDF lines_strict strategy."""
    if fitz is None:
        return None

    page_rect = page.rect
    if page_rect.width <= 0 or page_rect.height <= 0:
        return None

    try:
        finder = page.find_tables(strategy="lines_strict", clip=clip)
    except (RuntimeError, ValueError, TypeError):
        return None

    tables = getattr(finder, "tables", None) or []
    rects: List["fitz.Rect"] = []
    for table in tables:
        bbox = getattr(table, "bbox", None)
        if bbox and len(bbox) == 4:
            rects.append(fitz.Rect(bbox))

    union = _union_rects(rects)
    if union is None:
        return None
    return validate_bbox(_normalize_rect(union, page_rect))


def detect_figure_bbox(page, min_area_ratio: float = 0.05) -> Optional[List[float]]:
    """Detect flowchart/vector regions: union first, then exclude chrome."""
    if fitz is None:
        return None

    page_rect = page.rect
    page_area = page_rect.width * page_rect.height
    if page_area <= 0:
        return None

    candidates: List["fitz.Rect"] = []

    for drawing in page.get_drawings():
        rect = drawing.get("rect")
        if rect is not None:
            candidates.append(fitz.Rect(rect))

    try:
        blocks = page.get_text("dict", flags=fitz.TEXTFLAGS_TEXT).get("blocks", [])
    except (RuntimeError, ValueError):
        blocks = []
    for block in blocks:
        if block.get("type") != 1:
            continue
        bbox = block.get("bbox")
        if bbox and len(bbox) == 4:
            candidates.append(fitz.Rect(bbox))

    if not candidates:
        return _fallback_content_bbox(page_rect)

    union = _union_rects(candidates)
    if union is None:
        return _fallback_content_bbox(page_rect)

    union_norm = validate_bbox(_normalize_rect(union, page_rect))
    if union_norm is None:
        return _fallback_content_bbox(page_rect)

    area_ratio = (union.width * union.height) / page_area
    if area_ratio > 0.95:
        clipped = fitz.Rect(
            page_rect.x0 + page_rect.width * 0.05,
            page_rect.y0 + page_rect.height * _CHROME_HEADER_RATIO,
            page_rect.x1 - page_rect.width * 0.05,
            page_rect.y1 - page_rect.height * _CHROME_FOOTER_RATIO,
        )
        return validate_bbox(_normalize_rect(clipped, page_rect))

    non_chrome = [
        rect
        for rect in candidates
        if not _is_chrome_zone(_rect_center_y_norm(rect, page_rect))
    ]
    if non_chrome:
        union = _union_rects(non_chrome)
        if union is not None:
            union_norm = validate_bbox(_normalize_rect(union, page_rect))
            if union_norm is not None:
                area_ratio = (union.width * union.height) / page_area
                if area_ratio >= min_area_ratio:
                    return union_norm

    if area_ratio >= min_area_ratio:
        return union_norm
    return _fallback_content_bbox(page_rect)


def detect_text_block_bbox(page, min_area_ratio: float = 0.08) -> Optional[List[float]]:
    """Union large text blocks excluding header/footer/navigation chrome."""
    if fitz is None:
        return None

    page_rect = page.rect
    page_area = page_rect.width * page_rect.height
    if page_area <= 0:
        return None

    try:
        blocks = page.get_text("dict", flags=fitz.TEXTFLAGS_TEXT).get("blocks", [])
    except (RuntimeError, ValueError):
        return None

    rects: List["fitz.Rect"] = []
    for block in blocks:
        if block.get("type") != 0:
            continue
        bbox = block.get("bbox")
        if not bbox or len(bbox) != 4:
            continue
        rect = fitz.Rect(bbox)
        if _is_chrome_zone(_rect_center_y_norm(rect, page_rect)):
            continue
        text_parts: List[str] = []
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text_parts.append(str(span.get("text", "")))
        text = " ".join(text_parts).strip().upper()
        if any(keyword in text for keyword in _NAV_KEYWORDS):
            continue
        area_ratio = (rect.width * rect.height) / page_area
        if area_ratio >= min_area_ratio:
            rects.append(rect)

    union = _union_rects(rects)
    if union is None:
        return None
    return validate_bbox(_normalize_rect(union, page_rect))


def _is_flowchart_chrome(center_y_norm: float, head: float, foot: float) -> bool:
    return center_y_norm < head or center_y_norm > foot


def detect_flowchart_bboxes(
    page,
    min_area_ratio: float = _FLOWCHART_MIN_TEXT_AREA,
    head: float = _FLOWCHART_HEAD_RATIO,
    foot: float = _FLOWCHART_FOOT_RATIO,
    margin: float = _FLOWCHART_VEC_MARGIN,
) -> Tuple[Optional[List[float]], Optional[List[float]], bool]:
    """Detect compact (flowchart body) and full (with footnotes) bboxes via cluster_drawings."""
    if fitz is None:
        return None, None, False

    page_rect = page.rect
    page_area = page_rect.width * page_rect.height
    if page_area <= 0:
        return None, None, False

    min_area = max(min_area_ratio, _FLOWCHART_MIN_TEXT_AREA)

    vectors: List["fitz.Rect"] = []
    try:
        clusters = page.cluster_drawings(
            x_tolerance=_CLUSTER_TOLERANCE,
            y_tolerance=_CLUSTER_TOLERANCE,
        )
    except (AttributeError, RuntimeError, TypeError):
        clusters = []

    for cluster in clusters:
        cy = _rect_center_y_norm(cluster, page_rect)
        if _is_flowchart_chrome(cy, head, foot):
            continue
        vectors.append(fitz.Rect(cluster))

    texts: List["fitz.Rect"] = []
    try:
        blocks = page.get_text("dict", flags=fitz.TEXTFLAGS_TEXT).get("blocks", [])
    except (RuntimeError, ValueError):
        blocks = []

    for block in blocks:
        if block.get("type") != 0:
            continue
        bbox = block.get("bbox")
        if not bbox or len(bbox) != 4:
            continue
        rect = fitz.Rect(bbox)
        cy = _rect_center_y_norm(rect, page_rect)
        if _is_flowchart_chrome(cy, head, foot):
            continue
        area_ratio = (rect.width * rect.height) / page_area
        if area_ratio < min_area:
            continue
        texts.append(rect)

    if not vectors and not texts:
        return None, None, False

    if vectors:
        vec_bottom = max(rect.y1 for rect in vectors)
        threshold = vec_bottom + margin * page_rect.height
        body_text = [rect for rect in texts if rect.y0 <= threshold]
        foot_text = [rect for rect in texts if rect.y0 > threshold]
        compact_union = _union_rects(vectors + body_text)
        full_union = _union_rects(vectors + texts)
        has_footnote = len(foot_text) > 0
    else:
        compact_union = full_union = _union_rects(texts)
        has_footnote = False

    compact = (
        validate_bbox(_normalize_rect(compact_union, page_rect))
        if compact_union is not None
        else None
    )
    full = (
        validate_bbox(_normalize_rect(full_union, page_rect))
        if full_union is not None
        else None
    )
    return compact, full, has_footnote


def detect_display_bboxes(
    page,
    min_area_ratio: float = 0.05,
) -> Tuple[Optional[List[float]], Optional[List[float]], Optional[str], bool]:
    """Display-oriented detection: table (single) -> flowchart (compact/full) -> text."""
    table_bbox = detect_table_bbox(page)
    if table_bbox:
        return table_bbox, table_bbox, "table", False

    compact, full, has_footnote = detect_flowchart_bboxes(
        page,
        min_area_ratio=min(min_area_ratio, _FLOWCHART_MIN_TEXT_AREA),
    )
    if compact:
        return compact, full or compact, "flowchart", has_footnote

    text_bbox = detect_text_block_bbox(page, min_area_ratio=max(min_area_ratio, 0.08))
    if text_bbox:
        return text_bbox, text_bbox, "text", False

    return None, None, None, False


def detect_display_bboxes_for_page(
    page_renderer,
    pdf_page: int,
    min_area_ratio: float = 0.05,
) -> Tuple[Optional[List[float]], Optional[List[float]], Optional[str], bool]:
    page = page_renderer.get_page(pdf_page)
    if page is None:
        return None, None, None, False
    return detect_display_bboxes(page, min_area_ratio=min_area_ratio)


def _fallback_content_bbox(page_rect: "fitz.Rect") -> Optional[List[float]]:
    margin_x = page_rect.width * 0.05
    margin_y = page_rect.height * 0.12
    fallback = fitz.Rect(
        page_rect.x0 + margin_x,
        page_rect.y0 + margin_y,
        page_rect.x1 - margin_x,
        page_rect.y1 - margin_y,
    )
    return validate_bbox(_normalize_rect(fallback, page_rect))


def detect_region_bbox(
    page,
    min_area_ratio: float = 0.05,
) -> Tuple[Optional[List[float]], Optional[str]]:
    """Deterministic region detection: table -> figure -> text."""
    table_bbox = detect_table_bbox(page)
    if table_bbox:
        return table_bbox, "table"

    figure_bbox = detect_figure_bbox(page, min_area_ratio=min_area_ratio)
    if figure_bbox:
        return figure_bbox, "figure"

    text_bbox = detect_text_block_bbox(page, min_area_ratio=max(min_area_ratio, 0.08))
    if text_bbox:
        return text_bbox, "text"

    return None, None


def detect_region_bbox_for_page(
    page_renderer,
    pdf_page: int,
    min_area_ratio: float = 0.05,
) -> Tuple[Optional[List[float]], Optional[str]]:
    page = page_renderer.get_page(pdf_page)
    if page is None:
        return None, None
    return detect_region_bbox(page, min_area_ratio=min_area_ratio)


def detect_figure_bbox_for_page(
    page_renderer,
    pdf_page: int,
    min_area_ratio: float = 0.05,
) -> Optional[List[float]]:
    """Legacy figure-only detect (kept for trace comparison)."""
    page = page_renderer.get_page(pdf_page)
    if page is None:
        return None
    return detect_figure_bbox(page, min_area_ratio=min_area_ratio)


def lookup_vlm_bbox(
    page_code: Optional[str],
    page_bboxes: dict[str, List[float]],
) -> Optional[List[float]]:
    code = normalize_page_code(page_code)
    if not code:
        return None
    if code in page_bboxes:
        return validate_bbox(page_bboxes[code])
    for key, bbox in page_bboxes.items():
        if normalize_page_code(key) == code:
            return validate_bbox(bbox)
    return None


def bbox_area_ratio(bbox: List[float]) -> float:
    x0, y0, x1, y1 = bbox
    return max(0.0, (x1 - x0) * (y1 - y0))


def bbox_width(bbox: List[float]) -> float:
    return max(0.0, bbox[2] - bbox[0])


def is_full_page_like(bbox: List[float], max_area: float = 0.8) -> bool:
    return bbox_area_ratio(bbox) >= max_area


def _bbox_key(bbox: List[float], precision: int = 3) -> tuple[float, ...]:
    return tuple(round(v, precision) for v in bbox)


def assess_vlm_bbox_quality(
    bbox: Optional[List[float]],
    all_bboxes: dict[str, List[float]],
    max_area: float = 0.8,
    dedup_guard: bool = True,
    deterministic_bbox: Optional[List[float]] = None,
    narrow_width_threshold: float = 0.1,
) -> str:
    """Return good | full_page_like | duplicated | too_narrow | missing."""
    if not bbox:
        return "missing"
    if is_full_page_like(bbox, max_area=max_area):
        return "full_page_like"
    if dedup_guard and len(all_bboxes) > 1:
        unique = {_bbox_key(b) for b in all_bboxes.values() if validate_bbox(b)}
        if len(unique) == 1 and is_full_page_like(bbox, max_area=0.5):
            return "duplicated"
    if deterministic_bbox:
        det_w = bbox_width(deterministic_bbox)
        vlm_w = bbox_width(bbox)
        if det_w > 0 and (det_w - vlm_w) / det_w > narrow_width_threshold:
            return "too_narrow"
    return "good"
