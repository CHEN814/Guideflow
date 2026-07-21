from __future__ import annotations

import json
import re
from typing import Dict, Generator, List, Optional, Sequence, Tuple

import requests

from backend.app.models import EvidenceBundle, RetrievalHit
from backend.app.prompts import (
    AGENT_SYSTEM_PROMPT,
    CHITCHAT_SYSTEM,
    CONDENSE_SYSTEM,
    EVIDENCE_GATE_SYSTEM,
    GENERAL_MEDICAL_SYSTEM,
    INTENT_CLASSIFY_SYSTEM,
    SYSTEM_PROMPT,
    agent_system_prompt_for_source,
    build_evidence_prompt,
    format_history_for_prompt,
    system_prompt_for_source,
)
from backend.app.services.agent_tools import TOOL_DEFINITIONS
from backend.app.services.dlbcl_flow_map import is_decision_flow_page
from backend.app.services.figure_selection import lexical_overlap


GENERAL_MEDICAL_BANNER = "> **非指南内容 · 通用医学知识（仅供参考，不替代临床判断）**"


def _format_page_info(hit: RetrievalHit) -> str:
    doc = hit.document
    return doc.printed_page_code or f"pdf_page={doc.pdf_page}"


def _lexical_gate_indices(question: str, hits: List[RetrievalHit], min_keep: int = 2) -> List[int]:
    scored: List[tuple[float, int]] = []
    for idx, hit in enumerate(hits, start=1):
        doc = hit.document
        page = doc.printed_page_code or ""
        score = lexical_overlap(question, doc.text or "", page, doc.section or "")
        scored.append((score, idx))
    scored.sort(reverse=True, key=lambda item: item[0])
    keep = [idx for score, idx in scored if score > 0]
    if len(keep) < min_keep:
        keep = [idx for _, idx in scored[: min(min_keep, len(scored))]]
    return sorted(set(keep))


def _fallback_indices(
    question: str,
    hits: List[RetrievalHit],
    protected: set[int],
    *,
    protect_decision_pages: bool,
) -> List[int]:
    """Lexical gate fallback; drop decision pages unless protect is on.

    When protect_decision_pages is False (discussion/evidence questions),
    decision-flow pages must not survive an empty/failed LLM gate — they
    would otherwise trip the evidence→flowchart soft upgrade. If stripping
    them empties the set, keep the original lexical set to avoid blank evidence.
    """
    indices = sorted(set(_lexical_gate_indices(question, hits)) | protected)
    if protect_decision_pages:
        return indices
    filtered = [
        idx
        for idx in indices
        if not is_decision_flow_page(hits[idx - 1].document.printed_page_code)
    ]
    return filtered if filtered else indices


def _history_messages(
    history: Sequence[dict] | None,
    max_turns: int = 4,
) -> List[Dict[str, str]]:
    """Convert UI history into OpenAI-style chat messages (truncated)."""
    if not history:
        return []
    messages: List[Dict[str, str]] = []
    for turn in list(history)[-max_turns * 2 :]:
        role = str(turn.get("role") or "").strip().lower()
        content = str(turn.get("content") or "").strip()
        if role not in ("user", "assistant") or not content:
            continue
        # Cap each turn to keep prompts small.
        messages.append({"role": role, "content": content[:1200]})
    return messages


def _heuristic_intent(question: str) -> str:
    q = (question or "").strip()
    if not q:
        return "chitchat"
    lower = q.lower()
    chitchat_re = re.compile(
        r"^(你好|您好|嗨|hi|hello|hey|谢谢|感谢|早上好|晚安|在吗)[\s!！?？.。~～]*$",
        re.I,
    )
    if chitchat_re.match(q) or len(q) <= 2:
        return "chitchat"
    guideline_markers = [
        "dlbcl", "fl", "mcl", "mzl", "pmbl", "hgbl", "burkitt", "ptld",
        "淋巴瘤", "r-chop", "pola", "car-t", "一线", "二线", "复发", "难治",
        "分期", "随访", "cns", "prophylaxis", "指南", "治疗", "方案",
        "bcl2", "myc", "ipi", "fish",
    ]
    if any(m in lower for m in guideline_markers):
        return "guideline"
    general_markers = [
        "发烧", "发热", "退热", "感冒", "血压", "血糖", "头痛", "咳嗽",
        "多少度", "体温", "腹泻", "呕吐", "过敏",
    ]
    if any(m in lower for m in general_markers):
        return "general_medical"
    # Default: treat as guideline-related so we don't invent answers for clinical Qs.
    return "guideline"


def _parse_json_object(content: str) -> Optional[dict]:
    match = re.search(r"\{.*\}", content or "", re.DOTALL)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


