# 实验目录

本目录集中存放 Part 1–3 的题集、配置、脚本、运行结果与报告。线上系统代码仍在 `backend/`。

v3 起主实验只跑一种系统：**混合系统**（检索指南 + 单次融合生成，允许通用医学知识）。不再设纯模型组，也不跑 S0/S1/S2。

## 布局

| 路径 | 内容 |
| --- | --- |
| `design/` | 评估方案（v1 迁入 + v2 增补） |
| `datasets/part1` | 选择题。`v1_questions.json` 冻结；主实验用 `v2_all.json`（139 题，已剔除 MZL） |
| `datasets/part2` | 检索题。NCCN 主集 `v3_nccn_questions.json` + `v3_nccn_safety.json`；主指标为检索 Recall@40，方法见 `reports/v3_Part2_检索Recall_方法说明.md`，结果见 `reports/v3_Part2_NCCN.md` |
| `datasets/part3` | 病历题（gitignore） |
| `datasets/sources` | 原始题库下载（gitignore） |
| `configs/` | 实验组 yaml，由 runner 覆盖 Settings，不改线上默认 |
| `scripts/` | 可复现入口 |
| `runs/` | 每次运行一个目录（gitignore） |
| `reports/` | 可读报告 |

## 混合系统

`answer_policy: hybrid`。指南证据优先，用到标 `[Sn]`；证据不足时可用通用知识，句末标「（通用知识）」；与指南冲突时以指南为准。线上默认仍是 `guideline_only`。

实验臂：

- `hybrid_qwen_plus.yaml`（agentic）
- `hybrid_qwen_turbo.yaml`（agentic；本账号无法调用 `qwen2-7b-instruct`，中档改用 turbo）
- `hybrid_ds_1p5b.yaml`（linear）

## 常用命令

在 `code/` 下执行：

```text
python experiments/scripts/run_part1.py --arm experiments/configs/hybrid_qwen_plus.yaml --limit 3
python experiments/scripts/run_part2.py --arm experiments/configs/hybrid_qwen_plus.yaml --limit 3
python experiments/scripts/run_formal.py --limit 3
python experiments/scripts/run_formal.py
```

正式编排：Part 1 三个底座各跑 139 题；Part 2 只跑 `qwen-plus`（v3 NCCN 正向题 + 负向题）。支持 `--resume` 与 `--workers`（默认 4）。

Part 1 第一组正式结果见 [`reports/v3_Part1.md`](reports/v3_Part1.md)，方法说明见 [`reports/v3_Part1_方法说明.md`](reports/v3_Part1_方法说明.md)。
