const pptxgen = require("pptxgenjs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const OUT = path.join(ROOT, "docs", "本周进展-CSCO与EHA数据源.pptx");
const IMG_CSCO = path.join(ROOT, "docs", "assets", "CSCO.png");
const IMG_EHA = path.join(ROOT, "docs", "assets", "EHA.png");
const IMG_CASE = path.join(ROOT, "docs", "assets", "病历分析.png");
const IMG_FEEDBACK = path.join(ROOT, "docs", "assets", "feedback.png");

// Palette — clinical teal / navy (not generic purple)
const C = {
  ink: "0F172A",
  navy: "0B3D4A",
  teal: "0D7377",
  seafoam: "14919B",
  mint: "0EA5A0",
  csco: "0F766E",
  eha: "2563EB",
  case: "C2410C",
  feedback: "B45309",
  soft: "F0FDFA",
  softBlue: "EFF6FF",
  softOrange: "FFF7ED",
  softGray: "F8FAFC",
  white: "FFFFFF",
  muted: "64748B",
  line: "E2E8F0",
  accent: "F59E0B",
};

const pres = new pptxgen();
pres.defineLayout({ name: "WIDE16x9", width: 10, height: 5.625 });
pres.layout = "WIDE16x9";
pres.author = "Guideflow";
pres.title = "本周进展：多源指南与临床工作流";

function shadowSoft() {
  return { type: "outer", color: "0F172A", blur: 12, offset: 3, opacity: 0.08 };
}

function addFeatureDemoSlide({
  title,
  badge,
  badgeColor,
  subtitle,
  imagePath,
  imageRatio,
  points,
  pointColor,
}) {
  const s = pres.addSlide();
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 10, h: 5.625, fill: { color: C.softGray },
  });
  s.addText(title, {
    x: 0.45, y: 0.28, w: 6.5, h: 0.4,
    fontFace: "Arial", fontSize: 26, bold: true, color: C.ink, margin: 0,
  });
  const badgeW = Math.max(1.1, badge.length * 0.28 + 0.35);
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: 9.1 - badgeW, y: 0.32, w: badgeW, h: 0.32,
    fill: { color: badgeColor }, rectRadius: 0.08,
  });
  s.addText(badge, {
    x: 9.1 - badgeW, y: 0.32, w: badgeW, h: 0.32,
    fontFace: "Arial", fontSize: 12, bold: true, color: C.white,
    align: "center", valign: "middle", margin: 0,
  });
  s.addText(subtitle, {
    x: 0.45, y: 0.72, w: 9.1, h: 0.3,
    fontFace: "Calibri", fontSize: 14, color: C.muted, margin: 0,
  });

  // screenshot panel — keep native aspect
  const imgW = 5.35;
  const imgH = imgW / imageRatio;
  const panelX = 4.35;
  const panelY = 1.15;
  const pad = 0.12;
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: panelX, y: panelY, w: imgW + pad * 2, h: Math.min(imgH + pad * 2, 4.15),
    fill: { color: C.white },
    rectRadius: 0.1,
    shadow: shadowSoft(),
  });
  s.addImage({
    path: imagePath,
    x: panelX + pad,
    y: panelY + pad,
    w: imgW,
    h: Math.min(imgH, 3.9),
  });

  points.forEach((p, i) => {
    const y = 1.25 + i * 0.95;
    s.addShape(pres.shapes.OVAL, {
      x: 0.5, y: y + 0.05, w: 0.28, h: 0.28,
      fill: { color: pointColor },
    });
    s.addText(String(i + 1), {
      x: 0.5, y: y + 0.05, w: 0.28, h: 0.28,
      fontFace: "Arial", fontSize: 11, bold: true, color: C.white,
      align: "center", valign: "middle", margin: 0,
    });
    s.addText(p.t, {
      x: 0.95, y: y, w: 3.1, h: 0.3,
      fontFace: "Arial", fontSize: 14, bold: true, color: C.ink, margin: 0,
    });
    s.addText(p.d, {
      x: 0.95, y: y + 0.32, w: 3.1, h: 0.5,
      fontFace: "Calibri", fontSize: 12, color: C.muted, margin: 0,
    });
  });
}

