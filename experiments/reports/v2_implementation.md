# 实验 v2 落地记录

日期：2026-10-13。本文件记录**已实现的代码与离线结果**。付费全量重跑（Part 1 test × 多底座、Part 2 端到端、Part 3 C-01）按方案需先估 token、你确认后再执行。

## 目录

实验入口：[`../README.md`](../README.md)。v1 结果原样在 `runs/2026-09-14_v1/`。仓库当时没有 git 提交历史，文件用复制归档而不是 `git mv`。

## 系统代码（单独评审）

- [`backend/app/services/reranker.py`](../../backend/app/services/reranker.py)：`BailianReranker`，与问答共用 `qwen.base_url` / API key。默认仍 `lexical`。禁止连打多个模型探活。
- 实测可用模型：**`qwen3.7-text-rerank`**（`configs/rerank_probe.json`）。
- [`prompts.py`](../../backend/app/prompts.py) / [`qwen.py`](../../backend/app/services/qwen.py) / [`qa.py`](../../backend/app/services/qa.py)：`allow_labeled_parametric`、相关性门控、未覆盖病种回退。
- [`disease_scope.py`](../../backend/app/services/disease_scope.py)：MALT→MZL；CLL/WM/HCL 在 NCCN 上 `kb_covered=False`；`non-Hodgkin` 不再误判为 HL。
- [`evidence_policy.py`](../../backend/app/services/evidence_policy.py)：参考文献页降权、门控至少保留 N 条。
- Settings 新字段默认关闭，线上行为不变。实验用 `configs/*.yaml` + `Settings.replace`。

`tests/test_disease_scope.py`：6 通过。

## Part 1

正式结果见 [`v3_Part1.md`](v3_Part1.md)。扩充题库已剔除 MZL 7 道（不在本轮考察范围），入组 139 题：

| 组别 | 模型 | n | 严格准确率 |
| --- | --- | ---: | --- |
| 混合系统（检索 + 通用知识） | qwen-plus | 139 | **84.2%** |
| 纯模型（同题配对） | qwen-turbo | 124 | 86.3% |
| 混合系统（检索 + 通用知识） | qwen-turbo | 124 | 62.1% |

第一组实验已结束。

## Part 2

- 计分读 trace 各阶段；金标准支持等价组：`scripts/run_part2.py`。
- 负向题 3 道移入 `datasets/part2/safety_refusal.json`。
- 扩题后 NCCN 非负向：FL/MCL/MZL/Burkitt/HGBL/PTLD/HIV 各 6 题。草稿状态 `draft_v2_needs_blind_review`，双人标完用 `compute_kappa.py`。
- 离线消融（82 题，未调 rerank API）：

| 变体 | recall@6 | mrr@6 | 备注 |
| --- | --- | --- | --- |
| BM25 | 0.50 | 0.35 | 词面重排与 BM25 相同 |
| lexical | 0.50 | 0.35 | 无增益，与 v1 诊断一致 |
| lexical+refpen | 0.51 | 0.35 | DLBCL recall@6 0.72→0.81 |

按病种 BM25 recall@6：DLBCL 0.72，MCL 0.50，FL 0.43，Burkitt 0.33，MZL 0.17，HIV 0.00（草稿页码待盲标核对）。百炼 rerank 消融用 `--live`。

- 引用评委：`scripts/judge_citations.py --run-dir <part2-run>`，评委 `qwen-plus`。

## 冻结候选

[`configs/frozen_candidate.yaml`](../configs/frozen_candidate.yaml)：S2 + `qwen3.7-text-rerank` + VLM 关。阈值 0.35 与门控至少 3 条要在 **dev 上再定**，不能直接当最终冻结。

## 仍需你确认后才跑的付费步骤

1. `run_part1.py --arm configs/s0_current.yaml` 等，先 `--questions datasets/part1/v2_dev.json --limit` 估价。
2. 测试集只跑一次：底座 × 有无指南。
3. `retrieval_ablation.py --live`；`run_part2.py` VLM 开/关各一次。
4. `run_part3.py` 回归 C-01，对比 v1 安全失败数。
5. 双人盲标 Part 2 草稿金标准。
