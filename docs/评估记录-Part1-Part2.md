# DLBCL-Evidence Part 1 / Part 2 真实评测记录

> 批次 `EVAL-20260914`。原始 JSON 在 `code/eval/results/`（D 盘）。方案见 [评估方案.md](./评估方案.md)。
> MedQA 题干版权属原题库；本表保留题号与得分，全文在本地 `eval/part1_questions.json`。

## 结果要点

| 模块 | DLBCL-Evidence | 同底座无检索对照 | 方案参考线 |
| --- | --- | --- | --- |
| Part 1 严格准确率 | **38/49（77.6%）**，CI 64.1–87.0 | **44/49（89.8%）**，CI 78.2–95.6 | 不低于对照：未达到 |
| Part 1 DLBCL | 6 / 83.3% | 6 / 66.7% | n&lt;20，只描述 |
| Part 1 有效作答率 | 100.0% | 98.0% | — |
| Part 2 引用 Recall 微平均（修正后） | **0.608** | 0.000 | ≥0.60 |
| Part 2 引用 Precision 微平均（修正后） | **0.397** | 0.000 | ≥0.50 |
| Part 2 引用 F1 微平均（修正后） | 0.481 | 0.000 | — |
| Part 2 负向题正确拒绝 | 100%（n=3） | 100% | ≥0.80 |
| Part 2 结论「支持」 | 27/45（60%） | 25/45（56%） | 与引用 F1 分开报告 |

## 分析：对照模型、Part 1 为何下降、是否格式误判

### 无检索对照用的是什么模型

- 与 DLBCL-Evidence **同一底座**：`config.yaml` 的 `qwen.model` = **qwen-plus**（DashScope）。
- 对照不接 BM25 / 指南 / 图谱；`temperature=0` 直接 chat。
- DLBCL-Evidence 走线上智能体（检索 + 证据门控；NCCN 流程图题可能再调 `qwen-vl-max`），生成温度约 0.1。
- 因此对照不是“更强的别的模型”，而是 **同一 qwen-plus 去掉检索**。

### 计分会不会因为输出不干净而误判

不会。规则只取最后一次 `最终答案: X`，前面的推理、`[S1]`、中英文混写都不扣分。
- DLBCL-Evidence：0 道 invalid（有效作答率 100.0%）。11 道错题都解析出了**明确的错误字母**，例如 P1-012 金标准 B、解析 C；P1-037 金标准 B、解析 C。
- 对照：1 道 invalid（P1-047 写成 `Final answer: C` 而未写“最终答案”，按严格规则记 0）。

### 加上指南后选择题正确率为何更低

McNemar（n=49）：DLBCL-Evidence 对而对照错 2；对照对而 DLBCL-Evidence 错 8。

主因是 **MedQA 题型与产品能力错位**，不是输出格式：

1. 不少题是药代、精神、疫苗、心内膜炎、胃 MALT 操作顺序，NCCN 帮不上忙。接上检索后模型围着片段转，或因“指南未覆盖”改选更差选项（P1-037、P1-041）。
2. 题库含 CLL / 化疗并发症等，系统仍按淋巴瘤指南检索，产生干扰（P1-012 美司钠 vs 环丙沙星；P1-039 高黏滞应先血浆置换却选了利妥昔）。
3. 对照吃的是 qwen-plus 考前知识，USMLE 风格题它本来就强。

这不能说明“加指南让淋巴瘤决策变差”，只能说明 **用 USMLE 选择题测指南 RAG，无检索对照会占便宜**。DLBCL 亚组方向相反（DLBCL-Evidence 更高）但只有 6 题。

## 分析：Recall / Precision 定义、修正与适用性

### 怎么计算

每题冻结必须命中单元 \(G\)（通常 1–2 个）。最终回答引用集合为 \(C\)（`[Sn]` 对应来源 + 文中页码）。

\(\mathrm{Recall}_q=|C\cap G|/|G|\)，\(\mathrm{Precision}_q=|C\cap G|/|C|\)；空 \(C\) 时 Precision=0。主报微平均。负向题不进 P/R。

### 第一次 Precision 算错在哪（已修正）

同一物理页被计了两次：`printed_page_code`（`nccn:BLAST-1`）和内部 `source_id`（`nccn:page-BLAST-1`）都进了 \(C\)。分母约放大一倍，Precision 被系统性压低。Recall 分子按金标准去重，受影响较小。

修正：**一页/一个 chunk 只保留一个规范键** `{source}:{page_or_chunk}`，去掉 `page-` 前缀后去重。用已有 raw 作答重算，**未重新跑模型**。

| 指标（DLBCL-Evidence 全源，45 道非负向） | 修正前（错误双计） | 修正后（一页一次） |
| --- | --- | --- |
| Recall_micro | 0.608 | **0.608** |
| Precision_micro | 0.225 | **0.397** |
| F1_micro | 0.328 | **0.481** |
| 非负向题平均 \|C\| | 3.07 | **1.73** |

分源（DLBCL-Evidence，修正后）：

| 数据源 | Recall_micro | Precision_micro | F1_micro |
| --- | --- | --- | --- |
| NCCN | 0.562 | 0.310 | 0.400 |
| CSCO | 0.778 | 0.538 | 0.636 |
| EHA | 0.471 | 0.348 | 0.400 |

### 修正后为何仍可能偏低

1. **真偏差**：检索打偏。例如 P2-N01 金标准 `DIAG-1`，系统引到 `BLAST-1`；P2-N02 金标准 `ST-5`，引到 `NHODG-C 3 OF 3`。结论文字有时仍对，页没对上则 Recall=0。
2. **金标准偏紧**：\(G\) 只标 1–2 个必须页，线上证据包常带多条相关页，多引会降 Precision。
3. **对照 P/R=0 信息量有限**：无检索就没有可对齐的单元 ID，不宜解读为“引用能力为零”。

### 这两个指标适不适合评本系统

**适合**评“有没有引到该引的指南位置”（可追溯性）。**不适合**单独当系统总分：结论对但邻页错、P/R 可为 0；多引相关页会被 Precision 惩罚。建议：Recall 看漏引；Precision 作诊断、不设硬门槛；另报结论支持率。

## 表 A1 评测批次登记

| 字段 | 填写 |
| --- | --- |
| 批次 ID | EVAL-20260914 |
| 日期 | 2026-09-14 |
| git commit | ed97a9e |
| 生成模型 | qwen-plus |
| 温度 | baseline chat temperature=0.0；DLBCL-Evidence 沿用线上 generate 默认（约 0.1） |
| NCCN / CSCO / EHA | （2026.V3）NCCN临床 实践指南：B细胞淋巴瘤.pdf / 3.2025CSCO淋巴瘤诊疗指南(OCR).pdf / 2025 EHA临床实践指南：大B细胞淋巴瘤的诊断、治疗和随访.pdf |
| 检索 Top-K | {'bm25_top_k': 40, 'rerank_top_k': 16, 'final_top_k': 6} |
| 对照系统 | 同底座 qwen-plus，不接指南检索 |
| 跑分人 | Cursor Agent |

## 入组说明（Part 1）

- 题源：GBaker/MedQA-USMLE-4-options（CC-BY-4.0；Jin et al. MedQA）。test+train 共 11451 题。
- 关键词初筛后，再要求**题干**含淋巴瘤/CLL/R-CHOP/利妥昔等核心词，并剔除流行病学/偏倚类题。
- 正式入组 **49** 题（DLBCL 6）。公开 MedQA 中 B 细胞淋巴瘤核心题不足 120，**不扩写成无官方答案的自编题**，以免污染金标准。

### 表 B1 题目入组清单

| 题号 | 题源 | 原始 ID | 语言 | disease | topic | 选项数 | 金标准 | 纳入 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| P1-001 | MedQA-USMLE-4-options | step1:test:20 | en | DLBCL | 一线 | 4 | C | Y |
| P1-002 | MedQA-USMLE-4-options | step1:test:142 | en | 跨病种 | 一线 | 4 | A | Y |
| P1-003 | MedQA-USMLE-4-options | step2&3:test:525 | en | 其他 B-NHL | 诊断 | 4 | D | Y |
| P1-004 | MedQA-USMLE-4-options | step2&3:test:565 | en | 跨病种 | 一线 | 4 | B | Y |
| P1-005 | MedQA-USMLE-4-options | step1:train:32 | en | 跨病种 | 一线 | 4 | C | Y |
| P1-006 | MedQA-USMLE-4-options | step1:train:57 | en | DLBCL | 诊断 | 4 | C | Y |
| P1-007 | MedQA-USMLE-4-options | step1:train:180 | en | 跨病种 | 诊断 | 4 | B | Y |
| P1-008 | MedQA-USMLE-4-options | step2&3:train:253 | en | 跨病种 | 分期预后 | 4 | D | Y |
| P1-009 | MedQA-USMLE-4-options | step2&3:train:724 | en | 跨病种 | 一线 | 4 | A | Y |
| P1-010 | MedQA-USMLE-4-options | step2&3:train:962 | en | 其他 B-NHL | 一线 | 4 | A | Y |
| P1-011 | MedQA-USMLE-4-options | step2&3:train:1340 | en | 跨病种 | 一线 | 4 | D | Y |
| P1-012 | MedQA-USMLE-4-options | step2&3:train:1417 | en | 跨病种 | 一线 | 4 | B | Y |
| P1-013 | MedQA-USMLE-4-options | step1:train:1627 | en | MCL | 一线 | 4 | B | Y |
| P1-014 | MedQA-USMLE-4-options | step1:train:1892 | en | DLBCL | 一线 | 4 | C | Y |
| P1-015 | MedQA-USMLE-4-options | step1:train:2024 | en | 其他 B-NHL | 诊断 | 4 | C | Y |
| P1-016 | MedQA-USMLE-4-options | step2&3:train:2331 | en | 跨病种 | 一线 | 4 | D | Y |
| P1-017 | MedQA-USMLE-4-options | step1:train:2707 | en | 其他 B-NHL | 一线 | 4 | D | Y |
| P1-018 | MedQA-USMLE-4-options | step1:train:3412 | en | 其他 B-NHL | 一线 | 4 | D | Y |
| P1-019 | MedQA-USMLE-4-options | step1:train:3907 | en | FL | 诊断 | 4 | D | Y |
| P1-020 | MedQA-USMLE-4-options | step2&3:train:4195 | en | 跨病种 | 复发难治 | 4 | A | Y |
| P1-021 | MedQA-USMLE-4-options | step1:train:4301 | en | 跨病种 | 一线 | 4 | D | Y |
| P1-022 | MedQA-USMLE-4-options | step1:train:4307 | en | 其他 B-NHL | 一线 | 4 | B | Y |
| P1-023 | MedQA-USMLE-4-options | step1:train:4376 | en | 跨病种 | 一线 | 4 | C | Y |
| P1-024 | MedQA-USMLE-4-options | step2&3:train:4499 | en | 其他 B-NHL | 一线 | 4 | D | Y |
| P1-025 | MedQA-USMLE-4-options | step1:train:4789 | en | FL | 诊断 | 4 | C | Y |
| P1-026 | MedQA-USMLE-4-options | step1:train:5060 | en | 跨病种 | 诊断 | 4 | B | Y |
| P1-027 | MedQA-USMLE-4-options | step2&3:train:5146 | en | 跨病种 | 一线 | 4 | D | Y |
| P1-028 | MedQA-USMLE-4-options | step2&3:train:5306 | en | 跨病种 | 一线 | 4 | D | Y |
| P1-029 | MedQA-USMLE-4-options | step2&3:train:5472 | en | 跨病种 | 复发难治 | 4 | B | Y |
| P1-030 | MedQA-USMLE-4-options | step1:train:5732 | en | 跨病种 | 一线 | 4 | B | Y |
| P1-031 | MedQA-USMLE-4-options | step2&3:train:6053 | en | 其他 B-NHL | 一线 | 4 | B | Y |
| P1-032 | MedQA-USMLE-4-options | step2&3:train:6086 | en | 其他 B-NHL | 一线 | 4 | A | Y |
| P1-033 | MedQA-USMLE-4-options | step2&3:train:6258 | en | 跨病种 | 一线 | 4 | B | Y |
| P1-034 | MedQA-USMLE-4-options | step1:train:6268 | en | 其他 B-NHL | 诊断 | 4 | C | Y |
| P1-035 | MedQA-USMLE-4-options | step2&3:train:6469 | en | 跨病种 | 诊断 | 4 | D | Y |
| P1-036 | MedQA-USMLE-4-options | step1:train:6495 | en | 跨病种 | 诊断 | 4 | A | Y |
| P1-037 | MedQA-USMLE-4-options | step2&3:train:6552 | en | 其他 B-NHL | 诊断 | 4 | B | Y |
| P1-038 | MedQA-USMLE-4-options | step2&3:train:6558 | en | 跨病种 | 诊断 | 4 | B | Y |
| P1-039 | MedQA-USMLE-4-options | step1:train:6735 | en | 其他 B-NHL | 一线 | 4 | B | Y |
| P1-040 | MedQA-USMLE-4-options | step2&3:train:7026 | en | 跨病种 | 一线 | 4 | C | Y |
| P1-041 | MedQA-USMLE-4-options | step1:train:7666 | en | 跨病种 | 一线 | 4 | B | Y |
| P1-042 | MedQA-USMLE-4-options | step1:train:7717 | en | DLBCL | 一线 | 4 | B | Y |
| P1-043 | MedQA-USMLE-4-options | step2&3:train:8386 | en | 跨病种 | 一线 | 4 | B | Y |
| P1-044 | MedQA-USMLE-4-options | step2&3:train:9055 | en | 其他 B-NHL | 一线 | 4 | A | Y |
| P1-045 | MedQA-USMLE-4-options | step2&3:train:9077 | en | DLBCL | 诊断 | 4 | B | Y |
| P1-046 | MedQA-USMLE-4-options | step1:train:9225 | en | FL | 诊断 | 4 | B | Y |
| P1-047 | MedQA-USMLE-4-options | step2&3:train:9254 | en | DLBCL | 复发难治 | 4 | C | Y |
| P1-048 | MedQA-USMLE-4-options | step2&3:train:9368 | en | 其他 B-NHL | 特殊部位 | 4 | A | Y |
| P1-049 | MedQA-USMLE-4-options | step2&3:train:9867 | en | 跨病种 | 一线 | 4 | D | Y |

