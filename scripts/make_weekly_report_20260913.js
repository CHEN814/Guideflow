/**
 * Weekly report deck: 2026-08-31 — 2026-09-13
 * Run: node scripts/make_weekly_report_20260913.js
 */
const path = require("path");
const pptxgen = require(path.join(__dirname, "..", "docs", "_ppt_build", "node_modules", "pptxgenjs"));

const OUT = path.join(__dirname, "..", "docs", "周报-20260831-20260913.pptx");

const C = {
  ink: "0F172A",
  navy: "0B3D4A",
  teal: "0D7377",
  seafoam: "14919B",
  mint: "0EA5A0",
  paper: "F7F4EE",
  card: "FFFFFF",
  muted: "5B6B73",
  line: "D6E2E0",
  amber: "B45309",
  rust: "9A3412",
  softTeal: "E6F4F3",
  softAmber: "FFF7ED",
  softNavy: "E8EEF0",
  white: "FFFFFF",
};

function sh() {
  return { type: "outer", color: "0F172A", blur: 10, offset: 3, opacity: 0.08 };
}

function footer(s, page, total) {
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 5.4, w: 10, h: 0.225, fill: { color: C.navy },
  });
  s.addText("DLBCL-Evidence  ·  周报  8.31–9.13", {
    x: 0.4, y: 5.4, w: 7.2, h: 0.225,
    fontFace: "Calibri", fontSize: 11, color: "A5D8D5", margin: 0, valign: "middle",
  });
  s.addText(`${page} / ${total}`, {
    x: 8.2, y: 5.4, w: 1.4, h: 0.225,
    fontFace: "Calibri", fontSize: 11, color: "A5D8D5", margin: 0,
    align: "right", valign: "middle",
  });
}

const pres = new pptxgen();
pres.defineLayout({ name: "WIDE16x9", width: 10, height: 5.625 });
pres.layout = "WIDE16x9";
pres.author = "DLBCL-Evidence";
pres.title = "周报 2026-08-31 至 2026-09-13";
pres.subject = "评估方法 · 系统更名 · 分子证据并入问答";

const TOTAL = 6;

// ─── 1 Cover ───────────────────────────────────────────────
{
  const s = pres.addSlide();
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 10, h: 5.625, fill: { color: C.navy },
  });
  s.addShape(pres.shapes.OVAL, {
    x: 7.1, y: -1.3, w: 4.6, h: 4.6,
    fill: { color: C.teal }, transparency: 70,
  });
  s.addShape(pres.shapes.OVAL, {
    x: -1.6, y: 3.2, w: 3.9, h: 3.9,
    fill: { color: C.seafoam }, transparency: 78,
  });
  s.addText("DLBCL-EVIDENCE  ·  工作周报", {
    x: 0.65, y: 1.25, w: 8.6, h: 0.32,
    fontFace: "Arial", fontSize: 13, color: C.mint, margin: 0, charSpacing: 2,
  });
  s.addText("评估能写进论文，\n名字和交互也要对齐。", {
    x: 0.65, y: 1.7, w: 8.4, h: 1.35,
    fontFace: "Arial", fontSize: 30, bold: true, color: C.white, margin: 0,
  });
  s.addText("2026.08.31  —  2026.09.13", {
    x: 0.65, y: 3.2, w: 8, h: 0.32,
    fontFace: "Calibri", fontSize: 16, color: "A5D8D5", margin: 0,
  });
  const tags = [
    { t: "评估方法", x: 0.65 },
    { t: "系统更名", x: 2.55 },
    { t: "分子证据并入 QA", x: 4.45 },
  ];
  tags.forEach((item) => {
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x: item.x, y: 3.75, w: 1.75, h: 0.34,
      fill: { color: C.teal }, rectRadius: 0.08,
    });
    s.addText(item.t, {
      x: item.x, y: 3.75, w: 1.75, h: 0.34,
      fontFace: "Calibri", fontSize: 12, bold: true, color: C.white,
      align: "center", valign: "middle", margin: 0,
    });
  });
}

