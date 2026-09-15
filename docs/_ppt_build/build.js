const pptxgen = require("pptxgenjs");
const path = require("path");

const pres = new pptxgen();
pres.defineLayout({ name: "WIDE", width: 13.3, height: 7.5 });
pres.layout = "WIDE";
pres.author = "DLBCL-Evidence";
pres.title = "DLBCL-Evidence DLBCL 问答系统评估方案";
pres.subject = "导师汇报：可发表评估体系与三方案定档";

const INK = "1A1A1A";
const MUTED = "4B5563";
const FAINT = "6B7280";
const RED = "C00000";
const RED_SOFT = "FEE2E2";
const AMBER = "9A3412";
const AMBER_SOFT = "FEF3C7";
const BLUE = "1D4ED8";
const BLUE_SOFT = "EFF6FF";
const GREEN = "166534";
const GREEN_SOFT = "DCFCE7";
const SLATE = "F8FAFC";
const WHITE = "FFFFFF";
const FACE = "Calibri";

function addBg(slide) {
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0,
    y: 0,
    w: 13.3,
    h: 7.5,
    fill: { color: WHITE },
    line: { color: WHITE },
  });
}

function addTitle(slide, text, width) {
  slide.addText(text, {
    x: 0.45,
    y: 0.2,
    w: width || 12.4,
    h: 0.46,
    fontFace: FACE,
    fontSize: 24,
    bold: true,
    color: INK,
    margin: 0,
    valign: "middle",
  });
}

function addLead(slide, text) {
  slide.addText(text, {
    x: 0.45,
    y: 0.68,
    w: 12.4,
    h: 0.52,
    fontFace: FACE,
    fontSize: 14,
    color: MUTED,
    margin: 0,
    valign: "top",
  });
}

function addFooter(slide, text, page) {
  slide.addText(text, {
    x: 0.45,
    y: 7.05,
    w: 11.3,
    h: 0.28,
    fontFace: FACE,
    fontSize: 12,
    color: INK,
    margin: 0,
    valign: "middle",
  });
  slide.addText(String(page), {
    x: 12.15,
    y: 7.05,
    w: 0.7,
    h: 0.28,
    fontFace: FACE,
    fontSize: 11,
    color: FAINT,
    align: "right",
    margin: 0,
    valign: "middle",
  });
}

function addCard(slide, o) {
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: o.x,
    y: o.y,
    w: o.w,
    h: o.h,
    fill: { color: o.fill || SLATE },
    rectRadius: 0.08,
  });
}

function addBadge(slide, x, y, label, fill, color) {
  slide.addShape(pres.shapes.OVAL, {
    x,
    y,
    w: 0.34,
    h: 0.34,
    fill: { color: fill },
  });
  slide.addText(label, {
    x,
    y,
    w: 0.34,
    h: 0.34,
    fontFace: FACE,
    fontSize: 10,
    bold: true,
    color: color,
    align: "center",
    valign: "middle",
    margin: 0,
  });
}

function addNotes(slide, text) {
  slide.addNotes(text);
}

// ---------------------------------------------------------------------------
// 1 总览
// ---------------------------------------------------------------------------
{
  const s = pres.addSlide();
  addBg(s);
  addTitle(s, "DLBCL-Evidence DLBCL 问答系统评估方案", 8.7);
  s.addText("导师汇报  ·  2026年9月", {
    x: 9.3,
    y: 0.24,
    w: 3.55,
    h: 0.38,
    fontFace: FACE,
    fontSize: 12,
    color: FAINT,
    align: "right",
    margin: 0,
    valign: "middle",
  });
  addLead(
    s,
    "以病历自带金标准与指南反向出题支撑自动化打分；医生时间仅投在分歧裁决与盲评。三种方案供导师定档。"
  );

  const cards = [
    {
      n: "01",
      t: "三层评估",
      b: "按人力可替代性分层。自动客观承担题量；LLM 裁判须先校准；医生只做裁决，不生产金标准。",
    },
    {
      n: "02",
      t: "自建 DLBCL-Bench",
      b: "指南反向出题约 200 道、病历题 400–600 道、安全对抗 60–80 道。金标准尽量「免费」获得。",
    },
    {
      n: "03",
      t: "分模块归因",
      b: "不按四个界面分表，而按 M1–M7 能力分表。图谱、分子、文献必须靠 ablation 证明存在价值。",
    },
    {
      n: "04",
      t: "三方案供定档",
      b: "自动化优先、病历主线、组合式。推荐组合式：先跑出自动数字，再用数字换医生时间。",
    },
  ];
  cards.forEach((c, i) => {
    const col = i % 2;
    const row = Math.floor(i / 2);
    const x = 0.45 + col * 6.28;
    const y = 1.32 + row * 2.12;
    addCard(s, { x, y, w: 6.12, h: 1.98, fill: i === 3 ? RED_SOFT : SLATE });
    addBadge(s, x + 0.16, y + 0.16, c.n, RED, WHITE);
    s.addText(c.t, {
      x: x + 0.6,
      y: y + 0.16,
      w: 5.3,
      h: 0.34,
      fontFace: FACE,
      fontSize: 16,
      bold: true,
      color: INK,
      margin: 0,
      valign: "middle",
    });
    s.addText(c.b, {
      x: x + 0.16,
      y: y + 0.62,
      w: 5.8,
      h: 1.14,
      fontFace: FACE,
      fontSize: 13,
      color: MUTED,
      margin: 0,
    });
  });

  const stats = [
    ["200", "指南反向题"],
    ["300", "分层抽样病历"],
    ["12–16 h", "医生不可替代投入"],
    ["3 项", "待导师确认"],
  ];
  addCard(s, { x: 0.45, y: 5.68, w: 12.4, h: 1.16, fill: SLATE });
  stats.forEach((st, i) => {
    const x = 0.65 + i * 3.1;
    s.addText(st[0], {
      x,
      y: 5.8,
      w: 2.9,
      h: 0.52,
      fontFace: FACE,
      fontSize: 22,
      bold: true,
      color: RED,
      margin: 0,
    });
    s.addText(st[1], {
      x,
      y: 6.32,
      w: 2.9,
      h: 0.36,
      fontFace: FACE,
      fontSize: 12,
      color: MUTED,
      margin: 0,
    });
  });

  addFooter(s, "小结：不让医生「生产」金标准，只让医生「裁决」分歧。", 1);
  addNotes(
    s,
    "这一页是整份汇报的总览。对象是 DLBCL-Evidence 的 DLBCL 问答系统，要解决的问题是：如何做成一套能发论文的评估，同时尽量少耗医生时间。\n\n开场先把原则说清楚。金标准来自两处免费来源：病历里医生已经写好的结构化字段，以及从指南页反向出题时天然带着的 gold 页码。医生时间只投在两处不可替代的环节——决策分歧裁决，以及最终盲评。\n\n右下四张卡片对应后文四条主线。第一，三层评估：自动客观、校准后的 LLM 裁判、医生盲评。第二，自建 DLBCL-Bench，三个子集。第三，按能力分 M1 到 M7，而不是按四个界面分。第四，给导师三档方案，推荐组合式。\n\n数字可以这样报：指南反向题约 200 道；病历分层抽 300 份；医生不可替代投入 12 到 16 小时；需要导师当场拍板的是三项。\n\n收束用页脚这句话：不让医生生产金标准，只让医生裁决分歧。"
  );
}

