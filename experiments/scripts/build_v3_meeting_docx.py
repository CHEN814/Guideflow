# -*- coding: utf-8 -*-
"""Generate the v3 experiment report Word document."""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch
import numpy as np
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn, nsmap
from docx.shared import Cm, Inches, Pt, RGBColor, Emu
from lxml import etree

ROOT = Path(__file__).resolve().parents[1]
FIG_DIR = ROOT / "reports" / "v3_meeting_figures"
DOC_PATH = ROOT / "reports" / "v3实验报告.docx"

NAVY = "#1B365D"
STEEL = "#4A7BA7"
TEAL = "#2F6F6A"
GOLD = "#B0892E"
ROSE = "#8B3A3A"
GRAY = "#5C6570"
LIGHT = "#EEF2F6"
WHITE = "#FFFFFF"

plt.rcParams.update(
    {
        "font.sans-serif": ["Microsoft YaHei", "SimHei", "SimSun"],
        "axes.unicode_minus": False,
        "figure.facecolor": WHITE,
        "axes.facecolor": WHITE,
        "axes.edgecolor": NAVY,
        "axes.labelcolor": NAVY,
        "xtick.color": NAVY,
        "ytick.color": NAVY,
        "text.color": NAVY,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "grid.color": "#D5DCE4",
        "grid.linewidth": 0.6,
        "grid.alpha": 0.9,
        "font.size": 11,
        "axes.titlesize": 13,
        "axes.titleweight": "bold",
        "figure.dpi": 160,
        "savefig.dpi": 220,
        "savefig.bbox": "tight",
        "savefig.facecolor": WHITE,
    }
)


def _hex(c: str) -> RGBColor:
    c = c.lstrip("#")
    return RGBColor(int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16))


def set_run_font(run, size=12, bold=False, color=None, east="宋体", west="Times New Roman"):
    run.bold = bold
    run.font.size = Pt(size)
    run.font.name = west
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.get_or_add_rFonts()
    rFonts.set(qn("w:ascii"), west)
    rFonts.set(qn("w:hAnsi"), west)
    rFonts.set(qn("w:eastAsia"), east)
    if color:
        run.font.color.rgb = _hex(color)


def shade_cell(cell, fill: str):
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:fill"), fill.lstrip("#"))
    shd.set(qn("w:val"), "clear")
    tcPr.append(shd)


def set_cell_border(cell, color="1B365D", sz="4"):
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    tcBorders = OxmlElement("w:tcBorders")
    for edge in ("top", "left", "bottom", "right"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), sz)
        el.set(qn("w:color"), color)
        tcBorders.append(el)
    tcPr.append(tcBorders)


def set_cell_text(cell, text, *, size=10.5, bold=False, color=None, align="left", east="宋体"):
    cell.text = ""
    p = cell.paragraphs[0]
    p.alignment = {
        "left": WD_ALIGN_PARAGRAPH.LEFT,
        "center": WD_ALIGN_PARAGRAPH.CENTER,
        "right": WD_ALIGN_PARAGRAPH.RIGHT,
    }[align]
    pf = p.paragraph_format
    pf.space_before = Pt(2)
    pf.space_after = Pt(2)
    run = p.add_run(text)
    set_run_font(run, size=size, bold=bold, color=color, east=east)


def add_heading(doc, text, level=1):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.space_before = Pt(16 if level == 1 else 12)
    pf.space_after = Pt(8)
    pf.keep_with_next = True
    if level == 1:
        p.paragraph_format.border_bottom = None
        run = p.add_run(text)
        set_run_font(run, size=16, bold=True, color=NAVY, east="黑体")
        # underline bar via bottom border
        pPr = p._p.get_or_add_pPr()
        pBdr = OxmlElement("w:pBdr")
        bottom = OxmlElement("w:bottom")
        bottom.set(qn("w:val"), "single")
        bottom.set(qn("w:sz"), "12")
        bottom.set(qn("w:space"), "1")
        bottom.set(qn("w:color"), "1B365D")
        pBdr.append(bottom)
        pPr.append(pBdr)
    else:
        run = p.add_run(text)
        set_run_font(run, size=13, bold=True, color=STEEL, east="黑体")
    return p