// ─── Slide 1: Title ───────────────────────────────────────────
{
  const s = pres.addSlide();
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 10, h: 5.625, fill: { color: C.navy },
  });
  s.addShape(pres.shapes.OVAL, {
    x: 7.2, y: -1.2, w: 4.5, h: 4.5,
    fill: { color: C.teal }, transparency: 72,
  });
  s.addShape(pres.shapes.OVAL, {
    x: -1.4, y: 3.4, w: 3.8, h: 3.8,
    fill: { color: C.seafoam }, transparency: 78,
  });

  s.addText("GUIDEFLOW · 本周进展", {
    x: 0.7, y: 1.2, w: 8.5, h: 0.35,
    fontFace: "Arial", fontSize: 13, color: C.mint,
    margin: 0, charSpacing: 3,
  });
  s.addText("多源指南 + 临床工作流", {
    x: 0.7, y: 1.7, w: 8.5, h: 0.7,
    fontFace: "Arial", fontSize: 34, bold: true, color: C.white, margin: 0,
  });
  s.addText("CSCO / EHA 数据源 · 病历分析入口 · 医生反馈", {
    x: 0.7, y: 2.55, w: 8.5, h: 0.4,
    fontFace: "Calibri", fontSize: 18, color: "A5D8D5", margin: 0,
  });
  s.addText("证据约束问答，走向可落地的临床辅助闭环", {
    x: 0.7, y: 3.2, w: 8, h: 0.35,
    fontFace: "Calibri", fontSize: 15, color: "7AB8B4", margin: 0,
  });
  s.addText("淋巴瘤指南 RAG Agent", {
    x: 0.7, y: 4.85, w: 5, h: 0.3,
    fontFace: "Calibri", fontSize: 12, color: "7AB8B4", margin: 0,
  });
}

// ─── Slide 2: Overview ────────────────────────────────────────
{
  const s = pres.addSlide();
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 10, h: 5.625, fill: { color: C.white },
  });
  s.addText("本周做了什么", {
    x: 0.5, y: 0.28, w: 9, h: 0.4,
    fontFace: "Arial", fontSize: 30, bold: true, color: C.ink, margin: 0,
  });
  s.addText("指南底座扩展 + 两条临床侧能力落地（最新 PR）", {
    x: 0.5, y: 0.72, w: 9, h: 0.3,
    fontFace: "Calibri", fontSize: 14, color: C.muted, margin: 0,
  });

  const cards = [
    {
      x: 0.45, y: 1.2,
      title: "CSCO",
      sub: "国内指南源",
      body: "2025 淋巴瘤诊疗指南\nOCR → 知识库 + BM25\n推荐级别可溯源",
      bg: C.soft,
      tag: C.csco,
    },
    {
      x: 5.15, y: 1.2,
      title: "EHA",
      sub: "国际指南源",
      body: "2025 大 B 细胞淋巴瘤指南\n论文型解析 + 表 VLM\n章节标签约束回答",
      bg: C.softBlue,
      tag: C.eha,
    },
    {
      x: 0.45, y: 3.35,
      title: "病历分析",
      sub: "临床入口",
      body: "输入栏一键打开弹窗\n粘贴病历 → 结构化 → 指南问答\n可选指南来源",
      bg: C.softOrange,
      tag: C.case,
    },
    {
      x: 5.15, y: 3.35,
      title: "医生反馈",
      sub: "质量闭环",
      body: "评分 + 分类 + 意见落库\n自动归类标签\n后台可统计与回看",
      bg: "FEF3C7",
      tag: C.feedback,
    },
  ];

  for (const c of cards) {
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x: c.x, y: c.y, w: 4.4, h: 1.95,
      fill: { color: c.bg },
      rectRadius: 0.12,
      shadow: shadowSoft(),
    });
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x: c.x + 0.2, y: c.y + 0.2, w: 1.25, h: 0.34,
      fill: { color: c.tag },
      rectRadius: 0.08,
    });
    s.addText(c.title, {
      x: c.x + 0.2, y: c.y + 0.2, w: 1.25, h: 0.34,
      fontFace: "Arial", fontSize: 12, bold: true, color: C.white,
      align: "center", valign: "middle", margin: 0,
    });
    s.addText(c.sub, {
      x: c.x + 1.6, y: c.y + 0.22, w: 2.5, h: 0.3,
      fontFace: "Calibri", fontSize: 13, color: C.muted, margin: 0, valign: "middle",
    });
    s.addText(c.body, {
      x: c.x + 0.2, y: c.y + 0.7, w: 4.0, h: 1.1,
      fontFace: "Calibri", fontSize: 13, color: C.ink, margin: 0,
      lineSpacing: 20,
    });
  }
}