// ---------------------------------------------------------------------------
// 2 原则
// ---------------------------------------------------------------------------
{
  const s = pres.addSlide();
  addBg(s);
  addTitle(s, "核心原则：按人力可替代性分层，医生只裁决分歧");
  addLead(
    s,
    "医生时间是最稀缺资源。评估越往下越贵、题量越少；绝大部分判定应由脚本完成。"
  );

  const layers = [
    {
      n: "01",
      k: "自动客观",
      tag: "零医生成本",
      fill: SLATE,
      b: "金标准来自病历原文、指南原页，以及 ClinVar / CIViC 等外部库。全脚本打分，承担检索、字段核对、图谱自核、分子解析、对抗题与效率，覆盖绝大部分题量。",
    },
    {
      n: "02",
      k: "LLM 裁判",
      tag: "极少医生成本",
      fill: AMBER_SOFT,
      b: "先用 30–50 题与医生评分对照，报告 Spearman 与 Gwet AC1。达标后才放大到全量开放题。校准不过关则不放大，避免未对齐的模型分数进入主表。",
    },
    {
      n: "03",
      k: "医生盲评",
      tag: "不可替代",
      fill: RED_SOFT,
      b: "只用在三处：决策题的分歧裁决、最终成对偏好盲评、第 2 层的校准集。2–3 人，报 Fleiss κ 与 Gwet AC1。可压到 2 人 × 4 小时的最小版。",
    },
  ];
  layers.forEach((c, i) => {
    const x = 0.45 + i * 4.2;
    addCard(s, { x, y: 1.36, w: 4.04, h: 3.42, fill: c.fill });
    addBadge(s, x + 0.18, 1.56, c.n, RED, WHITE);
    s.addText(c.k, {
      x: x + 0.64,
      y: 1.56,
      w: 3.2,
      h: 0.34,
      fontFace: FACE,
      fontSize: 18,
      bold: true,
      color: INK,
      margin: 0,
      valign: "middle",
    });
    s.addText(c.tag, {
      x: x + 0.18,
      y: 2.08,
      w: 3.68,
      h: 0.3,
      fontFace: FACE,
      fontSize: 13,
      italic: true,
      color: RED,
      margin: 0,
    });
    s.addText(c.b, {
      x: x + 0.18,
      y: 2.5,
      w: 3.68,
      h: 2.08,
      fontFace: FACE,
      fontSize: 14,
      color: MUTED,
      margin: 0,
    });
  });

  addCard(s, { x: 0.45, y: 4.96, w: 12.4, h: 1.86, fill: SLATE });
  s.addText("关键杠杆", {
    x: 0.67,
    y: 5.12,
    w: 11.96,
    h: 0.3,
    fontFace: FACE,
    fontSize: 14,
    bold: true,
    color: RED,
    margin: 0,
  });
  s.addText(
    "医生从「标准答案的生产者」转为「分歧的裁决者」。真实决策受试验入组、经济条件与患者意愿影响，未必等于指南最优；因此一致可自动判定，只有疑似不一致才需要临床判断。",
    {
      x: 0.67,
      y: 5.46,
      w: 11.96,
      h: 1.16,
      fontFace: FACE,
      fontSize: 14,
      color: MUTED,
      margin: 0,
    }
  );

  addFooter(
    s,
    "既有工作常把医生用于出题与写答案；本方案把医生投入压缩到无法自动化的三处。",
    2
  );
  addNotes(
    s,
    "这一页讲设计原则。医生时间是最稀缺资源，所以全部评估按人力可替代性分成三层，越往下越贵、题量越少。\n\n第一层，自动客观，零医生成本。金标准不是人写的，而是病历原文里已经有的字段、指南原页的页码，以及 ClinVar、CIViC 这类外部库。脚本打分，承担绝大部分题量。\n\n第二层，LLM 裁判。不能直接放大。先拿 30 到 50 题和医生评分对齐，报告 Spearman 和 Gwet AC1，达标才能用到全量开放题。这一层的校准本身也要占一点医生时间，但它换下来的是后面几百题。\n\n第三层，医生盲评，不可替代。只用在三处：决策分歧裁决、成对偏好盲评、以及刚才说的校准集。\n\n底部这句是整份方案的杠杆：不让医生生产金标准，只让医生裁决分歧。真实临床决策不一定等于指南最优，所以「一致」可以自动判，「疑似不一致」才需要人。"
  );
}

// ---------------------------------------------------------------------------
// 3 方法学定位
// ---------------------------------------------------------------------------
{
  const s = pres.addSlide();
  addBg(s);
  addTitle(s, "方法学全景：公开榜单不能证明专病临床深度");
  addLead(
    s,
    "医学问答评估是四层叠加。方法类论文与临床类论文的主表位置完全不同。"
  );

  const layers = [
    {
      n: "01",
      t: "执照知识层",
      tag: "方法类主表",
      b: "MedQA / MedMCQA / MMLU-med / CMB / CMExam。指标是准确率。MIRAGE 要求检索阶段不得看选项。",
    },
    {
      n: "02",
      t: "开放知识层",
      tag: "长答案",
      b: "无选项生成。早期用 ROUGE / BERTScore，现在用 LLM 裁判或 STAR 式配对偏好。",
    },
    {
      n: "03",
      t: "医生盲评层",
      tag: "临床类主表",
      b: "自建临床题 + Likert / 成对偏好 / mGPS。题量从数千降到数十至三百。",
    },
    {
      n: "04",
      t: "安全与溯源层",
      tag: "Almanac 核心表",
      b: "对抗题、强制出处、引用真伪逐条核查、拒答率与有害率。",
    },
  ];
  layers.forEach((c, i) => {
    const x = 0.45 + i * 3.2;
    addCard(s, { x, y: 1.36, w: 3.05, h: 2.72, fill: i === 2 ? RED_SOFT : SLATE });
    addBadge(s, x + 0.14, 1.52, c.n, RED, WHITE);
    s.addText(c.t, {
      x: x + 0.56,
      y: 1.52,
      w: 2.35,
      h: 0.34,
      fontFace: FACE,
      fontSize: 14,
      bold: true,
      color: INK,
      margin: 0,
      valign: "middle",
    });
    s.addText(c.tag, {
      x: x + 0.14,
      y: 2.0,
      w: 2.77,
      h: 0.26,
      fontFace: FACE,
      fontSize: 12,
      italic: true,
      color: RED,
      margin: 0,
    });
    s.addText(c.b, {
      x: x + 0.14,
      y: 2.34,
      w: 2.77,
      h: 1.55,
      fontFace: FACE,
      fontSize: 12,
      color: MUTED,
      margin: 0,
    });
  });

  addCard(s, { x: 0.45, y: 4.24, w: 12.4, h: 2.62, fill: SLATE });
  s.addText("DLBCL-Evidence 的差异化位置", {
    x: 0.67,
    y: 4.4,
    w: 11.96,
    h: 0.3,
    fontFace: FACE,
    fontSize: 15,
    bold: true,
    color: INK,
    margin: 0,
  });
  s.addText(
    "DLBCL 单病种 + 中文真实入院记录 + 指南原页溯源。这一格基本没有现成对照。心血管做到 100 道专科 MCQ，肿瘤做到 316 例 MDT 模板，淋巴瘤做到 50 例 NCCN 一致性，都没有下到 FISH / 双表达 / CR 后移植这一层。",
    {
      x: 0.67,
      y: 4.78,
      w: 11.96,
      h: 0.95,
      fontFace: FACE,
      fontSize: 13,
      color: MUTED,
      margin: 0,
    }
  );
  s.addText(
    "MedCheck 审 56 个公开基准：约一半对不齐正式医学标准，45% 未论证临床效用。这条正好用来为「专病深度优先于榜单广度」辩护。",
    {
      x: 0.67,
      y: 5.76,
      w: 11.96,
      h: 0.88,
      fontFace: FACE,
      fontSize: 13,
      color: MUTED,
      margin: 0,
    }
  );

  addFooter(s, "主表不应落在公开选择题；公开集只能证明底座不弱。", 3);
  addNotes(
    s,
    "这一页讲方法学定位：别人怎么评，我们该站哪一格。医学问答评估实际是四层叠加，方法类论文和临床类论文的主表完全不同。\n\n第一层执照知识，MedQA、MedMCQA、中文 CMB / CMExam，指标是准确率。方法类论文主表在这里。MIRAGE 规范要求检索阶段不能看选项。第二层开放知识，长答案，现在主流是 LLM 裁判或 STAR 配对偏好。第三层医生盲评，临床类论文主表在这里，题量从几千掉到几十到三百。第四层安全与溯源，Almanac 和 HealthBench 的核心表。\n\nDLBCL-Evidence 的差异化是这一句：DLBCL 单病种，加上中文真实入院记录，加上指南原页溯源。心血管做到 100 道专科选择题，肿瘤做到 316 例 MDT，淋巴瘤做到 50 例 NCCN 一致性，都没有下到 FISH、双表达、CR 后移植这一层。\n\nMedCheck 审了 56 个公开基准，大约一半对不齐正式医学标准，45% 没有论证临床效用。审稿人如果问为什么不主打公开榜，就用这条为「深度优于广度」辩护。"
  );
}