// ─── 2 Three tracks ────────────────────────────────────────
{
  const s = pres.addSlide();
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 10, h: 5.625, fill: { color: C.paper },
  });
  s.addText("本周三条主线", {
    x: 0.45, y: 0.22, w: 8, h: 0.42,
    fontFace: "Arial", fontSize: 28, bold: true, color: C.ink, margin: 0,
  });
  s.addText("设计为主，代码只动必须统一的名字；分子证据并入问答还停在方案层。", {
    x: 0.45, y: 0.66, w: 9.1, h: 0.28,
    fontFace: "Calibri", fontSize: 13, color: C.muted, margin: 0,
  });

  const cards = [
    {
      x: 0.4, title: "01  评估", tag: C.teal, bg: C.softTeal,
      body: "公开题 + 指南引用 + 病历自建集。赵老师要细节：怎么计分、怎么估 P/R、病历怎么抽。",
    },
    {
      x: 3.55, title: "02  更名", tag: C.navy, bg: C.softNavy,
      body: "对外统一叫 DLBCL-Evidence。仓库、服务器路径、cookie、systemd 先不动，避免现网断登录。",
    },
    {
      x: 6.7, title: "03  交互", tag: C.amber, bg: C.softAmber,
      body: "分子证据按钮应从跳转改成开关。综合答案先拼接、后融合，融合不能改门控原句。",
    },
  ];
  cards.forEach((c) => {
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x: c.x, y: 1.15, w: 2.95, h: 3.95,
      fill: { color: C.card }, rectRadius: 0.1, shadow: sh(),
    });
    s.addShape(pres.shapes.RECTANGLE, {
      x: c.x, y: 1.15, w: 0.12, h: 3.95, fill: { color: c.tag },
    });
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x: c.x + 0.28, y: 1.38, w: 2.4, h: 0.42,
      fill: { color: c.bg }, rectRadius: 0.06,
    });
    s.addText(c.title, {
      x: c.x + 0.28, y: 1.38, w: 2.4, h: 0.42,
      fontFace: "Arial", fontSize: 14, bold: true, color: C.ink,
      align: "center", valign: "middle", margin: 0,
    });
    s.addText(c.body, {
      x: c.x + 0.28, y: 2.05, w: 2.45, h: 2.7,
      fontFace: "Calibri", fontSize: 14, color: C.ink, margin: 0,
    });
  });
  footer(s, 2, TOTAL);
}

// ─── 3 Evaluation ──────────────────────────────────────────
{
  const s = pres.addSlide();
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 10, h: 5.625, fill: { color: C.paper },
  });
  s.addText("评估三部分，各答一个问题", {
    x: 0.45, y: 0.2, w: 9, h: 0.4,
    fontFace: "Arial", fontSize: 26, bold: true, color: C.ink, margin: 0,
  });
  s.addText("图谱与分子模块的评测由同事文档覆盖，这里只写指南问答与病历推理。", {
    x: 0.45, y: 0.62, w: 9.1, h: 0.26,
    fontFace: "Calibri", fontSize: 13, color: C.muted, margin: 0,
  });

  const rows = [
    { n: "1", name: "公开选择题", q: "底座知不知道淋巴瘤？", m: "准确率 + 95% CI", g: "MedQA 官方答案；病种扩到 B-NHL" },
    { n: "2", name: "指南引用", q: "有没有找对、引对？", m: "引用层 P / R / F1", g: "逐题冻结的知识库 ID" },
    { n: "3", name: "病历 benchmark", q: "真实入院记录会不会推理、胡说？", m: "医生量表 → 评分模型", g: "约 20 例 × 10 题，先标 50 题种子" },
  ];
  rows.forEach((r, i) => {
    const y = 1.05 + i * 1.28;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x: 0.4, y, w: 9.2, h: 1.16,
      fill: { color: C.card }, rectRadius: 0.08, shadow: sh(),
    });
    s.addShape(pres.shapes.OVAL, {
      x: 0.58, y: y + 0.32, w: 0.52, h: 0.52,
      fill: { color: C.teal },
    });
    s.addText(r.n, {
      x: 0.58, y: y + 0.32, w: 0.52, h: 0.52,
      fontFace: "Arial", fontSize: 18, bold: true, color: C.white,
      align: "center", valign: "middle", margin: 0,
    });
    s.addText(r.name, {
      x: 1.3, y: y + 0.12, w: 3.4, h: 0.32,
      fontFace: "Arial", fontSize: 16, bold: true, color: C.ink, margin: 0,
    });
    s.addText(r.q, {
      x: 1.3, y: y + 0.44, w: 4.2, h: 0.28,
      fontFace: "Calibri", fontSize: 13, color: C.teal, margin: 0,
    });
    s.addText(r.m, {
      x: 1.3, y: y + 0.74, w: 4.2, h: 0.26,
      fontFace: "Calibri", fontSize: 13, color: C.muted, margin: 0,
    });
    s.addText(r.g, {
      x: 5.7, y: y + 0.28, w: 3.7, h: 0.62,
      fontFace: "Calibri", fontSize: 13, color: C.ink, margin: 0, valign: "middle",
    });
  });
  footer(s, 3, TOTAL);
}