def add_body(doc, text, *, first_line=True):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.space_before = Pt(2)
    pf.space_after = Pt(6)
    pf.line_spacing = 1.28
    if first_line:
        pf.first_line_indent = Cm(0.74)
    run = p.add_run(text)
    set_run_font(run, size=12, east="宋体")
    return p


def add_bullet(doc, text):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.left_indent = Cm(0.75)
    pf.first_line_indent = Cm(-0.37)
    pf.space_before = Pt(1)
    pf.space_after = Pt(3)
    pf.line_spacing = 1.22
    run = p.add_run("•  " + text)
    set_run_font(run, size=12, east="宋体")
    return p


def add_caption(doc, text):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    pf = p.paragraph_format
    pf.space_before = Pt(4)
    pf.space_after = Pt(12)
    run = p.add_run(text)
    set_run_font(run, size=10, bold=True, color=GRAY, east="楷体")
    return p


def add_note(doc, text):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.space_before = Pt(2)
    pf.space_after = Pt(8)
    pf.line_spacing = 1.2
    run = p.add_run(text)
    set_run_font(run, size=10.5, color=GRAY, east="楷体")
    return p


def add_picture(doc, path: Path, width_in=6.3):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    pf = p.paragraph_format
    pf.space_before = Pt(6)
    pf.space_after = Pt(2)
    run = p.add_run()
    run.add_picture(str(path), width=Inches(width_in))
    return p


def add_table(doc, headers, rows, col_widths=None):
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.autofit = True
    for i, h in enumerate(headers):
        cell = table.rows[0].cells[i]
        shade_cell(cell, NAVY)
        set_cell_text(cell, h, size=10, bold=True, color=WHITE, align="center", east="黑体")
        set_cell_border(cell, "1B365D", "4")
    for r_i, row in enumerate(rows):
        fill = WHITE if r_i % 2 == 0 else LIGHT
        for c_i, val in enumerate(row):
            cell = table.rows[r_i + 1].cells[c_i]
            shade_cell(cell, fill)
            align = "center" if c_i else "left"
            bold = c_i == 0
            set_cell_text(cell, str(val), size=10, bold=bold, color=NAVY, align=align)
            set_cell_border(cell, "C5CED8", "4")
    if col_widths:
        for row in table.rows:
            for i, w in enumerate(col_widths):
                row.cells[i].width = Cm(w)
    # space after
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(2)
    return table


def set_cell_margins(cell, **kwargs):
    pass


