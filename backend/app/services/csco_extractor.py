"""CSCO Lymphoma Diagnosis & Treatment Guidelines PDF extractor.

Parses the OCR PDF into a StructuredKnowledgeBase compatible with the existing
retrieval schema:

  - DiscussionChunk : narrative notes + treatment tables (as Markdown)
  - ReferenceEntry  : per-chapter numbered references
  - GuidelinePage   : front matter / evidence legend pages (not BM25-indexed)

CSCO structure (2025, 320 PDF pages):
  PDF 1–18   : cover, copyright, TOC (printed pages before ·1)
  PDF 19–20  : evidence categories + recommendation levels
  PDF 21–301 : disease / topic chapters (header = chapter title)
  PDF 302–320: appendices

Printed page ≈ PDF page − 18 (detected at runtime from TOC).
No flowchart / VLM pages — tables are extracted programmatically.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from backend.app.models import (
    DiscussionChunk,
    GuidelinePage,
    ReferenceEntry,
    StructuredKnowledgeBase,
)
from backend.app.services.csco_table_extractor import extract_tables_as_markdown

try:
    import fitz  # PyMuPDF
except ImportError:  # pragma: no cover
    fitz = None


DOC_TITLE = "中国临床肿瘤学会(CSCO)淋巴瘤诊疗指南 2025"
DOCUMENT_VERSION = "2025"
SOURCE_KEY = "csco"


# ── Evidence legend (PDF p19–p20; allowed hardcode) ────────────────────────

EVIDENCE_CATEGORIES: Dict[str, Dict[str, str]] = {
    "1A": {
        "level": "高",
        "source": "严谨的meta分析、大型随机对照研究",
        "consensus": "一致共识（支持意见≥80%）",
    },
    "1B": {
        "level": "高",
        "source": "严谨的meta分析、大型随机对照研究",
        "consensus": "基本一致共识（支持意见60%～<80%）",
    },
    "2A": {
        "level": "稍低",
        "source": "一般质量的meta分析、小型随机对照研究、设计良好的大型回顾性研究、病例-对照研究",
        "consensus": "一致共识（支持意见≥80%）",
    },
    "2B": {
        "level": "稍低",
        "source": "一般质量的meta分析、小型随机对照研究、设计良好的大型回顾性研究、病例-对照研究",
        "consensus": "基本一致共识（支持意见60%～<80%）",
    },
    "3": {
        "level": "低",
        "source": "非对照的单臂临床研究、病例报告、专家观点",
        "consensus": "无共识，且争议大（支持意见<60%）",
    },
}

RECOMMENDATION_LEVELS: Dict[str, str] = {
    "I": "1A类证据和部分2A类证据；专家共识度高且中国可及性好，纳入国家医保目录的诊治措施",
    "II": "1B类证据和部分2A类证据；高级别证据但可及性欠佳或效价比不高，或临床获益明显但价格较贵",
    "III": "2B类证据和3类证据；临床习惯使用或有探索价值、专家组可接受的诊治措施",
}


def evidence_legend_prompt_block() -> str:
    """Compact legend text for CSCO system / planner prompts."""
    lines = [
        "【CSCO 证据类别】",
        "1A=高证据+一致共识(≥80%)；1B=高证据+基本一致(60%～<80%)；",
        "2A=稍低证据+一致共识；2B=稍低证据+基本一致；3=低证据+争议大(<60%)。",
        "【CSCO 推荐等级】",
        "I级=1A及部分可及性好的2A；II级=1B及部分可及性欠佳的2A；III级=2B与3类。",
        "表格单元格内 [1A类]/[2A类] 等为证据类别；上标数字为该章参考文献编号。",
    ]
    return "\n".join(lines)


# ── Chapter title → article_id (minimal hardcode) ─────────────────────────

CHAPTER_CATALOG: List[Tuple[str, str]] = [
    ("CSCO诊疗指南证据类别", "evidence-categories"),
    ("CSCO诊疗指南推荐等级", "recommendation-levels"),
    ("总则", "general"),
    ("淋巴瘤病理学诊断", "pathology"),
    ("弥漫大B细胞淋巴瘤", "dlbcl"),
    ("高级别B细胞淋巴瘤", "hgbl"),
    ("原发纵隔大B细胞淋巴瘤", "pmbl"),
    ("原发乳腺弥漫大B细胞淋巴瘤", "primary-breast-dlbcl"),
    ("原发睾丸弥漫大B细胞淋巴瘤", "primary-testicular-dlbcl"),
    ("原发中枢神经系统淋巴瘤", "pcnsl"),
    ("滤泡性淋巴瘤", "fl"),
    ("套细胞淋巴瘤", "mcl"),
    ("边缘区淋巴瘤", "mzl"),
    ("伯基特淋巴瘤", "burkitt"),
    ("慢性淋巴细胞白血病", "cll"),
    ("外周T细胞淋巴瘤", "ptcl"),
    ("结外NK/T细胞淋巴瘤", "nktcl"),
    ("结外NK/T 细胞淋巴瘤", "nktcl"),
    ("霍奇金淋巴瘤", "hl"),
    ("Castleman病", "castleman"),
    ("原发性皮肤淋巴瘤", "cutaneous"),
    ("免疫检查点抑制剂在淋巴瘤中的应用", "ici"),
    ("淋巴瘤临床试验", "clinical-trials"),
    ("附录", "appendix"),
    ("附录1", "appendix-1"),
    ("附录2", "appendix-2"),
    ("附录3", "appendix-3"),
    ("附录4", "appendix-4"),
]

# Longer titles first for greedy matching
_CHAPTER_BY_LEN = sorted(CHAPTER_CATALOG, key=lambda t: len(t[0]), reverse=True)

# Chapters treated as always-retrievable support material when disease-scoped
COMMON_ARTICLE_IDS: List[str] = [
    "general",
    "pathology",
    "evidence-categories",
    "recommendation-levels",
    "appendix",
    "appendix-1",
    "appendix-2",
    "appendix-3",
    "appendix-4",
]


# Disease name aliases (Chinese full name + English acronym) baked into each
# chunk's searchable text. The guideline body is written in Chinese, so an
# English-acronym query ("DLBCL") would otherwise never match a chapter whose
# prose only says "弥漫大B细胞淋巴瘤". Allowed hardcode (per project brief).
ARTICLE_ALIASES: Dict[str, List[str]] = {
    "general": ["总则"],
    "pathology": ["淋巴瘤病理学诊断", "病理诊断"],
    "dlbcl": ["弥漫大B细胞淋巴瘤", "DLBCL"],
    "hgbl": ["高级别B细胞淋巴瘤", "HGBL", "双打击淋巴瘤", "三打击淋巴瘤"],
    "pmbl": ["原发纵隔大B细胞淋巴瘤", "PMBL"],
    "primary-breast-dlbcl": ["原发乳腺弥漫大B细胞淋巴瘤", "原发乳腺DLBCL"],
    "primary-testicular-dlbcl": ["原发睾丸弥漫大B细胞淋巴瘤", "原发睾丸DLBCL", "PTDLBCL"],
    "pcnsl": ["原发中枢神经系统淋巴瘤", "PCNSL"],
    "fl": ["滤泡性淋巴瘤", "FL"],
    "mcl": ["套细胞淋巴瘤", "MCL"],
    "mzl": ["边缘区淋巴瘤", "MZL"],
    "burkitt": ["伯基特淋巴瘤", "BL"],
    "cll": ["慢性淋巴细胞白血病", "小淋巴细胞淋巴瘤", "CLL", "SLL"],
    "ptcl": ["外周T细胞淋巴瘤", "PTCL"],
    "nktcl": ["结外NK/T细胞淋巴瘤", "NKTCL"],
    "hl": ["霍奇金淋巴瘤", "HL"],
    "castleman": ["Castleman病", "巨大淋巴结增生症"],
    "cutaneous": ["原发性皮肤淋巴瘤"],
    "ici": ["免疫检查点抑制剂"],
    "clinical-trials": ["淋巴瘤临床试验"],
    "evidence-categories": ["CSCO诊疗指南证据类别"],
    "recommendation-levels": ["CSCO诊疗指南推荐等级"],
    "appendix": ["附录"],
    "appendix-1": ["附录1", "Lugano分期"],
    "appendix-2": ["附录2"],
    "appendix-3": ["附录3"],
    "appendix-4": ["附录4"],
}


def _alias_label(article_id: str, article_title: str) -> str:
    aliases = ARTICLE_ALIASES.get(article_id)
    if aliases:
        return " ".join(aliases)
    return article_title or article_id


def _chunk_caption(article_id: str, article_title: str, section: str) -> str:
    """Disease + section caption prepended to a chunk (display + BM25 search)."""
    label = _alias_label(article_id, article_title)
    sec = section if section and section not in ("正文", "表格", "图例") else ""
    return f"{label} · {sec}".strip(" ·") if sec else label


_SECTION_RE = re.compile(
    r"^(\d+(?:\.\d+)*)\s+(.+?)\s*$",
)
_REF_HEADER_RE = re.compile(r"^参考文献\s*$")
# Line-anchored (MULTILINE) header used to split a page into pre-ref / ref parts.
_REF_HEADER_LINE_RE = re.compile(r"^\s*参考文献\s*$", re.M)
_REF_ENTRY_RE = re.compile(
    r"^\[(\d+)\]\s*(.+)$",
)
_INLINE_REF_RE = re.compile(
    r"(?:\[|\】)?(\d+(?:\s*[-–—～~]\s*\d+)?)(?:\]|】)?(?=\[(?:\d|[1-3][AB]?类)|$|[^\d])",
)
_EVIDENCE_TAG_RE = re.compile(r"\[([1-3][AB]?类)\]")
_NOISE_LINE_RE = re.compile(
    r"^("
    r"肿瘤医师资讯\s*[（(]Onco\s*Info[）)]"
    r"|版权所有"
    r")\s*$",
    re.I,
)
_PAGE_NUM_ONLY_RE = re.compile(r"^\d{1,3}$")
_PMID_RE = re.compile(r"PMID[:\s]*(\d+)", re.I)
_DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.I)


@dataclass(frozen=True)
class CscoChapter:
    article_id: str
    title: str
    pdf_start: int
    pdf_end: int


def resolve_chapter_id(text: str) -> Optional[Tuple[str, str]]:
    """Match a header/footer line to (article_id, canonical_title)."""
    if not text:
        return None
    cleaned = text.strip().replace(" ", "")
    for title, article_id in _CHAPTER_BY_LEN:
        key = title.replace(" ", "")
        if cleaned == key or cleaned.startswith(key) or key in cleaned:
            return article_id, title
    return None


def _clean_page_text(raw: str, *, chapter_title: Optional[str] = None) -> str:
    kept: List[str] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            kept.append("")
            continue
        if _NOISE_LINE_RE.match(stripped):
            continue
        if _PAGE_NUM_ONLY_RE.match(stripped):
            continue
        if chapter_title and stripped.replace(" ", "") == chapter_title.replace(" ", ""):
            continue
        kept.append(stripped)
    text = "\n".join(kept)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _detect_printed_offset(doc) -> int:
    """Infer printed_page = pdf_page - offset from the evidence-category page (not TOC)."""
    for i in range(min(30, doc.page_count)):
        text = doc[i].get_text() or ""
        compact = text.replace(" ", "").replace("\u3000", "")
        # TOC lines look like "CSCO诊疗指南证据类别·1"; the real page has the table body.
        if "CSCO诊疗指南证据类别" not in compact:
            continue
        if "证据特征" not in compact and "1A" not in compact:
            continue
        for line in reversed(text.splitlines()):
            if _PAGE_NUM_ONLY_RE.match(line.strip()):
                printed = int(line.strip())
                if 1 <= printed <= 5:
                    return (i + 1) - printed
        return (i + 1) - 1
    return 18


def _detect_chapter_from_page(page_text: str) -> Optional[Tuple[str, str]]:
    lines = [ln.strip() for ln in page_text.splitlines() if ln.strip()]
    # Headers usually in first 3 / last 3 lines
    candidates = lines[:4] + lines[-3:]
    for line in candidates:
        hit = resolve_chapter_id(line)
        if hit and hit[0] not in ("evidence-categories", "recommendation-levels"):
            return hit
    for line in candidates:
        hit = resolve_chapter_id(line)
        if hit:
            return hit
    return None


def _build_chapter_map(doc, offset: int) -> List[CscoChapter]:
    """Walk pages and group consecutive pages sharing the same chapter id."""
    page_ids: List[Optional[Tuple[str, str]]] = []
    for i in range(doc.page_count):
        text = doc[i].get_text() or ""
        page_ids.append(_detect_chapter_from_page(text))

    # Forward-fill unknown pages from nearest known chapter (skip true front matter)
    last: Optional[Tuple[str, str]] = None
    filled: List[Optional[Tuple[str, str]]] = []
    for i, hit in enumerate(page_ids):
        pdf_page = i + 1
        if pdf_page <= offset:  # before printed ·1
            filled.append(("front-matter", "前言与目录") if pdf_page > 1 else ("cover", "封面"))
            continue
        if hit:
            last = hit
            filled.append(hit)
        elif last:
            filled.append(last)
        else:
            filled.append(("general", "总则"))

    chapters: List[CscoChapter] = []
    if not filled:
        return chapters
    start = 1
    cur = filled[0]
    for i in range(1, len(filled) + 1):
        if i == len(filled) or filled[i] != cur:
            assert cur is not None
            chapters.append(
                CscoChapter(
                    article_id=cur[0],
                    title=cur[1],
                    pdf_start=start,
                    pdf_end=i,
                )
            )
            if i < len(filled):
                start = i + 1
                cur = filled[i]
    return chapters


def _extract_inline_ref_ids(text: str) -> List[str]:
    ids: List[str] = []
    # Prefer explicit [n] / [n-m] near evidence tags or after treatments
    for m in re.finditer(r"\[(\d+(?:\s*[-–—～~]\s*\d+)?)\]", text):
        token = m.group(1)
        if re.search(r"类", token):
            continue
        if re.search(r"[-–—～~]", token):
            parts = re.split(r"[-–—～~]", token)
            try:
                a, b = int(parts[0]), int(parts[-1])
                if 0 < a <= b <= 200 and b - a <= 30:
                    ids.extend(str(n) for n in range(a, b + 1))
            except ValueError:
                pass
        else:
            try:
                n = int(token)
                if 1 <= n <= 200:
                    ids.append(str(n))
            except ValueError:
                pass
    # Dedupe preserve order
    seen = set()
    out: List[str] = []
    for x in ids:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _leading_section(clean: str) -> Optional[str]:
    """Best-effort section title from the first lines of a page (table caption)."""
    for line in clean.splitlines()[:8]:
        stripped = line.strip()
        m = _SECTION_RE.match(stripped)
        if m and len(m.group(2)) < 40 and not m.group(2).startswith(("①", "②", "③", "④", "⑤")):
            return f"{m.group(1)} {m.group(2)}".strip()
    return None


def _is_table_reflow(body: str) -> bool:
    """Heuristic: narrative that is really a table's cells re-flowed as text."""
    b = body.strip()
    if not b:
        return True
    sentences = len(re.findall(r"[。！？]", b))
    has_table_words = bool(re.search(r"级推荐|分层|分组|Ⅱ级|Ⅲ级|I级", b))
    if has_table_words and sentences <= 1:
        return True
    if sentences == 0 and len(b) < 400:
        return True
    return False


