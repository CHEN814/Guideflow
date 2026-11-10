# -*- coding: utf-8 -*-
"""Weekly report 2026-09-28 — 2026-10-13 (Word)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyBboxPatch

ROOT = Path(__file__).resolve().parents[1]
FIG_DIR = ROOT / "reports" / "v3_meeting_figures"
DOC_PATH = ROOT.parent / "docs" / "周报-20260928-20261013.docx"

spec = importlib.util.spec_from_file_location(
    "exp_docx", ROOT / "scripts" / "build_v3_meeting_docx.py"
)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

NAVY, STEEL, TEAL, WHITE, GRAY = m.NAVY, m.STEEL, m.TEAL, m.WHITE, m.GRAY
GOLD, ROSE, LIGHT = m.GOLD, m.ROSE, m.LIGHT


def _box(ax, x, y, w, h, color, title, value, sub, title_size=11, value_size=22):
    ax.add_patch(
        FancyBboxPatch(
            (x, y), w, h, boxstyle="round,pad=0.03,rounding_size=0.10",
            facecolor=color, edgecolor=color, linewidth=0,
        )
    )
    ax.text(x + w / 2, y + h - 0.38, title, ha="center", va="center",
            color="white", fontsize=title_size, fontweight="bold")
    ax.text(x + w / 2, y + h / 2 - 0.02, value, ha="center", va="center",
            color="white", fontsize=value_size, fontweight="bold")
    ax.text(x + w / 2, y + 0.38, sub, ha="center", va="center",
            color="white", fontsize=9.5, linespacing=1.35)


def make_week_figures():
    FIG_DIR.mkdir(parents=True, exist_ok=True)

    # ── 核心数据看板 ──────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(10.8, 2.55))
    ax.set_xlim(0, 12.4)
    ax.set_ylim(0, 3.1)
    ax.axis("off")
    cards = [
        (0.15, 0.25, 2.90, 2.60, NAVY, "Part 1  选择题", "84.2%", "117 / 139\n严格准确率  ·  plus"),
        (3.20, 0.25, 2.90, 2.60, TEAL, "Part 2  DLBCL", "0.975", "39 / 40 组\n检索 Recall@40"),
        (6.25, 0.25, 2.90, 2.60, STEEL, "Part 2  核心病种", "0.934", "85 / 91 组\n检索 Recall@40"),
        (9.30, 0.25, 2.90, 2.60, GOLD, "Part 2  负向题", "9 / 10", "正确拒绝"),
    ]
    for args in cards:
        _box(ax, *args)
    fig.savefig(FIG_DIR / "fig_week_kpi.png")
    plt.close(fig)

    # ── 评测框架 ──────────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(10.2, 3.15))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 3.9)
    ax.axis("off")
    boxes = [
        (0.45, 0.55, 4.35, 2.70, NAVY, "Part 1  知识选择题",
         "MedQA 入组 139 题\n主指标：严格准确率\n只评选项字母"),
        (5.20, 0.55, 4.35, 2.70, TEAL, "Part 2  指南检索",
         "NCCN 临床提问\n主指标：检索 Recall@40\n只评检索，不评是否引用"),
    ]
    for x, y, w, h, color, title, body in boxes:
        ax.add_patch(
            FancyBboxPatch(
                (x, y), w, h, boxstyle="round,pad=0.04,rounding_size=0.12",
                facecolor=color, edgecolor=color, linewidth=0,
            )
        )
        ax.text(x + w / 2, y + h - 0.50, title, ha="center", va="center",
                color="white", fontsize=13, fontweight="bold")
        ax.text(x + w / 2, y + 1.00, body, ha="center", va="center",
                color="white", fontsize=11, linespacing=1.5)
    fig.savefig(FIG_DIR / "fig_week_framework.png")
    plt.close(fig)

    # ── Part 1 准确率（不含未齐样本） ─────────────────────────────
    fig, axes = plt.subplots(1, 2, figsize=(10.8, 4.25), gridspec_kw={"wspace": 0.30})

    ax = axes[0]
    vals = np.array([84.2])
    lo, hi = np.array([77.2]), np.array([89.3])
    yerr = np.vstack([vals - lo, hi - vals])
    ax.bar([0], vals, color=NAVY, width=0.55, zorder=3)
    ax.errorbar([0], vals, yerr=yerr, fmt="none", ecolor="#2C3E50",
                capsize=4, elinewidth=1.2, zorder=4)
    ax.set_ylim(0, 108)
    ax.set_xlim(-0.8, 0.8)
    ax.set_ylabel("严格准确率（%）")
    ax.set_xticks([0])
    ax.set_xticklabels(["混合系统\nqwen-plus"], fontsize=10.5)
    ax.set_title("(a)  主结果（n=139）")
    ax.text(0, 84.2 + 5.0, "84.2%", ha="center", va="bottom", fontsize=12, fontweight="bold")
    ax.text(0, 6, "117 / 139", ha="center", va="bottom", fontsize=9.5, color="white")
    ax.text(0, 98, "95% CI  77.2–89.3", ha="center", fontsize=9, color=GRAY)

    ax = axes[1]
    labels = ["纯模型\n不接检索", "混合系统\n检索 + 可回退"]
    vals = np.array([86.3, 62.1])
    lo = np.array([79.1, 53.3])
    hi = np.array([91.3, 70.2])
    x = np.arange(2)
    yerr = np.vstack([vals - lo, hi - vals])
    ax.bar(x, vals, color=[GRAY, ROSE], width=0.55, zorder=3)
    ax.errorbar(x, vals, yerr=yerr, fmt="none", ecolor="#2C3E50",
                capsize=3, elinewidth=1, zorder=4)
    ax.set_ylim(0, 108)
    ax.set_ylabel("严格准确率（%）")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=10)
    ax.set_title("(b)  qwen-turbo 同题配对（n=124）")
    for i, v in enumerate(vals):
        ax.text(i, v + 3.5, f"{v:.1f}%", ha="center", va="bottom", fontsize=11, fontweight="bold")
    ax.text(0.5, 100, "McNemar  p < 0.001", ha="center", fontsize=9, color=GRAY)

    fig.suptitle("Part 1  知识选择题准确率", fontsize=14, fontweight="bold", color=NAVY, y=1.02)
    fig.savefig(FIG_DIR / "fig_week_part1.png")
    plt.close(fig)

    # ── Part 1 分病种 ─────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(10.6, 4.2))
    diseases = ["DLBCL", "HCL", "MCL", "CLL", "WM", "Burkitt", "跨病种", "FL", "全体"]
    acc = np.array([100, 100, 100, 94.4, 90.9, 81.8, 79.8, 75.0, 84.2])
    ns = [6, 4, 1, 18, 11, 11, 84, 4, 139]
    colors = [NAVY] * 8 + [TEAL]
    colors[7] = GOLD
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
    fig.savefig(FIG_DIR / "fig_week_part1_disease.png")
    plt.close(fig)

    # ── Part 2 分层 Recall ────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(10.6, 5.0))
    names = [
        "PTLD", "DLBCL/LBCL", "Burkitt", "MCL", "MZL",
        "Discussion", "流程图页", "FL", "HIV", "通用", "HGBL/PMBL/转化",
    ]
    rec = np.array([1.000, 0.975, 0.889, 0.875, 0.875, 0.825, 0.814, 0.790, 0.750, 0.583, 0.250])
    ns = [10, 39, 9, 16, 16, 40, 101, 19, 8, 12, 12]
    colors = []
    for v in rec:
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
    fig.savefig(FIG_DIR / "fig_week_part2_disease.png")
    plt.close(fig)


def build():
    make_week_figures()
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt

    doc = Document()
    section = doc.sections[0]
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.left_margin = Cm(2.4)
    section.right_margin = Cm(2.4)
    section.top_margin = Cm(2.2)
    section.bottom_margin = Cm(2.0)

    styles = doc.styles["Normal"]
    styles.font.name = "Times New Roman"
    styles.font.size = Pt(12)
    styles.element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")

    header = section.header
    header.is_linked_to_previous = False
    hp = header.paragraphs[0]
    hp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    hr = hp.add_run("DLBCL-Evidence  ·  工作周报  ·  2026-09-28 至 2026-10-13")
    m.set_run_font(hr, size=9, color=GRAY, east="宋体")
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
    run1 = fp.add_run("第 ")
    m.set_run_font(run1, size=9, color=GRAY)
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
    m.set_run_font(r2, size=9, color=GRAY)
    run3 = fp.add_run(" 页")
    m.set_run_font(run3, size=9, color=GRAY, east="宋体")

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(6)
    run = p.add_run("DLBCL-Evidence 工作周报")
    m.set_run_font(run, size=22, bold=True, color=NAVY, east="黑体")

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(6)
    run = p.add_run("2026 年 9 月 28 日  —  10 月 13 日")
    m.set_run_font(run, size=13, color=STEEL, east="楷体")

    m.add_table(
        doc,
        ["项", "内容"],
        [
            ["周期", "2026-09-28 — 2026-10-13"],
            ["系统", "混合系统（指南检索 + 单次融合生成）；主实验底座 qwen-plus"],
            ["知识库", "NCCN B 细胞淋巴瘤指南 2026.V3"],
            ["性质", "v3 正式评测：Part 1 知识选择题 + Part 2 指南检索"],
        ],
        col_widths=[3.2, 12.8],
    )

    m.add_body(
        doc,
        "上周期完成首轮实测与文献对照。本周期按既定分工完成 v3 混合系统评测，并形成实验报告。评测拆成两件事：封闭选择题上会不会选对（Part 1），以及指定指南下检索器能不能把必须依据的页或块找进候选（Part 2）。两部分不合成单一总分。",
    )

    m.add_heading(doc, "1  本周完成", 1)
    m.add_bullet(doc, "跑完 v3 混合系统正式评测，主实验底座为 qwen-plus。")
    m.add_bullet(doc, "Part 1：MedQA 入组 139 题，主报严格准确率。")
    m.add_bullet(doc, "Part 2：NCCN 临床提问，主报检索 Recall@40；只评检索，不评生成是否引用。")
    m.add_bullet(doc, "形成实验报告，下文只列核心结果。")

    m.add_heading(doc, "1.1  核心结果", 2)
    m.add_picture(doc, FIG_DIR / "fig_week_kpi.png", 6.35)
    m.add_caption(doc, "图 1  本周期核心数据")

    m.add_table(
        doc,
        ["部分", "指标", "结果"],
        [
            ["Part 1", "混合系统 qwen-plus 严格准确率", "84.2%（117/139，CI 77.2%–89.3%）"],
            ["Part 2", "DLBCL 检索 Recall@40", "0.975（39/40 组，CI 0.923–1.000）"],
            ["Part 2", "核心病种检索 Recall@40", "0.934（85/91 组）"],
            ["Part 2", "负向题正确拒绝", "9/10"],
        ],
        col_widths=[2.8, 5.6, 7.6],
    )
    m.add_note(doc, "核心病种 = DLBCL + MCL + Burkitt + PTLD + MZL。plus 混合有效作答率 98.6%。")

    m.add_heading(doc, "1.2  评测设定", 2)
    m.add_picture(doc, FIG_DIR / "fig_week_framework.png", 6.2)
    m.add_caption(doc, "图 2  本周期评测分工")
    m.add_table(
        doc,
        ["项", "设定"],
        [
            ["作答策略", "混合：指南证据优先；证据不足时可使用通用医学知识"],
            ["生成模型", "主实验 qwen-plus；敏感性对照 qwen-turbo"],
            ["检索", "BM25，词面重排；前 40 条候选"],
            ["解码", "temperature = 0，每题一次"],
        ],
        col_widths=[3.2, 12.8],
    )

    m.add_heading(doc, "1.3  Part 1  知识选择题", 2)
    m.add_body(
        doc,
        "题源为 MedQA（USMLE 风格四选一），入组 139 道 B 细胞淋巴瘤及相关知识点单选题。标准答案为官方选项字母。计分只看解析出的字母，解释对错不给分。主指标为严格准确率，并报 Wilson 95% 置信区间。",
    )
    m.add_table(
        doc,
        ["组别", "模型", "n", "正确", "严格准确率", "95% CI"],
        [
            ["混合系统（主报）", "qwen-plus", "139", "117", "84.2%", "77.2%–89.3%"],
            ["纯模型（同题配对）", "qwen-turbo", "124", "107", "86.3%", "79.1%–91.3%"],
            ["混合系统（同题配对）", "qwen-turbo", "124", "77", "62.1%", "53.3%–70.2%"],
        ],
    )
    m.add_note(
        doc,
        "turbo 两行是同一批 124 题的配对对照，不与 plus 混比。McNemar：纯模型对而混合错 34 题，混合对而纯模型错 4 题，p < 0.001。",
    )
    m.add_picture(doc, FIG_DIR / "fig_week_part1.png", 6.4)
    m.add_caption(
        doc,
        "图 3  Part 1 准确率。(a) qwen-plus 主结果；(b) qwen-turbo 同题配对。误差线为 Wilson 95% 区间。",
    )
    m.add_table(
        doc,
        ["病种", "n", "正确", "准确率"],
        [
            ["DLBCL", "6", "6", "100%"],
            ["HCL", "4", "4", "100%"],
            ["MCL", "1", "1", "100%"],
            ["CLL", "18", "17", "94.4%"],
            ["WM", "11", "10", "90.9%"],
            ["Burkitt", "11", "9", "81.8%"],
            ["跨病种", "84", "67", "79.8%"],
            ["FL", "4", "3", "75.0%"],
            ["全体", "139", "117", "84.2%"],
        ],
        col_widths=[4.0, 4.0, 4.0, 4.0],
    )
    m.add_picture(doc, FIG_DIR / "fig_week_part1_disease.png", 6.4)
    m.add_caption(doc, "图 4  混合系统 qwen-plus 139 题分病种准确率。虚线为总体 84.2%。亚组 n 通常小于 20，只作描述。")
    m.add_body(
        doc,
        "读法：在已完成的同底座对照里，不接检索的纯模型高于混合系统。MedQA 中相当一部分题目考查药代、并发症或本份 NCCN 未单列专章的病种，接上指南检索后片段可能干扰作答。混合策略允许回退到通用知识，因而仍可达到 84.2%，但低于纯模型。不能表述为「接上指南后选择题更准」。",
    )

    m.add_heading(doc, "1.4  Part 2  指南检索", 2)
    m.add_body(
        doc,
        "范围限于 NCCN B 细胞淋巴瘤指南（2026.V3）。评的是检索能力：该依据的指南单元有没有进入系统返回的前 40 条候选。k = 40 计数的是条，不是去重页。生成模型是否引用该条不进入主指标。主报微平均检索 Recall@40，并报按题自助法 95% 区间。",
    )
    m.add_table(
        doc,
        ["指标", "DLBCL / LBCL（39 题）", "核心病种（90 题）"],
        [
            ["检索 Recall@40（微平均）", "0.975", "0.934"],
            ["命中组 / 必须组", "39 / 40", "85 / 91"],
            ["95% CI", "0.923–1.000", "—"],
            ["全部命中的题", "38 / 39", "—"],
        ],
    )
    m.add_note(doc, "核心病种 = DLBCL + MCL + Burkitt + PTLD + MZL。负向题 9 / 10 正确拒绝，不计入上表。")
    m.add_picture(doc, FIG_DIR / "fig_week_part2_disease.png", 6.4)
    m.add_caption(doc, "图 5  Part 2 分层检索 Recall@40。深蓝为 ≥0.87。")
    m.add_body(
        doc,
        "DLBCL 40 个必须组中 39 个出现在前 40 条里。主要病种检索稳定：PTLD 1.000，Burkitt 0.889，MCL 与 MZL 均为 0.875。流程图页 0.814，Discussion 0.825。短板在 HGBL / PMBL / 转化（0.250）和通用题（0.583），属于检索本身偏掉。新题必须命中单元仍为草稿，尚未双人盲标，上述数字为初步观测。",
    )

    m.add_heading(doc, "2  下周计划", 1)
    m.add_bullet(doc, "完成 Part 2 新题必须命中单元的双人核对，冻结后再报检索数字。")
    m.add_bullet(doc, "将 qwen-plus 的纯模型对照臂跑到与 139 题同一批，再读方法差异。")
    m.add_bullet(doc, "针对 HGBL / PMBL / 转化补检索（查询改写或模块过滤）。")

    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(DOC_PATH))
    print("wrote", DOC_PATH)


if __name__ == "__main__":
    build()