def make_figures():
    FIG_DIR.mkdir(parents=True, exist_ok=True)

    # ── Fig 0 framework ─────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(10.6, 3.4))
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 4)
    ax.axis("off")
    ax.set_title("评测分工（本轮完成 Part 1 与 Part 2）", pad=8)

    boxes = [
        (0.35, 0.7, 3.5, 2.5, NAVY, "Part 1  知识选择题", "MedQA 入组 139 题\n主指标：严格准确率\n只评选项字母"),
        (4.25, 0.7, 3.5, 2.5, TEAL, "Part 2  指南检索", "NCCN 临床提问 141 题\n另有负向 10 题\n主指标：检索 Recall@40"),
        (8.15, 0.7, 3.5, 2.5, GRAY, "Part 3  病历问答", "真实病历开放题\n本轮未做"),
    ]
    for x, y, w, h, color, title, body in boxes:
        ax.add_patch(
            FancyBboxPatch(
                (x, y), w, h, boxstyle="round,pad=0.04,rounding_size=0.12",
                facecolor=color, edgecolor=color, linewidth=0,
            )
        )
        ax.text(x + w / 2, y + h - 0.55, title, ha="center", va="center",
                color="white", fontsize=13, fontweight="bold")
        ax.text(x + w / 2, y + 0.95, body, ha="center", va="center",
                color="white", fontsize=10, linespacing=1.45)
    fig.savefig(FIG_DIR / "fig0_framework.png")
    plt.close(fig)

    # ── Fig 1 Part 1 ────────────────────────────────────────────────
    fig, axes = plt.subplots(1, 2, figsize=(10.8, 4.35), gridspec_kw={"wspace": 0.28})

    ax = axes[0]
    labels = ["纯模型\nplus（未齐）", "仅指南\nplus（未齐）", "混合\nplus（全量）"]
    vals = np.array([90.7, 75.5, 84.2])
    lo = np.array([78.4, 61.9, 77.2])
    hi = np.array([96.3, 85.4, 89.3])
    ns = ["n=43", "n=49", "n=139"]
    colors = [GRAY, STEEL, NAVY]
    x = np.arange(len(labels))
    yerr = np.vstack([vals - lo, hi - vals])
    bars = ax.bar(x, vals, color=colors, width=0.68, zorder=3,
                  error_kw={"ecolor": "#2C3E50", "capsize": 3, "elinewidth": 1})
    ax.errorbar(x, vals, yerr=yerr, fmt="none", ecolor="#2C3E50", capsize=3, elinewidth=1, zorder=4)
    ax.set_ylim(0, 108)
    ax.set_ylabel("严格准确率（%）")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=9.5)
    ax.set_title("(a)  qwen-plus：方法对照")
    for i, (v, n) in enumerate(zip(vals, ns)):
        ax.text(i, v + 4.2, f"{v:.1f}%", ha="center", va="bottom", fontsize=9, fontweight="bold")
        ax.text(i, 4.5, n, ha="center", va="bottom", fontsize=8, color="white")
    ax.axhline(84.2, color=NAVY, ls="--", lw=0.8, alpha=0.45)

    ax = axes[1]
    labels = ["纯模型\n不接检索", "混合系统\n检索 + 可回退"]
    vals = np.array([86.3, 62.1])
    lo = np.array([79.1, 53.3])
    hi = np.array([91.3, 70.2])
    x = np.arange(2)
    yerr = np.vstack([vals - lo, hi - vals])
    ax.bar(x, vals, color=[GRAY, ROSE], width=0.55, zorder=3)
    ax.errorbar(x, vals, yerr=yerr, fmt="none", ecolor="#2C3E50", capsize=3, elinewidth=1, zorder=4)
    ax.set_ylim(0, 108)
    ax.set_ylabel("严格准确率（%）")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=10)
    ax.set_title("(b)  qwen-turbo：同题配对（n=124）")
    for i, v in enumerate(vals):
        ax.text(i, v + 3.5, f"{v:.1f}%", ha="center", va="bottom", fontsize=10, fontweight="bold")
    ax.text(0.5, 100, "McNemar  p < 0.001", ha="center", fontsize=9, color=GRAY)

    fig.suptitle("Part 1  知识选择题准确率", fontsize=14, fontweight="bold", color=NAVY, y=1.02)
    fig.savefig(FIG_DIR / "fig1_part1.png")
    plt.close(fig)

    # ── Fig 1c disease accuracy ─────────────────────────────────────
    fig, ax = plt.subplots(figsize=(10.6, 4.2))
    diseases = ["DLBCL", "HCL", "MCL", "CLL", "WM", "Burkitt", "跨病种", "FL", "全体"]
    acc = np.array([100, 100, 100, 94.4, 90.9, 81.8, 79.8, 75.0, 84.2])
    ns = [6, 4, 1, 18, 11, 11, 84, 4, 139]
    colors = [NAVY if d != "全体" else TEAL for d in diseases]
    colors[-2] = GOLD  # FL
    y = np.arange(len(diseases))
    ax.barh(y, acc, color=colors, height=0.68, zorder=3)
    ax.set_yticks(y)
    ax.set_yticklabels([f"{d}  (n={n})" for d, n in zip(diseases, ns)])
    ax.set_xlim(0, 112)
    ax.set_xlabel("严格准确率（%）")
    ax.set_title("Part 1  混合系统（qwen-plus）139 题 · 分病种准确率")
    ax.axvline(84.2, color=TEAL, ls="--", lw=1)
    for i, v in enumerate(acc):
        ax.text(v + 1.2, i, f"{v:.1f}", va="center", fontsize=9)
    ax.invert_yaxis()
    fig.savefig(FIG_DIR / "fig1b_part1_disease.png")
    plt.close(fig)

    # ── Fig 3 disease ───────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(10.6, 5.0))
    names = [
        "PTLD", "DLBCL/LBCL", "Burkitt", "MCL", "MZL",
        "Discussion", "流程图页", "FL", "HIV", "通用", "HGBL/PMBL/转化",
    ]
    rec = np.array([1.000, 0.975, 0.889, 0.875, 0.875, 0.825, 0.814, 0.790, 0.750, 0.583, 0.250])
    ns = [10, 39, 9, 16, 16, 40, 101, 19, 8, 12, 12]
    colors = []
    for n, v in zip(names, rec):
        if v >= 0.87:
            colors.append(NAVY)
        elif v >= 0.70:
            colors.append(STEEL)
        elif v >= 0.50:
            colors.append(GOLD)
        else:
            colors.append(ROSE)
    y = np.arange(len(names))
    ax.barh(y, rec, color=colors, height=0.68, zorder=3)
    ax.set_yticks(y)
    ax.set_yticklabels([f"{n}  (n={k})" for n, k in zip(names, ns)])
    ax.set_xlim(0, 1.18)
    ax.set_xlabel("检索 Recall@40")
    ax.set_title("Part 2  分层检索 Recall@40")
    ax.axvline(0.975, color=NAVY, ls=":", lw=1, label="DLBCL 0.975")
    for i, v in enumerate(rec):
        ax.text(v + 0.015, i, f"{v:.3f}", va="center", fontsize=9)
    ax.legend(frameon=False, loc="lower right")
    ax.invert_yaxis()
    fig.savefig(FIG_DIR / "fig3_part2_disease.png")
    plt.close(fig)

    # ── Fig 4 recall@k ──────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(8.6, 4.3))
    ks = np.array([6, 16, 24, 32])
    rec_off = np.array([0.536, 0.780, 0.837, 0.865])
    ax.plot(ks, rec_off, "-o", color=STEEL, lw=2, ms=7, label="离线 BM25（141 题）")
    ax.scatter([40], [0.975], s=80, color=NAVY, zorder=5, marker="s", label="线上 DLBCL @40 = 0.975")
    ax.annotate("0.536", (6, 0.536), xytext=(6, 0.46), ha="center", fontsize=8, color=STEEL)
    ax.annotate("0.780", (16, 0.780), xytext=(16, 0.70), ha="center", fontsize=8, color=STEEL)
    ax.annotate("0.837", (24, 0.837), xytext=(24, 0.90), ha="center", fontsize=8, color=STEEL)
    ax.annotate("0.865", (32, 0.865), xytext=(31.2, 0.93), ha="center", fontsize=8, color=STEEL)
    ax.set_xlim(2, 44)
    ax.set_ylim(0.35, 1.05)
    ax.set_xlabel("候选条数 k")
    ax.set_ylabel("检索 Recall@k")
    ax.set_title("Part 2  候选宽度与检索召回")
    ax.set_xticks([6, 16, 24, 32, 40])
    ax.legend(frameon=False, loc="lower right")
    fig.savefig(FIG_DIR / "fig4_part2_k.png")
    plt.close(fig)


