"""Display metadata for sources and attached references (Web UI)."""
from __future__ import annotations

import re
from typing import Any, Dict, Optional

from backend.app.models import ReferenceEntry, SearchDocument

_BOILERPLATE_RE = re.compile(
    r"(?:Note:\s*All recommendations are category 2A unless otherwise indicated\.?\s*)"
    r"|(?:Table of Contents\s+Discussion\s*)"
    r"|(?:B-Cell Lymphomas\s*)"
    r"|(?:Diffuse Large B-Cell Lymphoma\s*)",
    re.IGNORECASE,
)
_PAGE_CODE_INLINE_RE = re.compile(
    r"\b([A-Z]+-[A-Z0-9]+(?:\s+\d+\s+OF\s+\d+)?)\b",
    re.IGNORECASE,
)
_AVAILABLE_AT_RE = re.compile(r"\s*Available at:\s*\S+", re.IGNORECASE)
_LEADING_REF_NUM_RE = re.compile(r"^\s*\[?\d{1,3}\]?\.?\s+")
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
_AUTHOR_RE = re.compile(r"^([A-Za-z][A-Za-z'`-]+)")
_WHITESPACE_RE = re.compile(r"\s+")
# Authors end at first sentence period before a capitalized title word.
_CITATION_SPLIT_RE = re.compile(
    r"^(?P<authors>.+?)\.\s+(?P<title>.+?)\.\s+(?P<rest>.+)$"
)
_JOURNAL_YEAR_RE = re.compile(
    r"^(?P<journal>.+?)\s+(?P<year>19|20)\d{2}\b",
    re.IGNORECASE,
)