// ─── Slide 3: CSCO demo ───────────────────────────────────────
{
  const s = pres.addSlide();
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 10, h: 5.625, fill: { color: C.softGray },
  });
  s.addText("功能一 · CSCO 指南", {
    x: 0.5, y: 0.28, w: 5.5, h: 0.4,
    fontFace: "Arial", fontSize: 26, bold: true, color: C.ink, margin: 0,
  });
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: 8.2, y: 0.32, w: 0.95, h: 0.32,
    fill: { color: C.csco }, rectRadius: 0.08,
  });
  s.addText("CSCO", {
    x: 8.2, y: 0.32, w: 0.95, h: 0.32,
    fontFace: "Arial", fontSize: 12, bold: true, color: C.white,
    align: "center", valign: "middle", margin: 0,
  });
  s.addText("国内循证路径可问、可溯 · 推荐级别与正文引用随回答呈现", {
    x: 0.5, y: 0.72, w: 9, h: 0.3,
    fontFace: "Calibri", fontSize: 14, color: C.muted, margin: 0,
  });

  s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: 0.5, y: 1.15, w: 9.0, h: 2.55,
    fill: { color: C.white },
    rectRadius: 0.1,
    shadow: shadowSoft(),
  });
  s.addImage({
    path: IMG_CSCO,
    x: 0.65, y: 1.28, w: 8.7, h: 2.29,
  });

  const points = [
    { t: "独立知识库", d: "OCR PDF → 结构化块 + BM25" },
    { t: "推荐级别", d: "I / II 级与 1A、2A 随文" },
    { t: "正文引用", d: "徽章回看指南原文" },
    { t: "精简 Agent", d: "仅检索 + 直答，无运行时 VLM" },
  ];
  points.forEach((p, i) => {
    const x = 0.5 + i * 2.35;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x: x, y: 3.95, w: 2.2, h: 1.3,
      fill: { color: C.white },
      rectRadius: 0.1,
      shadow: shadowSoft(),
    });
    s.addShape(pres.shapes.OVAL, {
      x: x + 0.15, y: 4.15, w: 0.28, h: 0.28,
      fill: { color: C.csco },
    });
    s.addText(String(i + 1), {
      x: x + 0.15, y: 4.15, w: 0.28, h: 0.28,
      fontFace: "Arial", fontSize: 11, bold: true, color: C.white,
      align: "center", valign: "middle", margin: 0,
    });
    s.addText(p.t, {
      x: x + 0.15, y: 4.55, w: 1.9, h: 0.28,
      fontFace: "Arial", fontSize: 13, bold: true, color: C.ink, margin: 0,
    });
    s.addText(p.d, {
      x: x + 0.15, y: 4.85, w: 1.9, h: 0.3,
      fontFace: "Calibri", fontSize: 11, color: C.muted, margin: 0,
    });
  });
}

