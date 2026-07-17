"""Tool schemas and status helpers for the agentic QA loop."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from backend.app.models import FigureReference, RetrievalHit


TOOL_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_guidelines",
            "description": (
                "检索 NCCN B 细胞淋巴瘤指南页与讨论段落。"
                "淋巴瘤诊疗/分期/方案/路径问题应优先调用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "检索用查询（可与用户问题相同或更聚焦）",
                    },
                    "kind": {
                        "type": "string",
                        "enum": ["flowchart", "evidence", "any"],
                        "description": "flowchart=路径/治疗；evidence=机制/定义；any=不限",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_graph",
            "description": (
                "按需查询知识图谱三元组，用于关系推理。"
                "治疗类问题仅在文本证据不足时调用；勿用于通用实体噪声召回。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "用于图谱检索的问题或子问题",
                    },
                    "relation": {
                        "type": "string",
                        "description": "可选关系过滤，如 RECOMMENDS / TREATS",
                    },
                },
                "required": ["question"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "view_pages",
            "description": (
                "按需查看候选流程图/方案表页。"
                "page_codes 必须来自候选清单；一线问题应同时包含决策页与方案表。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "page_codes": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "要渲染并送入视觉模型的页码列表，如 [\"BCEL-3\", \"BCEL-C 1 OF 7\"]",
                    },
                },
                "required": ["page_codes"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "respond_directly",
            "description": "闲聊或与本指南无关的通用医学问题，跳过指南检索。",
            "parameters": {
                "type": "object",
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": ["chitchat", "general_medical"],
                    },
                },
                "required": ["kind"],
            },
        },
    },
]


@dataclass
class AgentState:
    """Mutable state accumulated across agent tool calls."""

    hits: List[RetrievalHit] = field(default_factory=list)
    graph_hits: list = field(default_factory=list)
    figures: List[FigureReference] = field(default_factory=list)
    candidate_pages: List[Dict[str, Any]] = field(default_factory=list)
    route: str = "evidence"
    answer_kind: str = "guideline"
    early_answer: Optional[str] = None
    early_degraded: Optional[str] = None
    seed_page_code: Optional[str] = None
    seed_meta: Dict[str, Any] = field(default_factory=dict)
    steps: List[Dict[str, Any]] = field(default_factory=list)
    ready: bool = False
    diagnostics: Dict[str, Any] = field(default_factory=dict)
    gate_degraded: Optional[str] = None


def status_event(stage: str, label: str, detail: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "type": "status",
        "stage": stage,
        "label": label,
        "detail": detail or {},
    }


def status_for_tool(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    if name == "search_guidelines":
        query = str(arguments.get("query") or "").strip()
        kind = str(arguments.get("kind") or "any")
        label = f"检索指南中：「{query[:48]}」" if query else "检索指南中…"
        return status_event("search", label, {"tool": name, "kind": kind, "query": query})
    if name == "query_graph":
        return status_event(
            "graph",
            "查询知识图谱中…",
            {"tool": name, "relation": arguments.get("relation")},
        )
    if name == "view_pages":
        codes = arguments.get("page_codes") or []
        if isinstance(codes, str):
            codes = [codes]
        joined = "、".join(str(c) for c in codes[:6])
        label = f"读取流程图：{joined}" if joined else "读取流程图中…"
        return status_event("view_pages", label, {"tool": name, "page_codes": list(codes)})
    if name == "respond_directly":
        kind = str(arguments.get("kind") or "chitchat")
        label = "准备直接回复…" if kind == "chitchat" else "准备通用医学说明…"
        return status_event("direct", label, {"tool": name, "kind": kind})
    return status_event("tool", f"执行工具：{name}", {"tool": name})


def parse_tool_arguments(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, json.JSONDecodeError):
        return {}


def summarize_hits_for_agent(hits: Sequence[RetrievalHit], limit: int = 8) -> str:
    lines: List[str] = []
    for idx, hit in enumerate(hits[:limit], start=1):
        doc = hit.document
        page = doc.printed_page_code or f"pdf_page={doc.pdf_page}"
        snippet = (doc.text or "").replace("\n", " ")[:160]
        lines.append(
            f"[S{idx}] 页码={page}; 类型={doc.page_type}; score={hit.score:.3f}; {snippet}"
        )
    return "\n".join(lines) if lines else "(无命中)"


def summarize_candidates(candidates: Sequence[Dict[str, Any]]) -> str:
    if not candidates:
        return "(无候选页)"
    lines = []
    for item in candidates:
        lines.append(
            f"- {item.get('page_code')} | 类型={item.get('page_kind')} | "
            f"{item.get('summary') or ''}"
        )
    return "\n".join(lines)


def extract_ready_payload(content: str) -> Optional[Dict[str, Any]]:
    if not content:
        return None
    match_start = content.find("{")
    match_end = content.rfind("}")
    if match_start < 0 or match_end <= match_start:
        return None
    try:
        parsed = json.loads(content[match_start : match_end + 1])
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, dict) and parsed.get("ready"):
        return parsed
    return None