// ---------------------------------------------------------------------------
// 4 七维
// ---------------------------------------------------------------------------
{
  const s = pres.addSlide();
  addBg(s);
  addTitle(s, "必须分模块评估：按能力与可归因性，而非按界面");
  addLead(
    s,
    "图谱、分子与文献若只看端到端指标，贡献会被稀释到看不见。每个维度对应论文里的一张表。"
  );

  const top = [
    {
      h: "M1 指南检索",
      tag: "自动",
      b: "Recall@k / MRR / nDCG / 页码 Precision。金标准=反向出题的 gold 页码。三源分报；消融 BM25 → 重排 → 门控 → agent。",
    },
    {
      h: "M3 知识图谱",
      tag: "自动自核",
      b: "待审 5953 + trusted 601 中抽 200 条，按指南原文核对。报三元组精确率与本体违规率，并做 graph prompt 消融。",
    },
    {
      h: "M4 分子证据",
      tag: "全自动",
      b: "ClinVar 构造 300–500 条变异解析金标准；与 CIViC 分级比一致率；60 例边界样本测 SafetyGate 四档混淆矩阵。",
    },
    {
      h: "M5 联网文献",
      tag: "弱金标准",
      b: "1028 个指南 PMID 验证 E1–E5。另测 POLARIX / EPCORE / STARGLO 等截止后试验召回。抽 50 条请医生复核。",
    },
  ];
  top.forEach((c, i) => {
    const x = 0.45 + i * 3.2;
    addCard(s, { x, y: 1.36, w: 3.05, h: 2.48, fill: SLATE });
    s.addText(c.h, {
      x: x + 0.14,
      y: 1.48,
      w: 2.77,
      h: 0.3,
      fontFace: FACE,
      fontSize: 14,
      bold: true,
      color: INK,
      margin: 0,
    });
    s.addText(c.tag, {
      x: x + 0.14,
      y: 1.78,
      w: 2.77,
      h: 0.22,
      fontFace: FACE,
      fontSize: 11,
      italic: true,
      color: RED,
      margin: 0,
    });
    s.addText(c.b, {
      x: x + 0.14,
      y: 2.06,
      w: 2.77,
      h: 1.62,
      fontFace: FACE,
      fontSize: 12,
      color: MUTED,
      margin: 0,
    });
  });

  const bot = [
    {
      h: "M2 端到端答案质量",
      tag: "主表 · 需医生",
      fill: RED_SOFT,
      b: "五维 Likert：事实正确、指南一致、完整性、安全性、溯源可信；加成对偏好。另报引用忠实度：逐条核查每个 [Sn] 是否支持所在结论句。",
    },
    {
      h: "M6 安全与拒答",
      tag: "自动",
      fill: AMBER_SOFT,
      b: "对抗题下的编造剂量率、缺信息主动声明率、隐私字段泄露率、越界推荐率。",
    },
    {
      h: "M7 效率与成本",
      tag: "自动",
      fill: BLUE_SOFT,
      b: "延迟 p50 / p95、token 与成本、agent 步数。profile_latency.py 与 runs/*.jsonl 已有原料。",
    },
  ];
  bot.forEach((c, i) => {
    const widths = [6.12, 3.05, 3.05];
    const xs = [0.45, 6.73, 9.93];
    addCard(s, { x: xs[i], y: 4.0, w: widths[i], h: 2.62, fill: c.fill });
    s.addText(c.h, {
      x: xs[i] + 0.16,
      y: 4.14,
      w: widths[i] - 0.32,
      h: 0.32,
      fontFace: FACE,
      fontSize: 15,
      bold: true,
      color: INK,
      margin: 0,
    });
    s.addText(c.tag, {
      x: xs[i] + 0.16,
      y: 4.48,
      w: widths[i] - 0.32,
      h: 0.24,
      fontFace: FACE,
      fontSize: 12,
      italic: true,
      color: RED,
      margin: 0,
    });
    s.addText(c.b, {
      x: xs[i] + 0.16,
      y: 4.82,
      w: widths[i] - 0.32,
      h: 1.64,
      fontFace: FACE,
      fontSize: 13,
      color: MUTED,
      margin: 0,
    });
  });

  addFooter(
    s,
    "界面（主问答 / 证据 / 图谱 / 分子）不能作为分表依据；ablation 才能证明模块值得存在。",
    4
  );
  addNotes(
    s,
    "这一页讲为什么必须分模块评，以及怎么分。分法不按四个界面，而按能力和可归因性分成七个维度，每个维度对应论文里的一张表。\n\n上面四个是组件表，都可以自动打。M1 指南检索，金标准是反向出题时带着的 gold 页码，报 Recall、MRR、nDCG 和页码 Precision，三源分开报，并做 BM25、重排、门控、agent 多步的消融。M3 知识图谱，从待审和 trusted 三元组里抽 200 条，自己对照指南原文就能判，不需要医生。M4 分子证据是最容易出漂亮表的一块：ClinVar 做解析金标准，CIViC 做分级一致率，自造 60 例边界样本看 SafetyGate 四档。M5 文献分档，用指南已经引用的 1028 个 PMID 当弱金标准，E1、E2 应该更常被指南引用；再拿指南截止后的关键试验测新证据召回。\n\n下面三个：M2 是主表，必须有医生，五维 Likert 加成对偏好，再加上引用忠实度，逐条看 [Sn] 是否真的支持那句话。M6 安全、M7 效率都是自动的。\n\n讲这一页时强调一句：图谱、分子、文献如果只看端到端，贡献会被稀释到看不见。"
  );
}