// ─── 4 Teacher notes ───────────────────────────────────────
{
  const s = pres.addSlide();
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 10, h: 5.625, fill: { color: C.paper },
  });
  s.addText("赵老师要的细节，写到可执行", {
    x: 0.45, y: 0.22, w: 9, h: 0.4,
    fontFace: "Arial", fontSize: 26, bold: true, color: C.ink, margin: 0,
  });
  s.addText("原话大意：思路没问题，但太粗。计分、召回/精确率、病历抽题都要落到规程。", {
    x: 0.45, y: 0.64, w: 9.1, h: 0.28,
    fontFace: "Calibri", fontSize: 13, color: C.muted, margin: 0,
  });

  const items = [
    { k: "怎么得分", v: "只看选项。解析「最终答案: X」，对 1 错 0；解析失败也进分母。解释质量不入分。" },
    { k: "怎么估 P/R", v: "对齐知识库 ID。主指标用最终引用集合 C，检索列表只诊断。空引用 Precision=0。负向题改报拒答与幻觉。" },
    { k: "病历怎么抽", v: "分层约 20 例、每例 10 题。医生先打 50 题种子（20 题双标）。评分模型过门槛后再打剩余 150 题。" },
  ];
  items.forEach((it, i) => {
    const y = 1.1 + i * 1.3;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x: 0.4, y, w: 9.2, h: 1.16,
      fill: { color: C.card }, rectRadius: 0.08, shadow: sh(),
    });
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x: 0.58, y: y + 0.34, w: 1.7, h: 0.48,
      fill: { color: C.softTeal }, rectRadius: 0.06,
    });
    s.addText(it.k, {
      x: 0.58, y: y + 0.34, w: 1.7, h: 0.48,
      fontFace: "Arial", fontSize: 13, bold: true, color: C.teal,
      align: "center", valign: "middle", margin: 0,
    });
    s.addText(it.v, {
      x: 2.5, y: y + 0.22, w: 6.85, h: 0.74,
      fontFace: "Calibri", fontSize: 14, color: C.ink, margin: 0, valign: "middle",
    });
  });
  footer(s, 4, TOTAL);
}

// ─── 5 Molecular into QA ───────────────────────────────────
{
  const s = pres.addSlide();
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 10, h: 5.625, fill: { color: C.paper },
  });
  s.addText("分子证据：从跳转页变成问答能力", {
    x: 0.45, y: 0.2, w: 9.2, h: 0.4,
    fontFace: "Arial", fontSize: 24, bold: true, color: C.ink, margin: 0,
  });

  s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: 0.4, y: 0.78, w: 4.5, h: 4.35,
    fill: { color: C.card }, rectRadius: 0.1, shadow: sh(),
  });
  s.addText("现在为什么合不进去", {
    x: 0.62, y: 0.96, w: 4.1, h: 0.32,
    fontFace: "Arial", fontSize: 15, bold: true, color: C.ink, margin: 0,
  });
  const left = [
    "按钮是链接，不是开关",
    "QA 走 SSE，分子证据是同步整包 JSON",
    "输入一个是自然语言，一个是变异文本 / OCR",
    "分子链路不调 LLM，模板成文 + 安全门控",
    "不是多 agent：一个智能体 + 一条工具链",
  ];
  left.forEach((t, i) => {
    const y = 1.42 + i * 0.68;
    s.addShape(pres.shapes.OVAL, {
      x: 0.68, y: y + 0.06, w: 0.18, h: 0.18, fill: { color: C.amber },
    });
    s.addText(t, {
      x: 1.02, y: y, w: 3.65, h: 0.58,
      fontFace: "Calibri", fontSize: 13, color: C.ink, margin: 0,
    });
  });

  s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: 5.1, y: 0.78, w: 4.5, h: 4.35,
    fill: { color: C.card }, rectRadius: 0.1, shadow: sh(),
  });
  s.addText("综合答案怎么做", {
    x: 5.32, y: 0.96, w: 4.1, h: 0.32,
    fontFace: "Arial", fontSize: 15, bold: true, color: C.ink, margin: 0,
  });
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: 5.32, y: 1.42, w: 4.06, h: 1.55,
    fill: { color: C.softTeal }, rectRadius: 0.08,
  });
  s.addText("先拼接（建议本轮）", {
    x: 5.48, y: 1.52, w: 3.75, h: 0.3,
    fontFace: "Arial", fontSize: 14, bold: true, color: C.teal, margin: 0,
  });
  s.addText("同一条消息里分区放指南回答和分子报告。门控原句不动，引用体系并列。", {
    x: 5.48, y: 1.86, w: 3.75, h: 0.95,
    fontFace: "Calibri", fontSize: 13, color: C.ink, margin: 0,
  });
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: 5.32, y: 3.12, w: 4.06, h: 1.7,
    fill: { color: C.softAmber }, rectRadius: 0.08,
  });
  s.addText("后融合（有风险）", {
    x: 5.48, y: 3.24, w: 3.75, h: 0.3,
    fontFace: "Arial", fontSize: 14, bold: true, color: C.rust, margin: 0,
  });
  s.addText("让 LLM 写成一段话更像问诊，但可能改掉安全措辞。若做，门控句必须原样保留。", {
    x: 5.48, y: 3.58, w: 3.75, h: 1.08,
    fontFace: "Calibri", fontSize: 13, color: C.ink, margin: 0,
  });
  footer(s, 5, TOTAL);
}