### 表 B2 作答与计分

| 批次 | 系统 | 题号 | 原始输出摘录（末200字） | 解析选项 | 解析规则步 | 金标准 | 正确 | 耗时s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| EVAL-20260914 | DLBCL-Evidence | P1-001 | 出现的继发性淋巴瘤已被文献报道，且指南在讨论中隐含了治疗相关淋巴瘤的可能性（如Hepatitis B testing注释中提到免疫抑制相关风险，间接支持治疗相关因素）[S1]。 - 既往放射治疗（C）是已知的继发性淋巴瘤危险因素，尤其在乳腺癌放疗后可增加非霍奇金淋巴瘤发生率，符合该患者的病史背景。  因此，在所列选项中，最可能与该患者DLBCL相关的风险因素是既往接受的放射治疗。  最终答案: C | C | 1 | C | 1 | 37.11 |
| EVAL-20260914 | 无检索对照 | P1-001 | 乳腺癌本身：原发癌病史本身不是NHL的独立危险因素；真正起作用的是**治疗手段**（如放疗、烷化剂类化疗）所致的基因组不稳定性。单纯乳腺癌病史不增加NHL风险；而放疗是明确致瘤因素。  补充：该患者还有30包年吸烟史——吸烟与某些淋巴瘤亚型（如MALT）弱相关，但与DLBCL无强关联；且题干未列其为选项。  因此，最直接、最强证据支持的致病风险因素是：**既往放射治疗（C）**。  最终答案: C | C | 1 | C | 1 | 22.7 |
| EVAL-20260914 | DLBCL-Evidence | P1-002 | 功能障碍导致远端轴索变性，引发**剂量依赖性、长度依赖性周围神经病**——这正是该患者表现。    其他选项：   B. 创建自由基、解旋DNA → 典型为**博来霉素**或**蒽环类**（如阿霉素）机制；   C. 抑制二氢叶酸还原酶 → **甲氨蝶呤**机制；   D. 掺入假嘧啶类似物 → **5-氟尿嘧啶**或**阿糖胞苷**机制。    均与vincristine无关。  最终答案: A | A | 1 | A | 1 | 15.83 |
| EVAL-20260914 | 无检索对照 | P1-002 | n of dihydrofolate reductase → 是甲氨蝶呤（methotrexate）的作用靶点，干扰叶酸代谢，影响DNA合成。  D. Incorporation of false pyrimidine analogues into DNA → 如5-氟尿嘧啶（5-FU）或阿糖胞苷（cytarabine）等抗代谢药机制，与长春新碱无关。  因此，最可能的机制是A。  最终答案: A | A | 1 | A | 1 | 12.24 |
| EVAL-20260914 | DLBCL-Evidence | P1-003 | RAP阳性、CD103+/CD25+/CD11c+**；本例无脾大描述，且淋巴细胞比例50%（HCL外周血淋巴细胞常不显著增多，毛细胞比例通常不高），更不符合。  D. smudge cells：CLL最经典外周血形态学表现，与CD20+、淋巴细胞增多、肝/淋巴结肿大、年龄相符。  因此最可能的发现是smudge cells。  具体诊疗请咨询医生；本回答不来自当前指南证据检索。  最终答案: D | D | 1 | D | 1 | 29.25 |
| EVAL-20260914 | 无检索对照 | P1-003 | LL的经典镜下表现（>10%即高度提示）；   - 其他选项均不具同等特异性或不符合：    A（EPO低）→ 无依据；    B（LAP低）→ 见于CML，非CLL；    C（hairy cells）→ 形态不同，且HCL无显著淋巴结肿大，脾大更突出，且常全血细胞减少更严重，而本例WBC升高、PLT仅轻度减少；  因此，最可能的检查发现是外周血涂片见smudge cells。  最终答案: D | D | 1 | D | 1 | 32.0 |
| EVAL-20260914 | DLBCL-Evidence | P1-004 | 为63岁男性，有B症状（发热、盗汗、体重减轻）、肝脾肿大及淋巴结肿大，属于需要治疗的进展性SLL/CLL。 - FCR方案在适合接受化疗的患者中为首选一线治疗，尤其适用于年轻、体能状态良好者；但需评估是否适合强化疗。 - 其他选项：A. 全反式维甲酸用于急性早幼粒细胞白血病；C. 观察仅适用于无症状、惰性病程者；D. 伊马替尼用于费城染色体阳性白血病或胃肠道间质瘤，不适用于此病。  最终答案: B | B | 1 | B | 1 | 25.93 |
| EVAL-20260914 | 无检索对照 | P1-004 | 肿大、血小板减少，绝对不符合观察指征。❌   D. Imatinib → BCR-ABL抑制剂，用于CML、Ph⁺ ALL、GIST等，CLL无BCR-ABL融合，不适用。❌    注意：虽然目前新型靶向药（如BTK抑制剂）已成为CLL一线主流，但本题选项中仅有FCR是公认有效的CLL治疗方案；其余均不适用。题干未提供分子学（如TP53、IGHV）信息，故按传统标准选FCR合理。  最终答案: B | B | 1 | B | 1 | 20.53 |
| EVAL-20260914 | DLBCL-Evidence | P1-005 | 排泄，直接刺激膀胱黏膜，引起炎症、溃疡和出血。尤其在水化不足或未予预防（如美司钠）时更易发生。   - 甲氨蝶呤（A）主要引起黏膜炎、骨髓抑制、肾毒性（高剂量时），但不典型导致血尿/膀胱刺激症状；   - 利妥昔单抗（B）为单抗，常见不良反应为输注反应、感染风险增加，无泌尿系统直接毒性；   - 泼尼松（D）为糖皮质激素，不引起血尿或膀胱炎。    因此，最可能致病的是环磷酰胺。  最终答案: C | C | 1 | C | 1 | 13.88 |
| EVAL-20260914 | 无检索对照 | P1-005 | 妥昔单抗）**：单抗类靶向药，主要不良反应为输注反应、感染风险增加、罕见乙肝再激活；**不引起出血性膀胱炎**。  - **Prednisone（泼尼松）**：糖皮质激素，常见副作用包括高血糖、免疫抑制、骨质疏松等；**无直接膀胱毒性**。  综上，最符合该患者泌尿系症状的化疗药物是**环磷酰胺**，尤其在NHL常用方案如CHOP（环磷酰胺、多柔比星、长春新碱、泼尼松）中包含它。  最终答案: C | C | 1 | C | 1 | 11.11 |
| EVAL-20260914 | DLBCL-Evidence | P1-006 | ，CD20阳性是DLBCL的关键免疫表型标志，而Burkitt淋巴瘤虽也CD20阳性，但通常表现为极高的增殖指数（如Ki-67接近100%）和特定染色体易位（如MYC重排），且常伴有骨髓或中枢神经系统受累；Hodgkin淋巴瘤则以Reed-Sternberg细胞为特征，CD20阴性或弱阳性；成人T细胞淋巴瘤为T细胞来源，CD20阴性。  因此，最可能的诊断是弥漫性大B细胞淋巴瘤。  最终答案: C | C | 1 | C | 1 | 20.97 |
| EVAL-20260914 | 无检索对照 | P1-006 | icular淋巴结为首发突出表现，且其淋巴结常呈“鱼肉样”，但诊断需MYC+IgH重排等支持，题干未提示； - DLBCL是最常见的侵袭性B细胞淋巴oma，中老年好发，可原发淋巴结或结外，常伴B症状、LDH升高、高Ki-67、CD20+、CD10/BCL6/MUM1等可变，但CD20强阳性是基本特征；本例临床+病理高度契合。  综上，最可能诊断为弥漫大B细胞淋巴瘤（DLBCL）。  最终答案: C | C | 1 | C | 1 | 14.87 |
| EVAL-20260914 | DLBCL-Evidence | P1-007 | CD30（常共表达CD15），指南明确将CD15/CD30阴性作为支持NLPHL诊断的关键鉴别点 [S1]。  指南未直接提及“popcorn cells”术语，但[S1]明确将CD19/CD20阳性、CD15/CD30阴性列为B细胞淋巴瘤免疫表型分析的核心判别要素，并强调需结合形态学（含细胞大小、模式）与临床特征综合判断；该免疫表型组合在霍奇金淋巴瘤分类中特异性指向NLPHL。  最终答案: B | B | 1 | B | 1 | 59.14 |
| EVAL-20260914 | 无检索对照 | P1-007 | 化型cHL：最常见cHL亚型，典型为胶原带分隔的结节、陷窝细胞（CD30+/CD15+），不呈爆米花样，且有明显纤维化。  D. 淋巴细胞消减型cHL：罕见，预后差，富于RS细胞、淋巴细胞稀少，常伴EBV+，CD30+/CD15+，不符合。  因此，最可能诊断是 **Nodular lymphocyte-predominant Hodgkin lymphoma（NLPHL）**。  最终答案: B | B | 1 | B | 1 | 16.78 |
| EVAL-20260914 | DLBCL-Evidence | P1-008 | 分缓解且IPI 0–2可考虑继续利妥昔单抗，否则需化疗免疫治疗。 - 若初始即为化疗免疫治疗，则后续见BCEL-7 [S1]。  此外，[S2]图2（BCEL-1）显示DLBCL需进行免疫表型分型（CD20+、CD45+、CD3-等）及FISH检测MYC/BCL2/BCL6重排，但此患者尚未确诊，故需先活检明确病理类型。然而，基于其移植背景和临床表现，PTLD是最可能的诊断路径。  最终答案: D | D | 1 | D | 1 | 38.9 |
| EVAL-20260914 | 无检索对照 | P1-008 | 肾功能不全、高钙、M蛋白、溶骨性病变；本例无骨痛、肌酐正常、无高钙、无M蛋白提示（未查但题干未提异常蛋白电泳），且淋巴结肿大和脾大非MM特征（MM极少引起显著淋巴结/脾大）。  - D. 非霍奇金淋巴瘤（NHL）：完全符合：免疫抑制+年龄+全身症状+多站淋巴结肿大+脾大+LDH↑+血细胞减少+家族史。尤其在移植后患者中，NHL（尤其是DLBCL型PTLD）是最常见的恶性肿瘤之一。  最终答案: D | D | 1 | D | 1 | 15.8 |
| EVAL-20260914 | DLBCL-Evidence | P1-009 | 乏NCCN证据支持。  - **D. Charcot–Marie–Tooth disease**：为遗传性周围神经病，起病隐匿、进展缓慢、常有家族史；本例急性起病（1周）、与化疗时间高度相关，不符合该病临床特征；指南亦未在任何段落中提及该病与淋巴瘤或其治疗的关联 [S1–S6]。  综上，最可能病因是vincristine所致周围神经病变，属R-CHOP方案已知且典型的不良反应。  最终答案: A | A | 1 | A | 1 | 21.08 |
| EVAL-20260914 | 无检索对照 | P1-009 | 脑变性、Lambert-Eaton综合征），且多与特定抗体相关（如anti-Hu、anti-CV2），但本例为化疗期间新发、快速进展的对称性远端神经病，更符合药物毒性； - Charcot–Marie–Tooth病（D）是遗传性周围神经病，起病早（青少年期），慢性进展，家族史常阳性，不符合本例急性亚急性、老年、化疗相关病史。  综上，最可能原因为vincristine的神经毒性。  最终答案: A | A | 1 | A | 1 | 13.62 |
| EVAL-20260914 | DLBCL-Evidence | P1-010 | 使用rasburicase进行预防，而allopurinol仅适用于低风险或对rasburicase不耐受者 [S1]。因此，最可能预防此情况的是rasburicase，但选项中未直接列出，而allopurinol虽可用于低风险患者，但在此高风险情况下效果有限。然而，在现有选项中，allopurinol是唯一与TLS预防相关的药物，且指南明确指出其用于低风险患者的预防 [S1]。  最终答案: A | A | 1 | A | 1 | 21.06 |
| EVAL-20260914 | 无检索对照 | P1-010 | ly to have prevented”，四个选项中仅A有合理病理生理依据。  注意：该患儿已出现明显AKI、高钾、低钙等，说明TLS已发生，但问题问的是“which is most likely to have prevented”——即回顾性判断哪个干预最可能阻止该病程。  综上，最佳答案是A（Allopurinol），因其是标准预防用药之一，而其他选项均无预防TLS证据。  最终答案: A | A | 1 | A | 1 | 23.51 |
| EVAL-20260914 | DLBCL-Evidence | P1-011 | 瘤（如甲状腺MALT淋巴瘤）的典型初始表现进行讨论——尽管原发性甲状腺淋巴瘤可表现为甲状腺肿块，但本例存在明确甲状腺毒症生化证据，更倾向良性毒性结节或Graves病，而非常见于老年人的甲状腺黏膜相关淋巴组织（MALT）淋巴瘤，且指南未就此类鉴别提供流程或推荐 [S1–S6]。  因此，基于NCCN B细胞淋巴瘤指南的可用证据，**无法依据[S1–S6]对本题选项作出循证推荐**。  最终答案: D | D | 1 | D | 1 | 12.98 |
| EVAL-20260914 | 无检索对照 | P1-011 | 癌，但**甲亢的存在优先要求明确功能状态**，因为功能状态决定诊断路径和初始干预。超声特征（高回声）本身不特异（可为胶质结节，也可见于乳头状癌，但高回声更倾向良性）；而ATA指南强调：**所有TSH降低的结节，均应先行scintigraphy**（除非临床高度怀疑癌且需紧急处理，但本例无呼吸困难、声嘶、固定硬块、LN肿大等紧迫恶性征象）。  综上，下一步最合理的是甲状腺核素扫描。  最终答案: D | D | 1 | D | 1 | 27.77 |
| EVAL-20260914 | DLBCL-Evidence | P1-012 | **ciprofloxacin** 是唯一可能通过预防继发感染来减轻症状的药物，但并非直接预防出血性膀胱炎。而 **dexrazoxane** 仅用于心脏保护，不适用于此。  综上所述，**该患者当前状况最可能是由化疗药物引起的出血性膀胱炎，而选项中无直接预防该并发症的药物**。但在所有选项中，**ciprofloxacin** 可能通过预防继发感染间接改善症状，因此相对更合理。  最终答案: C | C | 1 | B | 0 | 28.47 |
| EVAL-20260914 | 无检索对照 | P1-012 | cin：抗生素，虽可治疗细菌性膀胱炎，但本例无明确感染证据（细菌偶见、WBC仅7/hpf、无发热、无脓尿），且不能预防化疗药物所致的毒性膀胱炎 → ❌   D. Dexrazoxane：用于预防**蒽环类药物（如多柔比星）所致的心脏毒性**，对膀胱毒性无效 → ❌    因此，最可能预防该患者出血性膀胱炎的是**美司钠**（即 mercaptoethane sulfonate）。  最终答案: B | B | 1 | B | 1 | 13.23 |
| EVAL-20260914 | DLBCL-Evidence | P1-013 | 是紫杉醇类药物的作用机制，如多西他赛，不适用于 bortezomib。 - C. 阻止DNA超螺旋的松弛：这属于拓扑异构酶抑制剂（如依托泊苷）的作用机制。 - D. 抑制酪氨酸激酶受体：这是布鲁顿酪氨酸激酶抑制剂（如 ibrutinib、acalabrutinib）的作用机制，而非 bortezomib。  因此，bortezomib 的药理作用最准确描述为引起泛素化蛋白的积累。  最终答案: B | B | 1 | B | 1 | 50.5 |
| EVAL-20260914 | 无检索对照 | P1-013 | ercoils → 这是拓扑异构酶II抑制剂（如etoposide）或拓扑异构酶I抑制剂（如irinotecan）的作用，错误。  D. Inhibition of tyrosine kinase receptors → 如伊马替尼（imatinib）靶向BCR-ABL，或gefitinib靶向EGFR，bortezomib不作用于酪氨酸激酶受体，错误。  因此，正确答案是 B。  最终答案: B | B | 1 | B | 1 | 7.66 |
| EVAL-20260914 | DLBCL-Evidence | P1-014 | zoxane：拓扑异构酶II抑制剂，用于蒽环类心脏保护，不影响6-MP代谢；   B. Mesna：结合尿路毒性代谢物（如丙烯醛），用于环磷酰胺/异环磷酰胺，不干扰嘌呤代谢；   D. Amifostine：有机硫代磷酸盐，自由基清除剂，用于减轻放化疗所致肾毒性和口腔炎，无已知6-MP相互作用。    因此，唯一明确增加6-MP毒性的药物是 **C. Allopurinol**。  最终答案: C | C | 1 | C | 1 | 13.59 |
| EVAL-20260914 | 无检索对照 | P1-014 | ：拓扑异构酶II抑制剂，用于蒽环类药物（如多柔比星）的心脏保护，不干扰6-MP代谢。 B. Mesna：与环磷酰胺/异环磷酰胺联用以预防出血性膀胱炎，通过结合丙烯醛起作用，不影响嘌呤代谢。 D. Amifostine：有机硫代磷酸盐，作为自由基清除剂用于减轻顺铂肾毒性和放疗口腔毒性，无已知对6-MP代谢的影响。  因此，唯一会显著增加6-MP毒性的药物是 allopurinol。  最终答案: C | C | 1 | C | 1 | 8.41 |
| EVAL-20260914 | DLBCL-Evidence | P1-015 | 巴瘤患者，尤其是接受化疗前存在高肿瘤负荷、高LDH、肾功能不全等危险因素者 [S2]。  - 指南未覆盖部分：本例患者无淋巴oma确诊依据、无化疗启动、无急性肾损伤或高尿酸等TLS支持证据；其慢性肌无力、便秘更符合原发性高钙血症（如原发性甲旁亢）表现，但NCCN B细胞淋巴瘤指南未讨论此类非TLS相关的钙磷代谢紊乱 [S1–S6 均未涉及PTH/钙/磷轴在无TLS状态下的判读]。  最终答案: B | B | 1 | C | 0 | 13.87 |
| EVAL-20260914 | 无检索对照 | P1-015 | e不引起高钙；但需注意——长期甲氨蝶呤可能致肝纤维化，但无关钙磷代谢。Lisinopril不影响钙磷。Metformin亦无影响。**  无证据支持维生素D中毒（无补充史）、结节病（无肺门淋巴结肿大、ACE升高、高钙等提示）、乳碱综合征（无大量钙剂/抗酸剂摄入史）。  综上，最可能诊断是**原发性甲状旁腺功能亢进**，典型生化：**PTH↑、Ca²⁺↑、Phosphate↓**。  最终答案: C | C | 1 | C | 1 | 17.5 |
| EVAL-20260914 | DLBCL-Evidence | P1-016 | 选项D（感染性外周静脉导管）缺乏临床支持：患者无导管局部征象，血培养为凝固酶阴性葡萄球菌（常见于皮肤定植，但在此免疫抑制背景下更倾向血源性播散至心脏，而非导管原发感染）；指南亦未将外周静脉导管列为IE主要危险因素。  指南未直接提及“凝固酶阴性葡萄球菌所致IE的最强危险因素分层”，但基于[S1][S2]对利妥昔单抗所致免疫抑制作为感染易感性核心机制的明确归因，其权重高于其他选项。  最终答案: C | C | 1 | D | 0 | 19.13 |
| EVAL-20260914 | 无检索对照 | P1-016 | fever + CoNS血培养+经食管超声（虽未明说，但TTE/TEE发现赘生物）→ 高度提示IE；   - **最强的解剖学易感基础是predamaged valve（MVP）**，它使细菌易于黏附、定植、形成赘生物。其他因素（拔牙、免疫抑制）是促成感染的协同因素，但非“最强”前提。  因此，**predamaged heart valve（A）是最强的、根本性的易感因素**。  最终答案: A | A | 1 | D | 0 | 26.98 |
| EVAL-20260914 | DLBCL-Evidence | P1-017 | 物 [S1]。  在选项中，抗CD20单克隆抗体（如利妥昔单抗）是用于CLL和B细胞淋巴瘤的标准治疗方案之一，其机制为靶向CD20阳性B细胞，导致B细胞耗竭，从而增加PML风险。其他选项如酪氨酸激酶抑制剂（如伊布替尼）、拓扑异构酶II抑制剂（如阿霉素）或EGFR单抗均不直接导致此类免疫抑制相关病毒感染。  因此，最可能引起该患者当前状况的抗肿瘤药物机制是针对CD20的单克隆抗体。  最终答案: D | D | 1 | D | 1 | 13.63 |
| EVAL-20260914 | 无检索对照 | P1-017 | nst EGFR：如西妥昔单抗，用于结直肠癌、头颈癌，不用于CLL，且与PML无关。  D. Monoclonal antibody against CD20+：即利妥昔单抗、奥妥珠单抗等。**利妥昔单抗是PML最强相关药物之一**，FDA黑框警告其PML风险，尤其在血液肿瘤（CLL、NHL）患者中。  因此，该患者PML由CD20单抗（利妥昔单抗）所致的严重B细胞免疫缺陷引发。  最终答案: D | D | 1 | D | 1 | 12.41 |
| EVAL-20260914 | DLBCL-Evidence | P1-018 | 未推荐用于 VZV；  - C（休息+NSAIDs）不能控制 VZV 复制，且 NSAIDs 在 Scr 3.0 mg/dL 时禁用；  - D（泛昔洛韦）是带状疱疹一线口服抗病毒药，但该适应症及用药决策不在 NCCN B 细胞淋巴瘤指南覆盖范围内 [S1]。  综上，NCCN B 细胞淋巴瘤指南未就本例的带状疱疹诊断及抗病毒治疗提供任何推荐或路径指引，所有选项均无指南支持依据。  最终答案: D | D | 1 | D | 1 | 16.33 |
| EVAL-20260914 | 无检索对照 | P1-018 | a painful stripe of vesicular lesions”），无系统症状，且选项中无阿昔洛韦（静或口），而D为famciclovir——其在轻中度免疫抑制患者中被指南认可（如IDSA 2018：对于HIV或血液肿瘤患者，若皮损局限、无内脏受累，可考虑口服泛昔洛韦/伐昔洛韦/法昔洛韦，但需密切监测）。且题目问“best course”，D是唯一针对病因的合理选择。  最终答案: D | D | 1 | D | 1 | 21.72 |
| EVAL-20260914 | DLBCL-Evidence | P1-019 | 在FL中具有高度特异性，是其标志性的染色体异常，尤其在BCL2过表达的情况下几乎可以确定存在该易位 [S1]。其他选项如t(3;3)、t(9;14)和t(11;18)分别与边缘区淋巴瘤、套细胞淋巴瘤或MALT淋巴瘤相关，不常见于FL [S1]。此外，FOLL-1流程图显示，当确诊为FL时，若存在BCL2重排，则归类为经典FL（cFL），并进入相应管理路径（FOLL-2）[S2]。  最终答案: D | D | 1 | D | 1 | 22.54 |
| EVAL-20260914 | 无检索对照 | P1-019 | 32），罕见，见于某些小淋巴细胞淋巴瘤或边缘区淋巴瘤，非FL。   C. t(11;18)(q21;q21) —— 即**API2-MALT1**融合，是黏膜相关淋巴组织（MALT）淋巴瘤的特征性易位，尤其与幽门螺杆菌阴性胃MALT或肺MALT相关，与FL无关。  因此，唯一符合“滤泡性淋巴瘤 + BCL-2过表达”的细胞遗传学异常是 **t(14;18)(q32;q21)**。  最终答案: D | D | 1 | D | 1 | 11.09 |
| EVAL-20260914 | DLBCL-Evidence | P1-020 | 患者中细菌性肺炎更常由革兰阴性菌或耐药菌引起，而非首选考虑；   - *Streptococcus pneumoniae*：典型社区获得性肺炎病原，免疫功能正常者多见，极少导致咯血及空洞，且对常规抗生素敏感，病情进展不会如此隐匿急进。   综上，最符合免疫抑制宿主、咯血、胸痛、发热及影像学异常的诊断是侵袭性肺曲霉病，*Aspergillus fumigatus* 是最常见致病菌。  最终答案: A | A | 1 | A | 1 | 21.25 |
| EVAL-20260914 | 无检索对照 | P1-020 | ，更倾向真菌而非典型细菌。  - A. Aspergillus fumigatus：是造血干细胞移植患者肺部侵袭性真菌感染最常见病原（占IPA的80–90%），尤其在中性粒细胞减少期及预处理后早期（本例正处此阶段）。咯血（因血管侵袭）、胸痛（胸膜炎或梗死）、发热、影像学特征性表现均高度支持。  综上，最可能诊断为侵袭性肺曲霉病，病原体为Aspergillus fumigatus。  最终答案: A | A | 1 | A | 1 | 17.27 |
| EVAL-20260914 | DLBCL-Evidence | P1-021 | 相关出血的常见原因，符合临床表现。  其他选项分析如下： - B. 扩张型心肌病：无证据支持，心脏杂音加重可能与原有主动脉瓣狭窄有关，而非新发心肌病。 - C. 肥厚型心肌病：无典型症状或体征支持，如胸痛、晕厥等。 - D. 感染性心内膜炎：虽有心脏杂音变化，但缺乏发热、栓塞事件、Osler结节等典型表现，且无感染证据。  因此，最可能的病因是化疗引起的血小板减少所致出血性体质。  最终答案: A | A | 1 | D | 0 | 27.17 |
| EVAL-20260914 | 无检索对照 | P1-021 | morrhages、触痛性petechiae等全身栓塞/感染征象。  D. 感染性心内膜炎：完美契合全部表现——免疫抑制+血管内导管+新发/加重杂音+微血管栓塞体征（Roth spots, splinter hemorrhages, painful digital petechiae）+全身症状（乏力、易瘀伤可能反映脓毒症状态及DIC早期）。  因此，最可能诊断是感染性心内膜炎。  最终答案: D | D | 1 | D | 1 | 21.21 |
| EVAL-20260914 | DLBCL-Evidence | P1-022 | 配合水化的情况下。  但更关键的是：**指南强调，TLS预防应在化疗前开始，且高风险患者应使用rasburicase** [S1]。而本例中，患儿已经开始化疗，且已出现症状，说明预防不足。  综上所述，**最可能有效预防该患者症状的措施是rasburicase**，但不在选项中。在现有选项中，**碱化尿液（B）是最接近合理的干预措施**，尽管其证据强度低于rasburicase。  最终答案: B | B | 1 | B | 1 | 33.4 |
| EVAL-20260914 | 无检索对照 | P1-022 | LS患者（如Burkitt）更推荐**别嘌醇或拉布立酶（rasburicase）** 控制尿酸，但本题问的是“most likely to have been effective in preventing”，且选项中未提供别嘌醇/拉布立酶；而**尿液碱化**是经典、基础、直接针对尿酸结晶形成的预防手段，尤其在未使用降尿酸药物时尤为关键。  综上，最可能有效的预防措施是尿液碱化。  最终答案: B | B | 1 | B | 1 | 15.84 |
| EVAL-20260914 | DLBCL-Evidence | P1-023 | 故必须优先解除梗阻 [S1]。   - 选项D（膀胱导尿）不能缓解上尿路梗阻，因超声已显示膀胱正常大小，排除尿潴留；选项A（袢利尿剂）在无尿及肾前性/肾后性损伤时无效且可能加重电解质紊乱；选项B（肾动脉支架）针对肾血管狭窄，与当前影像学表现不符；选项C（双侧输尿管支架）是解除上尿路梗阻、恢复尿流通畅的标准急诊干预措施，可立即改善肾灌注、促进代谢产物排泄，为后续抗肿瘤治疗创造条件。  最终答案: C | C | 1 | C | 1 | 16.94 |
| EVAL-20260914 | 无检索对照 | P1-023 | 膜后病变（如淋巴瘤）压迫输尿管所致的双侧梗阻性肾病。可迅速恢复尿流通畅，逆转AKI。  D. Catheterization of the bladder — 错误。膀胱正常大小，说明不是膀胱出口梗阻或尿潴留；导尿不能解决上尿路梗阻，且无法引流肾盂内尿液，故不能缓解肾积水或改善肾功能。  因此，最恰当、最紧急且有效的干预是双侧输尿管支架置入（ureteral stenting）。  最终答案: C | C | 1 | C | 1 | 15.77 |
| EVAL-20260914 | DLBCL-Evidence | P1-024 | BP 100/65，HR 100，无心动过速或低灌注体征），不支持B（肾血管收缩+容量不足）；   - 无溶血或横纹肌溶解病史，无血红蛋白尿/肌红蛋白尿，不支持C（色素肾病）；   - 尿酸结晶性肾病是TLS相关AKI的最常见机制之一，尤其在未充分水化、碱化尿液或预防降尿酸治疗时。  因此，最可能病因是：**尿酸在肾小管内沉淀 → 急性肾损伤**，即肿瘤溶解综合征的核心肾脏表现。  最终答案: D | D | 1 | D | 1 | 26.26 |
| EVAL-20260914 | 无检索对照 | P1-024 | 素性肾病，如肌红蛋白、血红蛋白）：无溶血或横纹肌溶解证据（Hb 15 g/dL正常，无LDH、肌酶、血红蛋白尿等提示）； - D明确指出“precipitation of uric acid in renal tubules / tumor lysis syndrome”，完全契合临床与实验室特征。  因此，最可能病因是尿酸在肾小管内沉淀所致的急性肾损伤，即TLS的核心肾脏机制。  最终答案: D | D | 1 | D | 1 | 14.9 |
| EVAL-20260914 | DLBCL-Evidence | P1-025 | 等介导，BCL-2不直接调控周期进程；   B. 激活DNA修复蛋白 → 如ATM、BRCA1/2、PARP等参与，BCL-2无关；   C. 抑制凋亡 → 正确，BCL-2是经典抗凋亡蛋白，阻断caspase级联激活；   D. 通过信号转导调节细胞生长 → 如RAS/MAPK、PI3K/AKT通路，BCL-2不属于信号转导分子，不直接调控生长信号。  因此，最可能的机制是C。  最终答案: C | C | 1 | C | 1 | 13.91 |
| EVAL-20260914 | 无检索对照 | P1-025 | C. Inhibits apoptosis → ✅ 正确。BCL2是经典凋亡抑制蛋白。  D. Regulates cell growth through signal transduction → 这是生长因子受体（如EGFR）、RAS/MAPK、PI3K/AKT通路等的功能；BCL2不属信号转导分子，不传递生长信号。  因此，最可能的致病蛋白是BCL2，其核心功能是抑制凋亡。  最终答案: C | C | 1 | C | 1 | 10.14 |
| EVAL-20260914 | DLBCL-Evidence | P1-026 |  酪氨酸激酶基因突变：BTK是关键的酪氨酸激酶，其突变导致XLA，符合本例所有表现。 - C. 染色体22q11.2微缺失：导致DiGeorge综合征，表现为胸腺发育不良、低钙血症、心脏畸形等，不符合本例。 - D. NADPH氧化酶基因突变：导致慢性肉芽肿病（CGD），表现为反复细菌和真菌感染，但通常有中性粒细胞功能异常，而非B细胞缺乏。  因此，最可能的病因是BTK基因突变。  最终答案: B | B | 1 | B | 1 | 28.85 |
| EVAL-20260914 | 无检索对照 | P1-026 | ，但抗体应答可能受损（因T细胞辅助不足）；本例B细胞明显缺乏，且无相关畸形，不支持。 - D. NADPH氧化酶基因突变 → 慢性肉芽肿病（CGD）：吞噬细胞杀菌功能障碍，易发过氧化氢酶阳性菌（如金黄色葡萄球菌、曲霉）感染，但B/T细胞数量和功能正常，无低丙种球蛋白，不引起B细胞减少或腺样体/扁桃体发育不良。  因此，最可能的诊断是XLA，由BTK（一种酪氨酸激酶）基因突变引起。  最终答案: B | B | 1 | B | 1 | 13.51 |
| EVAL-20260914 | DLBCL-Evidence | P1-027 | 受累 [S1]。然而，本题核心是急性感染的处理，而非淋巴瘤分型。  对于免疫功能低下的成人患者，怀疑细菌性脑膜炎时，初始经验性治疗应覆盖革兰氏阳性球菌（如肺炎链球菌）、革兰氏阴性杆菌（如大肠埃希菌）和李斯特菌。因此，推荐使用万古霉素（覆盖耐药革兰氏阳性菌）、氨苄西林（覆盖李斯特菌）和头孢吡肟（广谱抗革兰氏阴性菌）联合治疗 [S2]。此方案适用于免疫抑制患者，尤其是近期接受化疗者。  最终答案: D | D | 1 | D | 1 | 29.13 |
| EVAL-20260914 | 无检索对照 | P1-027 | 最恰当初始治疗是：**ampicillin + cefotaxime**（即选项A）。  注意：虽然cefotaxime本身不抗李斯特，但联合ampicillin是标准推荐；而单用ampicillin虽理论上可行，但指南不推荐单药（因需兼顾其他细菌）；选项中无ampicillin单药，A是唯一含ampicillin且搭配合理三代头孢的选项。  B、C明显错误；D过度治疗且无必要。  最终答案: A | A | 1 | D | 0 | 32.5 |
| EVAL-20260914 | DLBCL-Evidence | P1-028 | 2 cm，具有可疑影像学特征（不规则边缘、微钙化），结合病理结果，已高度提示恶性。  在NCCN B细胞淋巴瘤指南中，无关于甲状腺结节或甲状腺癌的直接推荐。然而，对于存在可疑恶性甲状腺结节的患者，尤其是有放射治疗史者（如本例曾接受头颈部放疗），应考虑手术切除以明确诊断并治疗潜在恶性病变。  因此，最合适的下一步是行**总甲状腺切除术**，以彻底评估和治疗可能存在的甲状腺乳头状癌。  最终答案: D | D | 1 | D | 1 | 35.68 |
| EVAL-20260914 | 无检索对照 | P1-028 | 状腺切除术（Total thyroidectomy）：符合当前指南推荐——FNA证实PTC + 有头颈部放疗史（高危因素）+ 年龄<45岁（AJCC分期自动为I期，但仍需充分手术）。虽部分低危单灶PTC可仅行腺叶切除，但本例存在明确高危背景，**全切是更合理、更常用的选择**，也为后续可能的RAI治疗和Tg监测奠定基础。  因此，最恰当的下一步是手术，且为**全甲状腺切除术**。  最终答案: D | D | 1 | D | 1 | 16.46 |
| EVAL-20260914 | DLBCL-Evidence | P1-029 |  Penicillin: **at time of surgery**（实际指术后即刻开始，临床常理解为围术期启动）**for 5 years**  选项B表述为：“Vaccinate: 2 weeks prior to surgery; Penicillin: at time of surgery for 5 years”——符合主流指南共识（如 ASH、IDSA、NICE）。  最终答案: B | B | 1 | B | 1 | 18.76 |
| EVAL-20260914 | 无检索对照 | P1-029 |  ≥2 weeks preop → eliminates C and D   - Penicillin must start *after* splenectomy → eliminates A (“2 weeks prior”)   → Only B remains.  Thus, B is the best available answer.  Final answer: B  最终答案: B | B | 1 | B | 1 | 44.69 |
| EVAL-20260914 | DLBCL-Evidence | P1-030 | 指南未直接提及组蛋白去乙酰化酶（HDAC）抑制剂对DNA结构或基因转录的分子作用机制。所有可用证据 [S1–S6] 均聚焦于B细胞淋巴瘤（如DLBCL、PTLD、EMZL等）的临床分类、预后因素、治疗反应及安全性数据，未涉及表观遗传调控机制、组蛋白修饰、染色质构象变化或HDAC抑制剂的药理学原理。  最终答案: B | B | 1 | B | 1 | 7.33 |
| EVAL-20260914 | 无检索对照 | P1-030 | ription：错误，HDACi通常增强（再激活）转录，尤其是沉默的抑癌基因； - D. Increased heterochromatin formation：错误，HDACi促进常染色质，减少异染色质。  注意：“DNA coiling”在此语境中是通俗指染色质高级结构（核小体串珠→螺线管→超螺线管等），并非DNA双螺旋本身的卷曲；组蛋白乙酰化主要影响核小体间及高级压缩程度。  最终答案: B | B | 1 | B | 1 | 7.34 |
| EVAL-20260914 | DLBCL-Evidence | P1-031 | 酸、钾、BUN，是终末期或药物无效/危及生命时的挽救治疗，但**rasburicase起效更快、更特异、创伤更小，且能逆转尿酸性肾病的病理基础**——因此，若无禁忌（如G6PD缺乏），**rasburicase应为首选初始紧急治疗**，常可避免透析。  注意：该患者有AIDS和淋巴瘤，需确认G6PD水平（rasburicase禁忌于G6PD缺乏），但题干未提示，故按常规首选处理。  最终答案: D | D | 1 | B | 0 | 13.58 |
| EVAL-20260914 | 无检索对照 | P1-031 | ，而rasburicase在数小时内即可显著降低尿酸，继而改善肾功能和电解质——这是最直接、最有效的逆转策略。透析是补救，rasburicase是靶向逆转。  此外，该患者为AIDS相关Burkitt淋巴oma，属极高肿瘤负荷，对rasburicase反应良好；且无G6PD缺乏禁忌（题干未提示，临床使用前需筛查，但本题未给出禁忌信息，故默认可用）。  综上，**D是最佳答案**。  最终答案: D | D | 1 | B | 0 | 26.6 |
| EVAL-20260914 | DLBCL-Evidence | P1-032 | 隆性白细胞，非原始细胞）；   - Evans综合征（选项C）需同时存在AIHA和免疫性血小板减少，但本例血小板计数正常（350,000/mm³），不支持；   - 单纯脾肿大（D）可致轻度血细胞滞留，但不足以解释重度溶血生化指标（LDH↑↑、胆红素↑↑）；骨髓浸润（B）在CLL中多呈渐进性，罕致急性重度贫血而无其他系受累，且LDH升高幅度通常不如AIHA显著 [S1, S2]。  最终答案: A | A | 1 | A | 1 | 25.17 |
| EVAL-20260914 | 无检索对照 | P1-032 | ，题干可能省略），且无需感染或其他诱因。  注意：MCV 105 μm³（即fL）偏高，需考虑是否合并叶酸/B12缺乏，但CLL患者AIHA急性发作时，网织红细胞大量释放（大细胞）可致MCV假性升高；且CLL本身不引起巨幼变，无其他巨幼特征（如中性粒细胞分叶过多未提及），故不支持原发营养缺乏。  综上，最可能诊断是 **Autoimmune hemolytic anemia**。  最终答案: A | A | 1 | A | 1 | 21.64 |
| EVAL-20260914 | DLBCL-Evidence | P1-033 | l nystatin）：局部抗真菌药，适用于轻中度口腔念珠菌病，安全有效，是典型一线经验性治疗。   - C（活检）：无特异性溃疡、结节、硬结或不愈合表现，且有典型真菌感染特征，活检非首选；仅当治疗无效或怀疑恶性/其他病因时考虑。   - D（局部激素）：可能加重真菌感染，绝对禁忌。    因此，下一步最合理的是启动经验性抗真菌治疗，即** topical nystatin**。  最终答案: B | B | 1 | B | 1 | 19.89 |
| EVAL-20260914 | 无检索对照 | P1-033 | 患者无食管受累表现（如吞咽痛、胸骨后痛），故可先试用局部治疗；   - Biopsy（C）适用于：不典型病变、治疗无效、怀疑恶性肿瘤或深部真菌/其他感染（如组织胞浆菌病），但本例临床典型，无需首选活检；   - Topical corticosteroids（D）会加重真菌感染，绝对禁忌。  因此，下一步最佳措施是启动经验性抗真菌治疗——**Topical nystatin**。  最终答案: B | B | 1 | B | 1 | 14.35 |
| EVAL-20260914 | DLBCL-Evidence | P1-034 | （如母亲HIV阳性）可导致免疫缺陷相关Burkitt淋巴瘤，但该患儿目前无明确HIV感染证据，且免疫缺陷相关型更常见于成人或免疫抑制个体 [S1]。 - 患儿的性别（男性）虽在某些研究中显示轻微倾向，但并非决定性因素；而近期从赤道非洲移民是该病发生的关键环境风险因素 [S1]。 - 颌下肿块伴溃疡可能是肿瘤本身的表现，而非直接病因；感染性溃疡是继发表现，非主要致病原因 [S1]。  最终答案: C | C | 1 | C | 1 | 18.99 |
| EVAL-20260914 | 无检索对照 | P1-034 | oradic) and biology, not sex.  Thus, the jaw lymph node involvement is most likely explained by the endemic form of Burkitt lymphoma, whose hallmark is geographic origin in equatorial Africa.  最终答案: C | C | 1 | C | 1 | 11.7 |
| EVAL-20260914 | DLBCL-Evidence | P1-035 |  400  - 假阳性（FP）= 健康对照组中检测阳性者 = 0  因此，PPV = $ \frac{400}{400 + 0} $，对应选项 D。  指南未在任何讨论段落（[S1]–[S2]）中定义或计算PPV，亦未涉及诊断试验性能指标（如敏感性、特异性、PPV、NPV）的公式推导或临床应用建议 [S1–S4]。该问题属于基础流行病学/诊断试验统计概念，不依赖NCCN指南内容。  最终答案: D | D | 1 | D | 1 | 10.69 |
| EVAL-20260914 | 无检索对照 | P1-035 | 即100%）  看选项：  A. 700 / (700 + 0) → 错误，混淆了患病总数与阳性数   B. 700 / (400 + 400) → 无意义   C. 400 / (400 + 300) → 300是诊断组中阴性人数（700−400），但分母应为所有阳性（TP+FP），不是TP+FN   D. 400 / (400 + 0) → 正确，TP / (TP + FP)  最终答案: D | D | 1 | D | 1 | 8.21 |
| EVAL-20260914 | DLBCL-Evidence | P1-036 | 不包含LPL，亦未将LPL归入EBV或HHV-8驱动的淋巴瘤类别。  适用人群： - 该HCV关联证据适用于确诊为低级别B细胞NHL（如LPL、边缘区淋巴瘤、慢性淋巴细胞白血病/小淋巴细胞淋巴瘤）的患者，尤其当伴肝脾肿大、冷球蛋白血症或混合性单克隆丙种球蛋白病时，HCV筛查为指南推荐 [S1]。  指南未直接提及淋巴浆细胞淋巴瘤与EBV、HHV-8或HIV的因果或高频率共存关系。  最终答案: A | A | 1 | A | 1 | 22.13 |
| EVAL-20260914 | 无检索对照 | P1-036 | —— 可导致DLBCL、Burkitt淋巴瘤、CNS淋巴瘤等，但非LPL/Waldenström的常见诱因；HIV相关淋巴瘤多为EBV驱动的高增殖性B细胞淋巴瘤；   D. EBV —— 与PTLD、DLBCL（尤其在免疫抑制者）、鼻型NK/T细胞淋巴瘤、霍奇金淋巴瘤密切相关，但在经典WM中EBV通常阴性（EBER原位杂交多为阴性）。  因此，最可能检出的感染因子是丙型肝炎病毒。  最终答案: A | A | 1 | A | 1 | 12.95 |
| EVAL-20260914 | DLBCL-Evidence | P1-037 | S1]末句提及CLL FISH鉴别），不构成对当前患者精神症状的解释依据；所有讨论内容均围绕肿瘤生物学、检测技术与治疗干预展开，**完全不涉及精神障碍分类、DSM/ICD诊断框架、发育期抑郁特征或哀伤反应鉴别**。  因此，本题所涉临床判断（在抑郁障碍谱系中区分MDD、调整障碍、PDD等）**超出NCCN B细胞淋巴瘤指南覆盖范围**，指南未提供任何直接或间接支持诊断选择的证据。  最终答案: C | C | 1 | B | 0 | 13.54 |
| EVAL-20260914 | 无检索对照 | P1-037 | 除。   B. Major depressive disorder：符合DSM-5标准：    • ≥2周的情绪低落或易激惹 + ≥4项其他症状（兴趣减退、食欲改变、睡眠过多、疲劳、注意力下降、功能损害）；    • 排除双相、物质、躯体疾病所致；    • 青少年中易激惹可等同于情绪低落作为核心症状。    因此最可能诊断是：Major depressive disorder。  最终答案: B | B | 1 | B | 1 | 12.82 |
| EVAL-20260914 | DLBCL-Evidence | P1-038 |  错误：使用的是患病率（prevalence），而非发病率；且未考虑时间因素 - D 错误：使用的是累积发病率（cumulative incidence），但未说明随访时间，且数值不准确  [S1] 中的决策流程图（BCEL-9）显示了复发/难治性DLBCL的随访策略，包括临床评估和影像学检查频率，但与本题无关。其他图片（BCEL-C系列）为治疗方案表，也未涉及流行病学指标计算。  最终答案: B | B | 1 | B | 1 | 22.69 |
| EVAL-20260914 | 无检索对照 | P1-038 | 准答案应基于**incidence rate（人时法）**，而非累计 incidence。因此该选项虽计算正确，但推论“risk is higher in study 2”不恰当——因为未控制时间，高累计 incidence 可能仅反映更长随访，而非更高速率。指南（如Gordis、Last）强调：当随访时间不同时，必须用人时发病率比较。  因此，唯一正确、严谨、可比的陈述是 B。  最终答案: B | B | 1 | B | 1 | 24.06 |
| EVAL-20260914 | DLBCL-Evidence | P1-039 | 现高粘滞综合征或中枢神经系统症状时，可能需要先进行血浆置换以缓解症状，但本例中CT正常且无急性高粘滞表现，故不首选。  因此，针对该患者的最佳初始治疗应为rituximab，因其可靶向清除异常B细胞并降低IgM水平，改善症状。其他选项如vincristine、prednisone虽可用于某些淋巴瘤，但非WM一线标准；plasmapheresis仅用于高粘滞危象，而本例无明确指征。  最终答案: C | C | 1 | B | 0 | 35.73 |
| EVAL-20260914 | 无检索对照 | P1-039 | amethasone），但起效慢，不适用于急性HVS。 - C. Rituximab：是WM一线系统性治疗的核心药物（尤其单药或联合），但起效需数周，不能快速缓解高黏滞症状。 - D. Prednisone：对WM疗效有限，不作为主要治疗，且无快速降IgM作用。  因此，在存在明确高黏滞综合征表现（CNS症状+出血+IgM升高）时，**首要干预是plasmapheresis**。  最终答案: B | B | 1 | B | 1 | 11.1 |
| EVAL-20260914 | DLBCL-Evidence | P1-040 | B. 全反式维甲酸：用于急性早幼粒细胞白血病，与此无关。 - C. 观察和随访：符合当前指南推荐，适用于无治疗指征的早期CLL/SLL患者 [S1]。 - D. Fludarabine, cyclophosphamide, and rituximab（FCR）：虽为一线治疗方案之一，但仅适用于适合化疗且有治疗指征的患者，不适用于无症状者。  因此，最合适的下一步管理是观察和随访。  最终答案: C | C | 1 | C | 1 | 29.12 |
| EVAL-20260914 | 无检索对照 | P1-040 | 者。 - B. 全反式维甲酸（ATRA）：用于急性早幼粒细胞白血病（APL），与CLL无关。 - D. FCR方案（氟达拉滨+环磷酰胺+利妥昔单抗）：是既往有症状、fit患者的常用一线方案，但**不适用于无症状患者**，且该患者71岁，FCR毒性大（尤其骨髓抑制、免疫抑制），现多被BTK抑制剂替代；更重要的是——无指征启动治疗。  因此，最适当下一步是：**观察和随访（C）**。  最终答案: C | C | 1 | C | 1 | 11.98 |
| EVAL-20260914 | DLBCL-Evidence | P1-041 | 不随浓度变化 —— 这是零级动力学的典型特征。零级动力学下，半衰期 = 0.5 × C₀ / k，随初始浓度线性变化 ⇒ 半衰期可变。  NCCN指南中未定义药代动力学基本原理，亦未讨论Drug A/B的具体性质；所有[S1]–[S2]段落均未涉及药物半衰期的计算逻辑、一级/零级动力学判别或相关数学关系 [Sn]。该问题属于基础药理学概念，超出NCCN B细胞淋巴瘤指南覆盖范围。  最终答案: C | C | 1 | B | 0 | 14.95 |
| EVAL-20260914 | 无检索对照 | P1-041 | 与C成正比   → 浓度升高，半衰期延长 ⇒ **半衰期不恒定（可变）**  ---  ### 结论：  - Drug A：一级动力学 → **恒定半衰期**   - Drug B：零级动力学 → **可变半衰期**  对应选项：   **B. The half-life of drug A is constant but that of drug B is variable**  最终答案: B | B | 1 | B | 1 | 11.83 |
| EVAL-20260914 | DLBCL-Evidence | P1-042 | L管理有专门路径，暗示其为常见类型之一。然而，结合临床背景，HIV患者中最常见的侵袭性B细胞淋巴瘤是**Burkitt淋巴瘤**，尤其在CD4+ < 200时风险显著升高，而本例CD4+为350，仍处于较高风险区间。  尽管指南未直接比较各亚型发病率，但从HIV相关淋巴瘤的流行病学特征及指南对HIV阳性患者的特殊处理路径来看，**Burkitt淋巴瘤**是该患者最可能发展的类型。  最终答案: A | A | 1 | B | 0 | 32.02 |
| EVAL-20260914 | 无检索对照 | P1-042 | HL中，Burkitt占约30–40%，DLBCL占约20–30%，而滤泡性淋巴瘤和SLL极为罕见（<2%），且无明确风险增加。  此外，患者37岁，年龄也更符合Burkitt（好发于青壮年），而滤泡性淋巴瘤和SLL多见于老年人（中位年龄60岁以上）。  因此，综合CD4水平（350）、年龄、HIV背景及流行病学数据，**Burkitt淋巴瘤是最可能的AIDS相关淋巴瘤类型**。  最终答案: A | A | 1 | B | 0 | 13.28 |
| EVAL-20260914 | DLBCL-Evidence | P1-043 | 20+/CD11c+及TRAP阳性支持MCL诊断。若后续检测发现TP53突变，则应考虑使用含venetoclax的方案（如Zanubrutinib, obinutuzumab, venetoclax），但目前无证据提示TP53突变，故暂不适用。  因此，对于该老年、合并多种基础疾病的MCL患者，首选一线治疗方案为**Bendamustine + rituximab**，即选项B。  最终答案: B | B | 1 | B | 1 | 24.59 |
| EVAL-20260914 | 无检索对照 | P1-043 | 重感染预防，但**不能治疗HCL本身**，且在HCL中可能加重脾肿大或白血病细胞动员，一般避免单用。   D. Doxorubicin：蒽环类化疗药，用于侵袭性淋巴瘤（如DLBCL）、AML等，**不用于HCL**；HCL对传统化疗（如CHOP）反应差，且doxo有心毒性和骨髓抑制，会加重已存在的全血细胞减少。  因此，**确诊HCL后，一线根治性治疗是cladribine**。  最终答案: B | B | 1 | B | 1 | 17.83 |
| EVAL-20260914 | DLBCL-Evidence | P1-044 | 作用。其他选项如肺炎球菌结合疫苗13价、脑膜炎球菌结合疫苗和水痘疫苗均未在当前证据中提及适用于该类患者，且部分为活疫苗，可能不安全。  具体分层如下： - 患者年龄≥60岁，属于高风险人群，应优先考虑流感疫苗。 - 正在接受利妥昔单抗治疗，导致免疫功能受损，需避免活疫苗。 - 流感疫苗为灭活疫苗，适合免疫抑制患者使用。 - 无证据支持在该情境下推荐肺炎球菌、脑膜炎球菌或水痘疫苗。  最终答案: D | D | 1 | A | 0 | 74.66 |
| EVAL-20260914 | 无检索对照 | P1-044 | CLL未作强推荐（相较而言，对脾切除或补体缺陷才是强推荐）。  D（Influenza）：时间不合适（7月）。  C：禁忌。  因此，**最适当的是A**——尽管PCV13已更新，但在本题选项中，它是唯一符合“免疫功能低下者亟需、安全（灭活）、无时间禁忌、指南强烈推荐”的疫苗。  （注：真实临床中应给PCV20或PCV15，但题目选项限定PCV13，视为代表肺炎球菌结合疫苗接种）  最终答案: A | A | 1 | A | 1 | 29.15 |
| EVAL-20260914 | DLBCL-Evidence | P1-045 | A）和Follicular lymphoma（D）均为惰性淋巴瘤，进展缓慢，极少出现明显B症状、LDH显著升高、高增殖指数及如此广泛快速进展的淋巴结肿大； - DLBCL（B）是老年人最常见侵袭性B细胞淋巴瘤，典型表现为迅速增大的淋巴结、B症状、结外受累（如本例脾肿大）、LDH升高，免疫表型CD20+，组织学见弥漫性大B细胞、高Ki-67。  因此最可能诊断为弥漫大B细胞淋巴瘤。  最终答案: B | B | 1 | B | 1 | 22.54 |
| EVAL-20260914 | 无检索对照 | P1-045 | 减少、无毛细胞描述、CD20+但未提及其他标志，且淋巴结高度肿大非HCL典型表现（HCL淋巴结肿大轻微或无）； - Diffuse large B-cell lymphoma（DLBCL）：最常见侵袭性B细胞淋巴瘤，可原发结内或结外，常表现为快速增大的淋巴结、B症状、LDH升高、高Ki-67、CD20+；本例所有临床与病理特征均高度吻合。  因此，最可能诊断是弥漫大B细胞淋巴瘤。  最终答案: B | B | 1 | B | 1 | 13.21 |
| EVAL-20260914 | DLBCL-Evidence | P1-046 | 泡性淋巴瘤（cFL），并进入FOLL-2进行后续评估 [S2]。 - 其他选项排除：  - 霍奇金淋巴瘤（A）通常表现为Reed-Sternberg细胞，且不具t(14;18)易位。  - Burkitt淋巴瘤（C）为高度侵袭性，常伴高乳酸脱氢酶、骨髓侵犯，且具有c-MYC重排而非t(14;18)。  - 边缘区淋巴瘤（D）多见于黏膜相关组织，如胃部，且缺乏t(14;18)易位。  最终答案: B | B | 1 | B | 1 | 26.88 |
| EVAL-20260914 | 无检索对照 | P1-046 | 动的淋巴结肿大。 - D. 边缘区淋巴瘤（MZL）：分为黏膜相关淋巴组织（MALT）、结内和脾边缘区；无特异性t(14;18)；脾MZL可有脾肿大，但通常无广泛淋巴结受累，且t(14;18)极罕见（仅个别脾MZL病例报道，非典型）；更常见t(11;18)等。  综上，临床表现（惰性、多灶性淋巴结肿大+脾肿大）、年龄、无B症状、t(14;18)阳性，均高度支持**滤泡性淋巴瘤**。  最终答案: B | B | 1 | B | 1 | 10.54 |
| EVAL-20260914 | DLBCL-Evidence | P1-047 | CL更常见于男性，但非HIV相关DLBCL的独立主要风险； - C. cART依从性差：直接导致CD4恢复不良、持续免疫抑制，是已知的HIV患者罹患非霍奇金淋巴瘤（包括DLBCL）的重要危险因素； - D. 收入水平：属于社会经济因素，指南未将其列为直接医学风险。  因此，在现有证据框架下，最相关的风险因素是**cART依从性差**，因其直接影响免疫功能，进而增加淋巴瘤发生风险。  最终答案: C | C | 1 | C | 1 | 64.0 |
| EVAL-20260914 | 无检索对照 | P1-047 | options, **C. Poor adherence to cART** is the greatest (and most direct) risk factor — it mechanistically underlies immunosuppression and chronic inflammation driving lymphomagenesis.  Final answer: C | invalid | invalid | C | 0 | 10.53 |
| EVAL-20260914 | DLBCL-Evidence | P1-048 | ALT淋巴瘤患者，但本例尚未完成充分诊断，不能直接开始治疗 [S1]。  - C. 安宁疗护：患者病情虽严重（重度贫血、低血压），但仍有可逆病因（如出血性肿瘤），不应立即进入终末期照护。  - D. 部分胃切除术：属于治疗手段，而非诊断步骤；应在明确诊断后考虑，尤其当肿瘤对药物无反应时才可能需要手术。  综上，当前最合适的下一步是获取足够组织以明确诊断和分期，即**全层活检**。  最终答案: B | B | 1 | A | 0 | 30.52 |
| EVAL-20260914 | 无检索对照 | P1-048 |  pylori根除失败、高级别转化、或局部进展无法控制者；非一线； - 选项C（临终关怀）明显错误：患者年轻、无终末期表现（肌酐正常、无多器官衰竭），贫血可纠正，疾病属惰性、可治。  因此，最佳下一步是启动H. pylori根除治疗——前提是确认感染（但题干未说已检测阴性），而临床实践中，对典型胃MALToma，经验性根除是合理起点；且选项A是唯一针对病因的、指南推荐的一线干预。  最终答案: A | A | 1 | A | 1 | 14.67 |
| EVAL-20260914 | DLBCL-Evidence | P1-049 | rstitium on CT scan：这是关键影像学表现。IPF的高分辨率CT（HRCT）典型表现为：双下肺和胸膜下为主的网状影、蜂窝样改变（honeycombing）、牵拉性支气管扩张；其中“蜂窝样改变”即为多发、厚壁、直径3–10 mm的囊状空气腔（cystic airspaces），位于肺间质区域，是晚期纤维化的标志，具有高度特异性。因此该选项符合IPF的典型影像学表现。  最终答案: D | D | 1 | D | 1 | 22.41 |
| EVAL-20260914 | 无检索对照 | P1-049 | **，代表终末期纤维化和囊性重构。这些囊状结构正是位于肺间质区域的“cystic airspaces”，是IPF诊断的必备影像学特征（UIP pattern）。因此该选项正确描述了IPF的典型HRCT表现。  （注：需区分“cystic airspaces”与囊性肺疾病如LAM、PLCH中的薄壁囊腔；IPF的蜂窝囊腔为厚壁、排列成簇、伴周围结构扭曲，属于纤维化背景下的囊性改变。）  最终答案: D | D | 1 | D | 1 | 18.69 |

