/**
 * Build a single-slide Guideflow product intro deck.
 * Run: node scripts/build_product_intro_pptx.js
 */
const path = require("path");
const pptxgen = require("pptxgenjs");

const ROOT = path.resolve(__dirname, "..");
const OUT = path.join(ROOT, "docs", "Guideflow产品介绍.pptx");
const SCREENSHOT = path.join(ROOT, "docs", "assets", "main.png");

const C = {
  teal: "028090",
  ink: "1A2B2E",
  muted: "4A5C5F",
  soft: "E8F4F3",
  softCard: "F3FAF9",
  white: "FFFFFF",
  faint: "7A8A8C",
};

async function main() {
  const pres = new pptxgen();
  pres.layout = "LAYOUT_16x9";
  pres.author = "Guideflow";
  pres.title = "Guideflow 产品介绍";

  const s = pres.addSlide();
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0,
    y: 0,
    w: 10,
    h: 5.625,
    fill: { color: C.white },
    line: { color: C.white },
  });

  // Header band
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: 0.4,
    y: 0.22,
    w: 9.2,
    h: 0.95,
    fill: { color: C.soft },
    rectRadius: 0.1,
    line: { color: C.soft },
  });

  s.addText("Guideflow", {
    x: 0.55,
    y: 0.3,
    w: 3.2,
    h: 0.42,
    fontFace: "Cambria",
    fontSize: 32,
    bold: true,
    color: C.teal,
    margin: 0,
  });

  s.addText("面向弥漫大 B 细胞淋巴瘤（DLBCL）的指南证据问答", {
    x: 3.7,
    y: 0.34,
    w: 5.7,
    h: 0.34,
    fontFace: "Calibri",
    fontSize: 14,
    bold: true,
    color: C.ink,
    valign: "middle",
    margin: 0,
  });

  s.addText("问一句临床问题，从权威指南里拿到可核对的答案", {
    x: 0.55,
    y: 0.78,
    w: 8.8,
    h: 0.28,
    fontFace: "Calibri",
    fontSize: 13,
    color: C.muted,
    margin: 0,
  });

  // Screenshot panel (landscape 2238×1146, keep aspect)
  const imgDispW = 3.95;
  const imgDispH = imgDispW * (1146 / 2238);
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: 5.35,
    y: 1.35,
    w: 4.25,
    h: imgDispH + 0.48,
    fill: { color: C.soft },
    rectRadius: 0.1,
    line: { color: C.soft },
  });

  s.addImage({
    path: SCREENSHOT,
    x: 5.5,
    y: 1.48,
    w: imgDispW,
    h: imgDispH,
  });

  s.addText("产品界面一览", {
    x: 5.5,
    y: 1.52 + imgDispH,
    w: 3.95,
    h: 0.22,
    fontFace: "Calibri",
    fontSize: 11,
    color: C.muted,
    align: "center",
    margin: 0,
  });

  // How it works
  s.addText("如何使用", {
    x: 0.5,
    y: 1.35,
    w: 2.2,
    h: 0.28,
    fontFace: "Calibri",
    fontSize: 13,
    bold: true,
    color: C.teal,
    margin: 0,
  });

  const steps = [
    { n: "1", title: "选指南", desc: "选择 NCCN / CSCO / EHA" },
    { n: "2", title: "提问", desc: "自然语言问治疗、分期、随访" },
    { n: "3", title: "核验", desc: "阅读带引用回答，点开出处核对" },
  ];

  steps.forEach((step, i) => {
    const y = 1.72 + i * 0.68;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x: 0.5,
      y,
      w: 4.6,
      h: 0.58,
      fill: { color: C.softCard },
      rectRadius: 0.08,
      shadow: {
        type: "outer",
        color: "1A2B2E",
        blur: 5,
        offset: 1,
        opacity: 0.07,
      },
    });
    s.addShape(pres.shapes.OVAL, {
      x: 0.65,
      y: y + 0.13,
      w: 0.32,
      h: 0.32,
      fill: { color: C.teal },
      line: { color: C.teal },
    });
    s.addText(step.n, {
      x: 0.65,
      y: y + 0.13,
      w: 0.32,
      h: 0.32,
      fontFace: "Calibri",
      fontSize: 13,
      bold: true,
      color: C.white,
      align: "center",
      valign: "middle",
      margin: 0,
    });
    s.addText(step.title, {
      x: 1.12,
      y: y + 0.06,
      w: 3.7,
      h: 0.26,
      fontFace: "Calibri",
      fontSize: 14,
      bold: true,
      color: C.ink,
      margin: 0,
    });
    s.addText(step.desc, {
      x: 1.12,
      y: y + 0.3,
      w: 3.7,
      h: 0.22,
      fontFace: "Calibri",
      fontSize: 12,
      color: C.muted,
      margin: 0,
    });
  });

  // Benefits
  s.addText("对医生的帮助", {
    x: 0.5,
    y: 3.95,
    w: 2.5,
    h: 0.26,
    fontFace: "Calibri",
    fontSize: 13,
    bold: true,
    color: C.teal,
    margin: 0,
  });

  const benefits = [
    { title: "快查", body: "不必整本翻 PDF，秒级定位「指南怎么写」" },
    { title: "可核", body: "答案带页码 / 章节出处，查房可当场核对" },
    { title: "路径清", body: "关键问题可对照决策流程图，不只是段落摘要" },
  ];

  benefits.forEach((b, i) => {
    const bx = 0.5 + i * 3.1;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x: bx,
      y: 4.28,
      w: 2.95,
      h: 0.78,
      fill: { color: C.softCard },
      rectRadius: 0.1,
      shadow: {
        type: "outer",
        color: "1A2B2E",
        blur: 5,
        offset: 1,
        opacity: 0.07,
      },
    });
    s.addText(b.title, {
      x: bx + 0.15,
      y: 4.34,
      w: 2.65,
      h: 0.24,
      fontFace: "Calibri",
      fontSize: 14,
      bold: true,
      color: C.teal,
      margin: 0,
    });
    s.addText(b.body, {
      x: bx + 0.15,
      y: 4.58,
      w: 2.65,
      h: 0.4,
      fontFace: "Calibri",
      fontSize: 12,
      color: C.muted,
      margin: 0,
    });
  });

  s.addText("仅供指南证据检索辅助，不替代临床判断", {
    x: 0.5,
    y: 5.28,
    w: 9.1,
    h: 0.22,
    fontFace: "Calibri",
    fontSize: 10,
    color: C.faint,
    margin: 0,
  });

  await pres.writeFile({ fileName: OUT });
  console.log("Wrote", OUT);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
