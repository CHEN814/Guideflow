"""Write the v3 Part 1/2 report, including the 43-question plus baseline reference."""
from __future__ import annotations

import json
from collections import Counter
from datetime import date
from pathlib import Path

from common.paths import DATASETS, REPORTS, RUNS
from common.io import load_json
from common.stats import wilson_ci


def _norm(q: str) -> str:
    return " ".join((q or "").lower().split())


def _acc(rows: list[dict]) -> tuple[int, int, float | None, list[float]]:
    n = len(rows)
    k = sum(int(r.get("correct") or 0) for r in rows)
    lo, hi = wilson_ci(k, n) if n else (0.0, 0.0)
    return n, k, (round(k / n, 4) if n else None), [round(lo, 4), round(hi, 4)]


def main() -> None:
    v1 = load_json(DATASETS / "part1" / "v1_questions.json")
    v2 = load_json(DATASETS / "part1" / "v2_all.json")
    v2_by_q = {_norm(x["question"]): x for x in v2}
    overlap_ids = {v2_by_q[_norm(x["question"])]["id"] for x in v1 if _norm(x["question"]) in v2_by_q}

    formal = RUNS / "2026-10-13_formal"
    v3 = RUNS / "2026-10-13_v3"
    p2 = RUNS / "2026-10-13_v3_part2"
    p1_rows = load_json(v3 / "part1_rows.json") if (v3 / "part1_rows.json").exists() else []
    p1_sum = load_json(v3 / "part1_summary.json") if (v3 / "part1_summary.json").exists() else []
    p2_sum = load_json(p2 / "part2_summary.json") if (p2 / "part2_summary.json").exists() else []
    base_rows = []
    if (formal / "part1_rows.json").exists():
        base_rows = [r for r in load_json(formal / "part1_rows.json") if r.get("system") == "baseline_qwen-plus"]

    v1_by_q = {_norm(x["question"]): x["id"] for x in v1}
    v2_to_v1 = {}
    for item in v2:
        vid = v1_by_q.get(_norm(item["question"]))
        if vid:
            v2_to_v1[item["id"]] = vid

    lines = [
        "# 实验报告 v3：混合系统 Part 1 / Part 2",
        "",
        f"- 日期：{date.today().isoformat()}",
        "- 系统：混合系统（指南证据 + 通用知识，单次融合）",
        "- 题集：Part 1 `v2_all.json` 139 题（已剔除 MZL）；Part 2 `v3_nccn_questions.json` + `v3_nccn_safety.json`",
        "- 无正式纯模型对照组。下列 43 题 plus 纯模型数字来自 `2026-10-13_formal`，仅供参考。",
        "- 本账号无法调用 `qwen2-7b-instruct`（404），中档底座改用 `qwen-turbo`。",
        "- Part 2 金标准仍为草稿，引用指标为初步结果。",
        "",
        "## Part 1 全量",
        "",
    ]
    if p1_sum:
        lines += ["| 系统 | n | 严格准确率 | 95% CI | 有效作答率 |", "| --- | --- | --- | --- | --- |"]
        for s in p1_sum:
            ci = s.get("ci95") or [None, None]
            lines.append(
                f"| {s['system']} | {s['n']} | {s.get('strict_acc')} | {ci[0]}–{ci[1]} | {s.get('valid_rate')} |"
            )
        lines.append("")
        for s in p1_sum:
            lines.append(f"### {s['system']} 分病种")
            lines.append("")
            lines.append("| 病种 | n | 准确率 |")
            lines.append("| --- | --- | --- |")
            for dz, st in (s.get("by_disease") or {}).items():
                lines.append(f"| {dz} | {st['n']} | {st['acc']} |")
            lines.append("")
    else:
        lines += ["（尚无 `part1_summary.json`）", ""]

    plus_rows = [r for r in p1_rows if r.get("system") == "hybrid_qwen_plus" and r.get("id") in overlap_ids]
    base_map = {r["id"]: r for r in base_rows}
    paired_base = []
    paired_hyb = []
    for r in plus_rows:
        vid = v2_to_v1.get(r["id"])
        if vid and vid in base_map:
            paired_hyb.append(r)
            paired_base.append(base_map[vid])

    lines += ["## 43 题重合参考（qwen-plus）", ""]
    if paired_hyb:
        bn, bk, ba, bci = _acc(paired_base)
        hn, hk, ha, hci = _acc(paired_hyb)
        lines += [
            f"重合题 {len(overlap_ids)} 道中，双方都有结果的 {len(paired_hyb)} 道。",
            "",
            "| 系统 | n | 正确 | 准确率 | 95% CI |",
            "| --- | --- | --- | --- | --- |",
            f"| 纯模型 qwen-plus（参考） | {bn} | {bk} | {ba} | {bci[0]}–{bci[1]} |",
            f"| 混合系统 qwen-plus | {hn} | {hk} | {ha} | {hci[0]}–{hci[1]} |",
            "",
            "这不是正式对照，不能据此写「混合系统优于/劣于纯模型」。",
            "",
        ]
    else:
        lines += ["尚无足够重合结果。", ""]

    lines += ["## Part 2", ""]
    all_rows = [s for s in p2_sum if s.get("data_source") == "ALL"]
    if all_rows:
        lines += [
            "| 系统 | 正向题 | 引用 Recall | 检索 Recall | Precision | F1 | 通用知识句占比 | 未标注句占比 | 负向题 | 拒答率 |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for s in all_rows:
            lines.append(
                f"| {s['system']} | {s.get('n_pos')} | {s.get('recall_cite_micro')} | "
                f"{s.get('recall_retrieval_micro')} | {s.get('precision_micro')} | {s.get('f1_micro')} | "
                f"{s.get('generic_rate')} | {s.get('unlabeled_rate')} | {s.get('n_neg')} | {s.get('neg_refuse_rate')} |"
            )
        lines.append("")
    else:
        lines += ["（尚无 Part 2 汇总）", ""]

    out = REPORTS / "v3_Part1-Part2.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