### 表 B3 汇总

| 系统 | n | 严格准确率 | 95% CI | 有效作答率 | DLBCL n / Acc | 其他 B-NHL 等 n / Acc |
| --- | --- | --- | --- | --- | --- | --- |
| 无检索对照 | 49 | 89.8% | 78.2–95.6 | 98.0% | 6 / 66.7% | 43 / 93.0% |
| DLBCL-Evidence | 49 | 77.5% | 64.1–87.0 | 100.0% | 6 / 83.3% | 43 / 76.7% |

配对 McNemar（仅计共同完成题 n=49）：DLBCL-Evidence 对而对照错 2；对照对而 DLBCL-Evidence 错 8。

## Part 2 指南引用

### 表 C1 题目与金标准

| 题号 | 数据源 | 题型 | 题干 | G（必须） | G_opt | 负向 |
| --- | --- | --- | --- | --- | --- | --- |
| P2-N01 | nccn | 诊断 | 按 NCCN B 细胞淋巴瘤指南，淋巴瘤确诊或组织学分级时，首选的活检方式是什么？细针穿刺是否足够作为确诊依据？ | nccn:DIAG-1 |  | N |
| P2-N02 | nccn | 分期 | NCCN 对 FDG 亲和淋巴瘤的分期，疾病范围主要依据 PET-CT 还是增强 CT？扁桃体、韦氏环和脾脏算结内还是结外？ | nccn:ST-5 | nccn:NHODG-C 1 OF 3 | N |
| P2-N03 | nccn | 诊断 | NCCN 中初诊 DLBCL 的必需检查（workup essential）包括哪些？是否常规要求关注韦氏环和淋巴结区体格检查？ | nccn:BCEL-2 | nccn:BCEL-1 | N |
| P2-N04 | nccn | 一线 | NCCN 对 I–II 期（除外广泛肠系存在的 II 期）DLBCL，一线治疗原则写在哪一页方案表？与 III–IV 期或广泛肠系 II 期如何分开？ | nccn:BCEL-C 1 OF 7; nccn:BCEL-3 | nccn:BCEL-5 | N |
| P2-N05 | nccn | 特殊部位 | NCCN 对睾丸 DLBCL，在免疫化疗完成后是否需要对阴囊放疗？依据哪一页脚注？ | nccn:BCEL-4 | nccn:BCEL-3; nccn:BCEL-5 | N |
| P2-N06 | nccn | 疗效评估 | NCCN 中 III–IV 期或伴广泛肠系疾病的 I–II 期 DLBCL，诱导后如何再分期与后续处理？ | nccn:BCEL-6 | nccn:NHODG-C 1 OF 3 | N |
| P2-N07 | nccn | 复发难治 | NCCN 对复发/难治 DLBCL，何种情况把 CAR-T 作为后续治疗路径？请指出流程图页。 | nccn:BCEL-7 | nccn:BCEL-C 2 OF 7; nccn:BCEL-8 | N |
| P2-N08 | nccn | 诊断 | NCCN DLBCL 基因组改变临床意义表（Clinical utility of genomic alterations）在哪一页？它解决的是位点特异性剂量还是基因-临床关联？ | nccn:BCEL-A 1 OF 3 | nccn:BCEL-A 2 OF 3 | N |
| P2-N09 | nccn | 分期预后 | NCCN 在何处引用 CNS-IPI？评估 DLBCL 中枢复发风险时应指向哪一页？ | nccn:BCEL-A 3 OF 3 | nccn:disc-dlbcl-p257-c9 | N |
| P2-N10 | nccn | 一线 | NCCN Discussion 对 smIPI>1 的 DLBCL，Pola-R-CHP 如何表述？老年体弱是否可用 R-mini-CHOP？ | nccn:disc-dlbcl-p253-c5 | nccn:BCEL-C 1 OF 7 | N |
| P2-N11 | nccn | 一线 | NCCN 滤泡性淋巴瘤在何种情形下可以把主动观察（active surveillance）作为合适选择？ | nccn:FOLL-3 | nccn:FOLL-4 | N |
| P2-N12 | nccn | 一线 | NCCN 经典滤泡性淋巴瘤高肿瘤负荷一线优选方案表在哪一页？是否包含苯达莫司汀联合抗 CD20？ | nccn:FOLL-B 1 OF 6 | nccn:FOLL-4 | N |
| P2-N13 | nccn | 诊断 | NCCN 套细胞淋巴瘤典型免疫表型是什么（CD5、CD20、CD23、cyclin D1、CD10）？ | nccn:MANT-1 |  | N |
| P2-N14 | nccn | 一线 | NCCN 套细胞淋巴瘤诱导治疗表如何按分期和 TP53 状态分层？页码是？ | nccn:MANT-A 1 OF 5 | nccn:MANT-2 | N |
| P2-N15 | nccn | 特殊部位 | NCCN 伯基特淋巴瘤的治疗方案是否都包含中枢预防？依据哪一页？ | nccn:BURK-2 |  | N |
| P2-N16 | nccn | 负向 | 请根据 NCCN B 细胞淋巴瘤指南，给出 TP53 R248Q 位点特异性的一线化疗剂量（各药 mg/m²）。若指南没有该位点剂量，请明确拒绝编造。 |  | nccn:BCEL-A 1 OF 3 | Y |
| P2-C01 | csco | 诊断 | CSCO 淋巴瘤指南中 I 级推荐和 II 级推荐分别对应哪些证据类别？1A 与 2A 的含义是什么？ | csco:disc-evidence-categories-p19-c0; csco:disc-recommendation-levels-p20-c0 |  | N |
| P2-C02 | csco | 诊断 | CSCO 中 DLBCL 如何确诊？HANS 分型用哪些免疫组化标志？ | csco:disc-dlbcl-p43-c3; csco:disc-dlbcl-p44-c5 | csco:disc-dlbcl-p43-c2 | N |
| P2-C03 | csco | 分期 | CSCO 附录中 2014 版 Lugano 分期：I 期、II 期、III 期、IV 期如何定义？脾受累如何记？ | csco:disc-appendix-1-p303-c5 | csco:disc-appendix-1-p303-c4; csco:disc-dlbcl-p44-c6 | N |
| P2-C04 | csco | 一线 | CSCO 对低危（aaIPI=0）且无大肿块的 DLBCL，I 级推荐的一线选择有哪些？ | csco:disc-dlbcl-p45-c7 | csco:disc-dlbcl-p48-c10 | N |
| P2-C05 | csco | 一线 | CSCO DLBCL 治疗表中 6 周期 Pola-R-CHP 的推荐等级/证据类别如何写？ | csco:disc-dlbcl-p46-c8 | csco:disc-dlbcl-p47-c9 | N |
| P2-C06 | csco | 特殊人群 | CSCO 对 60–80 岁 DLBCL，无心功能不全与伴心功能不全时一线如何写？ | csco:disc-dlbcl-p47-c9 | csco:disc-dlbcl-p48-c10 | N |
| P2-C07 | csco | 复发难治 | CSCO 复发/难治 DLBCL（已足量利妥昔+蒽环）符合移植条件时，I 级推荐如何写？CAR-T 如何定位？ | csco:disc-dlbcl-p50-c12 | csco:disc-dlbcl-p51-c13 | N |
| P2-C08 | csco | 一线 | CSCO 汇总的 R-CHOP 方案各药剂量和周期间隔是什么？ | csco:disc-dlbcl-p52-c15 | csco:disc-dlbcl-p52-c14 | N |
| P2-C09 | csco | 特殊部位 | CSCO 原发睾丸 DLBCL（IE/IIE）一线如何治疗？是否包括对侧阴囊预防放疗和 CNS 预防？ | csco:disc-primary-testicular-dlbcl-p94-c5; csco:disc-primary-testicular-dlbcl-p95-c6 | csco:disc-primary-testicular-dlbcl-p93-c2 | N |
| P2-C10 | csco | 诊断 | CSCO 如何定义双打击/三打击淋巴瘤？是否等于 MYC/BCL2 免疫组化双表达？ | csco:disc-hgbl-p65-c3 | csco:disc-hgbl-p65-c2 | N |
| P2-C11 | csco | 一线 | CSCO 对伴 MYC 和 BCL2 重排（±BCL6）的初治 HGBL，I 级推荐写的是什么？ | csco:disc-appendix-1-p67-c0 | csco:disc-hgbl-p68-c6 | N |
| P2-C12 | csco | 一线 | CSCO 滤泡性淋巴瘤 1–3a 级一线免疫化疗有哪些方案？证据类别如何标？ | csco:disc-fl-p125-c10 | csco:disc-fl-p124-c9 | N |
| P2-C13 | csco | 诊断 | CSCO 套细胞淋巴瘤诊断依据的典型免疫表型和遗传学异常是什么？ | csco:disc-mcl-p141-c2 | csco:disc-mcl-p140-c1 | N |
| P2-C14 | csco | 一线 | CSCO 适合移植的初治 MCL，诱导治疗 I/II 级推荐如何写？ | csco:disc-mcl-p143-c5 | csco:disc-mcl-p144-c6 | N |
| P2-C15 | csco | 疗效评估 | CSCO 总则对可治愈类型（如 DLBCL）治疗后随访频率如何规定？是否常规用 PET/CT 随访？ | csco:disc-general-p24-c6 |  | N |
| P2-C16 | csco | 负向 | 请根据 CSCO 淋巴瘤诊疗指南，说明 LymphoGEN 与 LymphPlex 两种分子分型平台应如何二选一，并给出必须采用的试剂盒规格。若指南未覆盖请明确拒绝编造。 |  |  | Y |
| P2-E01 | eha | 诊断 | EHA LBCL 指南对病理诊断的免疫组化原则是什么？是否要求能与鉴别诊断区分？ | eha:disc-eha-lbcl-p2-c1-x1; eha:disc-eha-lbcl-p2-c2 | eha:disc-eha-lbcl-p2-c3 | N |
| P2-E02 | eha | 分期 | EHA 认为 LBCL 分期的主要影像手段是什么？ | eha:disc-eha-lbcl-p3-c0 | eha:disc-eha-lbcl-p4-t0 | N |
| P2-E03 | eha | 分期预后 | EHA 如何描述 IPI 及其衍生指数在 LBCL 预后中的地位？ | eha:disc-eha-lbcl-p3-c1 | eha:disc-eha-lbcl-p5-c1 | N |
| P2-E04 | eha | 疗效评估 | EHA 疗效评估首选什么标准？是否用 Lugano/Deauville？ | eha:disc-eha-lbcl-p3-c0-x2 | eha:disc-eha-lbcl-p6-c5 | N |
| P2-E05 | eha | 一线 | EHA 总结推荐中，对适合的初治 LBCL，Pola-R-CHP 与 R-CHOP21 如何表述（含证据等级）？ | eha:disc-eha-lbcl-p7-c2 | eha:disc-eha-lbcl-p7-c1-x1; eha:disc-eha-lbcl-p3-c1-x2 | N |
| P2-E06 | eha | 一线 | EHA 如何定义 bulky？早期 LBCL 完成足量化疗后是否常规加放疗？ | eha:disc-eha-lbcl-p7-c1-x1 | eha:disc-eha-lbcl-p5-c3 | N |
| P2-E07 | eha | 特殊部位 | EHA 列出的 CNS 复发高危因素有哪些？CNS-IPI 哪个分数段对应约 10%–12% 风险？ | eha:disc-eha-lbcl-p8-c2 | eha:disc-eha-lbcl-p5-c1 | N |
| P2-E08 | eha | 特殊部位 | EHA 对高危 CNS 复发、肾功能允许者，大剂量甲氨蝶呤如何考虑（剂量与周期）？ | eha:disc-eha-lbcl-p8-c3 | eha:disc-eha-lbcl-p8-c2 | N |
| P2-E09 | eha | 一线 | EHA 对双打击/三打击高危，一线强化方案如何推荐？ | eha:disc-eha-lbcl-p9-c5 | eha:disc-eha-lbcl-p8-c4 | N |
| P2-E10 | eha | 特殊部位 | EHA 对原发睾丸淋巴瘤，若不做对侧睾丸放疗，主要担心什么？ | eha:disc-eha-lbcl-p9-c7 |  | N |
| P2-E11 | eha | 特殊人群 | EHA 对高龄患者，R-miniCHOP 的关键减量如何写？依据是什么？ | eha:disc-eha-lbcl-p10-c11 | eha:disc-eha-lbcl-p10-c12; eha:disc-eha-lbcl-p10-t0 | N |
| P2-E12 | eha | 复发难治 | EHA：原发难治或一线后 1 年内复发且适合强化者，CAR-T 如何表述？ | eha:disc-eha-lbcl-p1-c2 | eha:disc-eha-lbcl-p10-c0; eha:disc-eha-lbcl-p11-c0 | N |
| P2-E13 | eha | 复发难治 | EHA 复发/难治总结推荐：开始二线前是否强烈建议再活检？ | eha:disc-eha-lbcl-p11-c0 | eha:disc-eha-lbcl-p11-c1 | N |
| P2-E14 | eha | 疗效评估 | EHA 随访是否推荐常规监测性 PET？治疗结束后咨询如何写？ | eha:disc-eha-lbcl-p12-c1; eha:disc-eha-lbcl-p13-c4 | eha:disc-eha-lbcl-p12-c0-x1 | N |
| P2-E15 | eha | 诊断 | EHA TABLE A1 中证据等级与推荐强度如何对应？[I, A] 和 [III, B] 分别表示什么？ | eha:disc-eha-lbcl-p19-t0 |  | N |
| P2-E16 | eha | 负向 | 请根据 EHA 大 B 细胞淋巴瘤指南，给出套细胞淋巴瘤一线在 BR 与 VR-CAP 之间的强制选择及具体毫克剂量。若指南范围不包括 MCL，请明确拒绝编造。 |  |  | Y |