// ─── 6 Next ────────────────────────────────────────────────
{
  const s = pres.addSlide();
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 10, h: 5.625, fill: { color: C.paper },
  });
  s.addText("已对齐的名字，和下一步", {
    x: 0.45, y: 0.2, w: 9, h: 0.4,
    fontFace: "Arial", fontSize: 26, bold: true, color: C.ink, margin: 0,
  });

  s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: 0.4, y: 0.78, w: 4.5, h: 2.15,
    fill: { color: C.card }, rectRadius: 0.1, shadow: sh(),
  });
  s.addText("对外已改", {
    x: 0.62, y: 0.94, w: 4.1, h: 0.3,
    fontFace: "Arial", fontSize: 14, bold: true, color: C.teal, margin: 0,
  });
  s.addText("界面品牌、页面标题、README、评估方案、API 名称：Guideflow → DLBCL-Evidence。", {
    x: 0.62, y: 1.32, w: 4.05, h: 1.35,
    fontFace: "Calibri", fontSize: 14, color: C.ink, margin: 0,
  });

  s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: 5.1, y: 0.78, w: 4.5, h: 2.15,
    fill: { color: C.card }, rectRadius: 0.1, shadow: sh(),
  });
  s.addText("基础设施先不动", {
    x: 5.32, y: 0.94, w: 4.1, h: 0.3,
    fontFace: "Arial", fontSize: 14, bold: true, color: C.amber, margin: 0,
  });
  s.addText("GitHub 仍是 CHEN814/Guideflow。/opt/guideflow、systemd、登录 cookie 保持原名，避免现网掉线。", {
    x: 5.32, y: 1.32, w: 4.05, h: 1.35,
    fontFace: "Calibri", fontSize: 14, color: C.ink, margin: 0,
  });

  const next = [
    { n: "1", t: "按评估方案推进 Part 1 / 2：冻结批次，把记录表填起来" },
    { n: "2", t: "分子证据按钮改开关，问答页先做分区拼接" },
    { n: "3", t: "和同事对齐图谱 / 分子评测接口，三部分指标不要互相打架" },
    { n: "4", t: "老师认可细节后，启动 Part 3 的两例试出题" },
  ];
  next.forEach((it, i) => {
    const x = 0.4 + (i % 2) * 4.7;
    const y = 3.12 + Math.floor(i / 2) * 1.0;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x, y, w: 4.5, h: 0.88,
      fill: { color: C.card }, rectRadius: 0.08, shadow: sh(),
    });
    s.addShape(pres.shapes.OVAL, {
      x: x + 0.16, y: y + 0.22, w: 0.42, h: 0.42, fill: { color: C.navy },
    });
    s.addText(it.n, {
      x: x + 0.16, y: y + 0.22, w: 0.42, h: 0.42,
      fontFace: "Arial", fontSize: 14, bold: true, color: C.white,
      align: "center", valign: "middle", margin: 0,
    });
    s.addText(it.t, {
      x: x + 0.7, y: y + 0.14, w: 3.6, h: 0.6,
      fontFace: "Calibri", fontSize: 13, color: C.ink, margin: 0, valign: "middle",
    });
  });
  footer(s, 6, TOTAL);
}

pres.writeFile({ fileName: OUT }).then(() => {
  console.log("wrote", OUT);
});