// ---------------------------------------------------------------------------
// 5 MedQA
// ---------------------------------------------------------------------------
{
  const s = pres.addSlide();
  addBg(s);
  addTitle(s, "从 MedQA 抽 DLBCL 题技术可行，但只能当附表");
  addLead(
    s,
    "MedQA-USMLE 约 1.27 万题中，DLBCL 直接相关约为个位数至数十题，test split 更少，撑不起统计检验。"
  );

  addCard(s, { x: 0.45, y: 1.36, w: 4.2, h: 5.5, fill: RED_SOFT });
  s.addText("结论", {
    x: 0.67,
    y: 1.56,
    w: 3.76,
    h: 0.28,
    fontFace: FACE,
    fontSize: 13,
    bold: true,
    color: RED,
    margin: 0,
  });
  s.addText("只能当附表，\n不能当主表。", {
    x: 0.67,
    y: 1.96,
    w: 3.76,
    h: 1.15,
    fontFace: FACE,
    fontSize: 22,
    bold: true,
    color: INK,
    margin: 0,
  });
  s.addText(
    "这张表的作用，是证明底座不弱、检索无害，而不是证明产品的临床价值。写论文时必须主动说明，避免被审稿人当成主要证据来攻击。",
    {
      x: 0.67,
      y: 3.28,
      w: 3.76,
      h: 1.7,
      fontFace: FACE,
      fontSize: 14,
      color: MUTED,
      margin: 0,
    }
  );
  s.addText(
    "儿科心脏病 304 题已表明：RAG 在 MCQ 上几乎不涨分。要预期同样的结果。",
    {
      x: 0.67,
      y: 5.1,
      w: 3.76,
      h: 1.4,
      fontFace: FACE,
      fontSize: 13,
      color: MUTED,
      margin: 0,
    }
  );

  const pts = [
    {
      n: "01",
      t: "折中：粒度放到淋巴瘤",
      b: "跨库合并 Lymphoma-MCQ：MedQA + MedMCQA（19.4 万）+ MMLU + 中文 CMB / CMExam。关键词初筛 → LLM 二筛 → 复核，目标 150–300 题。中文题必须有。",
    },
    {
      n: "02",
      t: "必须按 MIRAGE 规范做",
      b: "检索阶段不给选项，只在生成时选 A–E。否则检索指标会被选项泄漏污染。",
    },
    {
      n: "03",
      t: "必须报污染检查",
      b: "题目 n-gram 与指南全文 / 公开网络的重合度，以及无检索直答准确率作为记忆基线。Almanac 已批评公开选择题有污染且不像临床决策。",
    },
  ];
  pts.forEach((c, i) => {
    const y = 1.36 + i * 1.86;
    addCard(s, { x: 4.85, y, w: 8.0, h: 1.74, fill: SLATE });
    addBadge(s, 5.03, y + 0.16, c.n, RED, WHITE);
    s.addText(c.t, {
      x: 5.5,
      y: y + 0.16,
      w: 7.1,
      h: 0.34,
      fontFace: FACE,
      fontSize: 15,
      bold: true,
      color: INK,
      margin: 0,
      valign: "middle",
    });
    s.addText(c.b, {
      x: 5.03,
      y: y + 0.58,
      w: 7.6,
      h: 1.0,
      fontFace: FACE,
      fontSize: 13,
      color: MUTED,
      margin: 0,
    });
  });

  addFooter(
    s,
    "公开选择题用来守住「底座不弱」这一底，而不是证明 DLBCL-Evidence 的产品价值。",
    5
  );
  addNotes(
    s,
    "这一页回答第一个问题：能不能从 MedQA 里抽 DLBCL 题。结论先说：技术上可行，但只能当附表，不能当主表。\n\n原因很硬。MedQA-USMLE 大约 1.27 万题，血液肿瘤占比小，DLBCL 直接相关大概只有个位数到几十题，test split 里更少，撑不起统计检验。\n\n可行的折中，是把粒度从 DLBCL 放到淋巴瘤，跨库合成一个 Lymphoma-MCQ 子集。MedMCQA 有 19.4 万题，能捞到更多；中文必须有 CMB 或 CMExam，否则和系统的中文场景对不上。流程是关键词初筛、LLM 二筛、自己复核，目标 150 到 300 题。\n\n两件必须做的事。第一，按 MIRAGE：检索阶段不给选项，只在生成时选 A 到 E，否则检索指标被选项泄漏污染。第二，报污染检查：题目和指南全文、公开网络的 n-gram 重合，以及无检索直答的准确率当记忆基线。\n\n最后要预期 RAG 增益很小。儿科心脏病那篇 304 题已经说明，选择题上 RAG 几乎不涨。所以这张表的任务是证明底座不弱、检索无害。论文里要主动写明，免得审稿人把它当成主要证据来打。"
  );
}

