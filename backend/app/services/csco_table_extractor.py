"""CSCO PDF table extraction → Markdown (no VLM).

Uses PyMuPDF ``find_tables(strategy="text")`` as the primary extractor, with
x-coordinate clustering as a fallback. Cross-row cells (leading empty first
column) are merged into the previous row.

Single-column regimen glossaries (e.g. 「二线治疗方案」lists) often have a
centered title and right-margin running headers; word-grid clustering can invent
empty columns — those are normalized back into ``方案 | 组成`` tables.
"""
from __future__ import annotations

import re
from typing import List, Optional, Sequence, Tuple

try:
    import fitz  # PyMuPDF
except ImportError:  # pragma: no cover
    fitz = None


_HEADER_HINT = re.compile(
    r"(分期|分组|分层|推荐|评估|诊断|治疗|I\s*级|Ⅱ\s*级|Ⅲ\s*级|II\s*级|III\s*级)",
    re.I,
)

# One regimen line: "[R-DHAP]利妥昔单抗+顺铂+…" or "[R-CHOP] 利妥昔…"
_REGIMEN_LINE_RE = re.compile(r"^\[([^\]]+)\]\s*(.+)$")
# Right-margin / footer chrome (page number, vertical disease running header).
_PAGE_NUM_RE = re.compile(r"^\d{1,3}$")
_MARGIN_LABEL_RE = re.compile(
    r"^(?:弥漫大B细胞淋巴瘤|滤泡性淋巴瘤|套细胞淋巴瘤|霍奇金淋巴瘤|"
    r"外周T细胞淋巴瘤|结外NK/?T细胞淋巴瘤|伯基特淋巴瘤|"
    r"原发.*淋巴瘤|淋巴瘤)\s*\d*$"
)

# A grid that is really a chapter's reference list (Vancouver citations) rather
# than a clinical table. These leak into the index and pollute BM25 with English.
_REF_AUTHOR_RE = re.compile(r"[A-Z]{2,},?\s+[A-Z]\b")
_REF_YEAR_RE = re.compile(r"(?:19|20)\d{2}")
_REF_MARK_RE = re.compile(r"\[\d{1,3}\]")


def _looks_like_reference_grid(grid: Sequence[Sequence[str]]) -> bool:
    text = " ".join(_cell_text(c) for row in grid for c in row)
    if not text:
        return False
    signals = 0
    if re.search(r"参考文献|et\s+al", text, re.I):
        signals += 1
    if len(_REF_YEAR_RE.findall(text)) >= 3:
        signals += 1
    if re.search(r"doi|https?://|www\.|PMID", text, re.I):
        signals += 1
    if len(_REF_MARK_RE.findall(text)) >= 3:
        signals += 1
    if len(_REF_AUTHOR_RE.findall(text)) >= 3:
        signals += 1
    return signals >= 2


def _cell_text(value: Optional[str]) -> str:
    if not value:
        return ""
    text = str(value).replace("\n", " ").strip()
    text = re.sub(r"[ \t]+", " ", text)
    # OCR/extraction often turns the Roman numeral "I" (I级推荐) into a pipe.
    text = re.sub(r"^[|丨ｌl](?=\s*级)", "I", text)
    # Range tilde → fullwidth so Markdown never treats it as strikethrough.
    text = re.sub(r"([0-9A-Za-z])\s*~\s*([0-9A-Za-z])", r"\1～\2", text)
    return text


def _is_page_chrome(text: str) -> bool:
    """Page number or vertical running-header disease label (not clinical content)."""
    t = _cell_text(text)
    if not t:
        return False
    if _PAGE_NUM_RE.fullmatch(t):
        return True
    if _MARGIN_LABEL_RE.fullmatch(t):
        return True
    return False


