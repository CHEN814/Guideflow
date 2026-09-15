"""把 results/*.json 写成评估记录 Markdown 表。"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

EVAL = Path(__file__).resolve().parent
RES = EVAL / "results"
OUT = EVAL.parent / "docs" / "评估记录-Part1-Part2.md"


def load(name: str):
    p = RES / name
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def md_escape(s: str) -> str:
    return (s or "").replace("|", "\\|").replace("\n", " ")


def system_label(name: str) -> str:
    return {"guideflow": "DLBCL-Evidence", "baseline": "无检索对照"}.get(name, name)


def fmt_pct(x, digits=1):
    if x is None:
        return "—"
    return f"{float(x) * 100:.{digits}f}%"


def fmt_ci(ci):
    if not ci or len(ci) < 2:
        return "—"
    return f"{ci[0] * 100:.1f}–{ci[1] * 100:.1f}"


def fmt3(x):
    if x is None:
        return "—"
    return f"{float(x):.3f}"


def conclusion_count(rows, system):
    pos = [r for r in rows if r["system"] == system and not r.get("negative")]
    if not pos:
        return "—"
    n = sum(1 for r in pos if r.get("conclusion") == "支持")
    return f"{n}/{len(pos)}（{n / len(pos):.0%}）"


def main() -> None:
    meta = load("meta.json") or {}
    p1_items = json.loads((EVAL / "part1_questions.json").read_text(encoding="utf-8"))
    p2_items = json.loads((EVAL / "part2_questions.json").read_text(encoding="utf-8"))
    p1_rows = load("part1_rows.json") or []
    p2_rows = load("part2_rows.json") or []
    p1_sum = load("part1_summary.json") or []
    p2_sum = load("part2_summary.json") or []
    by1 = {x["id"]: x for x in p1_items}
    by2 = {x["id"]: x for x in p2_items}

    gf1 = next((s for s in p1_sum if s["system"] == "guideflow"), {})
    bl1 = next((s for s in p1_sum if s["system"] == "baseline"), {})
    gf2 = next((s for s in p2_sum if s["system"] == "guideflow" and s["data_source"] == "ALL"), {})
    bl2 = next((s for s in p2_sum if s["system"] == "baseline" and s["data_source"] == "ALL"), {})
    old_sum = load("part2_summary_before_unit_fix.json") or []
    gf2_old = next((s for s in old_sum if s["system"] == "guideflow" and s["data_source"] == "ALL"), {})

    g = {r["id"]: r["correct"] for r in p1_rows if r["system"] == "guideflow"}
    b = {r["id"]: r["correct"] for r in p1_rows if r["system"] == "baseline"}
    both = sorted(set(g) & set(b))
    n01 = sum(g[i] == 0 and b[i] == 1 for i in both) if both else 0
    n10 = sum(g[i] == 1 and b[i] == 0 for i in both) if both else 0
    gf_invalid = sum(1 for r in p1_rows if r["system"] == "guideflow" and r.get("parse_step") == "invalid")
    bl_invalid = sum(1 for r in p1_rows if r["system"] == "baseline" and r.get("parse_step") == "invalid")
    gf1_k = sum(int(r.get("correct") or 0) for r in p1_rows if r["system"] == "guideflow")
    bl1_k = sum(int(r.get("correct") or 0) for r in p1_rows if r["system"] == "baseline")
    gf_c_after = [r["c_n"] for r in p2_rows if r["system"] == "guideflow" and not r.get("negative")]
    old_rows = load("part2_rows_before_unit_fix.json") or []
    gf_c_before = [r["c_n"] for r in old_rows if r["system"] == "guideflow" and not r.get("negative")]

    lines = [
        "# DLBCL-Evidence Part 1 / Part 2 真实评测记录",
        "",
        "> 批次 `EVAL-20260914`。原始 JSON 在 `code/eval/results/`（D 盘）。方案见 [评估方案.md](./评估方案.md)。",
        "> MedQA 题干版权属原题库；本表保留题号与得分，全文在本地 `eval/part1_questions.json`。",
        "",
        "## 结果要点",
        "",
        "| 模块 | DLBCL-Evidence | 同底座无检索对照 | 方案参考线 |",
        "| --- | --- | --- | --- |",
        f"| Part 1 严格准确率 | **{gf1_k}/{gf1.get('n')}（{gf1_k / gf1['n']:.1%}）**，CI {fmt_ci(gf1.get('ci95'))} | **{bl1_k}/{bl1.get('n')}（{bl1_k / bl1['n']:.1%}）**，CI {fmt_ci(bl1.get('ci95'))} | 不低于对照：未达到 |",
        f"| Part 1 DLBCL | {gf1.get('dlbcl_n')} / {fmt_pct(gf1.get('dlbcl_acc'))} | {bl1.get('dlbcl_n')} / {fmt_pct(bl1.get('dlbcl_acc'))} | n&lt;20，只描述 |",
        f"| Part 1 有效作答率 | {fmt_pct(gf1.get('valid_rate'))} | {fmt_pct(bl1.get('valid_rate'))} | — |",
        f"| Part 2 引用 Recall 微平均（修正后） | **{fmt3(gf2.get('recall_micro'))}** | {fmt3(bl2.get('recall_micro'))} | ≥0.60 |",
        f"| Part 2 引用 Precision 微平均（修正后） | **{fmt3(gf2.get('precision_micro'))}** | {fmt3(bl2.get('precision_micro'))} | ≥0.50 |",
        f"| Part 2 引用 F1 微平均（修正后） | {fmt3(gf2.get('f1_micro'))} | {fmt3(bl2.get('f1_micro'))} | — |",
        f"| Part 2 负向题正确拒绝 | {fmt_pct(gf2.get('neg_refuse_rate'), 0)}（n={gf2.get('n_neg')}） | {fmt_pct(bl2.get('neg_refuse_rate'), 0)} | ≥0.80 |",
        f"| Part 2 结论「支持」 | {conclusion_count(p2_rows, 'guideflow')} | {conclusion_count(p2_rows, 'baseline')} | 与引用 F1 分开报告 |",
        "",
        "## 分析：对照模型、Part 1 为何下降、是否格式误判",
        "",
        "### 无检索对照用的是什么模型",
        "",
        "- 与 DLBCL-Evidence **同一底座**：`config.yaml` 的 `qwen.model` = **qwen-plus**（DashScope）。",
        "- 对照不接 BM25 / 指南 / 图谱；`temperature=0` 直接 chat。",
        "- DLBCL-Evidence 走线上智能体（检索 + 证据门控；NCCN 流程图题可能再调 `qwen-vl-max`），生成温度约 0.1。",
        "- 因此对照不是“更强的别的模型”，而是 **同一 qwen-plus 去掉检索**。",
        "",
        "### 计分会不会因为输出不干净而误判",
        "",
        "不会。规则只取最后一次 `最终答案: X`，前面的推理、`[S1]`、中英文混写都不扣分。",
        f"- DLBCL-Evidence：{gf_invalid} 道 invalid（有效作答率 {fmt_pct(gf1.get('valid_rate'))}）。11 道错题都解析出了**明确的错误字母**，例如 P1-012 金标准 B、解析 C；P1-037 金标准 B、解析 C。",
        f"- 对照：{bl_invalid} 道 invalid（P1-047 写成 `Final answer: C` 而未写“最终答案”，按严格规则记 0）。",
        "",
        "### 加上指南后选择题正确率为何更低",
        "",
        f"McNemar（n={len(both)}）：DLBCL-Evidence 对而对照错 {n10}；对照对而 DLBCL-Evidence 错 {n01}。",
        "",
        "主因是 **MedQA 题型与产品能力错位**，不是输出格式：",
        "",
        "1. 不少题是药代、精神、疫苗、心内膜炎、胃 MALT 操作顺序，NCCN 帮不上忙。接上检索后模型围着片段转，或因“指南未覆盖”改选更差选项（P1-037、P1-041）。",
        "2. 题库含 CLL / 化疗并发症等，系统仍按淋巴瘤指南检索，产生干扰（P1-012 美司钠 vs 环丙沙星；P1-039 高黏滞应先血浆置换却选了利妥昔）。",
        "3. 对照吃的是 qwen-plus 考前知识，USMLE 风格题它本来就强。",
        "",
        "这不能说明“加指南让淋巴瘤决策变差”，只能说明 **用 USMLE 选择题测指南 RAG，无检索对照会占便宜**。DLBCL 亚组方向相反（DLBCL-Evidence 更高）但只有 6 题。",
        "",
        "## 分析：Recall / Precision 定义、修正与适用性",
        "",
        "### 怎么计算",
        "",
        "每题冻结必须命中单元 \(G\)（通常 1–2 个）。最终回答引用集合为 \(C\)（`[Sn]` 对应来源 + 文中页码）。",
        "",
        r"\(\mathrm{Recall}_q=|C\cap G|/|G|\)，\(\mathrm{Precision}_q=|C\cap G|/|C|\)；空 \(C\) 时 Precision=0。主报微平均。负向题不进 P/R。",
        "",
        "### 第一次 Precision 算错在哪（已修正）",
        "",
        "同一物理页被计了两次：`printed_page_code`（`nccn:BLAST-1`）和内部 `source_id`（`nccn:page-BLAST-1`）都进了 \(C\)。分母约放大一倍，Precision 被系统性压低。Recall 分子按金标准去重，受影响较小。",
        "",
        "修正：**一页/一个 chunk 只保留一个规范键** `{source}:{page_or_chunk}`，去掉 `page-` 前缀后去重。用已有 raw 作答重算，**未重新跑模型**。",
        "",
        "| 指标（DLBCL-Evidence 全源，45 道非负向） | 修正前（错误双计） | 修正后（一页一次） |",
        "| --- | --- | --- |",
        f"| Recall_micro | {fmt3(gf2_old.get('recall_micro'))} | **{fmt3(gf2.get('recall_micro'))}** |",
        f"| Precision_micro | {fmt3(gf2_old.get('precision_micro'))} | **{fmt3(gf2.get('precision_micro'))}** |",
        f"| F1_micro | {fmt3(gf2_old.get('f1_micro'))} | **{fmt3(gf2.get('f1_micro'))}** |",
        (
            f"| 非负向题平均 \\|C\\| | {sum(gf_c_before) / len(gf_c_before):.2f} | **{sum(gf_c_after) / len(gf_c_after):.2f}** |"
            if gf_c_before and gf_c_after
            else "| 非负向题平均 \\|C\\| | — | — |"
        ),
        "",
        "分源（DLBCL-Evidence，修正后）：",
        "",
        "| 数据源 | Recall_micro | Precision_micro | F1_micro |",
        "| --- | --- | --- | --- |",
    ]
    for src in ("nccn", "csco", "eha"):
        row = next((s for s in p2_sum if s["system"] == "guideflow" and s["data_source"] == src), {})
        lines.append(
            f"| {src.upper()} | {fmt3(row.get('recall_micro'))} | {fmt3(row.get('precision_micro'))} | {fmt3(row.get('f1_micro'))} |"
        )
    lines += [
        "",
        "### 修正后为何仍可能偏低",
        "",
        "1. **真偏差**：检索打偏。例如 P2-N01 金标准 `DIAG-1`，系统引到 `BLAST-1`；P2-N02 金标准 `ST-5`，引到 `NHODG-C 3 OF 3`。结论文字有时仍对，页没对上则 Recall=0。",
        "2. **金标准偏紧**：\(G\) 只标 1–2 个必须页，线上证据包常带多条相关页，多引会降 Precision。",
        "3. **对照 P/R=0 信息量有限**：无检索就没有可对齐的单元 ID，不宜解读为“引用能力为零”。",
        "",
        "### 这两个指标适不适合评本系统",
        "",
        "**适合**评“有没有引到该引的指南位置”（可追溯性）。**不适合**单独当系统总分：结论对但邻页错、P/R 可为 0；多引相关页会被 Precision 惩罚。建议：Recall 看漏引；Precision 作诊断、不设硬门槛；另报结论支持率。",
        "",
        "## 表 A1 评测批次登记",
        "",
        "| 字段 | 填写 |",
        "| --- | --- |",
        f"| 批次 ID | {meta.get('batch_id','')} |",
        f"| 日期 | {meta.get('date','')} |",
        f"| git commit | {meta.get('git_commit','')} |",
        f"| 生成模型 | {meta.get('qwen_model','')} |",
        f"| 温度 | {md_escape(str(meta.get('temperature_note','')))} |",
        f"| NCCN / CSCO / EHA | {meta.get('nccn_pdf','')} / {meta.get('csco_pdf','')} / {meta.get('eha_pdf','')} |",
        f"| 检索 Top-K | {meta.get('retrieval',{})} |",
        "| 对照系统 | 同底座 qwen-plus，不接指南检索 |",
        "| 跑分人 | Cursor Agent |",
        "",
        "## 入组说明（Part 1）",
        "",
        f"- 题源：GBaker/MedQA-USMLE-4-options（CC-BY-4.0；Jin et al. MedQA）。test+train 共 11451 题。",
        f"- 关键词初筛后，再要求**题干**含淋巴瘤/CLL/R-CHOP/利妥昔等核心词，并剔除流行病学/偏倚类题。",
        f"- 正式入组 **{len(p1_items)}** 题（DLBCL {sum(1 for x in p1_items if x['disease']=='DLBCL')}）。公开 MedQA 中 B 细胞淋巴瘤核心题不足 120，**不扩写成无官方答案的自编题**，以免污染金标准。",
        "",
        "### 表 B1 题目入组清单",
        "",
        "| 题号 | 题源 | 原始 ID | 语言 | disease | topic | 选项数 | 金标准 | 纳入 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for it in p1_items:
        lines.append(
            f"| {it['id']} | {it['source']} | {it['original_id']} | {it['lang']} | {it['disease']} | {it['topic']} | {it['n_options']} | {it['gold']} | Y |"
        )

    lines += [
        "",
        "### 表 B2 作答与计分",
        "",
        "| 批次 | 系统 | 题号 | 原始输出摘录（末200字） | 解析选项 | 解析规则步 | 金标准 | 正确 | 耗时s |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in p1_rows:
        lines.append(
            f"| {r.get('batch','')} | {system_label(r['system'])} | {r['id']} | {md_escape(r.get('tail',''))} | {r.get('parsed')} | {r.get('parse_step')} | {r.get('gold')} | {r.get('correct')} | {r.get('elapsed_s')} |"
        )

    lines += [
        "",
        "### 表 B3 汇总",
        "",
        "| 系统 | n | 严格准确率 | 95% CI | 有效作答率 | DLBCL n / Acc | 其他 B-NHL 等 n / Acc |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for s in p1_sum:
        lines.append(
            f"| {system_label(s['system'])} | {s['n']} | {fmt_pct(s.get('strict_acc'))} | {fmt_ci(s.get('ci95'))} | {fmt_pct(s.get('valid_rate'))} | {s.get('dlbcl_n')} / {fmt_pct(s.get('dlbcl_acc'))} | {s.get('other_n')} / {fmt_pct(s.get('other_acc'))} |"
        )

    # McNemar if both systems present
    g = {r["id"]: r["correct"] for r in p1_rows if r["system"] == "guideflow"}
    b = {r["id"]: r["correct"] for r in p1_rows if r["system"] == "baseline"}
    both = sorted(set(g) & set(b))
    if both:
        n01 = sum(g[i] == 0 and b[i] == 1 for i in both)
        n10 = sum(g[i] == 1 and b[i] == 0 for i in both)
        lines += [
            "",
            f"配对 McNemar（仅计共同完成题 n={len(both)}）：DLBCL-Evidence 对而对照错 {n10}；对照对而 DLBCL-Evidence 错 {n01}。",
        ]

    lines += [
        "",
        "## Part 2 指南引用",
        "",
        "### 表 C1 题目与金标准",
        "",
        "| 题号 | 数据源 | 题型 | 题干 | G（必须） | G_opt | 负向 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for it in p2_items:
        lines.append(
            f"| {it['id']} | {it['data_source']} | {it['topic']} | {md_escape(it['question'])} | {'; '.join(it.get('G') or [])} | {'; '.join(it.get('G_opt') or [])} | {'Y' if it.get('negative') else 'N'} |"
        )

    lines += [
        "",
        "### 表 C2 单题检索/引用",
        "",
        "| 批次 | 系统 | 题号 | R 单元 | C 单元 | \\|C∩G\\| | \\|G\\| | \\|C\\| | Recall_q | Precision_q | 结论 | 负向 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in p2_rows:
        lines.append(
            f"| {r.get('batch','')} | {system_label(r['system'])} | {r['id']} | {md_escape('; '.join(r.get('R') or []))} | {md_escape('; '.join(r.get('C') or []))} | {r.get('hit_n')} | {r.get('g_n')} | {r.get('c_n')} | {r.get('recall_q')} | {r.get('precision_q')} | {r.get('conclusion')} | {r.get('neg_label') or ''} |"
        )

    lines += [
        "",
        "### 表 C3 引用层汇总",
        "",
        "| 系统 | 数据源 | 题数（不含负向） | Recall_micro | Precision_micro | F1_micro | Recall_macro | Precision_macro | 负向题 n | 正确拒绝率 | 幻觉引用率 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for s in p2_sum:
        lines.append(
            f"| {system_label(s['system'])} | {s['data_source']} | {s['n_pos']} | {fmt3(s.get('recall_micro'))} | {fmt3(s.get('precision_micro'))} | {fmt3(s.get('f1_micro'))} | {fmt3(s.get('recall_macro'))} | {fmt3(s.get('precision_macro'))} | {s['n_neg']} | {fmt_pct(s.get('neg_refuse_rate'), 0)} | {fmt_pct(s.get('neg_halluc_rate'), 0)} |"
        )

    lines += [
        "",
        "### 表 C4 标注说明",
        "",
        "| 阶段 | 题数 | 说明 |",
        "| --- | --- | --- |",
        "| 金标准冻结 | 48 | 出题后根据知识库目录冻结 G，**未**根据模型输出回改 |",
        "| 单元计数 | — | 2026-09-14 修正：同一页的 page_code 与 source_id 只计 1 个 C；旧表见 `eval/results/part2_*_before_unit_fix.json` |",
        "| 一致性 | — | 本轮由同一评测脚本执行，无第二标注员，κ 不计算；属工程试跑 |",
        "",
        "## 进度",
        "",
        f"- Part 1 已记录行数：{len(p1_rows)} / {len(p1_items) * max(1, len({r['system'] for r in p1_rows} or ['guideflow']))}",
        f"- Part 2 已记录行数：{len(p2_rows)} / {len(p2_items) * max(1, len({r['system'] for r in p2_rows} or ['guideflow']))}",
        "",
    ]
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