def _split_sections(clean: str) -> List[Tuple[str, str]]:
    """Split chapter page text into (section_title, body) parts."""
    lines = clean.splitlines()
    sections: List[Tuple[str, List[str]]] = []
    current_title = "正文"
    current_lines: List[str] = []

    for line in lines:
        stripped = line.strip()
        if _REF_HEADER_RE.match(stripped):
            if current_lines:
                sections.append((current_title, current_lines))
            current_title = "参考文献"
            current_lines = []
            continue
        m = _SECTION_RE.match(stripped)
        if m and len(m.group(2)) < 40:
            # Avoid matching numbered list items inside tables (too long / starts with ①)
            title_body = m.group(2)
            if not title_body.startswith(("①", "②", "③", "④", "⑤")):
                if current_lines:
                    sections.append((current_title, current_lines))
                current_title = f"{m.group(1)} {title_body}".strip()
                current_lines = []
                continue
        current_lines.append(line)

    if current_lines:
        sections.append((current_title, current_lines))
    return [(t, "\n".join(ls).strip()) for t, ls in sections if "\n".join(ls).strip()]


def _parse_references(article_id: str, text: str) -> List[ReferenceEntry]:
    entries: List[ReferenceEntry] = []
    # Join soft line-breaks: lines not starting with [n] continue previous
    blocks: List[Tuple[str, List[str]]] = []
    current_num: Optional[str] = None
    current_lines: List[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        m = _REF_ENTRY_RE.match(stripped)
        if m:
            if current_num is not None:
                blocks.append((current_num, current_lines))
            current_num = m.group(1)
            current_lines = [m.group(2).strip()]
        elif current_num is not None:
            current_lines.append(stripped)
    if current_num is not None:
        blocks.append((current_num, current_lines))

    for num, parts in blocks:
        body = " ".join(parts)
        body = re.sub(r"\s+", " ", body).strip()
        pmid = None
        doi = None
        url = None
        pm = _PMID_RE.search(body)
        if pm:
            pmid = pm.group(1)
            url = f"https://www.ncbi.nlm.nih.gov/pubmed/{pmid}"
        dm = _DOI_RE.search(body)
        if dm:
            doi = dm.group(0).rstrip(".")
        entries.append(
            ReferenceEntry(
                entry_id=f"ref-{article_id}-{num}",
                article_id=article_id,
                ref_number=num,
                text=body,
                pmid=pmid,
                doi=doi,
                url=url,
                source=SOURCE_KEY,
            )
        )
    return entries


def _normalize_range_tildes(text: str) -> str:
    """ASCII ~ ranges → fullwidth ～ so Markdown never renders <del>."""
    return re.sub(r"([0-9A-Za-z])\s*~\s*([0-9A-Za-z])", r"\1～\2", text or "")


def _chunk_narrative(
    *,
    article_id: str,
    article_title: str,
    pdf_page: int,
    section: str,
    text: str,
    chunk_idx: int,
    content_type: str = "text",
) -> DiscussionChunk:
    text = _normalize_range_tildes(text)
    refs = _extract_inline_ref_ids(text)
    return DiscussionChunk(
        chunk_id=f"disc-{article_id}-p{pdf_page}-c{chunk_idx}",
        article_id=article_id,
        article_title=article_title,
        pdf_page=pdf_page,
        ms_page_code=None,
        section=section,
        clean_text=text,
        reference_ids=refs,
        content_type=content_type,
        source=SOURCE_KEY,
    )


def build_csco_knowledge_base(pdf_path: Path | str) -> StructuredKnowledgeBase:
    if fitz is None:
        raise RuntimeError("PyMuPDF (fitz) is required to build the CSCO knowledge base.")

    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"CSCO PDF not found: {path}")

    doc = fitz.open(str(path))
    try:
        offset = _detect_printed_offset(doc)
        chapters = _build_chapter_map(doc, offset)

        guideline_pages: List[GuidelinePage] = []
        discussion_chunks: List[DiscussionChunk] = []
        reference_entries: List[ReferenceEntry] = []
        chunk_counters: Dict[str, int] = {}

        # Front matter pages
        for i in range(min(offset, doc.page_count)):
            pdf_page = i + 1
            raw = doc[i].get_text() or ""
            clean = _clean_page_text(raw)
            page_type = "front_matter"
            if "证据类别" in clean:
                page_type = "front_matter"
            guideline_pages.append(
                GuidelinePage(
                    page_id=f"csco-page-{pdf_page}",
                    pdf_page=pdf_page,
                    page_type=page_type,
                    clean_text=clean,
                    source=SOURCE_KEY,
                )
            )

        # Evidence legend pages as searchable discussion chunks
        for i in range(offset, min(offset + 2, doc.page_count)):
            pdf_page = i + 1
            raw = doc[i].get_text() or ""
            if "证据类别" in raw:
                aid, title = "evidence-categories", "CSCO诊疗指南证据类别"
                body = evidence_legend_prompt_block() + "\n\n" + _clean_page_text(raw, chapter_title=title)
            elif "推荐等级" in raw:
                aid, title = "recommendation-levels", "CSCO诊疗指南推荐等级"
                body = evidence_legend_prompt_block() + "\n\n" + _clean_page_text(raw, chapter_title=title)
            else:
                continue
            idx = chunk_counters.get(aid, 0)
            discussion_chunks.append(
                _chunk_narrative(
                    article_id=aid,
                    article_title=title,
                    pdf_page=pdf_page,
                    section="图例",
                    text=body,
                    chunk_idx=idx,
                )
            )
            chunk_counters[aid] = idx + 1

        for chapter in chapters:
            if chapter.article_id in ("cover", "front-matter"):
                continue
            if chapter.article_id in ("evidence-categories", "recommendation-levels"):
                continue

            ref_buffer: List[str] = []
            in_refs = False

            for pdf_page in range(chapter.pdf_start, chapter.pdf_end + 1):
                page = doc[pdf_page - 1]
                raw = page.get_text() or ""
                clean = _clean_page_text(raw, chapter_title=chapter.title)
                if not clean.strip():
                    continue

                # Once past 参考文献 in this chapter, the rest is all references.
                if in_refs:
                    ref_buffer.append(clean)
                    continue

                # Detect a 参考文献 boundary on this page (line-anchored). Split
                # into pre-ref content (tables + narrative) and the reference tail
                # so citation lists never get indexed as clinical tables.
                table_y_max: Optional[float] = None
                ref_match = _REF_HEADER_LINE_RE.search(clean)
                if ref_match:
                    pre_ref = clean[: ref_match.start()].strip()
                    post_ref = clean[ref_match.end():].strip()
                    if post_ref:
                        ref_buffer.append(post_ref)
                    in_refs = True
                    clean = pre_ref
                    try:
                        rects = page.search_for("参考文献")
                        if rects:
                            table_y_max = min(r.y0 for r in rects)
                    except Exception:
                        table_y_max = None
                    if not clean.strip():
                        continue

                page_section = _leading_section(clean) or "表格"

                # Tables first (Markdown chunks), clipped above any reference block.
                caption = _chunk_caption(chapter.article_id, chapter.title, page_section)
                table_mds = extract_tables_as_markdown(
                    page, section_hint=caption, y_max=table_y_max
                )
                used_table_text = False
                for md in table_mds:
                    idx = chunk_counters.get(chapter.article_id, 0)
                    discussion_chunks.append(
                        _chunk_narrative(
                            article_id=chapter.article_id,
                            article_title=chapter.title,
                            pdf_page=pdf_page,
                            section=page_section,
                            text=md,
                            chunk_idx=idx,
                            content_type="table",
                        )
                    )
                    chunk_counters[chapter.article_id] = idx + 1
                    used_table_text = True

                # Narrative sections
                sections = _split_sections(clean)
                for section_title, body in sections:
                    if section_title == "参考文献":
                        in_refs = True
                        ref_buffer.append(body)
                        continue
                    # When a table was already stored for this page, the narrative
                    # split usually re-flows the same cells → drop it to avoid
                    # duplicate BM25 noise, but keep any 【注释】 annotation prose.
                    if used_table_text:
                        note_parts = re.split(r"【注释】", body)
                        if len(note_parts) > 1:
                            body = "【注释】" + "【注释】".join(note_parts[1:])
                        elif _is_table_reflow(body):
                            continue
                    if len(body.strip()) < 20:
                        continue
                    # Chunk long narrative ~1200 chars, each prefixed with the
                    # disease/section caption so acronym queries can match.
                    section_caption = _chunk_caption(
                        chapter.article_id, chapter.title, section_title
                    )
                    pieces = _split_long_text(body, max_chars=1200)
                    for piece in pieces:
                        idx = chunk_counters.get(chapter.article_id, 0)
                        text_with_ctx = f"{section_caption}\n{piece}" if section_caption else piece
                        discussion_chunks.append(
                            _chunk_narrative(
                                article_id=chapter.article_id,
                                article_title=chapter.title,
                                pdf_page=pdf_page,
                                section=section_title,
                                text=text_with_ctx,
                                chunk_idx=idx,
                                content_type="text",
                            )
                        )
                        chunk_counters[chapter.article_id] = idx + 1

            if ref_buffer:
                reference_entries.extend(
                    _parse_references(chapter.article_id, "\n".join(ref_buffer))
                )

        article_counts: Dict[str, int] = {}
        for c in discussion_chunks:
            article_counts[c.article_id] = article_counts.get(c.article_id, 0) + 1

        stats = {
            "source": SOURCE_KEY,
            "doc_title": DOC_TITLE,
            "document_version": DOCUMENT_VERSION,
            "pdf_path": str(path),
            "pdf_page_count": doc.page_count,
            "printed_page_offset": offset,
            "guideline_page_count": len(guideline_pages),
            "discussion_chunk_count": len(discussion_chunks),
            "reference_entry_count": len(reference_entries),
            "table_chunk_count": sum(
                1 for c in discussion_chunks if getattr(c, "content_type", "text") == "table"
            ),
            "chapters": [
                {
                    "article_id": ch.article_id,
                    "title": ch.title,
                    "pdf_start": ch.pdf_start,
                    "pdf_end": ch.pdf_end,
                }
                for ch in chapters
            ],
            "chunks_per_article": article_counts,
            "evidence_categories": EVIDENCE_CATEGORIES,
            "recommendation_levels": RECOMMENDATION_LEVELS,
        }

        return StructuredKnowledgeBase(
            guideline_pages=guideline_pages,
            discussion_chunks=discussion_chunks,
            reference_entries=reference_entries,
            stats=stats,
            source=SOURCE_KEY,
        )
    finally:
        doc.close()


def _split_long_text(text: str, max_chars: int = 1200) -> List[str]:
    text = text.strip()
    if len(text) <= max_chars:
        return [text] if text else []
    # Split on blank lines / Chinese period
    paras = re.split(r"\n\s*\n|(?<=[。！？])\s*", text)
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