// ---------------------------------------------------------------------------
// 6 Bench 总览
// ---------------------------------------------------------------------------
{
  const s = pres.addSlide();
  addBg(s);
  addTitle(s, "自建 DLBCL-Bench：先有金标准，再反向生成题目");
  addLead(
    s,
    "三个子集全部围绕「金标准免费」设计。核心技巧是从指南页出发，而不是先出题再找答案。"
  );

  const cols = [
    {
      n: "A",
      t: "Guideline-QA",
      meta: "约 200 题  ·  零医生成本",
      fill: SLATE,
      b: "从指南页生成题目，gold 页码天然存在。M1 检索金标准与 M2 引用金标准同时免费获得。\n\n三源各 60–80 题，按 GuidelinePage / DiscussionChunk 分层。覆盖诊断分型、一线、复发难治、移植、CAR-T、支持治疗。\n\n每题附 gold 页码与要点 rubric。自己复核题目合理性即可。",
    },
    {
      n: "B",
      t: "Case-QA",
      meta: "约 400–600 题  ·  差异化核心",
      fill: RED_SOFT,
      b: "从 1000 份病历分层抽 300 份：初诊 / 复发难治 / 移植 / CAR-T，以及 GCB、双表达、TP53、结外、老年。\n\nB1 字段核对，全自动。\nB2 决策一致性，只裁分歧。\nB3 开放会诊题，医生盲评。\n\n三种题型的金标准来源完全不同，详见下一页。",
    },
    {
      n: "C",
      t: "Safety",
      meta: "约 60–80 题  ·  零医生成本",
      fill: AMBER_SOFT,
      b: "自造对抗题：信息不足时诱导给出预处理剂量；把双表达说成双打击；把血清 EBV 说成 EBER；诱导超说明书用药；输出电话住址；引用过期指南。\n\n指标为拒答 / 声明不确定率、幻觉率、隐私泄露率。",
    },
  ];
  cols.forEach((c, i) => {
    const x = 0.45 + i * 4.2;
    addCard(s, { x, y: 1.36, w: 4.04, h: 5.5, fill: c.fill });
    s.addText(c.n, {
      x: x + 0.2,
      y: 1.52,
      w: 3.64,
      h: 0.42,
      fontFace: FACE,
      fontSize: 22,
      bold: true,
      color: RED,
      margin: 0,
    });
    s.addText(c.t, {
      x: x + 0.2,
      y: 1.96,
      w: 3.64,
      h: 0.34,
      fontFace: FACE,
      fontSize: 18,
      bold: true,
      color: INK,
      margin: 0,
    });
    s.addText(c.meta, {
      x: x + 0.2,
      y: 2.34,
      w: 3.64,
      h: 0.28,
      fontFace: FACE,
      fontSize: 12,
      italic: true,
      color: RED,
      margin: 0,
    });
    s.addText(c.b, {
      x: x + 0.2,
      y: 2.74,
      w: 3.64,
      h: 3.88,
      fontFace: FACE,
      fontSize: 13,
      color: MUTED,
      margin: 0,
    });
  });

  addFooter(
    s,
    "反向出题使检索金标准与引用金标准同时免费获得，不占医生时间。",
    6
  );
  addNotes(
    s,
    "这一页进入主线：自建 benchmark 怎么构建。建议命名 DLBCL-Bench，三个子集，设计原则都是金标准免费。\n\n子集 A，指南问答，约 200 题，零医生成本。核心技巧是反向出题：不是先出题再找答案，而是从指南页出发生成题目，这样 gold 页码天然存在。检索的金标准和引用的金标准同时拿到。三源各 60 到 80 题，覆盖诊断、一线、复发难治、移植、CAR-T 和支持治疗。自己复核题目合理性即可。\n\n子集 B 是差异化核心，下一页展开。从 1000 份病历里分层抽 300 份，三种题型。\n\n子集 C 是安全对抗，60 到 80 题，也是零医生成本。诱导编剂量、把双表达说成双打击、把血清 EBV 说成 EBER、泄隐私、引过期指南。看它会不会拒答、会不会幻觉、会不会把电话住址吐出来。\n\n这一页记住一句话：先有金标准，再反向生成题目。"
  );
}

// ---------------------------------------------------------------------------
// 7 子集 B
// ---------------------------------------------------------------------------
{
  const s = pres.addSlide();
  addBg(s);
  addTitle(s, "病历主线构成差异化：字段自动核对，决策只裁分歧");
  addLead(
    s,
    "三种题型的金标准来源完全不同。医生只进入「疑似不一致」的那 20–30%。"
  );

  const rows = [
    {
      n: "B1",
      t: "抽取与事实核对",
      tag: "全自动  ·  题量最大  ·  医生零投入",
      fill: SLATE,
      b: "金标准就是病历里医生写好的字段：Hans、Ann Arbor、IPI / aaIPI、FISH、双表达、疗效、CD34。每份 8–12 个字段，300 份约 2400–3600 个字段级判定，精确匹配 / F1 自动打分。case_extractor.py 已抽成六段 JSON，管线可直接复用。",
    },
    {
      n: "B2",
      t: "回顾性决策一致性",
      tag: "半自动  ·  最有分量  ·  只裁 30–45 例",
      fill: RED_SOFT,
      b: "在病历时间线上截断、隐去后续，问「下一步该怎么做」，以当年真实决策为参考。约 150 个决策点，三分类为一致 / 合理不同 / 不一致。前者自动判定；只有疑似不一致才交医生，因为真实决策受试验、经济与患者意愿影响，未必等于指南最优。对标 JCO 316 例 MDT（κ=0.63）与淋巴瘤 ASH 摘要 50 例 mG-PS。",
    },
    {
      n: "B3",
      t: "开放决策与会诊题",
      tag: "医生盲评  ·  100 题  ·  论文主表",
      fill: AMBER_SOFT,
      b: "现有 ASCT 第 8 次入院病例的 A–I 区已是出题模板。G 区多源冲突与 J 区失败模式表可升级为评分量规：双表达 ≠ 双打击；点突变 + CNV-loss 须双证据；CR 后巩固存在争议前提；缺失信息必须拒答。",
    },
  ];
  rows.forEach((c, i) => {
    const y = 1.36 + i * 1.86;
    addCard(s, { x: 0.45, y, w: 12.4, h: 1.74, fill: c.fill });
    s.addText(c.n, {
      x: 0.65,
      y: y + 0.18,
      w: 1.1,
      h: 0.4,
      fontFace: FACE,
      fontSize: 20,
      bold: true,
      color: RED,
      margin: 0,
      valign: "middle",
    });
    s.addText(c.t, {
      x: 1.85,
      y: y + 0.16,
      w: 5.2,
      h: 0.34,
      fontFace: FACE,
      fontSize: 16,
      bold: true,
      color: INK,
      margin: 0,
      valign: "middle",
    });
    s.addText(c.tag, {
      x: 7.1,
      y: y + 0.18,
      w: 5.5,
      h: 0.32,
      fontFace: FACE,
      fontSize: 12,
      italic: true,
      color: RED,
      align: "right",
      margin: 0,
      valign: "middle",
    });
    s.addText(c.b, {
      x: 0.65,
      y: y + 0.58,
      w: 11.96,
      h: 1.04,
      fontFace: FACE,
      fontSize: 13,
      color: MUTED,
      margin: 0,
    });
  });

  addFooter(
    s,
    "对标临床向论文的题量量级：数十至三百，而不是公开集的数千。",
    7
  );
  addNotes(
    s,
    "这一页展开子集 B，这是整份方案里最有差异化的一块。从 1000 份病历分层抽 300 份。三种题型，金标准来源完全不同。\n\nB1，抽取与事实核对，全自动，题量最大。金标准直接是病历里医生写好的结构化字段：Hans 分型、分期、IPI、FISH、双表达、疗效、CD34。每份 8 到 12 个字段，300 份就是 2400 到 3600 个字段级判定，精确匹配和 F1 自动打。医生零投入。抽取管线已经有，可以直接复用。\n\nB2 是最有分量的设计。把病历时间线截断，隐去后面发生的事，问系统下一步该怎么做，用当年医生实际做的决策当参考。大约 150 个决策点。结果分成一致、合理不同、不一致。一致可以自动判。只有落在疑似不一致的那 20% 到 30%，大约 30 到 45 例，才交给医生。这里必须讲清楚：真实决策可能受临床试验、经济、患者意愿影响，不一定等于指南最优，所以不能把「和当年不一样」直接判成系统错。对标 JCO 那篇 316 例 MDT，以及淋巴瘤 ASH 摘要的 50 例。\n\nB3 是 100 道开放决策题，医生盲评，这是论文主表。现有那份 ASCT 第 8 次入院病例的分区已经是出题模板，尤其是多源冲突和失败模式表，可以直接升级成评分量规。"
  );
}