class QwenClient:
    def __init__(
        self,
        api_key: str | None,
        base_url: str,
        model: str,
        source_key: str = "nccn",
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.source_key = (source_key or "nccn").strip().lower()

    def _chat(
        self,
        messages: List[Dict[str, object]],
        *,
        temperature: float = 0.1,
        timeout: int = 60,
        tools: Optional[List[dict]] = None,
        tool_choice: Optional[str] = None,
    ) -> Dict[str, object]:
        """Return the raw assistant message dict (content / tool_calls)."""
        if not self.api_key:
            raise RuntimeError("qwen_api_unavailable")
        payload: Dict[str, object] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            payload["tools"] = tools
            if tool_choice is not None:
                payload["tool_choice"] = tool_choice
        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=timeout,
        )
        response.raise_for_status()
        message = response.json()["choices"][0]["message"]
        return message if isinstance(message, dict) else {"content": str(message)}

    def _chat_text(
        self,
        messages: List[Dict[str, object]],
        *,
        temperature: float = 0.1,
        timeout: int = 60,
    ) -> str:
        message = self._chat(messages, temperature=temperature, timeout=timeout)
        return str(message.get("content") or "")

    def run_tool_turn(
        self,
        messages: List[Dict[str, object]],
        *,
        tools: Optional[List[dict]] = None,
        temperature: float = 0.1,
        timeout: int = 60,
    ) -> Tuple[Dict[str, object], List[Dict[str, object]], Optional[str]]:
        """One agent turn. Returns (assistant_message, tool_calls, degraded)."""
        tools = tools if tools is not None else TOOL_DEFINITIONS
        if not self.api_key:
            return {"content": "", "role": "assistant"}, [], "agent_no_api_key"
        try:
            message = self._chat(
                messages,
                temperature=temperature,
                timeout=timeout,
                tools=tools,
                tool_choice="auto",
            )
        except (requests.RequestException, KeyError, ValueError, RuntimeError) as exc:
            return (
                {"content": "", "role": "assistant"},
                [],
                f"agent_tool_turn_failed:{type(exc).__name__}",
            )
        raw_calls = message.get("tool_calls") or []
        tool_calls: List[Dict[str, object]] = []
        if isinstance(raw_calls, list):
            for call in raw_calls:
                if not isinstance(call, dict):
                    continue
                fn = call.get("function") or {}
                if not isinstance(fn, dict):
                    continue
                tool_calls.append(
                    {
                        "id": call.get("id") or "",
                        "type": "function",
                        "function": {
                            "name": fn.get("name") or "",
                            "arguments": fn.get("arguments") or "{}",
                        },
                    }
                )
        # Normalize assistant message for replay into the next turn.
        assistant_msg: Dict[str, object] = {
            "role": "assistant",
            "content": message.get("content") or "",
        }
        if tool_calls:
            assistant_msg["tool_calls"] = tool_calls
        return assistant_msg, tool_calls, None

    def classify_intent(
        self,
        question: str,
        history: Sequence[dict] | None = None,
    ) -> Tuple[str, Optional[str]]:
        """Return (intent, degraded_reason)."""
        heuristic = _heuristic_intent(question)
        if not self.api_key:
            return heuristic, "intent_lexical_fallback"
        try:
            content = self._chat_text(
                [
                    {"role": "system", "content": INTENT_CLASSIFY_SYSTEM},
                    {
                        "role": "user",
                        "content": (
                            f"对话历史：\n{format_history_for_prompt(history or [])}\n\n"
                            f"当前问题：{question}"
                        ),
                    },
                ],
                temperature=0.0,
                timeout=20,
            )
            parsed = _parse_json_object(content) or {}
            intent = str(parsed.get("intent") or "").strip().lower()
            if intent not in ("guideline", "general_medical", "chitchat"):
                return heuristic, "intent_parse_fallback"
            return intent, None
        except (requests.RequestException, KeyError, ValueError, RuntimeError):
            return heuristic, "intent_request_failed"

    def condense_question(
        self,
        question: str,
        history: Sequence[dict] | None = None,
    ) -> Tuple[str, bool, Optional[str]]:
        """Return (standalone_question, topic_shift, degraded_reason)."""
        if not history:
            return question, False, None
        if not self.api_key:
            return question, False, "condense_skipped_no_key"
        try:
            content = self._chat_text(
                [
                    {"role": "system", "content": CONDENSE_SYSTEM},
                    {
                        "role": "user",
                        "content": (
                            f"对话历史：\n{format_history_for_prompt(history)}\n\n"
                            f"最新问题：{question}"
                        ),
                    },
                ],
                temperature=0.0,
                timeout=25,
            )
            parsed = _parse_json_object(content) or {}
            standalone = str(parsed.get("standalone_question") or "").strip() or question
            topic_shift = bool(parsed.get("topic_shift", False))
            return standalone, topic_shift, None
        except (requests.RequestException, KeyError, ValueError, RuntimeError):
            return question, False, "condense_request_failed"

    def generate_chitchat(self, question: str) -> Tuple[str, Optional[str]]:
        if not self.api_key:
            return (
                "你好！我是 NCCN B 细胞淋巴瘤指南助手，可以帮你查询指南中的诊疗路径与证据。"
                "直接提问即可，例如「DLBCL 一线治疗如何推荐？」",
                "qwen_api_unavailable",
            )
        try:
            answer = self._chat_text(
                [
                    {"role": "system", "content": CHITCHAT_SYSTEM},
                    {"role": "user", "content": question},
                ],
                temperature=0.4,
                timeout=30,
            )
            return answer.strip(), None
        except (requests.RequestException, KeyError, ValueError, RuntimeError) as exc:
            return (
                "你好！我是指南助手，可以帮你查询 NCCN B 细胞淋巴瘤相关问题。",
                f"chitchat_failed:{type(exc).__name__}",
            )

    def generate_general_medical(self, question: str) -> Tuple[str, Optional[str]]:
        if not self.api_key:
            answer = (
                f"{GENERAL_MEDICAL_BANNER}\n\n"
                "当前未配置大模型 API，无法生成通用医学说明。"
                "该问题似乎超出本指南检索范围；请咨询医生，或改问淋巴瘤指南相关问题。"
            )
            return answer, "qwen_api_unavailable"
        try:
            answer = self._chat_text(
                [
                    {"role": "system", "content": GENERAL_MEDICAL_SYSTEM},
                    {"role": "user", "content": question},
                ],
                temperature=0.3,
                timeout=60,
            ).strip()
            if GENERAL_MEDICAL_BANNER.split("**")[1] not in answer:
                answer = f"{GENERAL_MEDICAL_BANNER}\n\n{answer}"
            return answer, None
        except (requests.RequestException, KeyError, ValueError, RuntimeError) as exc:
            return (
                f"{GENERAL_MEDICAL_BANNER}\n\n"
                "暂时无法生成通用医学说明。该问题超出本指南证据范围，请咨询医生。",
                f"general_medical_failed:{type(exc).__name__}",
            )

    def gate_evidence(
        self,
        question: str,
        hits: List[RetrievalHit],
        *,
        protect_decision_pages: bool = False,
    ) -> Tuple[List[RetrievalHit], Optional[str], List[int]]:
        """Return filtered hits, optional degraded reason, and kept 1-based indices."""
        if not hits:
            return [], None, []

        protected = {
            idx
            for idx, hit in enumerate(hits, start=1)
            if protect_decision_pages and is_decision_flow_page(hit.document.printed_page_code)
        }

        if not self.api_key:
            indices = _fallback_indices(
                question, hits, protected, protect_decision_pages=protect_decision_pages
            )
            filtered = [hit for idx, hit in enumerate(hits, start=1) if idx in indices]
            return filtered, "evidence_gate_lexical_fallback", indices

        lines = []
        for idx, hit in enumerate(hits, start=1):
            doc = hit.document
            page = doc.printed_page_code or f"pdf_page={doc.pdf_page}"
            snippet = (doc.text or "").replace("\n", " ")[:200]
            lines.append(f"[S{idx}] 页码={page}; 类型={doc.page_type}; {snippet}")

        try:
            content = self._chat_text(
                [
                    {"role": "system", "content": EVIDENCE_GATE_SYSTEM},
                    {
                        "role": "user",
                        "content": f"问题：{question}\n\n证据：\n" + "\n".join(lines),
                    },
                ],
                temperature=0.0,
                timeout=30,
            )
            parsed = _parse_json_object(content) or {}
            raw = parsed.get("relevant", []) if isinstance(parsed, dict) else []
            indices: List[int] = []
            for item in raw:
                m = re.search(r"S?(\d+)", str(item), re.IGNORECASE)
                if m:
                    indices.append(int(m.group(1)))
            indices = sorted({i for i in indices if 1 <= i <= len(hits)} | protected)
            if not indices:
                indices = _fallback_indices(
                    question, hits, protected, protect_decision_pages=protect_decision_pages
                )
                filtered = [hit for idx, hit in enumerate(hits, start=1) if idx in indices]
                return filtered, "evidence_gate_empty_fallback", indices
            filtered = [hits[i - 1] for i in indices]
            return filtered, None, indices
        except (requests.RequestException, KeyError, ValueError, RuntimeError, json.JSONDecodeError):
            indices = _fallback_indices(
                question, hits, protected, protect_decision_pages=protect_decision_pages
            )
            filtered = [hit for idx, hit in enumerate(hits, start=1) if idx in indices]
            return filtered, "evidence_gate_request_failed", indices

    def build_agent_messages(
        self,
        question: str,
        history: Sequence[dict] | None = None,
    ) -> List[Dict[str, object]]:
        messages: List[Dict[str, object]] = [
            {"role": "system", "content": agent_system_prompt_for_source(self.source_key)},
        ]
        hist = format_history_for_prompt(history or [])
        ready_hint = (
            '{"ready": true, "route": "evidence"}'
            if self.source_key == "csco"
            else '{"ready": true, "route": "flowchart"|"evidence"|"hybrid"}'
        )
        messages.append(
            {
                "role": "user",
                "content": (
                    f"对话历史：\n{hist}\n\n"
                    f"用户问题：{question}\n\n"
                    f"请按需调用工具收集证据；完成后回复 {ready_hint}。"
                ),
            }
        )
        return messages

    def generate(
        self,
        question: str,
        bundle: EvidenceBundle,
        route: str = "evidence",
        history: Sequence[dict] | None = None,
    ) -> Tuple[str, str | None]:
        if not self.api_key:
            return self._fallback_answer(question, bundle, reason="no_key"), "qwen_api_unavailable"

        messages: List[Dict[str, object]] = [
            {"role": "system", "content": system_prompt_for_source(self.source_key)}
        ]
        messages.extend(_history_messages(history))
        messages.append(
            {
                "role": "user",
                "content": build_evidence_prompt(
                    question, bundle, route=route, source_key=self.source_key
                ),
            }
        )
        try:
            answer = self._chat_text(messages, temperature=0.1, timeout=90)
            return answer, None
        except (requests.RequestException, KeyError, ValueError, RuntimeError) as exc:
            return (
                self._fallback_answer(question, bundle, reason="request_failed", detail=str(exc)),
                f"qwen_request_failed:{type(exc).__name__}",
            )

    def generate_stream(
        self,
        question: str,
        bundle: EvidenceBundle,
        route: str = "evidence",
        history: Sequence[dict] | None = None,
    ) -> Generator[str, None, None]:
        """Yield text deltas from upstream OpenAI-compatible streaming API."""
        if not self.api_key:
            yield self._fallback_answer(question, bundle, reason="no_key")
            return

        messages: List[Dict[str, str]] = [
            {"role": "system", "content": system_prompt_for_source(self.source_key)}
        ]
        messages.extend(_history_messages(history))
        messages.append(
            {
                "role": "user",
                "content": build_evidence_prompt(
                    question, bundle, route=route, source_key=self.source_key
                ),
            }
        )
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.1,
            "stream": True,
        }
        try:
            with requests.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=120,
                stream=True,
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines(decode_unicode=True):
                    if not line:
                        continue
                    if line.startswith("data:"):
                        data = line[5:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        choices = chunk.get("choices") or []
                        if not choices:
                            continue
                        delta = choices[0].get("delta") or {}
                        text = delta.get("content")
                        if text:
                            yield str(text)
        except (requests.RequestException, KeyError, ValueError, RuntimeError) as exc:
            yield self._fallback_answer(
                question, bundle, reason="request_failed", detail=str(exc)
            )

    def _fallback_answer(
        self, question: str, bundle: EvidenceBundle, reason: str = "no_key", detail: str = ""
    ) -> str:
        if reason == "request_failed":
            header = "千问 API 调用失败（key 无效/被拒或网络问题），以下为证据摘要模式，不代表最终模型回答。"
            if detail:
                header += f"（{detail[:200]}）"
        else:
            header = "未检测到千问 API key，以下为证据摘要模式，不代表最终模型回答。"
        lines = [
            header,
            "",
            f"问题：{question}",
            "",
            "可用指南证据：",
        ]
        for idx, hit in enumerate(bundle.primary_hits, start=1):
            doc = hit.document
            snippet = doc.text.replace("\n", " ")[:280]
            page_info = _format_page_info(hit)
            lines.append(f"[S{idx}] {page_info}, {doc.page_type}, {doc.section}: {snippet}")
        if bundle.attached_references:
            lines.extend(["", "关联参考文献："])
            for entry in bundle.attached_references:
                lines.append(f"[{entry.ref_number}] {entry.text[:200]}")
        lines.extend(
            [
                "",
                "边界说明：请接入千问 API 后生成正式回答；当前仅用于检查检索证据是否合理。",
            ]
        )
        return "\n".join(lines)
