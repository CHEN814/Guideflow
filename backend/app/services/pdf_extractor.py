"""NCCN B-Cell Lymphoma PDF extractor.

Parses the PDF into a StructuredKnowledgeBase with three object types:
  - GuidelinePage  : front matter + clinical guideline pages (one per PDF page)
  - DiscussionChunk: semantic paragraph chunks from discussion articles
  - ReferenceEntry : numbered references from each discussion article

PDF structure assumed:
  Pages  1-13  : front matter (cover, table of contents, update log)
  Pages 14-139 : clinical practice guidelines (one page per GuidelinePage)
  Pages 140+   : discussion section (chunks + references)
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from backend.app.models import (
    DiscussionChunk,
    GuidelinePage,
    PageLink,
    ReferenceEntry,
    StructuredKnowledgeBase,
)

try:
    import fitz  # PyMuPDF
except ImportError:  # pragma: no cover
    fitz = None


# ── PDF structure constants ────────────────────────────────────────────────

DOC_TITLE = "NCCN Clinical Practice Guidelines in Oncology: B-Cell Lymphomas"
DOCUMENT_VERSION = "3.2026"


@dataclass(frozen=True)
class PageRanges:
    front_matter_start: int = 1
    front_matter_end: int = 13
    clinical_guideline_start: int = 14
    clinical_guideline_end: int = 139
    discussion_start: int = 140


# ── Noise patterns for clean_text ─────────────────────────────────────────

_NOISE_PATTERNS = [
    "National Comprehensive Cancer Network",
    "NCCN Guidelines",
    "All rights reserved",
    "may not be reproduced",
    "Version 3.2026",
    "Printed by",
    "NCCN makes no warranties",
    "not be used as",
]

# Footer / navigation lines that appear on every page
_NOISE_LINE_RE = re.compile(
    r"^("
    r"Continue"
    r"|NCCN\.ORG"
    r"|©\s*\d{4}"
    r"|MS-\s*\d+"       # MS-* codes appear as headers; keep the in-text ones
    r")\s*$",
    re.IGNORECASE,
)


def _clean_text(text: str) -> str:
    """Strip noise from a page's raw text."""
    kept: List[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            kept.append("")
            continue
        if any(pat.lower() in stripped.lower() for pat in _NOISE_PATTERNS):
            continue
        if _NOISE_LINE_RE.match(stripped):
            continue
        kept.append(stripped)
    result = "\n".join(kept)
    result = re.sub(r"[ \t]+", " ", result)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


# ── Footer code extraction (printed_page_code) ────────────────────────────

# Matches: BCEL-1  BCEL-6B  MANT-A  BCEL-A 1 OF 3  FOLL-2  NHODG-B 4 OF 5
# Deliberately excludes MS-116 style codes (pure multi-digit suffix, discussion pages).
# Valid suffixes: single digit, digit+letter, letter(s) with optional "N OF M" page indicator.
_FOOTER_CODE_RE = re.compile(
    r"^[A-Z]{2,8}-(?:[A-Z][A-Z0-9]*|\d[A-Z]|\d)(?:\s+\d+\s+OF\s+\d+)?$"
)


def _extract_footer_code(page) -> Optional[str]:
    """Extract the printed page code from the bottom-right corner of a page.

    Looks for text blocks whose top-left corner is in the bottom 15 % of the
    page height and the right 50 % of the page width, then tries to match the
    NCCN page code format (e.g. ``BCEL-1``, ``MANT-A 1 OF 5``).
    """
    rect = page.rect
    page_height = rect.height
    page_width = rect.width

    candidates: List[str] = []
    for block in page.get_text("blocks"):
        if len(block) < 5:
            continue
        x0, y0, _x1, _y1, raw_text = block[:5]
        if y0 < page_height * 0.85:
            continue
        if x0 < page_width * 0.5:
            continue
        normalised = re.sub(r"\s+", " ", str(raw_text).strip())
        if _FOOTER_CODE_RE.match(normalised):
            candidates.append(normalised)

    return candidates[0] if candidates else None


def _module_code_from(printed: str) -> str:
    """Return the part before the first '-', e.g. 'BCEL' from 'BCEL-A 1 OF 3'."""
    return printed.split("-")[0].strip()


# ── Raw link extraction (before resolution) ────────────────────────────────

def _raw_links(page) -> List[Dict]:
    """Collect raw PyMuPDF link dicts from a page."""
    links = []
    for link in page.get_links():
        rect = link.get("from")
        links.append(
            {
                "kind": link.get("kind"),
                "page": link.get("page"),   # 0-based target page index (internal)
                "uri": link.get("uri"),
                "from": list(rect) if rect else None,
            }
        )
    return links


# ── Link edge classification ───────────────────────────────────────────────

# Chrome / navigation anchors that appear on (almost) every page and must never
# be treated as clinical-flow edges during graph navigation.
_NAV_ANCHOR_RE = re.compile(
    r"table of contents|guidelines index|nccn guidelines index|^discussion$|^continue$",
    re.IGNORECASE,
)


def classify_edge(anchor_text: str, target_page_code: Optional[str]) -> str:
    """Classify a page link as a clinical-flow edge or a navigation/chrome edge.

    A link is "navigation" when it points to a page without a printed page code
    (front matter / discussion) or its anchor is the repeated chrome header
    (Index / Table of Contents / Discussion). Everything else (a real jump to
    another coded guideline page) is a "flow" edge that advances the decision
    path. Used both at extraction time and, defensively, at query time for KB
    files built before this field existed.
    """
    if not target_page_code:
        return "navigation"
    anchor = " ".join((anchor_text or "").split())
    if _NAV_ANCHOR_RE.search(anchor):
        return "navigation"
    return "flow"


# ── Link resolver (run after all pages are parsed) ────────────────────────

def _anchor_text_for(link_from: Optional[List[float]], blocks) -> str:
    """Find text that spatially overlaps with a link's bounding box."""
    if not link_from:
        return ""
    lx0, ly0, lx1, ly1 = link_from
    best_text = ""
    best_overlap = 0.0
    for block in blocks:
        if len(block) < 5:
            continue
        bx0, by0, bx1, by1, text = block[:5]
        ox = max(0.0, min(lx1, bx1) - max(lx0, bx0))
        oy = max(0.0, min(ly1, by1) - max(ly0, by0))
        overlap = ox * oy
        if overlap > best_overlap:
            best_overlap = overlap
            best_text = text.strip()
    return best_text


def _resolve_links(
    page_blocks: List,
    raw_links: List[Dict],
    source_page_code: Optional[str],
    code_map: Dict[int, Optional[str]],    # pdf_page (1-based) -> printed_page_code
) -> List[PageLink]:
    """Convert raw PyMuPDF links to structured PageLink objects."""
    resolved: List[PageLink] = []
    for link in raw_links:
        kind = link.get("kind")
        raw_page = link.get("page")     # 0-based
        uri = link.get("uri")
        from_rect = link.get("from")

        if kind == 4 and raw_page is not None:
            # Internal page jump
            target_pdf_page = int(raw_page) + 1   # convert to 1-based
            target_page_code = code_map.get(target_pdf_page)
            anchor = _anchor_text_for(from_rect, page_blocks)
            resolved.append(PageLink(
                source_page_code=source_page_code,
                target_pdf_page=target_pdf_page,
                target_page_code=target_page_code,
                anchor_text=anchor,
                edge_type=classify_edge(anchor, target_page_code),
            ))
        # External URIs are handled separately (reference entries), skip here

    return resolved


# ── Discussion section parsing ─────────────────────────────────────────────

_MS_CODE_RE = re.compile(r"\bMS-(\d+)\b")

# Canonical naming map: chapter-title pattern -> (stable_article_id, canonical_title).
# IMPORTANT: this is used ONLY to *label* a segment that the structural
# segmenter (_segment_discussion) has already split out. It is never used to
# decide article boundaries, so prose mentions / the TOC page can no longer
# split an article. Stable ids (e.g. "dlbcl") keep disease_scope.py working.
_DISEASE_ARTICLES: List[Tuple[re.Pattern, str, str]] = [
    (re.compile(r"diffuse large b.cell lymphoma", re.IGNORECASE), "dlbcl", "Diffuse Large B-Cell Lymphoma"),
    (re.compile(r"follicular lymphoma", re.IGNORECASE), "fl", "Follicular Lymphoma"),
    (re.compile(r"mantle cell lymphoma", re.IGNORECASE), "mcl", "Mantle Cell Lymphoma"),
    (re.compile(r"marginal zone", re.IGNORECASE), "mzl", "Marginal Zone Lymphoma"),
    (re.compile(r"primary mediastinal", re.IGNORECASE), "pmbl", "Primary Mediastinal B-Cell Lymphoma"),
    (re.compile(r"burkitt", re.IGNORECASE), "burkitt", "Burkitt Lymphoma"),
    (re.compile(r"high.grade b.cell", re.IGNORECASE), "hgbl", "High-Grade B-Cell Lymphoma"),
    (re.compile(r"small lymphocytic|chronic lymphocytic", re.IGNORECASE), "cll_sll", "CLL/SLL"),
    (re.compile(r"lymphoplasmacytic|waldenstrom", re.IGNORECASE), "lpwm", "Lymphoplasmacytic Lymphoma/Waldenström"),
    (re.compile(r"hairy cell", re.IGNORECASE), "hcl", "Hairy Cell Leukemia"),
    (re.compile(r"post.transplant lymphoproliferative", re.IGNORECASE), "ptld", "Post-Transplant Lymphoproliferative Disease"),
    (re.compile(r"grey.zone|gray.zone", re.IGNORECASE), "gzl", "Grey Zone Lymphoma"),
    (re.compile(r"large b.cell lymphoma", re.IGNORECASE), "lbcl", "Large B-Cell Lymphoma"),
]


def _normalize_title(text: str) -> str:
    """Lowercase, drop punctuation and collapse whitespace for fuzzy matching."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _slugify(text: str) -> str:
    """Generic, disease-name-free id fallback derived from a heading/title."""
    norm = _normalize_title(text)
    return re.sub(r"\s+", "-", norm) or "section"


# Table-of-contents dotted-leader line, e.g. "Follicular Lymphoma .......... 22".
_TOC_LINE_RE = re.compile(r"(?m)^(.+?)\s*\.{2,}\s*(\d+)\s*$")


def _is_toc_page(text: str) -> bool:
    """Structurally detect a discussion table-of-contents page (no page-number hardcode)."""
    return len(_TOC_LINE_RE.findall(text)) >= 5


def _parse_toc(text: str) -> List[Tuple[str, int]]:
    """Parse dotted-leader TOC lines into an ordered list of (title, start_page)."""
    entries: List[Tuple[str, int]] = []
    for m in _TOC_LINE_RE.finditer(text):
        title = m.group(1).strip()
        if title:
            entries.append((title, int(m.group(2))))
    return entries


def _running_header(
    discussion_pages: List[Tuple[int, str, List[Dict], List]],
) -> Optional[str]:
    """Infer the repeated running header (e.g. "B-Cell Lymphomas") generically.

    Returns the most frequent first non-empty line if it repeats on a large
    share of pages; otherwise None.
    """
    counts: Dict[str, int] = {}
    for _pdf_page, clean, _raw, _blocks in discussion_pages:
        for line in clean.splitlines():
            stripped = line.strip()
            if stripped:
                counts[stripped] = counts.get(stripped, 0) + 1
                break
    if not counts:
        return None
    header = max(counts, key=lambda k: counts[k])
    threshold = max(3, len(discussion_pages) // 2)
    return header if counts[header] >= threshold else None


def _heading_lines(text: str, running_header: Optional[str], n: int = 3) -> List[str]:
    """First ``n`` non-empty lines that are not the repeated running header."""
    out: List[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if running_header and stripped == running_header:
            continue
        out.append(stripped)
        if len(out) >= n:
            break
    return out


def _top_heading(text: str, running_header: Optional[str]) -> str:
    """First non-empty line that is not the repeated running header."""
    lines = _heading_lines(text, running_header, 1)
    return lines[0] if lines else ""


def _title_to_article(title: str) -> Tuple[str, str]:
    """Map a (clean) chapter title to (stable_article_id, canonical_title)."""
    for pattern, art_id, art_title in _DISEASE_ARTICLES:
        if pattern.search(title):
            return art_id, art_title
    return _slugify(title), title


def _chapter_label(
    body_text: str,
    running_header: Optional[str],
    toc_titles: List[str],
    prev_ref_text: Optional[str] = None,
) -> Tuple[str, str]:
    """Label a chapter segment as (article_id, article_title).

    NCCN discussion is two-column, so a chapter title may land either at the top
    of the first body page *or* on the boundary reference page that precedes it.
    Candidate title lines are therefore drawn from both the preceding reference
    page and the new body page's top lines. Matching priority:
      1. a line that *exactly* matches a TOC chapter title (robust: reference
         sentences are long and never equal a short title) -> canonical id;
      2. canonical disease pattern on the body's top heading -> stable id;
      3. slugify the body heading; 4. generic fallback.
    """
    toc_norm: Dict[str, str] = {}
    for title in toc_titles:
        norm = _normalize_title(title)
        if norm:
            toc_norm.setdefault(norm, title)

    candidates: List[str] = []
    if prev_ref_text:
        candidates.extend(line.strip() for line in prev_ref_text.splitlines() if line.strip())
    candidates.extend(_heading_lines(body_text, running_header, 3))

    for line in candidates:
        norm = _normalize_title(line)
        if norm in toc_norm:
            return _title_to_article(toc_norm[norm])

    heading = _top_heading(body_text, running_header)
    for pattern, art_id, art_title in _DISEASE_ARTICLES:
        if heading and pattern.search(heading):
            return art_id, art_title

    if heading:
        return _slugify(heading), heading
    return "general", "B-Cell Lymphomas"


def _extract_ms_code(text: str) -> Optional[str]:
    m = _MS_CODE_RE.search(text)
    return f"MS-{m.group(1)}" if m else None


# Reference section start markers
_REF_SECTION_RE = re.compile(r"^\s*References?\s*$", re.IGNORECASE | re.MULTILINE)
_REF_NUMBERED_LINE_RE = re.compile(r"^\s*(\d+)\.\s+.{10,}", re.MULTILINE)
_REF_SPLIT_RE = re.compile(r"(?m)(?=^\s*\d+\.\s+)")
# Citation-locator markers used to distinguish a real reference list from a
# numbered list inside body text. Must match actual URLs/identifiers, NOT the
# bare word "PubMed" that appears in body prose (e.g. "the PubMed database").
_REF_URL_RE = re.compile(
    r"ncbi\.nlm\.nih\.gov|doi\.org/10\.|/pubmed/\d|pmid:\s*\d|available at:\s*https?://",
    re.IGNORECASE,
)


def _looks_like_reference_page(text: str) -> bool:
    """Heuristic for a reference-list page.

    The discriminator is citation-locator (PubMed/DOI/NCBI) density: discussion
    body text never carries those URLs, while reference lists carry roughly one
    per entry. A page counts as references when any of the following hold:
      * it has a standalone "References" header; or
      * it carries >=3 citation-locator lines (covers continuation pages whose
        long references contain few numbered entries); or
      * it has >=2 numbered entries AND >=2 citation-locator lines.

    The locator requirement avoids misclassifying numbered treatment/option
    lists in body text as references, which would otherwise trigger a spurious
    chapter boundary; the locator-density rule avoids the opposite failure where
    a continuation reference page (few numbered entries) is mistaken for body.
    """
    if _REF_SECTION_RE.search(text):
        return True
    numbered = len(_REF_NUMBERED_LINE_RE.findall(text))
    locator_lines = sum(1 for line in text.splitlines() if _REF_URL_RE.search(line))
    if locator_lines >= 3:
        return True
    return numbered >= 2 and locator_lines >= 2


def _extract_inline_ref_ids(text: str) -> List[str]:
    """Extract inline citation numbers like 45-47, 45,46 or superscript patterns."""
    ids: set = set()
    # Patterns: .45-47,  .45,46,47  [45]  45-47
    for m in re.finditer(r"[\.,](\d{1,3})(?:-(\d{1,3}))?|[\[\(](\d{1,3})[\]\)]", text):
        start = int(m.group(1) or m.group(3))
        end = int(m.group(2)) if m.group(2) else start
        for n in range(start, min(end + 1, start + 20)):
            ids.add(str(n))
    return sorted(ids, key=int)


_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.。!?！？])\s+")


def _overlap_tail(text: str, max_chars: int) -> str:
    """Return the last whole sentence(s) of ``text`` up to ``max_chars``.

    Used to carry a small amount of trailing context into the next chunk so that
    a fact split across a chunk boundary stays retrievable from both sides.
    """
    if max_chars <= 0:
        return ""
    sentences = [s for s in _SENTENCE_SPLIT_RE.split(text.replace("\n", " ").strip()) if s]
    tail: List[str] = []
    total = 0
    for sentence in reversed(sentences):
        if tail and total + len(sentence) > max_chars:
            break
        tail.insert(0, sentence)
        total += len(sentence)
    return " ".join(tail).strip()


def _split_into_chunks(
    article_pages: List[Tuple[int, str]],
    article_id: str,
    article_title: str,
    chunk_counter: List[int],
    target_chars: int = 1100,
    overlap_chars: int = 160,
) -> List[DiscussionChunk]:
    """Chunk a whole discussion article (its body pages concatenated in order).

    Improvements over the previous per-page chunker:
      * Article-level concatenation - text flowing across a page break is no
        longer hard-cut at the page boundary.
      * Section-aware - a heading starts a fresh chunk (and a new ``section``);
        chunks never cross a section, giving a parent(section)/child(chunk)
        structure for retrieval.
      * Sentence-boundary overlap - consecutive chunks within a section share a
        trailing sentence window so boundary facts stay findable.

    ``ms_page_code`` and ``pdf_page`` are taken from where each chunk starts.
    """
    chunks: List[DiscussionChunk] = []
    current_section = "Discussion"
    buf: List[str] = []
    buf_start_page: Optional[int] = None
    last_page: Optional[int] = None

    def buf_len() -> int:
        return sum(len(p) for p in buf)

    def flush(carry_overlap: bool) -> None:
        nonlocal buf, buf_start_page
        body = "\n\n".join(buf).strip()
        if not body:
            buf = []
            buf_start_page = None
            return
        idx = chunk_counter[0]
        chunk_counter[0] += 1
        page = buf_start_page if buf_start_page is not None else (last_page or 0)
        chunks.append(DiscussionChunk(
            chunk_id=f"disc-{article_id}-p{page}-c{idx}",
            article_id=article_id,
            article_title=article_title,
            pdf_page=page,
            ms_page_code=_extract_ms_code(body),
            section=current_section,
            clean_text=body,
            reference_ids=_extract_inline_ref_ids(body),
        ))
        if carry_overlap:
            tail = _overlap_tail(body, overlap_chars)
            buf = [tail] if tail else []
            buf_start_page = last_page
        else:
            buf = []
            buf_start_page = None

    for pdf_page, clean in article_pages:
        last_page = pdf_page
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", clean) if p.strip()]
        for para in paragraphs:
            lines = para.splitlines()
            first_line = lines[0].strip() if lines else ""
            is_heading = (
                4 <= len(first_line) <= 80
                and not first_line.endswith(".")
                and first_line[:1].isupper()
                and len(lines) <= 2
            )
            if is_heading and buf and buf_len() > 0:
                # Section boundary: close the chunk, no overlap across sections.
                flush(carry_overlap=False)
                current_section = first_line
            if buf_len() + len(para) > target_chars and buf:
                flush(carry_overlap=True)
            if buf_start_page is None:
                buf_start_page = pdf_page
            buf.append(para)

    flush(carry_overlap=False)
    return chunks


# ── Reference entry parsing ────────────────────────────────────────────────

_PMID_RE = re.compile(r"pubmed/(\d{6,9})|PMID:?\s*(\d{6,9})")
_DOI_RE = re.compile(r"doi\.org/(10\.[^\s\)]+)|doi:\s*(10\.[^\s\)]+)", re.IGNORECASE)


def _parse_reference_entries(
    text: str,
    article_id: str,
    raw_links: List[Dict],
    page_blocks,
) -> List[ReferenceEntry]:
    """Parse numbered reference list text into ReferenceEntry objects."""
    entries: List[ReferenceEntry] = []

    # Split on numbered entry boundaries: "1.", "2.", etc.
    parts = _REF_SPLIT_RE.split(text)
    for part in parts:
        part = part.strip()
        if not part:
            continue
        m = re.match(r"^(\d+)\.\s+(.+)", part, re.DOTALL)
        if not m:
            continue
        ref_num = m.group(1)
        ref_body = m.group(2).strip()

        pmid: Optional[str] = None
        doi: Optional[str] = None
        url: Optional[str] = None

        m_pmid = _PMID_RE.search(ref_body)
        if m_pmid:
            pmid = m_pmid.group(1) or m_pmid.group(2)

        m_doi = _DOI_RE.search(ref_body)
        if m_doi:
            doi = m_doi.group(1) or m_doi.group(2)

        # Also check PyMuPDF links for URIs in this reference's area
        # (simple approach: look for URIs in page links that contain pubmed/doi)
        for link in raw_links:
            uri = link.get("uri") or ""
            if "pubmed" in uri and not pmid:
                m_u = re.search(r"pubmed/(\d+)", uri)
                if m_u:
                    pmid = m_u.group(1)
            if "doi.org" in uri and not doi:
                m_d = re.search(r"doi\.org/(10\.[^\s\)]+)", uri)
                if m_d:
                    doi = m_d.group(1)
            if uri and not url:
                url = uri

        entries.append(ReferenceEntry(
            entry_id=f"ref-{article_id}-{ref_num}",
            article_id=article_id,
            ref_number=ref_num,
            text=ref_body,
            pmid=pmid,
            doi=doi,
            url=url,
        ))

    return entries


def _dedupe_reference_entries(entries: List[ReferenceEntry]) -> List[ReferenceEntry]:
    """Drop exact duplicates and guarantee globally unique entry_id.

    Two failure modes are handled:
      1. Page-overlap re-parsing produces identical entries (same article_id,
         ref_number and text) -> dropped.
      2. Different reference blocks share the same (article_id, ref_number)
         because article segmentation could not split them (different text on
         the same id) -> kept, but the entry_id gets a "-b{n}" block suffix so
         it stays unique. article_id / ref_number are preserved for linkage.
    """
    seen_exact: set = set()
    id_counts: Dict[str, int] = {}
    result: List[ReferenceEntry] = []

    for entry in entries:
        exact_key = (entry.article_id, entry.ref_number, entry.text.strip())
        if exact_key in seen_exact:
            continue
        seen_exact.add(exact_key)

        base_id = entry.entry_id
        count = id_counts.get(base_id, 0)
        entry.entry_id = base_id if count == 0 else f"{base_id}-b{count}"
        id_counts[base_id] = count + 1
        result.append(entry)

    return result


# ── Discussion segmentation (structure-driven) ─────────────────────────────

def _segment_discussion(
    discussion_pages: List[Tuple[int, str, List[Dict], List]],
) -> Tuple[List[DiscussionChunk], List[ReferenceEntry], List[GuidelinePage]]:
    """Split discussion pages into disease articles using physical structure.

    Boundary signal: each chapter is a run of body pages followed by its own
    reference list (numbered from 1). A references->body transition therefore
    marks the start of the next chapter. Disease names are used only to *label*
    a segment (via :func:`_chapter_label`), never to decide boundaries, so
    prose mentions and the TOC page can no longer split an article.

    Returns (chunks, references, page_records). ``references`` is deduped.
    """
    chunks: List[DiscussionChunk] = []
    references: List[ReferenceEntry] = []
    pages: List[GuidelinePage] = []

    running_header = _running_header(discussion_pages)
    toc_titles: List[str] = []

    current_article_id = "general"
    current_article_title = "B-Cell Lymphomas"
    chunk_counter = [0]
    state = "body"          # body | refs
    started = False         # whether the first chapter has been opened
    last_ref_text: Optional[str] = None   # boundary ref page may carry next title
    # Body pages of the current article, accumulated so the whole article is
    # chunked together (instead of one chunk run per physical page).
    body_buffer: List[Tuple[int, str]] = []

    def flush_article() -> None:
        nonlocal body_buffer
        if body_buffer:
            chunks.extend(_split_into_chunks(
                body_buffer,
                current_article_id,
                current_article_title,
                chunk_counter,
            ))
        body_buffer = []

    for pdf_page, clean, raw_links, blocks in discussion_pages:
        # Table-of-contents page: harvest titles for labelling, never segment.
        if _is_toc_page(clean):
            toc_titles.extend(title for title, _ in _parse_toc(clean))
            pages.append(GuidelinePage(
                page_id=f"page-{pdf_page}",
                pdf_page=pdf_page,
                page_type="discussion_toc",
                clean_text=clean,
            ))
            continue

        if _looks_like_reference_page(clean):
            references.extend(
                _parse_reference_entries(clean, current_article_id, raw_links, blocks)
            )
            pages.append(GuidelinePage(
                page_id=f"page-{pdf_page}",
                pdf_page=pdf_page,
                page_type="discussion_references",
                clean_text=clean,
            ))
            state = "refs"
            last_ref_text = clean
            continue

        # Body page. A refs->body transition (or the very first body page)
        # opens a new chapter: flush the previous article, then relabel.
        if not started or state == "refs":
            flush_article()
            current_article_id, current_article_title = _chapter_label(
                clean, running_header, toc_titles, prev_ref_text=last_ref_text
            )
            chunk_counter = [0]
            started = True
            last_ref_text = None
        state = "body"

        body_buffer.append((pdf_page, clean))
        pages.append(GuidelinePage(
            page_id=f"page-{pdf_page}",
            pdf_page=pdf_page,
            page_type="discussion_text",
            clean_text=clean,
        ))

    flush_article()
    references = _dedupe_reference_entries(references)
    return chunks, references, pages


# ── Main build function ────────────────────────────────────────────────────

def build_knowledge_base(
    pdf_path: Path,
    ranges: PageRanges | None = None,
) -> StructuredKnowledgeBase:
    """Parse the NCCN PDF and return a StructuredKnowledgeBase.

    Two-pass approach:
      Pass 1 – collect GuidelinePage objects (raw links stored in metadata),
               collect discussion page texts.
      Pass 2 – resolve links using the complete printed_page_code map,
               parse discussion into DiscussionChunk + ReferenceEntry.
    """
    if fitz is None:
        raise RuntimeError(
            "PyMuPDF is required. Install with: pip install -r requirements.txt"
        )
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    ranges = ranges or PageRanges()
    pdf = fitz.open(str(pdf_path))

    guideline_pages: List[GuidelinePage] = []
    # Temp storage for pass 2
    _raw_guideline_links: Dict[int, Tuple[List, List[Dict]]] = {}  # pdf_page -> (blocks, raw_links)
    _discussion_pages: List[Tuple[int, str, List[Dict], List]] = []  # (pdf_page, clean_text, raw_links, blocks)

    # ── Pass 1: read every page ─────────────────────────────────────────

    for page_index in range(len(pdf)):
        page_num = page_index + 1
        page = pdf[page_index]

        clean = _clean_text(page.get_text("text"))
        if not clean:
            continue

        if ranges.front_matter_start <= page_num <= ranges.front_matter_end:
            guideline_pages.append(GuidelinePage(
                page_id=f"page-{page_num}",
                pdf_page=page_num,
                page_type="front_matter",
                clean_text=clean,
            ))

        elif ranges.clinical_guideline_start <= page_num <= ranges.clinical_guideline_end:
            footer = _extract_footer_code(page)
            module = _module_code_from(footer) if footer else None
            needs_rv = footer is None

            blocks = page.get_text("blocks")
            raw = _raw_links(page)
            _raw_guideline_links[page_num] = (blocks, raw)

            guideline_pages.append(GuidelinePage(
                page_id=f"page-{page_num}",
                pdf_page=page_num,
                page_type="clinical_guideline",
                clean_text=clean,
                printed_page_code=footer,
                module_code=module,
                needs_review=needs_rv,
            ))

        elif page_num >= ranges.discussion_start:
            blocks = page.get_text("blocks")
            raw = _raw_links(page)
            _discussion_pages.append((page_num, clean, raw, blocks))

    # ── Pass 2a: resolve guideline page links ──────────────────────────

    code_map: Dict[int, Optional[str]] = {
        p.pdf_page: p.printed_page_code for p in guideline_pages
    }

    for page in guideline_pages:
        if page.page_type != "clinical_guideline":
            continue
        blocks, raw = _raw_guideline_links.get(page.pdf_page, ([], []))
        page.outgoing_links = _resolve_links(
            blocks, raw, page.printed_page_code, code_map
        )

    # ── Pass 2b: segment discussion section (structure-driven) ─────────

    discussion_chunks, reference_entries, discussion_page_records = _segment_discussion(
        _discussion_pages
    )
    guideline_pages.extend(discussion_page_records)

    # ── Stats ──────────────────────────────────────────────────────────

    stats = {
        "source_pdf": str(pdf_path),
        "document_version": DOCUMENT_VERSION,
        "guideline_page_count": len(guideline_pages),
        "front_matter_count": sum(1 for p in guideline_pages if p.page_type == "front_matter"),
        "clinical_guideline_count": sum(1 for p in guideline_pages if p.page_type == "clinical_guideline"),
        "discussion_toc_count": sum(1 for p in guideline_pages if p.page_type == "discussion_toc"),
        "discussion_text_count": sum(1 for p in guideline_pages if p.page_type == "discussion_text"),
        "discussion_ref_count": sum(1 for p in guideline_pages if p.page_type == "discussion_references"),
        "discussion_chunk_count": len(discussion_chunks),
        "reference_entry_count": len(reference_entries),
        "needs_review_count": sum(1 for p in guideline_pages if p.needs_review),
        "page_ranges": {
            "front_matter": f"{ranges.front_matter_start}-{ranges.front_matter_end}",
            "clinical_guideline": f"{ranges.clinical_guideline_start}-{ranges.clinical_guideline_end}",
            "discussion_start": ranges.discussion_start,
        },
    }

    return StructuredKnowledgeBase(
        guideline_pages=guideline_pages,
        discussion_chunks=discussion_chunks,
        reference_entries=reference_entries,
        stats=stats,
    )
