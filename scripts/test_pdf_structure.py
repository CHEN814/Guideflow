"""临时脚本：测试 PyMuPDF 能否解析 NCCN PDF 结构并拆分 front_matter / guideline / discussion。

用法:
    python scripts/test_pdf_structure.py
    python scripts/test_pdf_structure.py --pdf "（2026.V3）NCCN临床 实践指南：B细胞淋巴瘤.pdf"
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.services.pdf_extractor import (  # noqa: E402
    PageRanges,
    _clean_text,
    _extract_footer_code,
    _extract_ms_code,
    _is_toc_page,
)
from backend.app.settings import load_settings

try:
    import fitz  # PyMuPDF
except ImportError:  # pragma: no cover
    fitz = None


@dataclass
class SectionProbe:
    name: str
    start: int | None
    end: int | None
    method: str
    confidence: str
    notes: list[str]


def _first_pdf(root: Path) -> Path:
    pdfs = sorted(root.glob("*.pdf"))
    if not pdfs:
        raise FileNotFoundError(f"No PDF found under {root}")
    return pdfs[0]


def probe_builtin_structure(pdf: fitz.Document) -> dict[str, Any]:
    """PyMuPDF 内置结构：书签 TOC、metadata、page labels。"""
    toc = pdf.get_toc(simple=False)  # [level, title, page, dest_dict?]
    metadata = pdf.metadata or {}
    page_labels = []
    try:
        for i in range(len(pdf)):
            label = pdf.get_page_labels()[i] if hasattr(pdf, "get_page_labels") else None
            page_labels.append(label)
    except Exception:
        page_labels = []

    return {
        "page_count": len(pdf),
        "metadata": {k: v for k, v in metadata.items() if v},
        "toc_entry_count": len(toc),
        "toc_sample": [
            {"level": lvl, "title": title, "page": page}
            for lvl, title, page, *_ in toc[:30]
        ],
        "toc_has_discussion": any(
            "discussion" in (title or "").lower() for _, title, *_ in toc
        ),
        "page_labels_available": bool(page_labels),
    }


def _extract_ms_footer_code(page) -> str | None:
    """Discussion 页右下角 MS-* 页码（与指南页 BCEL-* 不同，被 _extract_footer_code 排除）。"""
    rect = page.rect
    page_height = rect.height
    page_width = rect.width
    ms_re = re.compile(r"^MS-\d+$", re.IGNORECASE)
    for block in page.get_text("blocks"):
        if len(block) < 5:
            continue
        x0, y0, _x1, _y1, raw_text = block[:5]
        if y0 < page_height * 0.85 or x0 < page_width * 0.5:
            continue
        for line in raw_text.splitlines():
            token = line.strip()
            if ms_re.match(token):
                return token.upper()
    return None


def scan_page_signals(pdf: fitz.Document) -> list[dict[str, Any]]:
    """逐页扫描 footer code / MS code / 文本特征。"""
    rows: list[dict[str, Any]] = []
    for idx in range(len(pdf)):
        page_num = idx + 1
        page = pdf[idx]
        raw = page.get_text("text")
        clean = _clean_text(raw)
        footer = _extract_footer_code(page)
        ms_footer = _extract_ms_footer_code(page)
        ms = _extract_ms_code(clean) or ms_footer
        preview = clean[:120].replace("\n", " ") if clean else ""

        rows.append(
            {
                "page": page_num,
                "footer_code": footer,
                "ms_footer": ms_footer,
                "ms_code": ms,
                "is_toc": _is_toc_page(clean) if clean else False,
                "text_len": len(clean),
                "preview": preview,
            }
        )
    return rows


def detect_sections(rows: list[dict[str, Any]]) -> list[SectionProbe]:
    """基于页级信号启发式推断三段边界（不依赖硬编码页码）。"""
    notes: list[str] = []

    # 1) 第一页出现 footer code（BCEL-* 等）=> 指南段开始
    guideline_pages = [r["page"] for r in rows if r["footer_code"]]
    guideline_start = min(guideline_pages) if guideline_pages else None

    # 2) discussion 起点：第一页 MS footer 或 discussion TOC 页
    ms_footer_pages = [r["page"] for r in rows if r["ms_footer"]]
    toc_pages = [r["page"] for r in rows if r["is_toc"]]
    discussion_candidates = ms_footer_pages + toc_pages
    discussion_start = min(discussion_candidates) if discussion_candidates else None

    # 3) front matter = 1 .. guideline_start-1
    front_start = 1
    front_end = (guideline_start - 1) if guideline_start and guideline_start > 1 else None

    # 4) 指南段结束 = discussion 前一页，或最后一个 footer code 页
    if discussion_start and guideline_start:
        guideline_end = discussion_start - 1
    elif guideline_pages:
        guideline_end = max(guideline_pages)
        notes.append("未检测到 MS 页码，指南段结束取最后一个 footer code 页")
    else:
        guideline_end = None

    discussion_end = rows[-1]["page"] if rows else None

    # 5) 用 TOC 关键词交叉验证
    if toc_pages and discussion_start:
        first_toc = min(toc_pages)
        if abs(first_toc - discussion_start) <= 3:
            notes.append(f"discussion 起点与 TOC 页 ({first_toc}) 接近，信号一致")
        else:
            notes.append(
                f"discussion 起点 ({discussion_start}) 与 TOC 页 ({first_toc}) 相差较远，需人工核对"
            )

    def _conf(start: int | None, end: int | None) -> str:
        if start is None or end is None or start > end:
            return "low"
        span = end - start + 1
        if span <= 0:
            return "low"
        return "high" if span >= 3 else "medium"

    return [
        SectionProbe(
            "front_matter",
            front_start,
            front_end,
            "无 footer code 的前置页",
            _conf(front_start, front_end),
            notes.copy(),
        ),
        SectionProbe(
            "clinical_guideline",
            guideline_start,
            guideline_end,
            "footer code (BCEL-*/MANT-* 等) 连续区间",
            _conf(guideline_start, guideline_end),
            [f"含 footer code 的页数: {len(guideline_pages)}"],
        ),
        SectionProbe(
            "discussion",
            discussion_start,
            discussion_end,
            "MS-* 页码 + discussion TOC/参考文献结构",
            _conf(discussion_start, discussion_end),
            [
                f"含 MS footer 的页数: {len(ms_footer_pages)}",
                f"discussion TOC 页: {toc_pages[:5]}",
            ],
        ),
    ]


def compare_with_hardcoded(detected: list[SectionProbe], hardcoded: PageRanges) -> None:
    expected = {
        "front_matter": (hardcoded.front_matter_start, hardcoded.front_matter_end),
        "clinical_guideline": (
            hardcoded.clinical_guideline_start,
            hardcoded.clinical_guideline_end,
        ),
        "discussion": (hardcoded.discussion_start, None),
    }
    print("\n=== 与硬编码 PageRanges 对比 ===")
    for probe in detected:
        exp_start, exp_end = expected[probe.name]
        exp_end_str = str(exp_end) if exp_end else "EOF"
        det_end_str = str(probe.end) if probe.end else "EOF"
        match_start = probe.start == exp_start
        match_end = probe.end == exp_end if exp_end else True
        status = "OK" if match_start and match_end else "DIFF"
        print(
            f"  [{status}] {probe.name:20s} "
            f"检测 {probe.start}-{det_end_str} | 期望 {exp_start}-{exp_end_str}"
        )


def print_boundary_samples(rows: list[dict[str, Any]], sections: list[SectionProbe]) -> None:
    print("\n=== 各段边界页预览 ===")
    for probe in sections:
        if probe.start is None:
            print(f"\n-- {probe.name}: 未能检测 --")
            continue
        pages_to_show = [probe.start]
        if probe.end and probe.end != probe.start:
            pages_to_show.append(probe.end)
        print(f"\n-- {probe.name} ({probe.start}-{probe.end}) --")
        for p in pages_to_show:
            row = rows[p - 1]
            print(
                f"  p{p:4d} | footer={row['footer_code'] or '-':12s} "
                f"| ms_footer={row.get('ms_footer') or '-':8s} | {row['preview'][:80]}"
            )


def print_toc_analysis(toc_sample: list[dict[str, Any]]) -> None:
    print("\n=== PDF 书签 (Outline/TOC) 分析 ===")
    if not toc_sample:
        print("  (无书签 — PyMuPDF get_toc() 返回空)")
        return
    keywords = ("guideline", "discussion", "table of contents", "index", "update")
    hits = [
        e for e in toc_sample
        if any(k in (e["title"] or "").lower() for k in keywords)
    ]
    print(f"  书签条目数(采样): {len(toc_sample)}")
    print(f"  含 guideline/discussion 等关键词: {len(hits)}")
    for e in hits[:15]:
        print(f"    L{e['level']} p{e['page']:4d} | {e['title'][:70]}")


def main() -> None:
    if fitz is None:
        raise SystemExit("需要 PyMuPDF: pip install -r requirements.txt")

    settings = load_settings()
    parser = argparse.ArgumentParser(description="测试 PDF 结构解析与三段拆分")
    parser.add_argument("--pdf", type=Path, default=settings.pdf_path)
    parser.add_argument("--json-out", type=Path, default=None, help="可选，写出探测结果 JSON")
    args = parser.parse_args()

    pdf_path = args.pdf
    if not pdf_path.is_absolute():
        pdf_path = ROOT / pdf_path
    if not pdf_path.exists():
        pdf_path = _first_pdf(ROOT)

    print(f"PDF: {pdf_path.name}")
    pdf = fitz.open(str(pdf_path))

    builtin = probe_builtin_structure(pdf)
    print("\n=== PyMuPDF 内置结构 ===")
    print(f"  总页数: {builtin['page_count']}")
    print(f"  书签条目: {builtin['toc_entry_count']}")
    print(f"  书签含 'Discussion': {builtin['toc_has_discussion']}")
    if builtin["metadata"]:
        for k, v in list(builtin["metadata"].items())[:6]:
            print(f"  metadata.{k}: {str(v)[:80]}")

    print_toc_analysis(builtin["toc_sample"])

    rows = scan_page_signals(pdf)
    footer_counter = Counter(r["footer_code"] for r in rows if r["footer_code"])
    ms_counter = Counter(r["ms_code"] for r in rows if r["ms_code"])
    print("\n=== 页级信号统计 ===")
    print(f"  有 footer code 的页: {sum(1 for r in rows if r['footer_code'])}")
    print(f"  有 MS footer 的页: {sum(1 for r in rows if r.get('ms_footer'))}")
    print(f"  有 MS 页码(正文)的页: {sum(1 for r in rows if r['ms_code'])}")
    print(f"  discussion TOC 页: {sum(1 for r in rows if r['is_toc'])}")
    print(f"  footer 样例: {list(footer_counter.keys())[:8]}")
    print(f"  MS 样例: {sorted(ms_counter.keys())[:8]}")

    sections = detect_sections(rows)
    print("\n=== 启发式三段检测结果 ===")
    for probe in sections:
        end_str = str(probe.end) if probe.end else "EOF"
        print(
            f"  {probe.name:20s} p{probe.start}-{end_str} "
            f"[{probe.confidence}] via {probe.method}"
        )
        for note in probe.notes:
            print(f"    - {note}")

    compare_with_hardcoded(sections, PageRanges())
    print_boundary_samples(rows, sections)

    # 结论
    print("\n=== 结论（能否用于海量 PDF 大块分部分）===")
    if builtin["toc_entry_count"] == 0:
        print("  1. PDF 无书签/Outline → 不能依赖 get_toc() 自动分三段。")
    else:
        print("  1. PDF 有书签，但 NCCN 书签通常按疾病细分，不一定直接对应 front/guideline/discussion 三大块。")

    print("  2. PyMuPDF 提供的是「页级」能力：文本、块坐标、链接、渲染；没有语义章节树。")
    print("  3. 对本指南，可靠信号是：")
    print("     - 指南段：右下角 footer code (BCEL-1 等)")
    print("     - discussion 段：左上角 MS-* 页码 + 参考文献/TOC 结构")
    print("  4. 海量 PDF 可行路线：")
    print("     a) 每本文档注册 DocumentProfile（页码范围或规则）")
    print("     b) 或写通用启发式（footer/MS 模式 + TOC 关键词）+ 低置信度人工复核")
    print("     c) 书签仅作辅助，不能单独依赖")

    if args.json_out:
        payload = {
            "pdf": str(pdf_path),
            "builtin": builtin,
            "sections": [
                {
                    "name": s.name,
                    "start": s.start,
                    "end": s.end,
                    "method": s.method,
                    "confidence": s.confidence,
                    "notes": s.notes,
                }
                for s in sections
            ],
            "hardcoded": {
                "front_matter": [1, 13],
                "clinical_guideline": [14, 139],
                "discussion": [140, builtin["page_count"]],
            },
        }
        args.json_out.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\n已写出: {args.json_out}")

    pdf.close()


if __name__ == "__main__":
    main()
