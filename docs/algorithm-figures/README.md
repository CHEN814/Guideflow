# DLBCL-Evidence 算法组图

正式版本为 `imagegen-v2/` 下的四张 PNG，使用 ChatGPT 图像生成功能绘制。小脑图标表示大模型实际参与决策或生成的环节。生成提示词保存在 `imagegen-v2/prompts.json`；早期矢量方案及临时打包产物已移出仓库。

## 文件与图注

1. **01_system_overview**：系统总体数据流。问题结合历史形成独立问题，在单一主指南来源内收集证据，再通过文本或多模态模型生成回答。PubMed 为可选并行通道，在主回答生成后追加独立文献段落。多模态页面摘要写回缓存，增强后续检索。
2. **02_evidence_acquisition**：自适应证据收集。规划模型选择指南检索、候选页面选择或按需图谱查询，并根据结果摘要决定继续或停止。文字、图片与图谱材料经过各自筛选后汇入证据包。通道可用性依赖所选指南，存在固定流程回退与自动补充。
3. **03_generation_and_delivery**：证据包经文本或多模态路径生成回答草稿，再完成引用筛选、重编号、配图整理和结果检查。检查报告不是逐项临床结论的真实性证明，也没有自动修订闭环。
4. **04_worked_example**：2026-11-10 新运行实例。问题为“DLBCL 一线治疗如何推荐？”，NCCN 为主指南，开启 PubMed 并禁用题录及摘要缓存。40 条词面召回、0 条向量召回，重排保留 6 条，筛选后 5 条文字证据；结合 2 张页面图片及 6 条图谱关系生成回答，最后展示 3 条指南来源和 2 张配图。PubMed 初检 1,376 篇，收紧研究类型后为 85 篇，获取前 30 篇摘要并筛选为 5 篇。文献中含 2 篇二线治疗研究，展示了相关性排序的局限。指南内部关联参考文献为 0。本次检查通过不代表医学内容已由专家验证。

## 数据依据

- 运行：`20261110-152841-b63521c1`
- 日志：`../../logs/runs/20261110-152841-b63521c1.jsonl`
- 完整结果：`../../logs/runs/20261110-152841-b63521c1.result.json`
- 以该运行日志及当前代码为依据，没有将历史成功日志冒充新运行。

## 视觉研究来源

绘制前检索并查看了以下原始论文插图；仅参考分层组织、留白、配色和数据流表达，未复制其算法结构或图形。

- Nature, **Synthesizing scientific literature with retrieval-augmented language models**, Fig. 1: https://www.nature.com/articles/s41586-025-10072-4/figures/1
- Nature Medicine, **Toward expert-level medical question answering with large language models**, Extended Data Fig. 1: https://www.nature.com/articles/s41591-024-03423-7/figures/5

## 编辑和复现

图片为生成式栅格图，可用于算法文档及演示；提示词不能保证逐像素复现。算法事实以代码和配套文档为准。

`build_algorithm_doc.py` 用于从算法 Markdown 生成 Word 文档，需要另行安装 `python-docx`。运行日志属于本地产物，不随仓库发布。
