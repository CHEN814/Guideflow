from __future__ import annotations

import json
import re
from typing import List, Optional, Tuple

import requests

from backend.app.models import EvidenceBundle, RetrievalHit
from backend.app.prompts import (
    EVIDENCE_GATE_SYSTEM,
    SYSTEM_PROMPT,
    build_evidence_prompt,
)
from backend.app.services.figure_selection import lexical_overlap


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


class QwenClient:
    def __init__(self, api_key: str | None, base_url: str, model: str):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model

    def gate_evidence(
        self, question: str, hits: List[RetrievalHit]
    ) -> Tuple[List[RetrievalHit], Optional[str], List[int]]:
        """Return filtered hits, optional degraded reason, and kept 1-based indices."""
        if not hits:
            return [], None, []
        if not self.api_key:
            indices = _lexical_gate_indices(question, hits)
            filtered = [hit for idx, hit in enumerate(hits, start=1) if idx in indices]
            return filtered, "evidence_gate_lexical_fallback", indices

        lines = []
        for idx, hit in enumerate(hits, start=1):
            doc = hit.document
            page = doc.printed_page_code or f"pdf_page={doc.pdf_page}"
            snippet = (doc.text or "").replace("\n", " ")[:200]
            lines.append(f"[S{idx}] 页码={page}; 类型={doc.page_type}; {snippet}")

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": EVIDENCE_GATE_SYSTEM},
                {
                    "role": "user",
                    "content": f"问题：{question}\n\n证据：\n" + "\n".join(lines),
                },
            ],
            "temperature": 0.0,
        }
        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=30,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            match = re.search(r"\{.*\}", content, re.DOTALL)
            indices: List[int] = []
            if match:
                parsed = json.loads(match.group(0))
                raw = parsed.get("relevant", []) if isinstance(parsed, dict) else []
                for item in raw:
                    m = re.search(r"S?(\d+)", str(item), re.IGNORECASE)
                    if m:
                        indices.append(int(m.group(1)))
            indices = sorted({i for i in indices if 1 <= i <= len(hits)})
            if not indices:
                indices = _lexical_gate_indices(question, hits)
                filtered = [hit for idx, hit in enumerate(hits, start=1) if idx in indices]
                return filtered, "evidence_gate_empty_fallback", indices
            filtered = [hits[i - 1] for i in indices]
            return filtered, None, indices
        except (requests.RequestException, KeyError, ValueError, json.JSONDecodeError):
            indices = _lexical_gate_indices(question, hits)
            filtered = [hit for idx, hit in enumerate(hits, start=1) if idx in indices]
            return filtered, "evidence_gate_request_failed", indices

    def generate(
        self, question: str, bundle: EvidenceBundle, route: str = "evidence"
    ) -> Tuple[str, str | None]:
        if not self.api_key:
            return self._fallback_answer(question, bundle, reason="no_key"), "qwen_api_unavailable"

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_evidence_prompt(question, bundle, route=route)},
            ],
            "temperature": 0.1,
        }
        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=90,
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"], None
        except (requests.RequestException, KeyError, ValueError) as exc:
            # e.g. 401 (invalid key / wrong key type), timeout, malformed JSON.
            # Degrade to evidence-summary mode instead of crashing the caller.
            return (
                self._fallback_answer(question, bundle, reason="request_failed", detail=str(exc)),
                f"qwen_request_failed:{type(exc).__name__}",
            )

    def generate_stream(self, question: str, bundle: EvidenceBundle, route: str = "evidence"):
        """Yield text deltas from upstream OpenAI-compatible streaming API.

        Yields ``str`` chunks. On total failure yields a single fallback string then stops.
        Caller should join chunks for the final answer. Degraded reason is returned via
        the ``degraded`` attribute set on the generator after iteration (or use the
        companion ``stream_with_meta`` pattern in QAService).
        """
        if not self.api_key:
            yield self._fallback_answer(question, bundle, reason="no_key")
            return

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_evidence_prompt(question, bundle, route=route)},
            ],
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
                        data_str = line[5:].strip()
                    else:
                        continue
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    text = delta.get("content") or ""
                    if text:
                        yield text
        except (requests.RequestException, KeyError, ValueError) as exc:
            yield self._fallback_answer(question, bundle, reason="request_failed", detail=str(exc))

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