def build_doc():
    doc = Document()
    section = doc.sections[0]
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.left_margin = Cm(2.4)
    section.right_margin = Cm(2.4)
    section.top_margin = Cm(2.2)
    section.bottom_margin = Cm(2.0)

    # default style
    styles = doc.styles["Normal"]
    styles.font.name = "Times New Roman"
    styles.font.size = Pt(12)
    styles.element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")

    # header / footer
    header = section.header
    header.is_linked_to_previous = False
    hp = header.paragraphs[0]
    hp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    hr = hp.add_run("淋巴瘤指南问答系统  ·  v3 实验报告")
    set_run_font(hr, size=9, color=GRAY, east="宋体")
    hpPr = hp._p.get_or_add_pPr()
    pBdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "8")
    bottom.set(qn("w:color"), "1B365D")
    pBdr.append(bottom)
    hpPr.append(pBdr)

    footer = section.footer
    fp = footer.paragraphs[0]
    fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    # page number field
    run1 = fp.add_run("第 ")
    set_run_font(run1, size=9, color=GRAY)
    fldChar1 = OxmlElement("w:fldChar")
    fldChar1.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = " PAGE "
    fldChar2 = OxmlElement("w:fldChar")
    fldChar2.set(qn("w:fldCharType"), "end")
    r2 = fp.add_run()
    r2._r.append(fldChar1)
    r2._r.append(instr)
    r2._r.append(fldChar2)
    set_run_font(r2, size=9, color=GRAY)
    run3 = fp.add_run(" 页")
    set_run_font(run3, size=9, color=GRAY, east="宋体")

    # ── cover ──
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(28)
    run = p.add_run("淋巴瘤指南问答系统")
    set_run_font(run, size=22, bold=True, color=NAVY, east="黑体")

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run("v3 实验报告")
    set_run_font(run, size=26, bold=True, color=NAVY, east="黑体")

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(10)
    run = p.add_run("实验报告  ·  2026 年 10 月 13 日")
    set_run_font(run, size=13, color=STEEL, east="楷体")

    add_table(
        doc,
        ["项", "内容"],
        [
            ["评测对象", "混合系统（指南检索 + 单次融合生成）；底座 qwen-plus"],
            ["知识库", "NCCN B 细胞淋巴瘤指南 2026.V3"],
            ["Part 1", "MedQA 筛选后的 B 细胞淋巴瘤及相关知识点选择题，139 题"],
            ["Part 2", "NCCN 自建临床提问 141 题，另有负向 10 题"],
            ["未做", "CSCO / EHA；Part 3 病历问答；外系统对照"],
        ],
        col_widths=[3.2, 12.8],
    )

    add_heading(doc, "1  主要结果", 1)
    add_bullet(doc, "本轮只完成两件事：封闭选择题上会不会选对（Part 1），以及指定指南下检索器能不能找到必须依据的页或块（Part 2）。")
    add_bullet(doc, "Part 1 主结果：混合系统 qwen-plus 139 题，严格准确率 84.2%（95% CI 77.2%–89.3%）。同底座不接检索的对照尚未跑完全量。")
    add_bullet(doc, "Part 2 主结果：检索 Recall@40，DLBCL 为 0.975（39/40 组，CI 0.923–1.000）；核心病种 0.934。本部分只评检索，不评生成模型是否引用该条。")
    add_bullet(doc, "弱底座对照（qwen-turbo，同题 124 道）：纯模型 86.3%，混合系统 62.1%，配对差异显著。说明检索回退对弱底座伤害更大。")

    add_heading(doc, "2  评测框架", 1)
    add_body(
        doc,
        "评测按任务拆开，不合成单一总分。Part 1 使用公开执业考题，标准答案是官方选项字母，用来看知识覆盖；Part 2 使用自建临床提问，标准答案是必须依据的指南位置，用来看检索能力。生成阶段是否把已检索到的单元写进回答，属于底座模型的选择，不计入 Part 2 主指标。",
    )
    add_picture(doc, FIG_DIR / "fig0_framework.png", 6.35)
    add_caption(doc, "图 1  本轮评测分工")

    add_heading(doc, "2.1  系统配置", 2)
    add_table(
        doc,
        ["项", "设定"],
        [
            ["作答策略", "混合：指南证据优先；证据不足时可使用通用医学知识"],
            ["生成模型", "主实验 qwen-plus；敏感性 qwen-turbo"],
            ["检索", "BM25，词面重排；前 40 条候选"],
            ["路由", "Agentic（可多轮检索）；多轮时取最后一轮前 40 条计分"],
            ["关闭项", "读图（VLM）、PubMed 文献检索"],
            ["解码", "temperature = 0，每题一次"],
        ],
        col_widths=[3.2, 12.8],
    )

    add_heading(doc, "3  Part 1  知识选择题", 1)
    add_heading(doc, "3.1  题目与计分", 2)
    add_body(
        doc,
        "题源为 MedQA（USMLE 风格四选一）。公开库中真正的 DLBCL 专病题过少，入组范围扩大为 B 细胞淋巴瘤及相关诊疗知识点。入组 139 道互不重复的英文单选题。不自编题干，不改官方选项字母。",
    )
    add_table(
        doc,
        ["病种标签", "题数", "说明"],
        [
            ["跨病种", "84", "题干命中多个或未单点病名"],
            ["CLL", "18", ""],
            ["WM / Burkitt", "11 / 11", ""],
            ["DLBCL / FL / HCL / MCL", "6 / 4 / 4 / 1", "亚组 n 小，只描述"],
            ["合计", "139", ""],
        ],
        col_widths=[4.8, 3.2, 8.0],
    )
    add_body(
        doc,
        "三组方法共用同一作答模板，最后一行须写成「最终答案: X」。计分只看解析出的字母是否等于官方答案；解析失败记 0，仍计入分母。解释对错不给分。主指标为严格准确率，并报 Wilson 95% 置信区间。",
    )
    add_table(
        doc,
        ["组别", "是否检索指南", "生成约束"],
        [
            ["纯模型", "否", "仅按自身知识作答，禁止编造指南页码"],
            ["仅指南", "是", "医学判断只能依据检索到的指南证据"],
            ["混合系统", "是", "指南优先；未覆盖时允许通用医学知识，并须标明来源"],
        ],
        col_widths=[3.4, 3.6, 9.0],
    )

    add_heading(doc, "3.2  结果", 2)
    add_body(
        doc,
        "混合系统 qwen-plus 在 139 题上 117 题正确，严格准确率 84.2%（95% CI 77.2%–89.3%）。纯模型与仅指南两组样本量尚未与 139 题对齐，柱状图中单独标注 n，不能与全量混读为同一对照。",
    )
    add_table(
        doc,
        ["组别", "模型", "n", "正确", "严格准确率", "95% CI"],
        [
            ["混合系统（全量，主报）", "qwen-plus", "139", "117", "84.2%", "77.2%–89.3%"],
            ["纯模型（未齐）", "qwen-plus", "43", "39", "90.7%", "78.4%–96.3%"],
            ["仅指南（未齐）", "qwen-plus", "49", "37", "75.5%", "61.9%–85.4%"],
            ["纯模型（同题配对）", "qwen-turbo", "124", "107", "86.3%", "79.1%–91.3%"],
            ["混合系统（同题配对）", "qwen-turbo", "124", "77", "62.1%", "53.3%–70.2%"],
        ],
    )
    add_note(doc, "注：plus 未齐两行不可与 139 题混比。turbo 两行是同一批 124 题的配对对照。有效作答率：plus 混合 98.6%，turbo 纯模型 100%，turbo 混合 96.0%。")

    add_picture(doc, FIG_DIR / "fig1_part1.png", 6.4)
    add_caption(doc, "图 2  Part 1 准确率。(a) qwen-plus 方法对照，未齐样本不可与 n=139 混读；(b) qwen-turbo 同题配对 n=124。误差线为 Wilson 95% 区间。")

    add_picture(doc, FIG_DIR / "fig1b_part1_disease.png", 6.4)
    add_caption(doc, "图 3  混合系统 qwen-plus 139 题的分病种准确率。虚线为总体 84.2%。DLBCL 等亚组 n < 20，只作描述。")

    add_heading(doc, "3.3  读法", 2)
    add_body(
        doc,
        "在已完成的同底座对照里，纯模型高于混合系统，仅指南最低。这与公开执业考题的题型有关：相当一部分题目考查药代、并发症处理或知识库未覆盖的病种（如 CLL、WM），接上 NCCN B 细胞淋巴瘤检索后，模型容易被片段带走。混合策略允许回退到通用知识，因而高于「只能依据指南」的设定，但仍低于不接检索的纯模型。",
    )
    add_body(
        doc,
        "qwen-turbo 的配对结果把这一现象放大：纯模型对而混合错 34 题，混合对而纯模型错 4 题，McNemar p < 0.001。弱底座更依赖自身考前知识，检索干扰更明显。因此 Part 1 不能用来证明「接上指南后选择题更准」，只说明混合策略相对仅指南更稳，以及当前知识库覆盖与 MedQA 题型并不重合。",
    )

    add_heading(doc, "4  Part 2  指南检索", 1)
    add_heading(doc, "4.1  题目与计分", 2)
    add_body(
        doc,
        "范围限于 NCCN B 细胞淋巴瘤指南（2026.V3）全病种，CSCO 与 EHA 本轮不做。评的是检索能力：该依据的指南单元有没有进入系统返回的前 40 条候选。k = 40 计数的是检索命中条数，不是去重后的页数。流程图、方案表通常一页一条；Discussion 按语义切块，同一 PDF 页可以对应多条。计分时将 40 条映射为单元再去重，再与必须命中组比对。",
    )
    add_body(
        doc,
        "新题四步生成：从知识库抽出可执行的推荐句（须能在该页原文中对上），按病种分层取样，改写成中文临床提问（题干不出现页码），并另设 10 道负向题询问指南未覆盖的内容。推荐句所在页或块即为必须命中单元；同一推荐在流程图、脚注、方案表、Discussion 中的重复表述组成等价组，组内命中任一即算该组命中。v1 的 15 道旧题题干不重出，与新题用当前系统统一重跑。上一轮「入口页是哪一页」的 37 道扩题本轮不用。",
    )
    add_body(
        doc,
        "单题检索召回为 |R40 ∩ G| / |G|，其中 G 为必须命中组，R40 为前 40 条映射去重后的单元。多轮检索取最后一轮。主报微平均（各题命中组数与必须组数分别加总再相除），并报按题自助法（2000 次）的 95% 区间。负向题不进入召回分母。生成是否引用该条不进入主表。",
    )
    add_note(doc, "新题必须命中单元仍为草稿，尚未双人盲标。下列数字为初步观测，冻结前可能随标注修订。")

    add_heading(doc, "4.2  主结果", 2)
    add_table(
        doc,
        ["指标", "DLBCL / LBCL（39 题）", "核心病种（90 题）"],
        [
            ["检索 Recall@40（微平均）", "0.975", "0.934"],
            ["命中组 / 必须组", "39 / 40", "85 / 91"],
            ["95% CI", "0.923–1.000", "—"],
            ["宏平均", "0.974", "—"],
            ["全部命中的题", "38 / 39", "—"],
        ],
    )
    add_note(doc, "核心病种 = DLBCL + MCL + Burkitt + PTLD + MZL。负向题 9 / 10 正确拒绝，不计入上表。")

    add_heading(doc, "4.3  分层与候选宽度", 2)
    add_body(
        doc,
        "主要病种检索稳定：PTLD 1.000，Burkitt 0.889，MCL 与 MZL 均为 0.875。流程图页 0.814，Discussion 0.825，两种知识形态均可召回。旧题 0.813、新题 0.818，扩题后检索难度没有被旧题抬高。短板集中在 HGBL / PMBL / 转化（0.250，n=12）和通用题（0.583），这是检索本身偏掉，不是生成引用造成的。",
    )
    add_picture(doc, FIG_DIR / "fig3_part2_disease.png", 6.4)
    add_caption(doc, "图 4  分层检索 Recall@40。深蓝为 ≥0.87，红柱为明显短板。")

    add_picture(doc, FIG_DIR / "fig4_part2_k.png", 6.1)
    add_caption(doc, "图 5  离线 BM25 的 Recall@k。主指标取线上最后一轮 @40。词面重排与 BM25 相同，未带来额外增益。")

    add_heading(doc, "4.4  读法", 2)
    add_body(
        doc,
        "Part 2 回答的问题是：医生提出临床问题后，系统能不能把该打开的指南页或 Discussion 块找进候选。以 DLBCL 为例，40 个必须组中 39 个出现在前 40 条里。HGBL / PMBL / 转化与通用题拉低了部分病种的检索表现。",
    )
    add_body(
        doc,
        "线上生成目前只把约 6 条送进上下文，离线 @6 仅 0.54。那是生成可见窗口，不是本部分的检索指标。本部分主报 @40，与常见检索评测的 Recall@k 口径一致。",
    )

    add_heading(doc, "5  结论与后续", 1)
    add_heading(doc, "5.1  主要结论", 2)
    add_bullet(doc, "检索：在 NCCN B 细胞淋巴瘤上，混合系统能够把必须依据的单元找进前 40 条。DLBCL 检索 Recall@40 = 0.975；核心病种 0.934。")
    add_bullet(doc, "选择题：混合系统 qwen-plus 入组 139 题，准确率 84.2%。在当前对照下，不接检索的纯模型更高；混合高于仅指南。Part 1 证明的是知识覆盖与策略差异，不能表述为「系统比底座更会做题」。")
    add_bullet(doc, "安全：Part 2 负向题 9 / 10 正确拒绝。")
    add_bullet(doc, "底座敏感性：同一混合流程换到 qwen-turbo 后准确率降至 62.1%，与纯模型差距显著。正式比较应固定 plus。")

    add_heading(doc, "5.2  使用这些数字时的限制", 2)
    add_bullet(doc, "Part 2 新题尚未双人盲标，必须命中单元可能修订。")
    add_bullet(doc, "plus 的纯模型、仅指南未跑完 139 题，不能把 90.7%、75.5% 与 84.2% 写成同一实验的三臂结论。")
    add_bullet(doc, "无外系统 RAG 对照，也无 CSCO / EHA。")
    add_bullet(doc, "HGBL / PMBL / 转化检索失败，需要单独改查询或模块过滤，放宽 k 救不了。")
    add_bullet(doc, "Part 3 病历问答本轮未做。")

    add_heading(doc, "5.3  结论表述", 2)
    add_body(
        doc,
        "「v3 混合系统在 NCCN 上评了检索和选择题两件事。检索方面，DLBCL 的 Recall@40 是 0.975，核心 B 细胞淋巴瘤合计 0.934。选择题方面，plus 139 题准确率 84.2%；接指南后并没有超过不接检索的纯模型，这和 MedQA 题型、知识库覆盖范围有关。下一步是补齐 plus 三臂全量对照、完成新题盲标，并处理 HGBL 等少见病种的检索。」",
        first_line=True,
    )

    add_heading(doc, "附录  原始结果位置", 1)
    add_table(
        doc,
        ["内容", "路径"],
        [
            ["Part 1 方法", "experiments/reports/v3_Part1_方法说明.md"],
            ["Part 1 记录", "experiments/reports/v3_Part1.md（表内 plus 为未齐样本）"],
            ["Part 1 全量混合", "experiments/runs/2026-10-13_v3/part1_summary.json"],
            ["Part 2 方法", "experiments/reports/v3_Part2_检索Recall_方法说明.md"],
            ["Part 2 记录", "experiments/reports/v3_Part2_NCCN.md"],
            ["Part 2 原始", "experiments/runs/2026-10-13_v3_part2_nccn/"],
        ],
        col_widths=[4.2, 11.8],
    )

    doc.save(str(DOC_PATH))
    print("wrote", DOC_PATH)


if __name__ == "__main__":
    make_figures()
    build_doc()
