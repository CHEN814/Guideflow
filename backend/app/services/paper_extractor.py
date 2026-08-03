"""Generic paper-style guideline PDF extractor (profile-driven).

Designed for journal/guideline articles that are closer to academic papers than
textbook-style manuals (e.g. EHA LBCL CPG). Capabilities:

- dual-column reading-order reconstruction
- all-caps / title-case section heading detection
- span-level superscript citation harvesting → ``reference_ids``
- trailing global numbered reference list
- optional offline VLM table transcription via ``paper_table_vlm``

The ``PaperProfile`` interface is the stable contract; the rule-based backend
here can later be swapped for Docling without changing callers.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from backend.app.models import (
    DiscussionChunk,
    GuidelinePage,
    ReferenceEntry,
    StructuredKnowledgeBase,
)

try:
    import fitz  # PyMuPDF
except ImportError:  # pragma: no cover
    fitz = None


# ── Profile ───────────────────────────────────────────────────────────────

@dataclass
class PaperProfile:
    """Source-specific knobs for a paper-style guideline PDF."""

    source_key: str
    doc_title: str
    article_id: str
    document_version: str = ""
    heading_style: str = "allcaps"  # allcaps | fontsize
    table_caption_re: str = r"T\s*A\s*B\s*L\s*E\s+([A-Z]?\d+)"
    reference_start_hint: str = "REFERENCES"
    # Sections that should not enter BM25 clinical retrieval.
    skip_section_re: str = (
        r"^(AUTHOR CONTRIBUTIONS|CONFLICT OF INTEREST(?: STATEMENT)?|"
        r"DATA AVAILABILITY(?: STATEMENT)?|FUNDING|ORCID|REFERENCES|"
        r"ACKNOWLEDGEMENTS?|ACKNOWLEDGMENTS?)$"
    )
    front_matter_sections: Tuple[str, ...] = ("ABSTRACT", "METHODOLOGY")
    # Soft section titles that are not ALL CAPS (title case).
    soft_heading_re: str = r"^Summary of recommendations\b.*"


EHA_PROFILE = PaperProfile(
    source_key="eha",
    doc_title="Large B-cell lymphoma (LBCL): EHA Clinical Practice Guidelines for diagnosis, treatment, and follow-up",
    article_id="eha-lbcl",
    document_version="2025",
    heading_style="allcaps",
    table_caption_re=r"T\s*A\s*B\s*L\s*E\s+([A-Z]?\d+)",
    reference_start_hint="REFERENCES",
)


PROFILES: Dict[str, PaperProfile] = {
    "eha": EHA_PROFILE,
}


def get_paper_profile(source_key: str) -> PaperProfile:
    key = (source_key or "").strip().lower()
    if key not in PROFILES:
        raise ValueError(f"Unknown paper profile {source_key!r}. Known: {', '.join(PROFILES)}")
    return PROFILES[key]


# ── Evidence legend (EHA / ESMO-style) ─────────────────────────────────────

EHA_EVIDENCE_LEVELS: Dict[str, str] = {
    "I": "At least one large RCT of good quality, or meta-analyses of well-conducted RCTs without heterogeneity",
    "II": "Small RCTs or large RCTs with suspicion of bias, or meta-analyses of such trials / with heterogeneity",
    "III": "Prospective cohort studies",
    "IV": "Retrospective cohort or case–control studies",
    "V": "Uncontrolled studies, case reports, and expert opinions",
}

EHA_RECOMMENDATION_GRADES: Dict[str, str] = {
    "A": "Strong evidence for efficacy with substantial clinical benefit; strongly recommended",
    "B": "Strong/moderate evidence for efficacy with limited clinical benefit; generally recommended",
    "C": "Insufficient evidence or benefit does not outweigh risks/costs; optional",
    "D": "Moderate evidence against efficacy or for adverse outcome; generally not recommended",
    "E": "Strong evidence against efficacy or for adverse outcome; never recommended",
}


def eha_evidence_legend_prompt_block() -> str:
    return (
        "【EHA / ESMO 证据与推荐标记】\n"
        "正文中写作 [I, A]、[III, B] 等：罗马数字 I–V 为证据等级，字母 A–E 为推荐强度。\n"
        "I=大型高质量 RCT/无异质性 meta；II=小型 RCT 或有偏倚的大型 RCT；"
        "III=前瞻队列；IV=回顾队列/病例对照；V=无对照/病例报告/专家意见。\n"
        "A=强推荐；B=一般推荐；C=可选；D=一般不推荐；E=绝不推荐。"
    )


# ── Low-level PDF helpers ─────────────────────────────────────────────────

_CITATION_TOKEN_RE = re.compile(r"^\d{1,3}(?:\s*[,–—\-]\s*\d{1,3})*$")
_PMID_RE = re.compile(r"\bPMID\s*:?\s*(\d{5,9})\b", re.I)
_DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.I)
_REF_START_RE = re.compile(r"^\s*(\d{1,3})\.\s+")


@dataclass
class _TextUnit:
    text: str
    pdf_page: int
    y0: float
    is_heading: bool = False
    is_table_caption: bool = False
    reference_ids: List[str] = field(default_factory=list)
    table_id: str = ""


def _normalize_spaces(text: str) -> str:
    text = text.replace("\u00ad", "")  # soft hyphen
    text = text.replace("\u2010", "-").replace("\u2011", "-").replace("\u2013", "-")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _expand_citation_token(token: str) -> List[str]:
    ids: List[str] = []
    for part in re.split(r"\s*,\s*", token.strip()):
        part = part.strip()
        if not part:
            continue
        m = re.match(r"^(\d{1,3})\s*[–—\-]\s*(\d{1,3})$", part)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if b < a:
                a, b = b, a
            for n in range(a, min(b, a + 30) + 1):
                if 1 <= n <= 300:
                    ids.append(str(n))
        elif part.isdigit() and 1 <= int(part) <= 300:
            ids.append(str(int(part)))
    return ids


def _is_allcaps_heading(line: str) -> bool:
    s = line.strip()
    if len(s) < 6 or len(s) > 90:
        return False
    # Ignore spaced-out journal chrome like "G U I D E L I N E S"
    if re.fullmatch(r"(?:[A-Z]\s+){3,}[A-Z]", s):
        return False
    letters = [c for c in s if c.isalpha()]
    if len(letters) < 4:
        return False
    upper = sum(1 for c in letters if c.isupper())
    if upper / len(letters) < 0.9:
        return False
    # Avoid table fragments / short acronyms rows
    if s.count("|") >= 2:
        return False
    return True


def _page_mid_x(page) -> float:
    return float(page.rect.width) * 0.5


def _extract_page_units(
    page,
    pdf_page: int,
    *,
    table_caption_re: re.Pattern[str],
    soft_heading_re: re.Pattern[str],
) -> List[_TextUnit]:
    """Reconstruct reading order for a (possibly dual-column) page."""
    data = page.get_text("dict")
    blocks = [b for b in data.get("blocks", []) if b.get("type") == 0]
    if not blocks:
        return []

    mid = _page_mid_x(page)
    left, right, full = [], [], []
    for b in blocks:
        x0, y0, x1, y1 = b["bbox"]
        # Full-width blocks (headers / table captions spanning both columns)
        if x0 < mid * 0.55 and x1 > mid * 1.35:
            full.append(b)
        elif (x0 + x1) / 2.0 <= mid:
            left.append(b)
        else:
            right.append(b)

    ordered = sorted(full, key=lambda b: b["bbox"][1]) + sorted(
        left, key=lambda b: b["bbox"][1]
    ) + sorted(right, key=lambda b: b["bbox"][1])

    units: List[_TextUnit] = []
    for block in ordered:
        lines_out: List[str] = []
        ref_ids: List[str] = []
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            if not spans:
                continue
            sizes = [float(s.get("size") or 0) for s in spans]
            med = sorted(sizes)[len(sizes) // 2] if sizes else 0.0
            origins_y = [float((s.get("origin") or [0, 0])[1]) for s in spans]
            base_y = sorted(origins_y)[len(origins_y) // 2] if origins_y else 0.0

            parts: List[str] = []
            for span in spans:
                text = span.get("text") or ""
                if not text:
                    continue
                size = float(span.get("size") or 0)
                oy = float((span.get("origin") or [0, 0])[1])
                stripped = text.strip()
                is_super = (
                    med > 0
                    and size > 0
                    and size < med * 0.85
                    and oy < base_y - 0.6
                    and _CITATION_TOKEN_RE.match(stripped.replace(" ", "")) is not None
                )
                if is_super:
                    for cid in _expand_citation_token(stripped):
                        if cid not in ref_ids:
                            ref_ids.append(cid)
                    # Keep digits attached for readability / BM25.
                    if parts and not parts[-1].endswith((" ", "\n")):
                        parts.append(stripped)
                    else:
                        parts.append(stripped)
                else:
                    parts.append(text)
            line_text = _normalize_spaces("".join(parts))
            if line_text:
                lines_out.append(line_text)

        if not lines_out:
            continue
        text = _normalize_spaces("\n".join(lines_out))
        if not text:
            continue
        first = lines_out[0]
        caption_m = table_caption_re.search(first.replace(" ", ""))
        # Caption detection tolerates spaced letters: T A B L E 2
        spaced_caption = re.search(
            r"T\s*A\s*B\s*L\s*E\s+([A-Z]?\d+)", first, re.I
        )
        is_caption = bool(spaced_caption)
        table_id = spaced_caption.group(1).upper() if spaced_caption else ""
        is_heading = _is_allcaps_heading(first) or bool(soft_heading_re.match(first))
        units.append(
            _TextUnit(
                text=text,
                pdf_page=pdf_page,
                y0=float(block["bbox"][1]),
                is_heading=is_heading and not is_caption,
                is_table_caption=is_caption,
                reference_ids=ref_ids,
                table_id=table_id,
            )
        )
    return units


def _merge_heading_continuations(units: List[_TextUnit]) -> List[_TextUnit]:
    """Join consecutive all-caps heading fragments (wrapped titles)."""
    if not units:
        return []
    out: List[_TextUnit] = []
    i = 0
    while i < len(units):
        u = units[i]
        if u.is_heading and _is_allcaps_heading(u.text.split("\n", 1)[0]):
            title = u.text.split("\n", 1)[0].strip()
            body_rest = "\n".join(u.text.split("\n")[1:]).strip()
            j = i + 1
            while j < len(units):
                nxt = units[j]
                first = nxt.text.split("\n", 1)[0].strip()
                if (
                    nxt.is_heading
                    and nxt.pdf_page == u.pdf_page
                    and _is_allcaps_heading(first)
                    and len(first) < 60
                ):
                    title = f"{title} {first}".strip()
                    extra = "\n".join(nxt.text.split("\n")[1:]).strip()
                    if extra:
                        body_rest = f"{body_rest}\n{extra}".strip() if body_rest else extra
                    # merge refs
                    for rid in nxt.reference_ids:
                        if rid not in u.reference_ids:
                            u.reference_ids.append(rid)
                    j += 1
                else:
                    break
            merged_text = title if not body_rest else f"{title}\n{body_rest}"
            out.append(
                _TextUnit(
                    text=merged_text,
                    pdf_page=u.pdf_page,
                    y0=u.y0,
                    is_heading=True,
                    is_table_caption=False,
                    reference_ids=list(u.reference_ids),
                )
            )
            i = j
        else:
            out.append(u)
            i += 1
    return out


def _split_long_text(text: str, max_chars: int = 1400) -> List[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    paras = re.split(r"\n\s*\n|(?<=[.!?])\s+", text)
    chunks: List[str] = []
    buf = ""
    for p in paras:
        p = p.strip()
        if not p:
            continue
        if not buf:
            buf = p
        elif len(buf) + len(p) + 1 <= max_chars:
            buf = f"{buf}\n{p}"
        else:
            chunks.append(buf)
            buf = p
    if buf:
        chunks.append(buf)
    return chunks


def _parse_references(article_id: str, source_key: str, text: str) -> List[ReferenceEntry]:
    entries: List[ReferenceEntry] = []
    # Normalize hyphenation across line breaks.
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    text = text.replace("\n", " ")
    text = re.sub(r"\s+", " ", text).strip()
    # Split on " N. " reference starts, keeping the number.
    parts = re.split(r"(?:(?<=\s)|^)(\d{1,3})\.\s+", text)
    # parts: [preamble, num, body, num, body, ...]
    if len(parts) < 3:
        return entries
    i = 1
    while i + 1 < len(parts):
        num = parts[i].strip()
        body = parts[i + 1].strip()
        i += 2
        if not num.isdigit() or not body:
            continue
        # Truncate at next accidental author junk.
        body = body.strip(" ;")
        pmid_m = _PMID_RE.search(body)
        doi_m = _DOI_RE.search(body)
        entries.append(
            ReferenceEntry(
                entry_id=f"ref-{article_id}-{num}",
                article_id=article_id,
                ref_number=str(int(num)),
                text=body,
                pmid=pmid_m.group(1) if pmid_m else None,
                doi=doi_m.group(0) if doi_m else None,
                source=source_key,
            )
        )
    return entries


def _section_slug(title: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "-", title.strip().lower()).strip("-")
    return (s or "section")[:60]


# ── Public API ────────────────────────────────────────────────────────────

TableProvider = Callable[[Sequence[Tuple[int, str]]], Dict[int, List[str]]]


def build_paper_knowledge_base(
    pdf_path: Path | str,
    profile: PaperProfile | str = "eha",
    *,
    table_provider: Optional[TableProvider] = None,
    skip_vlm: bool = False,
    vlm_api_key: Optional[str] = None,
    vlm_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1",
    vlm_model: str = "qwen-vl-max",
    table_cache_path: Optional[Path] = None,
    page_image_dir: Optional[Path] = None,
) -> StructuredKnowledgeBase:
    """Parse a paper-style PDF into a StructuredKnowledgeBase."""
    if fitz is None:
        raise RuntimeError("PyMuPDF (fitz) is required to build paper knowledge bases")

    if isinstance(profile, str):
        profile = get_paper_profile(profile)
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(path)

    table_caption_re = re.compile(profile.table_caption_re, re.I)
    soft_heading_re = re.compile(profile.soft_heading_re, re.I)
    skip_section_re = re.compile(profile.skip_section_re, re.I)
    ref_hint = profile.reference_start_hint.upper()

    doc = fitz.open(str(path))
    try:
        all_units: List[_TextUnit] = []
        table_targets: List[Tuple[int, str]] = []
        for i in range(doc.page_count):
            pdf_page = i + 1
            units = _extract_page_units(
                doc[i],
                pdf_page,
                table_caption_re=table_caption_re,
                soft_heading_re=soft_heading_re,
            )
            units = _merge_heading_continuations(units)
            for u in units:
                if u.is_table_caption:
                    caption = u.text.split("\n", 1)[0].strip()
                    # Prefer canonical "TABLE N ..."
                    m = re.search(r"T\s*A\s*B\s*L\s*E\s+([A-Z]?\d+)", caption, re.I)
                    if m:
                        rest = caption[m.end() :].strip(" .:-)")
                        # Drop OCR junk / "(continued on next page)" chrome.
                        rest = re.sub(
                            r"^\(?\s*continued(?:\s+on\s+next\s+page)?\s*\)?\.?\s*",
                            "",
                            rest,
                            flags=re.I,
                        ).strip(" .:-)")
                        caption = f"TABLE {m.group(1).upper()}" + (f" {rest}" if rest else "")
                    table_targets.append((pdf_page, caption))
            all_units.extend(units)

        # Resolve tables
        tables_by_page: Dict[int, List[str]] = {}
        if table_provider is not None:
            tables_by_page = table_provider(table_targets) or {}
        else:
            from backend.app.services.paper_table_vlm import transcribe_tables

            root = path.parent
            cache = table_cache_path or (root / "data" / "cache" / f"{profile.source_key}_table_md.json")
            img_dir = page_image_dir or (root / "data" / "cache" / f"{profile.source_key}_page_images")
            tables_by_page = transcribe_tables(
                pdf_path=path,
                table_targets=table_targets,
                cache_path=cache,
                page_image_dir=img_dir,
                api_key=vlm_api_key,
                base_url=vlm_base_url,
                model=vlm_model,
                skip_vlm=skip_vlm,
            )

        guideline_pages: List[GuidelinePage] = []
        discussion_chunks: List[DiscussionChunk] = []
        reference_entries: List[ReferenceEntry] = []

        # Page 1 abstract / title as front matter.
        if doc.page_count >= 1:
            cover = _normalize_spaces(doc[0].get_text() or "")
            if cover:
                guideline_pages.append(
                    GuidelinePage(
                        page_id=f"page-{profile.source_key}-1",
                        pdf_page=1,
                        page_type="front_matter",
                        clean_text=cover[:4000],
                        source=profile.source_key,
                    )
                )

        current_section = "Introduction"
        section_bufs: Dict[str, List[Tuple[int, str, List[str]]]] = {}
        ref_mode = False
        ref_buf: List[str] = []
        seen_table_pages: set[int] = set()

        def flush_section(section: str) -> None:
            nonlocal discussion_chunks
            pieces = section_bufs.pop(section, [])
            if not pieces:
                return
            if skip_section_re.match(section.strip()):
                return
            # Front-matter style sections → GuidelinePage (not BM25-indexed as discussion)
            if section.strip().upper() in {s.upper() for s in profile.front_matter_sections}:
                text = _normalize_spaces("\n\n".join(t for _, t, _ in pieces))
                if text:
                    pdf_page = pieces[0][0]
                    guideline_pages.append(
                        GuidelinePage(
                            page_id=f"page-{profile.source_key}-{_section_slug(section)}",
                            pdf_page=pdf_page,
                            page_type="front_matter",
                            clean_text=text[:5000],
                            source=profile.source_key,
                        )
                    )
                return
            # Merge by page then chunk
            by_page: Dict[int, Tuple[List[str], List[str]]] = {}
            for pdf_page, text, refs in pieces:
                texts, rids = by_page.setdefault(pdf_page, ([], []))
                texts.append(text)
                for r in refs:
                    if r not in rids:
                        rids.append(r)
            chunk_idx = sum(1 for c in discussion_chunks if c.section == section)
            for pdf_page in sorted(by_page):
                texts, rids = by_page[pdf_page]
                body = _normalize_spaces("\n".join(texts))
                # Drop dense table-caption noise lines when we already have VLM tables.
                if pdf_page in tables_by_page:
                    kept = []
                    for ln in body.splitlines():
                        if re.search(r"T\s*A\s*B\s*L\s*E\s+[A-Z]?\d+", ln, re.I):
                            continue
                        kept.append(ln)
                    body = _normalize_spaces("\n".join(kept))
                if len(body) < 40:
                    continue
                caption = f"[{profile.doc_title} · {section}]"
                for piece in _split_long_text(body, max_chars=1400):
                    discussion_chunks.append(
                        DiscussionChunk(
                            chunk_id=f"disc-{profile.article_id}-p{pdf_page}-c{chunk_idx}",
                            article_id=profile.article_id,
                            article_title=profile.doc_title,
                            pdf_page=pdf_page,
                            ms_page_code=None,
                            section=section,
                            clean_text=f"{caption}\n{piece}",
                            reference_ids=list(rids),
                            source=profile.source_key,
                            content_type="text",
                        )
                    )
                    chunk_idx += 1

        for u in all_units:
            first_line = u.text.split("\n", 1)[0].strip()
            upper_first = first_line.upper()

            if upper_first == ref_hint or upper_first.startswith(ref_hint + " "):
                flush_section(current_section)
                ref_mode = True
                # Remainder after REFERENCES header on same unit.
                rest = "\n".join(u.text.split("\n")[1:]).strip()
                if rest:
                    ref_buf.append(rest)
                continue

            if ref_mode:
                ref_buf.append(u.text)
                continue

            if u.is_table_caption:
                # Emit VLM tables once per page.
                if u.pdf_page not in seen_table_pages and u.pdf_page in tables_by_page:
                    seen_table_pages.add(u.pdf_page)
                    for t_idx, md in enumerate(tables_by_page[u.pdf_page]):
                        discussion_chunks.append(
                            DiscussionChunk(
                                chunk_id=f"disc-{profile.article_id}-p{u.pdf_page}-t{t_idx}",
                                article_id=profile.article_id,
                                article_title=profile.doc_title,
                                pdf_page=u.pdf_page,
                                ms_page_code=None,
                                section=current_section if current_section else "Tables",
                                clean_text=md,
                                reference_ids=list(u.reference_ids),
                                source=profile.source_key,
                                content_type="table",
                            )
                        )
                continue

            if u.is_heading:
                flush_section(current_section)
                # Heading may include body after first line.
                lines = u.text.split("\n")
                current_section = lines[0].strip().title() if not _is_allcaps_heading(lines[0]) else lines[0].strip()
                # Normalize ALL CAPS titles to Title Case for display, keep meaning.
                if _is_allcaps_heading(current_section):
                    current_section = current_section.title()
                    # Keep known acronyms uppercase-ish
                    current_section = re.sub(
                        r"\bLbcl\b", "LBCL", current_section
                    )
                    current_section = re.sub(r"\b1l\b", "1L", current_section, flags=re.I)
                body = "\n".join(lines[1:]).strip()
                if body and not skip_section_re.match(current_section):
                    section_bufs.setdefault(current_section, []).append(
                        (u.pdf_page, body, list(u.reference_ids))
                    )
                continue

            if skip_section_re.match(current_section):
                continue
            section_bufs.setdefault(current_section, []).append(
                (u.pdf_page, u.text, list(u.reference_ids))
            )

        flush_section(current_section)

        # Any table pages not yet emitted (caption-less detection miss).
        for pdf_page, mds in tables_by_page.items():
            if pdf_page in seen_table_pages:
                continue
            for t_idx, md in enumerate(mds):
                discussion_chunks.append(
                    DiscussionChunk(
                        chunk_id=f"disc-{profile.article_id}-p{pdf_page}-t{t_idx}",
                        article_id=profile.article_id,
                        article_title=profile.doc_title,
                        pdf_page=pdf_page,
                        ms_page_code=None,
                        section="Tables",
                        clean_text=md,
                        reference_ids=[],
                        source=profile.source_key,
                        content_type="table",
                    )
                )

        if ref_buf:
            reference_entries = _parse_references(
                profile.article_id, profile.source_key, "\n".join(ref_buf)
            )

        # Deduplicate chunk ids if collisions.
        seen_ids: set[str] = set()
        for c in discussion_chunks:
            base = c.chunk_id
            n = 1
            while c.chunk_id in seen_ids:
                c.chunk_id = f"{base}-x{n}"
                n += 1
            seen_ids.add(c.chunk_id)

        stats = {
            "source": profile.source_key,
            "doc_title": profile.doc_title,
            "document_version": profile.document_version,
            "pdf_path": str(path),
            "pdf_page_count": doc.page_count,
            "guideline_page_count": len(guideline_pages),
            "discussion_chunk_count": len(discussion_chunks),
            "reference_entry_count": len(reference_entries),
            "table_chunk_count": sum(
                1 for c in discussion_chunks if c.content_type == "table"
            ),
            "table_targets": [
                {"pdf_page": p, "caption": c} for p, c in table_targets
            ],
            "sections": sorted({c.section for c in discussion_chunks}),
            "evidence_levels": EHA_EVIDENCE_LEVELS if profile.source_key == "eha" else {},
            "recommendation_grades": (
                EHA_RECOMMENDATION_GRADES if profile.source_key == "eha" else {}
            ),
        }
        return StructuredKnowledgeBase(
            guideline_pages=guideline_pages,
            discussion_chunks=discussion_chunks,
            reference_entries=reference_entries,
            stats=stats,
            source=profile.source_key,
        )
    finally:
        doc.close()