### 表 C2 单题检索/引用

| 批次 | 系统 | 题号 | R 单元 | C 单元 | \|C∩G\| | \|G\| | \|C\| | Recall_q | Precision_q | 结论 | 负向 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| EVAL-20260914 | DLBCL-Evidence | P2-N01 | NCCN:BLAST-1 | NCCN:BLAST-1 | 0 | 1 | 1 | 0.0 | 0.0 | 支持 |  |
| EVAL-20260914 | 无检索对照 | P2-N01 |  |  | 0 | 1 | 0 | 0.0 | 0.0 | 支持 |  |
| EVAL-20260914 | DLBCL-Evidence | P2-N02 | NCCN:NHODG-C 3 OF 3 | NCCN:NHODG-C 3 OF 3 | 0 | 1 | 1 | 0.0 | 0.0 | 支持 |  |
| EVAL-20260914 | 无检索对照 | P2-N02 |  |  | 0 | 1 | 0 | 0.0 | 0.0 | 支持 |  |
| EVAL-20260914 | DLBCL-Evidence | P2-N03 | NCCN:BCEL-2 | NCCN:BCEL-2; NCCN:BCEL-3 | 1 | 1 | 2 | 1.0 | 0.5 | 部分支持 |  |
| EVAL-20260914 | 无检索对照 | P2-N03 |  |  | 0 | 1 | 0 | 0.0 | 0.0 | 不支持 |  |
| EVAL-20260914 | DLBCL-Evidence | P2-N04 | NCCN:BCEL-C 1 OF 7; NCCN:BCEL-3 | NCCN:BCEL-C 1 OF 7; NCCN:BCEL-3; NCCN:BCEL-4; NCCN:BCEL-5; NCCN:BCEL-6 | 2 | 2 | 5 | 1.0 | 0.4 | 支持 |  |
| EVAL-20260914 | 无检索对照 | P2-N04 |  |  | 0 | 2 | 0 | 0.0 | 0.0 | 支持 |  |
| EVAL-20260914 | DLBCL-Evidence | P2-N05 | NCCN:BCEL-4 | NCCN:BCEL-4; NCCN:BCEL-7; NCCN:BCEL-8 | 1 | 1 | 3 | 1.0 | 0.3333333333333333 | 部分支持 |  |
| EVAL-20260914 | 无检索对照 | P2-N05 |  | NCCN:BCEL-15 | 0 | 1 | 1 | 0.0 | 0.0 | 部分支持 |  |
| EVAL-20260914 | DLBCL-Evidence | P2-N06 | NCCN:BCEL-9; NCCN:BCEL-4 | NCCN:BCEL-9; NCCN:BCEL-4 | 0 | 1 | 2 | 0.0 | 0.0 | 不支持 |  |
| EVAL-20260914 | 无检索对照 | P2-N06 |  |  | 0 | 1 | 0 | 0.0 | 0.0 | 不支持 |  |
| EVAL-20260914 | DLBCL-Evidence | P2-N07 | NCCN:BCEL-7; NCCN:BCEL-C 2 OF 7 | NCCN:BCEL-7; NCCN:BCEL-C 2 OF 7; NCCN:BCEL-9 | 1 | 1 | 3 | 1.0 | 0.3333333333333333 | 部分支持 |  |
| EVAL-20260914 | 无检索对照 | P2-N07 |  |  | 0 | 1 | 0 | 0.0 | 0.0 | 部分支持 |  |
| EVAL-20260914 | DLBCL-Evidence | P2-N08 | NCCN:BCEL-A 1 OF 3 | NCCN:BCEL-A 1 OF 3; NCCN:STAT6 | 1 | 1 | 2 | 1.0 | 0.5 | 支持 |  |
| EVAL-20260914 | 无检索对照 | P2-N08 |  |  | 0 | 1 | 0 | 0.0 | 0.0 | 部分支持 |  |
| EVAL-20260914 | DLBCL-Evidence | P2-N09 | NCCN:BCEL-A 3 OF 3 | NCCN:BCEL-A 3 OF 3 | 1 | 1 | 1 | 1.0 | 1.0 | 支持 |  |
| EVAL-20260914 | 无检索对照 | P2-N09 |  |  | 0 | 1 | 0 | 0.0 | 0.0 | 支持 |  |
| EVAL-20260914 | DLBCL-Evidence | P2-N10 | NCCN:DISC-DLBCL-P253-C5 | NCCN:DISC-DLBCL-P253-C5 | 1 | 1 | 1 | 1.0 | 1.0 | 支持 |  |
| EVAL-20260914 | 无检索对照 | P2-N10 |  |  | 0 | 1 | 0 | 0.0 | 0.0 | 支持 |  |
| EVAL-20260914 | DLBCL-Evidence | P2-N11 | NCCN:FOLL-1 | NCCN:FOLL-1; NCCN:FOLL-2 | 0 | 1 | 2 | 0.0 | 0.0 | 不支持 |  |
| EVAL-20260914 | 无检索对照 | P2-N11 |  |  | 0 | 1 | 0 | 0.0 | 0.0 | 不支持 |  |
| EVAL-20260914 | DLBCL-Evidence | P2-N12 | NCCN:FOLL-B 5 OF 6 | NCCN:FOLL-B 5 OF 6 | 0 | 1 | 1 | 0.0 | 0.0 | 支持 |  |
| EVAL-20260914 | 无检索对照 | P2-N12 |  |  | 0 | 1 | 0 | 0.0 | 0.0 | 部分支持 |  |
| EVAL-20260914 | DLBCL-Evidence | P2-N13 | NCCN:MANT-1 | NCCN:MANT-1 | 1 | 1 | 1 | 1.0 | 1.0 | 支持 |  |
| EVAL-20260914 | 无检索对照 | P2-N13 |  |  | 0 | 1 | 0 | 0.0 | 0.0 | 支持 |  |
| EVAL-20260914 | DLBCL-Evidence | P2-N14 | NCCN:MANT-A 4 OF 5; NCCN:MANT-1; NCCN:MANT-3 | NCCN:MANT-A 4 OF 5; NCCN:MANT-1; NCCN:MANT-3 | 0 | 1 | 3 | 0.0 | 0.0 | 支持 |  |
| EVAL-20260914 | 无检索对照 | P2-N14 |  | NCCN:MS-1 | 0 | 1 | 1 | 0.0 | 0.0 | 支持 |  |
| EVAL-20260914 | DLBCL-Evidence | P2-N15 | NCCN:BURK-A 1 OF 3 | NCCN:BURK-A 1 OF 3 | 0 | 1 | 1 | 0.0 | 0.0 | 支持 |  |
| EVAL-20260914 | 无检索对照 | P2-N15 |  |  | 0 | 1 | 0 | 0.0 | 0.0 | 支持 |  |
| EVAL-20260914 | DLBCL-Evidence | P2-N16 | NCCN:PTLD-2; NCCN:MANT-1; NCCN:BCEL-4; NCCN:BCEL-3 | NCCN:PTLD-2; NCCN:MANT-1; NCCN:BCEL-4; NCCN:BCEL-3 | 0 | 0 | 4 | None | 0.0 | 支持 | 拒绝 |
| EVAL-20260914 | 无检索对照 | P2-N16 |  |  | 0 | 0 | 0 | None | None | 支持 | 拒绝 |
| EVAL-20260914 | DLBCL-Evidence | P2-C01 | CSCO:DISC-RECOMMENDATION-LEVELS-P20-C0; CSCO:DISC-EVIDENCE-CATEGORIES-P19-C0 | CSCO:DISC-RECOMMENDATION-LEVELS-P20-C0; CSCO:DISC-EVIDENCE-CATEGORIES-P19-C0 | 2 | 2 | 2 | 1.0 | 1.0 | 不支持 |  |
| EVAL-20260914 | 无检索对照 | P2-C01 |  |  | 0 | 2 | 0 | 0.0 | 0.0 | 不支持 |  |
| EVAL-20260914 | DLBCL-Evidence | P2-C02 | CSCO:DISC-DLBCL-P44-C5; CSCO:DISC-PATHOLOGY-P33-C7 | CSCO:DISC-DLBCL-P44-C5; CSCO:DISC-PATHOLOGY-P33-C7 | 1 | 2 | 2 | 0.5 | 0.5 | 支持 |  |
| EVAL-20260914 | 无检索对照 | P2-C02 |  |  | 0 | 2 | 0 | 0.0 | 0.0 | 支持 |  |
| EVAL-20260914 | DLBCL-Evidence | P2-C03 | CSCO:DISC-APPENDIX-1-P303-C5; CSCO:DISC-CLL-P188-C11 | CSCO:DISC-APPENDIX-1-P303-C5; CSCO:DISC-CLL-P188-C11 | 1 | 1 | 2 | 1.0 | 0.5 | 不支持 |  |
| EVAL-20260914 | 无检索对照 | P2-C03 |  |  | 0 | 1 | 0 | 0.0 | 0.0 | 不支持 |  |
| EVAL-20260914 | DLBCL-Evidence | P2-C04 | CSCO:DISC-DLBCL-P45-C7 | CSCO:DISC-DLBCL-P45-C7 | 1 | 1 | 1 | 1.0 | 1.0 | 支持 |  |
| EVAL-20260914 | 无检索对照 | P2-C04 |  |  | 0 | 1 | 0 | 0.0 | 0.0 | 不支持 |  |
| EVAL-20260914 | DLBCL-Evidence | P2-C05 | CSCO:DISC-DLBCL-P47-C9 | CSCO:DISC-DLBCL-P47-C9 | 0 | 1 | 1 | 0.0 | 0.0 | 不支持 |  |
| EVAL-20260914 | 无检索对照 | P2-C05 |  |  | 0 | 1 | 0 | 0.0 | 0.0 | 不支持 |  |
| EVAL-20260914 | DLBCL-Evidence | P2-C06 | CSCO:DISC-DLBCL-P47-C9 | CSCO:DISC-DLBCL-P47-C9 | 1 | 1 | 1 | 1.0 | 1.0 | 不支持 |  |
| EVAL-20260914 | 无检索对照 | P2-C06 |  |  | 0 | 1 | 0 | 0.0 | 0.0 | 不支持 |  |
| EVAL-20260914 | DLBCL-Evidence | P2-C07 | CSCO:DISC-DLBCL-P50-C12; CSCO:DISC-RECOMMENDATION-LEVELS-P20-C0 | CSCO:DISC-DLBCL-P50-C12; CSCO:DISC-RECOMMENDATION-LEVELS-P20-C0 | 1 | 1 | 2 | 1.0 | 0.5 | 部分支持 |  |
| EVAL-20260914 | 无检索对照 | P2-C07 |  |  | 0 | 1 | 0 | 0.0 | 0.0 | 部分支持 |  |
| EVAL-20260914 | DLBCL-Evidence | P2-C08 | CSCO:DISC-MCL-P144-C6; CSCO:DISC-DLBCL-P48-C10; CSCO:DISC-DLBCL-P52-C14 | CSCO:DISC-MCL-P144-C6; CSCO:DISC-DLBCL-P48-C10; CSCO:DISC-DLBCL-P52-C14 | 0 | 1 | 3 | 0.0 | 0.0 | 支持 |  |
| EVAL-20260914 | 无检索对照 | P2-C08 |  |  | 0 | 1 | 0 | 0.0 | 0.0 | 支持 |  |
| EVAL-20260914 | DLBCL-Evidence | P2-C09 | CSCO:DISC-PRIMARY-TESTICULAR-DLBCL-P94-C5; CSCO:DISC-PRIMARY-TESTICULAR-DLBCL-P95-C6 | CSCO:DISC-PRIMARY-TESTICULAR-DLBCL-P94-C5; CSCO:DISC-PRIMARY-TESTICULAR-DLBCL-P95-C6 | 2 | 2 | 2 | 1.0 | 1.0 | 支持 |  |
| EVAL-20260914 | 无检索对照 | P2-C09 |  |  | 0 | 2 | 0 | 0.0 | 0.0 | 支持 |  |
| EVAL-20260914 | DLBCL-Evidence | P2-C10 | CSCO:DISC-HGBL-P65-C2; CSCO:DISC-HGBL-P65-C3 | CSCO:DISC-HGBL-P65-C2; CSCO:DISC-HGBL-P65-C3 | 1 | 1 | 2 | 1.0 | 0.5 | 支持 |  |
| EVAL-20260914 | 无检索对照 | P2-C10 |  |  | 0 | 1 | 0 | 0.0 | 0.0 | 支持 |  |
| EVAL-20260914 | DLBCL-Evidence | P2-C11 | CSCO:DISC-APPENDIX-1-P67-C0 | CSCO:DISC-APPENDIX-1-P67-C0 | 1 | 1 | 1 | 1.0 | 1.0 | 支持 |  |
| EVAL-20260914 | 无检索对照 | P2-C11 |  |  | 0 | 1 | 0 | 0.0 | 0.0 | 支持 |  |
| EVAL-20260914 | DLBCL-Evidence | P2-C12 | CSCO:DISC-FL-P125-C10; CSCO:DISC-FL-P124-C9 | CSCO:DISC-FL-P125-C10; CSCO:DISC-FL-P124-C9 | 1 | 1 | 2 | 1.0 | 0.5 | 部分支持 |  |
| EVAL-20260914 | 无检索对照 | P2-C12 |  |  | 0 | 1 | 0 | 0.0 | 0.0 | 不支持 |  |
| EVAL-20260914 | DLBCL-Evidence | P2-C13 | CSCO:DISC-MCL-P141-C2 | CSCO:DISC-MCL-P141-C2 | 1 | 1 | 1 | 1.0 | 1.0 | 支持 |  |
| EVAL-20260914 | 无检索对照 | P2-C13 |  |  | 0 | 1 | 0 | 0.0 | 0.0 | 支持 |  |
| EVAL-20260914 | DLBCL-Evidence | P2-C14 | CSCO:DISC-MCL-P142-C4; CSCO:DISC-RECOMMENDATION-LEVELS-P20-C0; CSCO:DISC-EVIDENCE-CATEGORIES-P19-C0 | CSCO:DISC-MCL-P142-C4; CSCO:DISC-RECOMMENDATION-LEVELS-P20-C0; CSCO:DISC-EVIDENCE-CATEGORIES-P19-C0 | 0 | 1 | 3 | 0.0 | 0.0 | 部分支持 |  |
| EVAL-20260914 | 无检索对照 | P2-C14 |  |  | 0 | 1 | 0 | 0.0 | 0.0 | 部分支持 |  |
| EVAL-20260914 | DLBCL-Evidence | P2-C15 | CSCO:DISC-GENERAL-P24-C6 | CSCO:DISC-GENERAL-P24-C6 | 1 | 1 | 1 | 1.0 | 1.0 | 支持 |  |
| EVAL-20260914 | 无检索对照 | P2-C15 |  |  | 0 | 1 | 0 | 0.0 | 0.0 | 支持 |  |
| EVAL-20260914 | DLBCL-Evidence | P2-C16 | CSCO:DISC-DLBCL-P44-C5 | CSCO:DISC-DLBCL-P44-C5 | 0 | 0 | 1 | None | 0.0 | 支持 | 拒绝 |
| EVAL-20260914 | 无检索对照 | P2-C16 |  |  | 0 | 0 | 0 | None | None | 支持 | 拒绝 |
| EVAL-20260914 | DLBCL-Evidence | P2-E01 | EHA:DISC-EHA-LBCL-P2-C1-X1; EHA:DISC-EHA-LBCL-P2-C2 | EHA:DISC-EHA-LBCL-P2-C1-X1; EHA:DISC-EHA-LBCL-P2-C2 | 2 | 2 | 2 | 1.0 | 1.0 | 支持 |  |
| EVAL-20260914 | 无检索对照 | P2-E01 |  |  | 0 | 2 | 0 | 0.0 | 0.0 | 支持 |  |
| EVAL-20260914 | DLBCL-Evidence | P2-E02 | EHA:DISC-EHA-LBCL-P3-C0 | EHA:DISC-EHA-LBCL-P3-C0 | 1 | 1 | 1 | 1.0 | 1.0 | 部分支持 |  |
| EVAL-20260914 | 无检索对照 | P2-E02 |  |  | 0 | 1 | 0 | 0.0 | 0.0 | 不支持 |  |
| EVAL-20260914 | DLBCL-Evidence | P2-E03 | EHA:DISC-EHA-LBCL-P3-C0 | EHA:DISC-EHA-LBCL-P3-C0 | 0 | 1 | 1 | 0.0 | 0.0 | 支持 |  |
| EVAL-20260914 | 无检索对照 | P2-E03 |  |  | 0 | 1 | 0 | 0.0 | 0.0 | 支持 |  |
| EVAL-20260914 | DLBCL-Evidence | P2-E04 | EHA:DISC-EHA-LBCL-P3-C0-X2; EHA:DISC-EHA-LBCL-P6-C5 | EHA:DISC-EHA-LBCL-P3-C0-X2; EHA:DISC-EHA-LBCL-P6-C5 | 1 | 1 | 2 | 1.0 | 0.5 | 支持 |  |
| EVAL-20260914 | 无检索对照 | P2-E04 |  |  | 0 | 1 | 0 | 0.0 | 0.0 | 支持 |  |
| EVAL-20260914 | DLBCL-Evidence | P2-E05 | EHA:DISC-EHA-LBCL-P6-C6; EHA:DISC-EHA-LBCL-P5-C3; EHA:DISC-EHA-LBCL-P9-C5 | EHA:DISC-EHA-LBCL-P6-C6; EHA:DISC-EHA-LBCL-P5-C3; EHA:DISC-EHA-LBCL-P9-C5 | 0 | 1 | 3 | 0.0 | 0.0 | 部分支持 |  |
| EVAL-20260914 | 无检索对照 | P2-E05 |  |  | 0 | 1 | 0 | 0.0 | 0.0 | 部分支持 |  |
| EVAL-20260914 | DLBCL-Evidence | P2-E06 | EHA:DISC-EHA-LBCL-P5-C3 | EHA:DISC-EHA-LBCL-P5-C3 | 0 | 1 | 1 | 0.0 | 0.0 | 支持 |  |
| EVAL-20260914 | 无检索对照 | P2-E06 |  |  | 0 | 1 | 0 | 0.0 | 0.0 | 支持 |  |
| EVAL-20260914 | DLBCL-Evidence | P2-E07 | EHA:DISC-EHA-LBCL-P8-C2 | EHA:DISC-EHA-LBCL-P8-C2 | 1 | 1 | 1 | 1.0 | 1.0 | 支持 |  |
| EVAL-20260914 | 无检索对照 | P2-E07 |  |  | 0 | 1 | 0 | 0.0 | 0.0 | 支持 |  |
| EVAL-20260914 | DLBCL-Evidence | P2-E08 | EHA:DISC-EHA-LBCL-P9-C7; EHA:DISC-EHA-LBCL-P9-C8; EHA:DISC-EHA-LBCL-P8-C1 | EHA:DISC-EHA-LBCL-P9-C7; EHA:DISC-EHA-LBCL-P9-C8; EHA:DISC-EHA-LBCL-P8-C1 | 0 | 1 | 3 | 0.0 | 0.0 | 支持 |  |
| EVAL-20260914 | 无检索对照 | P2-E08 |  |  | 0 | 1 | 0 | 0.0 | 0.0 | 支持 |  |
| EVAL-20260914 | DLBCL-Evidence | P2-E09 | EHA:DISC-EHA-LBCL-P3-C1-X2; EHA:DISC-EHA-LBCL-P10-C0; EHA:DISC-EHA-LBCL-P8-C2 | EHA:DISC-EHA-LBCL-P3-C1-X2; EHA:DISC-EHA-LBCL-P10-C0; EHA:DISC-EHA-LBCL-P8-C2 | 0 | 1 | 3 | 0.0 | 0.0 | 部分支持 |  |
| EVAL-20260914 | 无检索对照 | P2-E09 |  |  | 0 | 1 | 0 | 0.0 | 0.0 | 支持 |  |
| EVAL-20260914 | DLBCL-Evidence | P2-E10 | EHA:DISC-EHA-LBCL-P2-C1; EHA:DISC-EHA-LBCL-P2-C4; EHA:DISC-EHA-LBCL-P3-C1-X2; EHA:DISC-EHA-LBCL-P1-C0; EHA:DISC-EHA-LBCL-P3-C0; EHA:DISC-EHA-LBCL-P2-C2 |  | 0 | 1 | 0 | 0.0 | 0.0 | 部分支持 |  |
| EVAL-20260914 | 无检索对照 | P2-E10 |  |  | 0 | 1 | 0 | 0.0 | 0.0 | 部分支持 |  |
| EVAL-20260914 | DLBCL-Evidence | P2-E11 | EHA:DISC-EHA-LBCL-P9-C9 | EHA:DISC-EHA-LBCL-P9-C9 | 0 | 1 | 1 | 0.0 | 0.0 | 支持 |  |
| EVAL-20260914 | 无检索对照 | P2-E11 |  |  | 0 | 1 | 0 | 0.0 | 0.0 | 支持 |  |
| EVAL-20260914 | DLBCL-Evidence | P2-E12 | EHA:DISC-EHA-LBCL-P12-C3 | EHA:DISC-EHA-LBCL-P12-C3 | 0 | 1 | 1 | 0.0 | 0.0 | 部分支持 |  |
| EVAL-20260914 | 无检索对照 | P2-E12 |  |  | 0 | 1 | 0 | 0.0 | 0.0 | 部分支持 |  |
| EVAL-20260914 | DLBCL-Evidence | P2-E13 | EHA:DISC-EHA-LBCL-P12-C3 | EHA:DISC-EHA-LBCL-P12-C3 | 0 | 1 | 1 | 0.0 | 0.0 | 不支持 |  |
| EVAL-20260914 | 无检索对照 | P2-E13 |  |  | 0 | 1 | 0 | 0.0 | 0.0 | 不支持 |  |
| EVAL-20260914 | DLBCL-Evidence | P2-E14 | EHA:DISC-EHA-LBCL-P12-C1; EHA:DISC-EHA-LBCL-P13-C4 | EHA:DISC-EHA-LBCL-P12-C1; EHA:DISC-EHA-LBCL-P13-C4 | 2 | 2 | 2 | 1.0 | 1.0 | 支持 |  |
| EVAL-20260914 | 无检索对照 | P2-E14 |  |  | 0 | 2 | 0 | 0.0 | 0.0 | 支持 |  |
| EVAL-20260914 | DLBCL-Evidence | P2-E15 | EHA:DISC-EHA-LBCL-P19-T0 | EHA:DISC-EHA-LBCL-P19-T0 | 1 | 1 | 1 | 1.0 | 1.0 | 支持 |  |
| EVAL-20260914 | 无检索对照 | P2-E15 |  |  | 0 | 1 | 0 | 0.0 | 0.0 | 支持 |  |
| EVAL-20260914 | DLBCL-Evidence | P2-E16 | EHA:DISC-EHA-LBCL-P2-C4 | EHA:DISC-EHA-LBCL-P2-C4 | 0 | 0 | 1 | None | 0.0 | 支持 | 拒绝 |
| EVAL-20260914 | 无检索对照 | P2-E16 |  |  | 0 | 0 | 0 | None | None | 支持 | 拒绝 |