def _strip_trailing_chrome(text: str) -> str:
    """Remove a trailing '弥漫大B细胞淋巴瘤 37' suffix glued onto a cell."""
    t = _cell_text(text)
    if not t:
        return ""
    t = re.sub(
        r"\s*(?:弥漫大B细胞淋巴瘤|滤泡性淋巴瘤|套细胞淋巴瘤|霍奇金淋巴瘤|"
        r"外周T细胞淋巴瘤|结外NK/?T细胞淋巴瘤|伯基特淋巴瘤|"
        r"原发[\u4e00-\u9fffA-Za-z0-9/]{0,20}淋巴瘤|淋巴瘤)\s*\d*\s*$",
        "",
        t,
    )
    t = re.sub(r"\s+\d{1,3}\s*$", "", t) if re.search(r"\]\S", t) else t
    return t.strip()


def _flatten_row(row: Sequence[str]) -> str:
    parts = [_cell_text(c) for c in row if _cell_text(c) and not _is_page_chrome(c)]
    return " ".join(parts).strip()


def _normalize_regimen_glossary(
    rows: List[List[str]],
) -> Tuple[Optional[str], List[List[str]]]:
    """Rebuild single-column ``[NAME]drugs`` lists into ``方案 | 组成`` tables.

    Word-grid fallback often places a centered title in a different column from
    left-aligned regimens and parks the vertical margin label in a third column.
    """
    if not rows:
        return None, rows

    flat: List[str] = []
    for row in rows:
        text = _strip_trailing_chrome(_flatten_row(row))
        if not text or _is_page_chrome(text):
            continue
        flat.append(text)
    if len(flat) < 2:
        return None, rows

    regimen_hits = [t for t in flat if _REGIMEN_LINE_RE.match(t)]
    if len(regimen_hits) < 2:
        return None, rows

    title: Optional[str] = None
    body_start = 0
    if not _REGIMEN_LINE_RE.match(flat[0]) and (
        _HEADER_HINT.search(flat[0]) or "方案" in flat[0]
    ):
        title = flat[0]
        body_start = 1

    body = flat[body_start:]
    if not body:
        return None, rows
    if sum(1 for t in body if _REGIMEN_LINE_RE.match(t)) < max(2, (len(body) + 1) // 2):
        return None, rows

    # Already a clean two-column [NAME] | drugs grid — keep structure, just title.
    already_split = 0
    for row in rows:
        cells = [_cell_text(c) for c in row]
        if (
            len(cells) >= 2
            and re.match(r"^\[[^\]]+\]$", cells[0].replace(" ", ""))
            and cells[1]
            and not cells[1].startswith("[")
        ):
            already_split += 1
    if already_split >= max(2, len(regimen_hits) // 2):
        return title, rows

    out: List[List[str]] = [["方案", "组成"]]
    for t in body:
        m = _REGIMEN_LINE_RE.match(t)
        if m:
            out.append([f"[{m.group(1)}]", m.group(2).strip()])
        elif t and not _is_page_chrome(t):
            out.append([t, ""])
    return title, out


def _drop_empty_columns(rows: List[List[str]]) -> List[List[str]]:
    """Remove columns that are empty in every row."""
    if not rows:
        return rows
    width = max(len(r) for r in rows)
    keep = [
        i
        for i in range(width)
        if any(i < len(r) and _cell_text(r[i]) for r in rows)
    ]
    if len(keep) == width:
        return rows
    return [[(r[i] if i < len(r) else "") for i in keep] for r in rows]


def _merge_continuation_rows(rows: List[List[str]]) -> List[List[str]]:
    """Merge rows whose first column is empty into the previous data row."""
    if not rows:
        return rows
    merged: List[List[str]] = []
    for row in rows:
        cells = list(row)
        if not cells:
            continue
        first = cells[0].strip()
        rest_nonempty = any(c.strip() for c in cells[1:])
        if merged and not first and rest_nonempty:
            prev = merged[-1]
            while len(prev) < len(cells):
                prev.append("")
            for i, cell in enumerate(cells):
                if not cell.strip():
                    continue
                if i >= len(prev):
                    prev.append(cell)
                elif not prev[i].strip():
                    prev[i] = cell
                else:
                    prev[i] = f"{prev[i]} {cell}".strip()
            continue
        merged.append(cells)
    return merged


def _repair_split_bracket_cells(rows: List[List[str]]) -> List[List[str]]:
    """Rejoin regimen names split across columns, e.g. '[R-CHOE' + 'P]…' → '[R-CHOEP]'."""
    repaired: List[List[str]] = []
    for row in rows:
        cells = list(row)
        if len(cells) >= 2:
            left = cells[0].strip()
            right = cells[1].strip()
            # "[R-CHOE" | "P]利妥昔…"  or  "[R-CHOP" | "]利妥昔…"
            if left.startswith("[") and "]" not in left and "]" in right:
                m = re.match(r"^([^\]]*?\])\s*(.*)$", right)
                if m:
                    cells[0] = (left + m.group(1)).replace(" ", "")
                    cells[1] = m.group(2).strip()
            # "R-C" | "HOP方案 …" (notes row without brackets)
            elif (
                re.fullmatch(r"[A-Za-z][A-Za-z0-9+/-]{0,10}", left)
                and re.match(r"^[A-Za-z0-9+/-]+", right)
                and len(left) <= 10
            ):
                m = re.match(r"^([A-Za-z0-9+/-]+)(.*)$", right)
                if m:
                    cells[0] = left + m.group(1)
                    rest = m.group(2).lstrip(" ]").strip()
                    if rest.startswith("方案"):
                        cells[0] = cells[0] + "方案"
                        rest = rest[2:].strip()
                    cells[1] = rest
            # Fix truncated note header
            joined0 = cells[0].strip()
            if joined0 in ("注释】", "注释", "注 释】"):
                cells[0] = "【注释】"
        repaired.append(cells)
    return repaired


def _ensure_regimen_header(rows: List[List[str]]) -> List[List[str]]:
    """If the first data row is already a [NAME]|desc pair, insert a real header."""
    if not rows:
        return rows
    first = " ".join(_cell_text(c) for c in rows[0]).strip()
    if _HEADER_HINT.search(first):
        return rows
    # Already normalized by _normalize_regimen_glossary.
    if re.match(r"^方案(\s+组成)?$", first):
        return rows
    bracketish = sum(
        1 for r in rows if r and _cell_text(r[0]).lstrip().startswith("[")
    )
    if bracketish >= max(2, (len(rows) + 1) // 2):
        width = max(len(r) for r in rows)
        header = ["方案", "组成"] + [""] * max(0, width - 2)
        return [header[:width], *rows]
    return rows


def _looks_like_note_prose_grid(rows: Sequence[Sequence[str]]) -> bool:
    """Reject 【注释】 blocks that find_tables mistook for multi-column tables."""
    if not rows:
        return False
    header = " ".join(_cell_text(c) for c in rows[0]).strip()
    if re.match(r"^【?注释】?$", header):
        return True
    # Dense long prose with almost no short label cells → not a clinical table.
    cells = [_cell_text(c) for row in rows for c in row if _cell_text(c)]
    if not cells:
        return False
    long_cells = sum(1 for c in cells if len(c) >= 40)
    short_cells = sum(1 for c in cells if 0 < len(c) < 20)
    if long_cells >= 4 and long_cells > short_cells * 2 and not _HEADER_HINT.search(header):
        # Allow genuine regimen glossaries (many [NAME] short labels).
        bracket_labels = sum(1 for c in cells if re.match(r"^\[[^\]]+\]$", c.replace(" ", "")))
        if bracket_labels < 2:
            return True
    return False


def _looks_like_table(rows: Sequence[Sequence[str]]) -> bool:
    if len(rows) < 2:
        return False
    nonempty_rows = [r for r in rows if any(_cell_text(c) for c in r)]
    if len(nonempty_rows) < 2:
        return False
    if _looks_like_note_prose_grid(nonempty_rows):
        return False
    header = " ".join(_cell_text(c) for c in nonempty_rows[0])
    if _HEADER_HINT.search(header):
        return True
    # Regimen glossary: several "[NAME]" labels in column 0
    bracket_labels = sum(
        1
        for r in nonempty_rows
        if r and re.match(r"^\[", _cell_text(r[0]))
    )
    if bracket_labels >= 2:
        return True
    # At least 2 columns with content in most rows
    col_count = max(len(r) for r in nonempty_rows)
    if col_count < 2:
        return False
    filled = sum(1 for r in nonempty_rows if sum(1 for c in r if _cell_text(c)) >= 2)
    return filled >= 2


def rows_to_markdown(rows: Sequence[Sequence[str]], *, title: Optional[str] = None) -> str:
    """Serialize a 2D cell grid to a Markdown table."""
    cleaned: List[List[str]] = []
    for row in rows:
        cells = [_cell_text(c) for c in row]
        # Drop a stray reference-header row that abuts the table bottom.
        if "".join(cells).strip() in ("参考文献", "参考文献[1]", "参 考 文 献"):
            continue
        # Drop pure page-chrome rows (running header / page number).
        nonempty = [c for c in cells if c]
        if nonempty and all(_is_page_chrome(c) for c in nonempty):
            continue
        cells = [_strip_trailing_chrome(c) if c else "" for c in cells]
        if any(cells):
            cleaned.append(cells)
    cleaned = _merge_continuation_rows(cleaned)
    cleaned = _repair_split_bracket_cells(cleaned)
    intrinsic_title, cleaned = _normalize_regimen_glossary(cleaned)
    cleaned = _drop_empty_columns(cleaned)
    cleaned = _ensure_regimen_header(cleaned)
    if not cleaned:
        return ""

    width = max(len(r) for r in cleaned)
    normalized = [r + [""] * (width - len(r)) for r in cleaned]
    # Escape pipes inside cells
    normalized = [[c.replace("|", "\\|") for c in r] for r in normalized]

    header = normalized[0]
    body = normalized[1:] if len(normalized) > 1 else []
    lines: List[str] = []
    display_title = title
    if intrinsic_title:
        if title and intrinsic_title not in title:
            display_title = f"{title} · {intrinsic_title}"
        else:
            display_title = intrinsic_title if not title else title
    if display_title:
        lines.append(f"**{display_title}**")
        lines.append("")
    lines.append("| " + " | ".join(header) + " |")
    lines.append("| " + " | ".join("---" for _ in header) + " |")
    for row in body:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines).strip()


def _extract_via_find_tables(page, *, clip=None) -> List[List[List[str]]]:
    tables_out: List[List[List[str]]] = []
    kwargs = {"strategy": "text"}
    if clip is not None:
        kwargs["clip"] = clip
    try:
        finder = page.find_tables(**kwargs)
    except TypeError:
        try:
            finder = page.find_tables(clip=clip) if clip is not None else page.find_tables()
        except Exception:
            return tables_out
    except Exception:
        return tables_out

    for table in getattr(finder, "tables", []) or []:
        try:
            raw = table.extract() or []
        except Exception:
            continue
        rows = [[_cell_text(c) for c in row] for row in raw]
        if _looks_like_table(rows):
            tables_out.append(rows)
    return tables_out


def _cluster_columns(xs: Sequence[float], gap: float = 40.0) -> List[float]:
    if not xs:
        return []
    ordered = sorted(xs)
    clusters: List[List[float]] = [[ordered[0]]]
    for x in ordered[1:]:
        if x - clusters[-1][-1] <= gap:
            clusters[-1].append(x)
        else:
            clusters.append([x])
    return [sum(c) / len(c) for c in clusters]


def _extract_via_word_grid(page, *, y_min: float = 0.0, y_max: Optional[float] = None) -> List[List[List[str]]]:
    """Fallback: cluster words by x into columns, by y into rows."""
    words = page.get_text("words") or []
    if not words:
        return []
    try:
        page_w = float(page.rect.width)
    except Exception:
        page_w = 0.0
    # Right-margin running headers / page numbers sit far right of the content.
    margin_x = page_w * 0.85 if page_w else None

    filtered = []
    for w in words:
        x0, y0, x1, y1, text = w[0], w[1], w[2], w[3], w[4]
        if y_min and y0 < y_min:
            continue
        if y_max is not None and y0 > y_max:
            continue
        raw = str(text).strip()
        if not raw:
            continue
        if margin_x is not None and x0 >= margin_x and _is_page_chrome(raw):
            continue
        filtered.append((x0, y0, x1, y1, raw))
    if len(filtered) < 8:
        return []

    col_centers = _cluster_columns([w[0] for w in filtered], gap=45.0)
    if len(col_centers) < 2:
        # Still allow genuine single-column regimen lists through.
        if sum(1 for _x0, _y0, _x1, _y1, t in filtered if _REGIMEN_LINE_RE.match(t)) >= 2:
            col_centers = [_cluster_columns([w[0] for w in filtered], gap=9999.0)[0]]
        else:
            return []

    # Group into rows by y
    filtered.sort(key=lambda w: (round(w[1] / 8) * 8, w[0]))
    rows_raw: List[List[Tuple[float, str]]] = []
    current_y: Optional[float] = None
    current: List[Tuple[float, str]] = []
    for x0, y0, _x1, _y1, text in filtered:
        if current_y is None or abs(y0 - current_y) <= 8:
            current.append((x0, text))
            current_y = y0 if current_y is None else (current_y + y0) / 2
        else:
            rows_raw.append(current)
            current = [(x0, text)]
            current_y = y0
    if current:
        rows_raw.append(current)

    def assign_col(x: float) -> int:
        best_i, best_d = 0, abs(x - col_centers[0])
        for i, c in enumerate(col_centers[1:], start=1):
            d = abs(x - c)
            if d < best_d:
                best_i, best_d = i, d
        return best_i

    grid: List[List[str]] = []
    for row_words in rows_raw:
        cells = [""] * len(col_centers)
        for x, text in sorted(row_words, key=lambda t: t[0]):
            i = assign_col(x)
            cells[i] = f"{cells[i]} {text}".strip() if cells[i] else text
        if any(cells):
            grid.append(cells)

    if _looks_like_table(grid):
        return [grid]
    return []


def extract_tables_as_markdown(
    page, *, section_hint: Optional[str] = None, y_max: Optional[float] = None
) -> List[str]:
    """Return Markdown strings for tables detected on a page.

    ``y_max`` clips extraction to the region above a y coordinate (used to keep
    a chapter's 参考文献 block out of the extracted tables).
    """
    if fitz is None:
        return []

    clip = None
    if y_max is not None:
        try:
            rect = page.rect
            clip = fitz.Rect(rect.x0, rect.y0, rect.x1, min(y_max, rect.y1))
        except Exception:
            clip = None

    grids = _extract_via_find_tables(page, clip=clip)
    if not grids:
        grids = _extract_via_word_grid(page, y_max=y_max)

    markdowns: List[str] = []
    for grid in grids:
        # Never index a chapter's reference list as a clinical table.
        if _looks_like_reference_grid(grid):
            continue
        if _looks_like_note_prose_grid(grid):
            continue
        # Skip grids that are mostly narrative prose mistaken as tables
        # (find_tables may wrap body text into 4 columns). Keep regimen
        # glossaries whose column-0 cells are "[NAME]" labels.
        header = " ".join(_cell_text(c) for c in grid[0])
        bracket_labels = sum(
            1 for row in grid if row and re.match(r"^\[", _cell_text(row[0]))
        )
        if not _HEADER_HINT.search(header) and bracket_labels < 2:
            short_cells = sum(
                1
                for row in grid
                for c in row
                if 0 < len(_cell_text(c)) < 40
            )
            long_cells = sum(
                1
                for row in grid
                for c in row
                if len(_cell_text(c)) >= 80
            )
            if long_cells > short_cells:
                continue
        md = rows_to_markdown(grid, title=section_hint)
        if md and len(md) > 40:
            markdowns.append(md)
    return markdowns
