# Part 2 v3 NCCN 审核说明

1. 全量审核用 `v3_nccn_annotation_template.json`。核对题干是否像临床提问、预期结论是否只来自 `source_sentence`、等价组是否真是同一条推荐。
2. `agree` 填 `Y` / `N`。不同意时改 `G` / `G_opt` 并在 `notes` 写原因。
3. 盲标用 `v3_nccn_blind_a.json` 与 `v3_nccn_blind_b.json`（同一 30 题，不带必须命中单元）。两人独立填写 `G`。
4. 一致性：

```text
python experiments/scripts/compute_kappa.py experiments/datasets/part2/v3_nccn_blind_a.json experiments/datasets/part2/v3_nccn_blind_b.json
```

κ 低于 0.60 时先修订规则，再重审，不要按系统输出回改必须命中单元。