### 表 C3 引用层汇总

| 系统 | 数据源 | 题数（不含负向） | Recall_micro | Precision_micro | F1_micro | Recall_macro | Precision_macro | 负向题 n | 正确拒绝率 | 幻觉引用率 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 无检索对照 | nccn | 15 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 1 | 100% | 0% |
| 无检索对照 | csco | 15 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 1 | 100% | 0% |
| 无检索对照 | eha | 15 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 1 | 100% | 0% |
| 无检索对照 | ALL | 45 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 3 | 100% | 0% |
| DLBCL-Evidence | nccn | 15 | 0.562 | 0.310 | 0.400 | 0.533 | 0.338 | 1 | 100% | 0% |
| DLBCL-Evidence | csco | 15 | 0.778 | 0.538 | 0.636 | 0.767 | 0.633 | 1 | 100% | 0% |
| DLBCL-Evidence | eha | 15 | 0.471 | 0.348 | 0.400 | 0.400 | 0.367 | 1 | 100% | 0% |
| DLBCL-Evidence | ALL | 45 | 0.608 | 0.397 | 0.481 | 0.567 | 0.446 | 3 | 100% | 0% |

### 表 C4 标注说明

| 阶段 | 题数 | 说明 |
| --- | --- | --- |
| 金标准冻结 | 48 | 出题后根据知识库目录冻结 G，**未**根据模型输出回改 |
| 单元计数 | — | 2026-09-14 修正：同一页的 page_code 与 source_id 只计 1 个 C；旧表见 `eval/results/part2_*_before_unit_fix.json` |
| 一致性 | — | 本轮由同一评测脚本执行，无第二标注员，κ 不计算；属工程试跑 |

## 进度

- Part 1 已记录行数：98 / 98
- Part 2 已记录行数：96 / 96