def _collapse_ws(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", (text or "").replace("\u0000", "")).strip()


def _fix_encoding(text: str) -> str:
    # Common mojibake for en-dash / em-dash when PDF extraction fails.
    return (
        (text or "")
        .replace("\ufffdC", "–")
        .replace("�C", "–")
        .replace("\u2013", "–")
        .replace("\u2014", "—")
    )


def extract_guideline_title(text: str, fallback: str = "") -> str:
    """Heuristic readable subtitle from a clinical guideline page text."""
    cleaned = _fix_encoding(text or "")
    cleaned = _BOILERPLATE_RE.sub(" ", cleaned)
    cleaned = _collapse_ws(cleaned)
    # Drop a leading page-code token if present.
    cleaned = _PAGE_CODE_INLINE_RE.sub(" ", cleaned, count=1)
    cleaned = _collapse_ws(cleaned)
    # Drop leading footnote markers like "a Special Considerations..."
    cleaned = re.sub(r"^(?:[a-z]\s+){1,4}", "", cleaned)
    cleaned = _collapse_ws(cleaned)
    if not cleaned:
        return fallback
    # Prefer an ALL-CAPS heading-like span at the start (NCCN page titles).
    m = re.match(r"^([A-Z][A-Z0-9 ,/\-]{8,80})", cleaned)
    if m:
        return _collapse_ws(m.group(1)).rstrip(" ,/-")
    # Footnote-style leftovers (lowercase start, short) → empty (caller uses page code).
    if cleaned[0].islower() or len(cleaned) < 12:
        return ""
    # Otherwise take the first ~80 chars of meaningful text.
    snippet = cleaned[:100]
    if len(cleaned) > 100:
        cut = max(snippet.rfind(" "), snippet.rfind(","), snippet.rfind(";"))
        if cut > 40:
            snippet = snippet[:cut]
        snippet = snippet.rstrip(" ,;.") + "…"
    return snippet or fallback


def clean_reference_text(text: str) -> str:
    cleaned = _fix_encoding(text or "")
    cleaned = cleaned.replace("\n", " ")
    cleaned = _AVAILABLE_AT_RE.sub("", cleaned)
    cleaned = _LEADING_REF_NUM_RE.sub("", cleaned)
    return _collapse_ws(cleaned)


def extract_year(text: str) -> Optional[str]:
    m = _YEAR_RE.search(text or "")
    return m.group(0) if m else None


def extract_author_year(text: str, year: Optional[str] = None) -> str:
    cleaned = clean_reference_text(text)
    year = year or extract_year(cleaned)
    author_m = _AUTHOR_RE.match(cleaned)
    author = author_m.group(1) if author_m else "et al"
    if year:
        return f"{author} {year}"
    return author


def parse_reference_citation(text: str) -> Dict[str, Optional[str]]:
    """Split a Vancouver-style citation into authors / title / journal / year."""
    cleaned = clean_reference_text(text)
    year = extract_year(cleaned)
    authors: Optional[str] = None
    paper_title: Optional[str] = None
    journal: Optional[str] = None

    m = _CITATION_SPLIT_RE.match(cleaned)
    if m:
        authors = _collapse_ws(m.group("authors"))
        paper_title = _collapse_ws(m.group("title"))
        rest = _collapse_ws(m.group("rest"))
        jm = _JOURNAL_YEAR_RE.match(rest)
        if jm:
            journal = _collapse_ws(jm.group("journal")).rstrip(".,;")
        else:
            # Take text before year or first semicolon/volume marker.
            cut = rest
            if year and year in rest:
                cut = rest.split(year, 1)[0]
            cut = re.split(r"[;:]", cut)[0]
            journal = _collapse_ws(cut).rstrip(".,;") or None
    else:
        # Fallback: first sentence-ish chunk as title.
        paper_title = cleaned[:120] if cleaned else None

    return {
        "authors": authors,
        "paper_title": paper_title,
        "journal": journal,
        "year": year,
    }


def enrich_source_dict(doc: SearchDocument) -> Dict[str, Any]:
    """Attach display fields used by the Web References UI."""
    data = doc.to_dict()
    page_code = doc.printed_page_code or ""
    pdf_page = doc.pdf_page or 0

    if doc.page_type == "clinical_guideline":
        citation_label = page_code or (f"p.{pdf_page}" if pdf_page else doc.source_id)
        # Primary title = page code (OE-style short identifier).
        display_title = citation_label
        subtitle = extract_guideline_title(doc.text, fallback="")
        if subtitle and subtitle.upper() == citation_label.upper():
            subtitle = ""
        source_label = "NCCN B 细胞淋巴瘤指南"
        locator = f"p.{pdf_page}" if pdf_page else ""
        badge = "指南"
    elif doc.page_type == "discussion":
        citation_label = doc.section or "Discussion"
        display_title = doc.section or "Discussion"
        if doc.article_id:
            display_title = f"{doc.article_id.upper()} · {display_title}"
        subtitle = ""
        source_label = "NCCN 指南 · Discussion"
        locator = f"p.{pdf_page}" if pdf_page else ""
        badge = "Discussion"
    else:
        citation_label = page_code or doc.source_id
        display_title = citation_label
        subtitle = ""
        source_label = doc.page_type or "Source"
        locator = f"p.{pdf_page}" if pdf_page else ""
        badge = doc.page_type or "Source"

    data["display_title"] = display_title
    data["subtitle"] = subtitle
    data["source_label"] = source_label
    data["locator"] = locator
    data["citation_label"] = citation_label
    data["badge"] = badge
    return data


def enrich_reference_dict(entry: ReferenceEntry) -> Dict[str, Any]:
    data = entry.to_dict()
    cleaned = clean_reference_text(entry.text)
    parsed = parse_reference_citation(cleaned)
    year = parsed.get("year") or extract_year(cleaned)
    paper_title = parsed.get("paper_title") or cleaned
    authors = parsed.get("authors")
    journal = parsed.get("journal")

    data["display_title"] = paper_title
    data["paper_title"] = paper_title
    data["authors"] = authors
    data["journal"] = journal
    data["year"] = year
    data["author_year"] = extract_author_year(cleaned, year=year)
    data["badge"] = "文献"
    data["subtitle"] = ""

    meta_parts = []
    if journal:
        meta_parts.append(journal)
    if year:
        meta_parts.append(year)
    if authors:
        # Truncate long author lists for meta line.
        short_authors = authors
        if len(short_authors) > 80:
            short_authors = short_authors[:77].rstrip(", ") + "…"
        meta_parts.append(short_authors)
    elif entry.pmid:
        meta_parts.append(f"PMID {entry.pmid}")
    data["source_label"] = ". ".join(meta_parts) if meta_parts else (
        f"PMID {entry.pmid}" if entry.pmid else "Literature"
    )
    data["locator"] = f"PMID {entry.pmid}" if entry.pmid else ""
    data["citation_label"] = data["author_year"]
    return data


def build_cite_context_payload(
    hits,
    attached_references=None,
) -> Dict[str, Any]:
    """Provisional sources/refs for streaming citation decoration."""
    from backend.app.models import RetrievalHit  # local to avoid cycles in type checkers

    sources = []
    for hit in hits or []:
        doc = hit.document if isinstance(hit, RetrievalHit) else hit
        sources.append(enrich_source_dict(doc))
    refs = [enrich_reference_dict(r) for r in (attached_references or [])]
    return {"sources": sources, "attached_references": refs}