// ─── Slide 4: EHA demo ────────────────────────────────────────
{
  const s = pres.addSlide();
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 10, h: 5.625, fill: { color: C.softGray },
  });
  s.addText("功能二 · EHA 指南", {
    x: 0.5, y: 0.28, w: 5.5, h: 0.4,
    fontFace: "Arial", fontSize: 26, bold: true, color: C.ink, margin: 0,
  });
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: 8.35, y: 0.32, w: 0.85, h: 0.32,
    fill: { color: C.eha }, rectRadius: 0.08,
  });
  s.addText("EHA", {
    x: 8.35, y: 0.32, w: 0.85, h: 0.32,
    fontFace: "Arial", fontSize: 12, bold: true, color: C.white,
    align: "center", valign: "middle", margin: 0,
  });
  s.addText("国际 LBCL 实践指南补齐分子与病理证据面 · 章节标签可溯", {
    x: 0.5, y: 0.72, w: 9, h: 0.3,
    fontFace: "Calibri", fontSize: 14, color: C.muted, margin: 0,
  });

  s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: 0.5, y: 1.15, w: 9.0, h: 2.55,
    fill: { color: C.white },
    rectRadius: 0.1,
    shadow: shadowSoft(),
  });
  s.addImage({
    path: IMG_EHA,
    x: 0.65, y: 1.28, w: 8.7, h: 2.29,
  });

  const points = [
    { t: "论文型解析", d: "章节切块，专攻 LBCL" },
    { t: "构建期表 VLM", d: "表格入库前转 Markdown" },
    { t: "章节标签", d: "Diagnosis 等主题标注" },
    { t: "同构体验", d: "独立索引，下拉切源" },
  ];
  points.forEach((p, i) => {
    const x = 0.5 + i * 2.35;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x: x, y: 3.95, w: 2.2, h: 1.3,
      fill: { color: C.white },
      rectRadius: 0.1,
      shadow: shadowSoft(),
    });
    s.addShape(pres.shapes.OVAL, {
      x: x + 0.15, y: 4.15, w: 0.28, h: 0.28,
      fill: { color: C.eha },
    });
    s.addText(String(i + 1), {
      x: x + 0.15, y: 4.15, w: 0.28, h: 0.28,
      fontFace: "Arial", fontSize: 11, bold: true, color: C.white,
      align: "center", valign: "middle", margin: 0,
    });
    s.addText(p.t, {
      x: x + 0.15, y: 4.55, w: 1.9, h: 0.28,
      fontFace: "Arial", fontSize: 13, bold: true, color: C.ink, margin: 0,
    });
    s.addText(p.d, {
      x: x + 0.15, y: 4.85, w: 1.9, h: 0.3,
      fontFace: "Calibri", fontSize: 11, color: C.muted, margin: 0,
    });
  });
}

// ─── Slide 5: Case analysis ───────────────────────────────────
addFeatureDemoSlide({
  title: "功能三 · 病历分析入口",
  badge: "病例分析",
  badgeColor: C.case,
  subtitle: "输入栏右侧入口 → 弹窗粘贴病历 → 结构化摘要后走指南问答",
  imagePath: IMG_CASE,
  imageRatio: 1369 / 861,
  pointColor: C.case,
  points: [
    { t: "一键入口", d: "主输入栏「病例分析」按钮，随时切入病历场景" },
    { t: "结构化抽取", d: "CaseExtractor 解析入路 / 病理 / 治疗等文本" },
    { t: "指南联动", d: "弹窗内可选指南来源，结合证据给路径建议" },
    { t: "缺失显式标注", d: "病历不全时要求标明不确定项，避免编造" },
  ],
});

// ─── Slide 6: Doctor feedback ─────────────────────────────────
addFeatureDemoSlide({
  title: "功能四 · 医生反馈",
  badge: "医生反馈",
  badgeColor: C.feedback,
  subtitle: "对 AI 回答评分、分类、写意见 · 落库后可统计回看",
  imagePath: IMG_FEEDBACK,
  imageRatio: 1293 / 751,
  pointColor: C.feedback,
  points: [
    { t: "回答旁提交", d: "带上问题与回答摘要，减少医生填写成本" },
    { t: "五级评分", d: "1–5 分 + 反馈分类（如证据不足 / 其他）" },
    { t: "自动归类", d: "规则分类器打标签，辅助后续质检" },
    { t: "后台闭环", d: "反馈列表与统计，支撑持续改进" },
  ],
});

