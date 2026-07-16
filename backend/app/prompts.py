"""Centralized LLM / VLM prompt templates and builders."""
from __future__ import annotations

from typing import List

from backend.app.models import EvidenceBundle, RetrievalHit


SYSTEM_PROMPT = """你是 DLBCL 专病 NCCN 指南问答助手。

证据约束：
1. 医学判断只能依据「可用证据」中的指南页/讨论段落，每个判断后标注 [Sn]。
2. 问题中的具体实体或突变位点若证据未直接出现，首句写明「指南未直接提及{实体}」。
3. 禁止补充 NCCN 证据以外的医学常识、预后推测或诊疗建议。
4. 文末不要列出来源或参考文献，来源由系统单独展示。

回答结构（Markdown）：
## 结论
1-3 句直接回答，带 [Sn]。

## 指南依据
分点列出证据支持的内容，每点末尾带 [Sn]。

## 证据不足（仅当需要时）
仅说明指南未覆盖的部分，不做推测。
"""


MULTIMODAL_SYSTEM_PROMPT = """你是 DLBCL 专病 NCCN 指南问答助手，并能看懂 NCCN 决策流程图。

证据约束：
1. 医学判断只能依据「可用证据」中的指南页/讨论段落与随附的流程图图片，每个判断后标注 [Sn]。
2. 流程图是带分支的决策树：必须读出「前置条件 → 处置 → 下一步（页码）」的分支关系，不要把不同分支的结论混为一谈。
3. 凡是依赖条件的结论，必须写明其前置条件（如分期、疗效、是否适合移植等）。
4. 问题中的实体/位点若证据与图片均未出现，首句写明「指南未直接提及{实体}」。
5. 禁止补充 NCCN 证据以外的医学常识、预后推测或诊疗建议。
6. 文末不要列出来源或参考文献，来源由系统单独展示。

回答结构（Markdown）：
## 结论
1-3 句直接回答，带 [Sn]。

## 诊疗路径 / 指南依据
按「条件 → 处置 → 下一步」分点列出；涉及流程图分支时写明对应页码（如 BCEL-7），每点末尾带 [Sn]。

## 证据不足（仅当需要时）
仅说明指南未覆盖的部分，不做推测。

在全部回答之后，另起一行输出标记 `===PAGE_SUMMARY_JSON===`，其后输出一个 JSON 对象，
键为随附图片对应的页码（如 "BCEL-4"），值为该页流程图的一句话中文摘要字符串，
或对象 {"summary": "该页流程图一句话中文摘要（含关键分支条件与下一步页码）"}。

摘要供系统检索索引使用，不面向用户。展示裁剪由系统基于 PDF 几何解析完成，无需输出 bbox 坐标。"""

PAGE_SUMMARY_MARKER = "===PAGE_SUMMARY_JSON==="


ROUTE_GUIDANCE = {
    "flowchart": (
        "本次为「诊疗路径/流程图」类问题：优先依据流程图页（如 BCEL-*）回答，"
        "务必写明每个结论的前置条件（分期、疗效评估、是否适合移植等），"
        "并区分不同分支，必要时给出下一步页码。"
    ),
    "evidence": (
        "本次为「证据/机制」类问题：优先依据讨论(discussion)段落回答，"
        "聚焦定义、证据强度与适用人群，避免编造流程细节。"
    ),
    "hybrid": (
        "本次问题同时涉及诊疗路径与证据：先用流程图页给出路径与前置条件，"
        "再用讨论段落补充证据依据，两类来源都用 [Sn] 标注。"
    ),
}


FEW_SHOT_EXAMPLE = (
    "示例（仅示范格式，勿照抄内容）：\n"
    "问题：双表达淋巴瘤一线方案是什么？\n"
    "回答：\n"
    "## 结论\n"
    "指南未直接提及“双表达淋巴瘤”这一措辞；就 DLBCL 一线治疗，"
    "多数患者可用 R-CHOP[S1]。\n"
    "## 指南依据\n"
    "- 适合患者的一线方案为 6 周期 R-CHOP[S1]。\n"
)