// ---------------------------------------------------------------------------
// 8 打分与对照
// ---------------------------------------------------------------------------
{
  const s = pres.addSlide();
  addBg(s);
  addTitle(s, "打分三层与完整对照：缺少基线则论文没有说服力");
  addLead(
    s,
    "朴素 RAG 基线零成本可得。routing_mode=linear 即单次检索、无 agent 循环、无证据门控。"
  );

  addCard(s, { x: 0.45, y: 1.36, w: 6.12, h: 5.5, fill: SLATE });
  s.addText("打分三层", {
    x: 0.67,
    y: 1.54,
    w: 5.68,
    h: 0.32,
    fontFace: FACE,
    fontSize: 16,
    bold: true,
    color: INK,
    margin: 0,
  });
  const score = [
    ["1", "自动客观", "字段匹配、检索指标、三元组核对、变异解析、对抗题、延迟与成本。零医生。"],
    ["2", "LLM 裁判", "30–50 题校准，报 Spearman 与 Gwet AC1。达标后才放大到全量开放题。"],
    ["3", "医生盲评", "100 题五维 Likert + 成对偏好，2–3 人，报 Fleiss κ 与 Gwet AC1。"],
  ];
  score.forEach((c, i) => {
    const y = 2.02 + i * 1.48;
    addBadge(s, 0.67, y, c[0], RED, WHITE);
    s.addText(c[1], {
      x: 1.15,
      y,
      w: 5.1,
      h: 0.34,
      fontFace: FACE,
      fontSize: 15,
      bold: true,
      color: INK,
      margin: 0,
      valign: "middle",
    });
    s.addText(c[2], {
      x: 0.67,
      y: y + 0.42,
      w: 5.68,
      h: 0.9,
      fontFace: FACE,
      fontSize: 13,
      color: MUTED,
      margin: 0,
    });
  });

  addCard(s, { x: 6.73, y: 1.36, w: 6.12, h: 5.5, fill: RED_SOFT });
  s.addText("对照组必须齐全", {
    x: 6.95,
    y: 1.54,
    w: 5.68,
    h: 0.32,
    fontFace: FACE,
    fontSize: 16,
    bold: true,
    color: INK,
    margin: 0,
  });
  const bases = [
    ["通用大模型直答", "qwen-plus / GPT / DeepSeek，无检索"],
    ["通用大模型 + 联网", "通用搜索，不限定指南"],
    ["朴素 RAG", "linear 回退路径，零额外实现成本"],
    ["DLBCL-Evidence 完整版", "主系统"],
    [
      "六项消融",
      "去 agent / 去重排 / 去门控 / 去图谱 [G*] / 去 PubMed [Ln] / 去 VLM",
    ],
    ["可选人类上限", "医生自答子集。心血管那篇模型 95+ vs 医生约 70，说明 MCQ 测的是「会不会选」"],
  ];
  bases.forEach((c, i) => {
    const y = 2.0 + i * 0.74;
    s.addText(c[0], {
      x: 6.95,
      y,
      w: 5.68,
      h: 0.26,
      fontFace: FACE,
      fontSize: 13,
      bold: true,
      color: INK,
      margin: 0,
    });
    s.addText(c[1], {
      x: 6.95,
      y: y + 0.26,
      w: 5.68,
      h: 0.4,
      fontFace: FACE,
      fontSize: 12,
      color: MUTED,
      margin: 0,
    });
  });

  addFooter(s, "对照不齐，审稿人会认为增益来自底座模型，而不是来自系统。", 8);
  addNotes(
    s,
    "这一页讲打分和对照组。打分还是那三层：自动客观、校准后的 LLM 裁判、医生盲评。盲评是 100 题，五维 Likert 加成对偏好，2 到 3 位医生，报告 Fleiss κ 和 Gwet AC1。\n\n对照组必须齐全，否则论文没有说服力。四条主对照：通用大模型直答、通用大模型加联网、朴素 RAG、DLBCL-Evidence 完整版。朴素 RAG 不必另做——配置里的 linear 回退路径本身就是单次检索、无 agent、无门控，直接当基线。\n\n消融六项：去掉 agent 工具循环、去掉重排、去掉证据门控、去掉知识图谱、去掉 PubMed、去掉看图。这样四个模块各自的贡献才能进表。\n\n可选的人类上限，是让医生自己答一个子集。心血管那篇里模型 95 分以上、医生大约 70，恰好说明选择题测的是会不会选，不是临床决策能力。如果做了 Lymphoma-MCQ，这是一句很好的预防性说明。\n\n收束：对照不齐，审稿人会把增益记到底座模型头上。"
  );
}

// ---------------------------------------------------------------------------
// 9 范围
// ---------------------------------------------------------------------------
{
  const s = pres.addSlide();
  addBg(s);
  addTitle(s, "检索库已覆盖 B 细胞淋巴瘤全指南，扩展成本不在检索层");
  addLead(
    s,
    "库中本是 NCCN B 细胞淋巴瘤全指南。范围只是被 detect_disease_scope 锁在 DLBCL。放开即可做 QA。"
  );

  const opts = [
    {
      n: "1",
      t: "推荐 · 低成本",
      h: "专病深度 + 泛化小集",
      fill: GREEN_SOFT,
      accent: GREEN,
      b: "主体保持 DLBCL。另做 80 题覆盖 FL / MCL / BL / HGBL / PMBCL。检索侧几乎零改动。回应审稿人必问的泛化性，同时不动摇专病主线。性价比最高。",
    },
    {
      n: "2",
      t: "中成本 · 不作主线",
      h: "扩到血液肿瘤大类",
      fill: SLATE,
      accent: MUTED,
      b: "加髓系、骨髓瘤指南。需新增本体、抽取规则、KG 重建、评测集重做，工作量以月计。论文会从「专病深度」稀释成又一个通用医学 RAG。",
    },
    {
      n: "3",
      t: "不扩",
      h: "只写 Limitation",
      fill: AMBER_SOFT,
      accent: AMBER,
      b: "不做泛化集，只在局限里承认适用范围。风险是审稿人质疑适用面，需要在回复里用 MedCheck 的批评去挡。",
    },
  ];
  opts.forEach((c, i) => {
    const x = 0.45 + i * 4.2;
    addCard(s, { x, y: 1.36, w: 4.04, h: 5.5, fill: c.fill });
    s.addText("选项 " + c.n, {
      x: x + 0.2,
      y: 1.54,
      w: 3.64,
      h: 0.28,
      fontFace: FACE,
      fontSize: 13,
      bold: true,
      color: c.accent,
      margin: 0,
    });
    s.addText(c.t, {
      x: x + 0.2,
      y: 1.86,
      w: 3.64,
      h: 0.3,
      fontFace: FACE,
      fontSize: 13,
      italic: true,
      color: RED,
      margin: 0,
    });
    s.addText(c.h, {
      x: x + 0.2,
      y: 2.24,
      w: 3.64,
      h: 0.7,
      fontFace: FACE,
      fontSize: 18,
      bold: true,
      color: INK,
      margin: 0,
    });
    s.addText(c.b, {
      x: x + 0.2,
      y: 3.04,
      w: 3.64,
      h: 3.5,
      fontFace: FACE,
      fontSize: 14,
      color: MUTED,
      margin: 0,
    });
  });

  addFooter(
    s,
    "扩展后做 QA 完全可行，但不建议把它变成论文主线。深度优于广度。",
    9
  );
  addNotes(
    s,
    "这一页回答第三个问题：要不要扩到更大病种。有一个此前可能没注意的事实：检索库里装的本来就是 NCCN B 细胞淋巴瘤全指南，滤泡、套细胞、边缘区、伯基特、高级别、原发纵隔、中枢都在。只是被 detect_disease_scope 锁在了 DLBCL。所以扩展成本主要在知识图谱本体和评测集，不在检索层。\n\n三个选项。选项 1，推荐，低成本：主体继续做 DLBCL 专病深度，额外做一个 80 题的泛化小集，覆盖滤泡、套细胞、伯基特、高级别和原发纵隔。放开 scope 即可，检索侧几乎不用改。作用是回应审稿人必问的泛化性，同时不动摇专病主线。\n\n选项 2，扩到血液肿瘤大类，加髓系和骨髓瘤。本体、抽取、图谱、评测集都要重做，按月计。而且论文会从专病深度变成又一个通用医学 RAG，差异化反而丢了。\n\n选项 3，不扩，只在 Limitation 里写。风险是审稿人质疑适用面。\n\n结论是选项 1。扩展后做问答完全可行，但不建议变成论文主线。MedCheck 的批评正好支持深度优于广度。"
  );
}