// ─── Slide 7: Architecture comparison ─────────────────────────
{
  const s = pres.addSlide();
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 10, h: 5.625, fill: { color: C.white },
  });
  s.addText("三源能力对照", {
    x: 0.55, y: 0.32, w: 9, h: 0.45,
    fontFace: "Arial", fontSize: 30, bold: true, color: C.ink, margin: 0,
  });
  s.addText("同一套问答框架，按源裁剪工具与解析策略", {
    x: 0.55, y: 0.8, w: 9, h: 0.3,
    fontFace: "Calibri", fontSize: 14, color: C.muted, margin: 0,
  });

  const colX = [0.55, 2.55, 5.0, 7.45];
  const colW = [1.9, 2.3, 2.3, 2.05];
  const headers = ["能力", "NCCN", "CSCO（新）", "EHA（新）"];
  const headerColors = [C.navy, C.navy, C.csco, C.eha];

  s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: 0.55, y: 1.3, w: 8.95, h: 0.5,
    fill: { color: C.softGray }, rectRadius: 0.08,
  });
  headers.forEach((h, i) => {
    s.addText(h, {
      x: colX[i], y: 1.35, w: colW[i], h: 0.4,
      fontFace: "Arial", fontSize: 13, bold: true, color: headerColors[i],
      align: i === 0 ? "left" : "center", valign: "middle", margin: 0,
    });
  });

  const rows = [
    ["PDF 解析", "流程图导向", "OCR + 表抽取", "论文型 + 表 VLM"],
    ["表格策略", "运行时读图", "预抽 Markdown", "构建期落库"],
    ["Agent 工具", "检索 / 图谱 / 读页", "检索 + 直答", "检索 + 直答"],
    ["知识图谱", "默认开启", "关闭", "关闭"],
    ["使用方式", "下拉选源", "下拉选源", "下拉选源"],
  ];

  rows.forEach((row, ri) => {
    const y = 1.95 + ri * 0.6;
    if (ri % 2 === 0) {
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
        x: 0.55, y: y - 0.05, w: 8.95, h: 0.55,
        fill: { color: "F8FAFC" }, rectRadius: 0.06,
      });
    }
    row.forEach((cell, ci) => {
      s.addText(cell, {
        x: colX[ci], y: y, w: colW[ci], h: 0.45,
        fontFace: "Calibri",
        fontSize: 13,
        bold: ci === 0,
        color: ci === 0 ? C.ink : C.muted,
        align: ci === 0 ? "left" : "center",
        valign: "middle",
        margin: 0,
      });
    });
  });
}

// ─── Slide 8: Pipeline ────────────────────────────────────────
{
  const s = pres.addSlide();
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 10, h: 5.625, fill: { color: C.white },
  });
  s.addText("端到端链路", {
    x: 0.55, y: 0.28, w: 9, h: 0.4,
    fontFace: "Arial", fontSize: 28, bold: true, color: C.ink, margin: 0,
  });
  s.addText("指南问答主链路 + 病历分析 / 医生反馈两条旁路", {
    x: 0.55, y: 0.7, w: 9, h: 0.28,
    fontFace: "Calibri", fontSize: 14, color: C.muted, margin: 0,
  });

  const steps = [
    { n: "01", t: "选源", d: "下拉选\nNCCN/CSCO/EHA" },
    { n: "02", t: "问答 / 病历", d: "普通提问\n或病例分析" },
    { n: "03", t: "检索生成", d: "BM25 + Agent\n证据门控" },
    { n: "04", t: "约束回答", d: "角标 + 引用\n可回看原文" },
    { n: "05", t: "医生反馈", d: "评分分类\n落库统计" },
  ];

  steps.forEach((st, i) => {
    const x = 0.45 + i * 1.9;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x: x, y: 1.2, w: 1.7, h: 2.35,
      fill: { color: i === 4 ? C.softOrange : i % 2 === 0 ? C.soft : C.softBlue },
      rectRadius: 0.12,
      shadow: shadowSoft(),
    });
    s.addText(st.n, {
      x: x + 0.15, y: 1.4, w: 1.4, h: 0.35,
      fontFace: "Arial", fontSize: 20, bold: true, color: C.teal, margin: 0,
    });
    s.addText(st.t, {
      x: x + 0.15, y: 1.9, w: 1.4, h: 0.35,
      fontFace: "Arial", fontSize: 15, bold: true, color: C.ink, margin: 0,
    });
    s.addText(st.d, {
      x: x + 0.15, y: 2.4, w: 1.4, h: 0.85,
      fontFace: "Calibri", fontSize: 12, color: C.muted, margin: 0,
      lineSpacing: 18,
    });
    if (i < steps.length - 1) {
      s.addText("→", {
        x: x + 1.55, y: 2.15, w: 0.35, h: 0.35,
        fontFace: "Arial", fontSize: 18, color: C.teal,
        align: "center", margin: 0,
      });
    }
  });

  // two callouts
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: 0.45, y: 3.85, w: 4.4, h: 1.3,
    fill: { color: C.softOrange }, rectRadius: 0.1,
  });
  s.addText("病历分析旁路", {
    x: 0.7, y: 4.05, w: 3.9, h: 0.3,
    fontFace: "Arial", fontSize: 14, bold: true, color: C.case, margin: 0,
  });
  s.addText("粘贴病历 → 结构化摘要 → 增强提问 → 走同一套指南问答", {
    x: 0.7, y: 4.4, w: 3.9, h: 0.55,
    fontFace: "Calibri", fontSize: 13, color: C.ink, margin: 0,
  });

  s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: 5.15, y: 3.85, w: 4.4, h: 1.3,
    fill: { color: "FEF3C7" }, rectRadius: 0.1,
  });
  s.addText("反馈闭环", {
    x: 5.4, y: 4.05, w: 3.9, h: 0.3,
    fontFace: "Arial", fontSize: 14, bold: true, color: C.feedback, margin: 0,
  });
  s.addText("回答可提交评分与意见，自动打标签，支撑质检与迭代", {
    x: 5.4, y: 4.4, w: 3.9, h: 0.55,
    fontFace: "Calibri", fontSize: 13, color: C.ink, margin: 0,
  });
}