EVIDENCE_GATE_SYSTEM = """你是医学证据筛选助手。给定用户问题和若干条编号证据 [S1]..[Sn]，
只返回与回答问题直接相关的证据编号 JSON，格式严格为：{"relevant": ["S1", "S3"]}
不要输出其它文字。"""


def _route_guidance(route: str) -> str:
    return ROUTE_GUIDANCE.get(route, ROUTE_GUIDANCE["evidence"])


def _format_page_info(hit: RetrievalHit) -> str:
    doc = hit.document
    return doc.printed_page_code or f"pdf_page={doc.pdf_page}"


def build_evidence_prompt(question: str, bundle: EvidenceBundle, route: str = "evidence") -> str:
    evidence_blocks = []
    for idx, hit in enumerate(bundle.primary_hits, start=1):
        doc = hit.document
        page_info = _format_page_info(hit)
        section = doc.section or "N/A"
        evidence_blocks.append(
            f"[S{idx}] 页码={page_info}; 类型={doc.page_type}; 章节={section}\n{doc.text}"
        )
    evidence = "\n\n".join(evidence_blocks)

    graph_lines: List[str] = []
    for idx, triple in enumerate(bundle.graph_triples, start=1):
        evidence_ids = ", ".join(triple.evidence_source_ids) if triple.evidence_source_ids else "无"
        graph_lines.append(
            f"[G{idx}] {triple.subject_name}({triple.subject_type}) --{triple.relation}--> "
            f"{triple.object_name}({triple.object_type}) | 置信度={triple.confidence:.2f} | "
            f"证据={evidence_ids} | 状态={triple.validation_status}"
        )
    graph_section = ""
    if graph_lines:
        graph_section = (
            "\n\n可用知识图谱证据（仅用于补召回和路径推理，回答仍需标注 [Sn]）：\n"
            + "\n".join(graph_lines)
        )
    if bundle.graph_context:
        graph_section += "\n" + "\n".join(bundle.graph_context)

    reference_lines: List[str] = []
    source_index = {
        hit.document.source_id: idx
        for idx, hit in enumerate(bundle.primary_hits, start=1)
    }
    for entry in bundle.attached_references:
        linked_sources = [
            f"[S{source_index[source_id]}]"
            for source_id, ref_numbers in bundle.reference_links.items()
            if entry.ref_number in ref_numbers and source_id in source_index
        ]
        linked_label = "、".join(linked_sources) if linked_sources else "关联"
        reference_lines.append(f"- 与 {linked_label} 关联 | {entry.ref_number}. {entry.text}")

    reference_section = ""
    if reference_lines:
        reference_section = (
            "\n\n关联参考文献（仅供读者查阅，回答中不要用文献序号替代 [Sn]）：\n"
            + "\n".join(reference_lines)
        )

    return (
        f"{_route_guidance(route)}\n\n"
        f"{FEW_SHOT_EXAMPLE}\n"
        f"用户问题：{question}\n\n"
        f"可用证据（指南页与讨论段落，引用请仅用 [Sn]）：\n{evidence}"
        f"{graph_section}"
        f"{reference_section}\n\n"
        "请用中文按系统提示的结构回答。"
    )


def build_multimodal_prompt(question: str, bundle: EvidenceBundle, route: str = "flowchart") -> str:
    """Text portion of the multimodal message: evidence text + a figure manifest."""
    base = build_evidence_prompt(question, bundle, route=route)
    if not bundle.figures:
        return base

    figure_lines: List[str] = []
    for order, fig in enumerate(bundle.figures, start=1):
        label = fig.page_code or f"pdf_page={fig.pdf_page}"
        sn = f"[S{fig.source_index}]" if fig.source_index else "相关指南页"
        figure_lines.append(f"- 图{order}：{label}（对应 {sn}）")

    figure_section = (
        "\n\n随附流程图图片（按顺序）：\n"
        + "\n".join(figure_lines)
        + "\n请结合图片读出分支的「前置条件 → 处置 → 下一步页码」，"
        "引用页内容时仍用对应的 [Sn]。"
        "\n在 ===PAGE_SUMMARY_JSON=== 中，请为上述每一页分别输出一句话 summary（中文）。"
    )
    return base + figure_section