// ---------------------------------------------------------------------------
// 10 三方案
// ---------------------------------------------------------------------------
{
  const s = pres.addSlide();
  addBg(s);
  addTitle(s, "三种定档方案：推荐组合式，用自动数字换医生时间");
  addLead(
    s,
    "投稿定位尚未确定时，阶段 1 的自动结果无论最终投哪里都不浪费。"
  );

  const plans = [
    {
      n: "A",
      t: "自动化优先",
      tag: "最小可发表  ·  约 4 周",
      fill: SLATE,
      rows: [
        ["医生", "0–4 小时，仅 30 题校准抽检"],
        ["内容", "A 200 + Lymphoma-MCQ 200 + C 60 + 组件表 + 全套对照"],
        ["去向", "方法类 / 系统类"],
        ["弱点", "无真实病历，无医生金标准。「医生认可吗」答不上。"],
      ],
    },
    {
      n: "B",
      t: "病历主线",
      tag: "临床向  ·  约 8–10 周",
      fill: AMBER_SOFT,
      rows: [
        ["医生", "约 20 小时，3 人各 6–7 小时"],
        ["内容", "子集 B 全量 + 引用逐条核查 + 完整对照"],
        ["去向", "NEJM AI / npj Digit. Med. / JAMIA / JCO CCI"],
        ["弱点", "强依赖伦理审批与医生协调，周期长。"],
      ],
    },
    {
      n: "C",
      t: "组合式",
      tag: "推荐  ·  两阶段",
      fill: RED_SOFT,
      rows: [
        ["医生", "阶段 1 为零；阶段 2 为 12–16 小时"],
        ["内容", "先跑 A+C+B1+组件表；再做 B2/B3 与泛化小集"],
        ["去向", "临床向、方法向两种写法都能走"],
        ["结构", "主表=病历+盲评；附表=MCQ+组件；另附 ablation"],
      ],
    },
  ];
  plans.forEach((c, i) => {
    const x = 0.45 + i * 4.2;
    addCard(s, { x, y: 1.36, w: 4.04, h: 5.5, fill: c.fill });
    s.addText("方案 " + c.n, {
      x: x + 0.2,
      y: 1.52,
      w: 3.64,
      h: 0.28,
      fontFace: FACE,
      fontSize: 13,
      bold: true,
      color: RED,
      margin: 0,
    });
    s.addText(c.t, {
      x: x + 0.2,
      y: 1.82,
      w: 3.64,
      h: 0.36,
      fontFace: FACE,
      fontSize: 20,
      bold: true,
      color: INK,
      margin: 0,
    });
    s.addText(c.tag, {
      x: x + 0.2,
      y: 2.2,
      w: 3.64,
      h: 0.28,
      fontFace: FACE,
      fontSize: 12,
      italic: true,
      color: RED,
      margin: 0,
    });
    c.rows.forEach((r, j) => {
      const y = 2.64 + j * 0.96;
      s.addText(r[0], {
        x: x + 0.2,
        y,
        w: 3.64,
        h: 0.24,
        fontFace: FACE,
        fontSize: 12,
        bold: true,
        color: INK,
        margin: 0,
      });
      s.addText(r[1], {
        x: x + 0.2,
        y: y + 0.24,
        w: 3.64,
        h: 0.64,
        fontFace: FACE,
        fontSize: 13,
        color: MUTED,
        margin: 0,
      });
    });
  });

  addFooter(
    s,
    "推荐方案 C。先用可见数字换第二阶段的人力，而不是一上来协调 20 小时医生时间。",
    10
  );
  addNotes(
    s,
    "这一页把三种方案摊开，请导师定档。\n\n方案 A，自动化优先，大约 4 周，医生 0 到 4 小时。做指南题、淋巴瘤选择题、安全题、组件表和全套对照。适合方法类、系统类投稿。弱点很清楚：没有真实病历，没有医生金标准，「医生认可吗」这一问答不上。\n\n方案 B，病历主线，8 到 10 周，医生大约 20 小时。子集 B 全上，引用逐条核查。对标 Almanac 和 JCO 那篇 NCCN-RAG，差异化最强，适合 NEJM AI、npj Digital Medicine、JAMIA、JCO CCI。弱点是强依赖伦理审批和医生档期。\n\n方案 C，推荐。分两阶段。阶段 1 用 2 到 3 周跑通自动骨架：指南题、安全题、病历字段抽取、组件指标和对照，零医生，先产出可见数字。阶段 2 再用 4 到 6 周做分歧裁决、100 题盲评和 80 题泛化小集，医生 12 到 16 小时。论文结构是：主表病历加盲评，附表选择题加组件，消融表证明四个模块。\n\nC 的好处是同时支撑临床向和方法向。阶段 1 无论最后投哪里都不浪费。用第一阶段的数字去换第二阶段的人力，而不是一上来就要 20 小时医生时间。"
  );
}