// ─── Slide 9: Closing ─────────────────────────────────────────
{
  const s = pres.addSlide();
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 10, h: 5.625, fill: { color: C.navy },
  });
  s.addShape(pres.shapes.OVAL, {
    x: 7.8, y: -0.8, w: 3.5, h: 3.5,
    fill: { color: C.teal }, transparency: 70,
  });
  s.addShape(pres.shapes.OVAL, {
    x: -1.2, y: 3.6, w: 3.2, h: 3.2,
    fill: { color: C.seafoam }, transparency: 75,
  });

  s.addText("小结", {
    x: 0.7, y: 0.85, w: 8.5, h: 0.35,
    fontFace: "Arial", fontSize: 15, color: C.mint, margin: 0, charSpacing: 2,
  });
  s.addText("本周交付：四条能力落地", {
    x: 0.7, y: 1.3, w: 8.5, h: 0.5,
    fontFace: "Arial", fontSize: 28, bold: true, color: C.white, margin: 0,
  });

  const takeaways = [
    { tag: "CSCO", color: C.csco, desc: "国内诊疗推荐进入可检索、可引用的问答" },
    { tag: "EHA", color: C.eha, desc: "国际 LBCL 实践指南补齐分子与病理证据面" },
    { tag: "病历", color: C.case, desc: "输入栏入口 → 结构化病例 → 指南联动分析" },
    { tag: "反馈", color: C.feedback, desc: "评分分类落库，形成质量闭环" },
  ];
  takeaways.forEach((t, i) => {
    const y = 2.05 + i * 0.7;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x: 0.7, y: y, w: 1.1, h: 0.42,
      fill: { color: t.color },
      rectRadius: 0.08,
    });
    s.addText(t.tag, {
      x: 0.7, y: y, w: 1.1, h: 0.42,
      fontFace: "Arial", fontSize: 13, bold: true, color: C.white,
      align: "center", valign: "middle", margin: 0,
    });
    s.addText(t.desc, {
      x: 2.05, y: y, w: 7, h: 0.42,
      fontFace: "Calibri", fontSize: 16, color: "D1FAE5",
      valign: "middle", margin: 0,
    });
  });
}

pres.writeFile({ fileName: OUT }).then(() => {
  console.log("Wrote", OUT);
}).catch((err) => {
  console.error(err);
  process.exit(1);
});