// ---------------------------------------------------------------------------
// 11 医生时间与风险
// ---------------------------------------------------------------------------
{
  const s = pres.addSlide();
  addBg(s);
  addTitle(s, "医生仅需 12–16 小时；伦理与云端 LLM 是硬前提");
  addLead(
    s,
    "可压缩到 2 人 × 4 小时的最小版。其余题量全部由病历自带金标准与脚本承担。"
  );

  const tasks = [
    { n: "1", t: "盲评 100 题", d: "3 人 × 约 5 小时。论文主表，无替代方案。" },
    { n: "2", t: "分歧裁决 30–45 例", d: "约 2 小时。判「合理不同」还是「真错」。" },
    { n: "3", t: "校准集 30–50 题", d: "约 2 小时。不校准就不能用 LLM 裁判放大。" },
  ];
  tasks.forEach((c, i) => {
    const x = 0.45 + i * 4.2;
    addCard(s, { x, y: 1.36, w: 4.04, h: 1.7, fill: RED_SOFT });
    addBadge(s, x + 0.16, 1.52, c.n, RED, WHITE);
    s.addText(c.t, {
      x: x + 0.6,
      y: 1.52,
      w: 3.24,
      h: 0.34,
      fontFace: FACE,
      fontSize: 14,
      bold: true,
      color: INK,
      margin: 0,
      valign: "middle",
    });
    s.addText(c.d, {
      x: x + 0.16,
      y: 2.0,
      w: 3.72,
      h: 0.86,
      fontFace: FACE,
      fontSize: 13,
      color: MUTED,
      margin: 0,
    });
  });

  const risks = [
    {
      n: "01",
      t: "伦理与脱敏",
      b: "1000 份病历需 IRB / 伦理批件。示例病历含电话、住址、住院号，脱敏必须先行。评测集与病历一律不进 git。",
    },
    {
      n: "02",
      t: "云端 LLM 与数据出境",
      b: "qwen-plus / qwen-vl-max 走 DashScope。真实病历出院内网络需院方批准，或改本地部署。这是方案 B / C 阶段 2 的硬前提。",
    },
    {
      n: "03",
      t: "病历噪声",
      b: "原文存在「腹部腹部腹部」「无子女现有1子」一类笔误。建议当作鲁棒性测试项——本身就是卖点——而不是预先清洗。",
    },
    {
      n: "04",
      t: "并入时序",
      b: "分子证据 agent 若并入主问答，宜先做出独立客观指标再合并。并入后只能靠端到端 ablation 说话，独立指标更难拿。",
    },
  ];
  risks.forEach((c, i) => {
    const col = i % 2;
    const row = Math.floor(i / 2);
    const x = 0.45 + col * 6.28;
    const y = 3.24 + row * 1.82;
    addCard(s, { x, y, w: 6.12, h: 1.7, fill: SLATE });
    addBadge(s, x + 0.16, y + 0.16, c.n, RED, WHITE);
    s.addText(c.t, {
      x: x + 0.6,
      y: y + 0.16,
      w: 5.3,
      h: 0.34,
      fontFace: FACE,
      fontSize: 14,
      bold: true,
      color: INK,
      margin: 0,
      valign: "middle",
    });
    s.addText(c.b, {
      x: x + 0.16,
      y: y + 0.58,
      w: 5.8,
      h: 0.98,
      fontFace: FACE,
      fontSize: 13,
      color: MUTED,
      margin: 0,
    });
  });

  addFooter(
    s,
    "方案 B / C 阶段 2 启动前，必须确认病历文本能否调用云端模型。",
    11
  );
  addNotes(
    s,
    "这一页把医生时间和前置风险放在一起，明天汇报务必提出。\n\n医生真正必须上手的只有三处，合计 12 到 16 小时，可以压到两人各 4 小时的最小版。第一，盲评 100 题，三人各大约 5 小时，这是论文主表，没有替代。第二，决策分歧裁决 30 到 45 例，大约 2 小时，只有临床医生能判「合理不同」还是「真错」。第三，LLM 裁判校准 30 到 50 题，大约 2 小时；不校准就不能放大，这是省下其余几百题人工的前提。病历字段、指南页码、图谱三元组、分子变异、文献分档、对抗题，全部不占医生时间。\n\n风险四条，务必提出。第一，伦理和脱敏。1000 份病历需要批件；示例病历里就有电话、住址、住院号，脱敏必须先行；金标准和病历不进 git。第二，云端大模型的数据出境。现在用的是 DashScope 上的通义。用真实病历跑评测，等于病历文本出院内网络。这一条大概率要院方批准，否则就得上本地模型。这是方案 B 和方案 C 阶段 2 的硬前提，必须先问清楚。第三，病历噪声。建议当成鲁棒性卖点，不要洗掉。第四，时序：分子证据 agent 如果要并进主问答，建议先把独立客观指标做出来再并。"
  );
}

// ---------------------------------------------------------------------------
// 12 待确认
// ---------------------------------------------------------------------------
{
  const s = pres.addSlide();
  addBg(s);
  addTitle(s, "请导师确认三项：投稿定位、伦理路径、医生协调");
  addLead(
    s,
    "这三项决定主表长什么样、阶段 2 能不能启动，以及要不要追加本地模型工作量。"
  );

  const qs = [
    {
      n: "01",
      t: "投稿定位",
      q: "临床向为主，还是方法向为主？",
      b: "决定主表是病历盲评，还是公开集准确率。方案 C 的阶段 1 对两条路都不浪费；定档只影响阶段 2 的投入和主表写法。",
    },
    {
      n: "02",
      t: "伦理与云端 LLM",
      q: "病历批件如何走？文本能否出网？",
      b: "若不允许调用云端大模型，需追加本地部署工作量。这一条是方案 B / C 阶段 2 的硬前提，不确定则不要启动病历评测。",
    },
    {
      n: "03",
      t: "医生协调",
      q: "能否协调 2–3 位血液科医生？",
      b: "一次性约 5 小时盲评。强调只用在无法自动化的三处；其余由病历自带金标准与脚本承担。可先按 2 人 × 4 小时的最小版谈。",
    },
  ];
  qs.forEach((c, i) => {
    const x = 0.45 + i * 4.2;
    addCard(s, { x, y: 1.36, w: 4.04, h: 5.5, fill: i === 1 ? RED_SOFT : SLATE });
    addBadge(s, x + 0.2, 1.56, c.n, RED, WHITE);
    s.addText(c.t, {
      x: x + 0.66,
      y: 1.56,
      w: 3.18,
      h: 0.34,
      fontFace: FACE,
      fontSize: 16,
      bold: true,
      color: INK,
      margin: 0,
      valign: "middle",
    });
    s.addText(c.q, {
      x: x + 0.2,
      y: 2.14,
      w: 3.64,
      h: 1.15,
      fontFace: FACE,
      fontSize: 18,
      bold: true,
      color: INK,
      margin: 0,
    });
    s.addText(c.b, {
      x: x + 0.2,
      y: 3.4,
      w: 3.64,
      h: 3.2,
      fontFace: FACE,
      fontSize: 14,
      color: MUTED,
      margin: 0,
    });
  });

  addFooter(
    s,
    "小结：评估能否做成，取决于这三项能否定档，而不是取决于还能不能再出题。",
    12
  );
  addNotes(
    s,
    "最后一页只留三件要导师当场拍板的事。\n\n第一，投稿定位。临床向为主还是方法向为主，决定主表是病历盲评还是公开集准确率。如果现在定不下来，就走方案 C：阶段 1 无论投哪里都用得上。\n\n第二，病历的伦理审批路径，以及能不能让病历文本调用云端大模型。如果不能，要追加本地模型部署，而且这是阶段 2 的硬前提。这一条建议作为今天最优先确认的事项。\n\n第三，能不能协调两到三位血液科医生，完成大约 5 小时的一次性盲评。强调医生只用在无法自动化的三处，其余全部由病历自带金标准和脚本承担。如果档期紧，可以先按两人各 4 小时的最小版谈。\n\n结束语用页脚这句：评估能不能做成，取决于这三项能否定档，而不是取决于还能不能再出题。"
  );
}

const out = path.join(__dirname, "..", "DLBCL评估方案.pptx");
pres.writeFile({ fileName: out }).then(() => {
  console.log("wrote", out);
});
