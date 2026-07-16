"""Query-time multimodal (VLM) client."""
from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests

from backend.app.models import EvidenceBundle
from backend.app.prompts import (
    MULTIMODAL_SYSTEM_PROMPT,
    PAGE_SUMMARY_MARKER,
    build_multimodal_prompt,
)


def _normalize_page_code(page_code: Optional[str]) -> Optional[str]:
    if not page_code:
        return None
    return " ".join(page_code.upper().split())


def _parse_bbox(raw: object) -> Optional[List[float]]:
    if not isinstance(raw, (list, tuple)) or len(raw) != 4:
        return None
    try:
        coords = [float(v) for v in raw]
    except (TypeError, ValueError):
        return None
    x0, y0, x1, y1 = coords
    if not all(0.0 <= v <= 1.0 for v in coords):
        return None
    if x1 <= x0 or y1 <= y0:
        return None
    return [x0, y0, x1, y1]


def _split_answer_and_summary(
    content: str,
) -> Tuple[str, Dict[str, str], Dict[str, List[float]]]:
    """Separate user answer from trailing page-summary JSON (with optional bbox)."""
    if PAGE_SUMMARY_MARKER not in content:
        return content.strip(), {}, {}

    answer, _, tail = content.partition(PAGE_SUMMARY_MARKER)
    summaries: Dict[str, str] = {}
    bboxes: Dict[str, List[float]] = {}
    match = re.search(r"\{.*\}", tail, re.DOTALL)
    if not match:
        return answer.strip(), summaries, bboxes

    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return answer.strip(), summaries, bboxes

    if not isinstance(parsed, dict):
        return answer.strip(), summaries, bboxes

    for key, value in parsed.items():
        page_key = _normalize_page_code(str(key))
        if not page_key:
            continue
        if isinstance(value, str):
            if value.strip():
                summaries[page_key] = value.strip()
            continue
        if isinstance(value, dict):
            summary = value.get("summary")
            if summary:
                summaries[page_key] = str(summary).strip()
            bbox = _parse_bbox(value.get("bbox"))
            if bbox:
                bboxes[page_key] = bbox

    return answer.strip(), summaries, bboxes


def _encode_image(path: Path) -> Optional[str]:
    try:
        data = Path(path).read_bytes()
    except OSError:
        return None
    b64 = base64.b64encode(data).decode("ascii")
    suffix = Path(path).suffix.lower().lstrip(".") or "png"
    mime = "jpeg" if suffix in {"jpg", "jpeg"} else suffix
    return f"data:image/{mime};base64,{b64}"


class MultimodalClient:
    def __init__(self, api_key: Optional[str], base_url: str, model: str):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def generate(
        self, question: str, bundle: EvidenceBundle, route: str = "flowchart"
    ) -> Tuple[str, Optional[str], Dict[str, str], Dict[str, List[float]]]:
        """Return (answer, degraded_reason, page_summaries, page_bboxes)."""
        if not self.api_key:
            return self._fallback(question, bundle), "vlm_api_unavailable", {}, {}

        image_urls: List[str] = []
        for fig in bundle.figures:
            encoded = _encode_image(Path(fig.image_path))
            if encoded:
                image_urls.append(encoded)

        if not image_urls:
            return self._fallback(question, bundle), "vlm_no_images", {}, {}

        content: List[dict] = [
            {"type": "text", "text": build_multimodal_prompt(question, bundle, route=route)}
        ]
        for url in image_urls:
            content.append({"type": "image_url", "image_url": {"url": url}})

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": MULTIMODAL_SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ],
            "temperature": 0.1,
        }
        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=90,
            )
            response.raise_for_status()
            data = response.json()
            answer, summaries, bboxes = _split_answer_and_summary(
                data["choices"][0]["message"]["content"]
            )
            return answer, None, summaries, bboxes
        except (requests.RequestException, KeyError, ValueError) as exc:
            return (
                self._fallback(question, bundle),
                f"vlm_request_failed:{type(exc).__name__}",
                {},
                {},
            )

    def generate_stream(self, question: str, bundle: EvidenceBundle, route: str = "flowchart"):
        """Yield text deltas; after exhaustion, caller parses full text for summaries/bboxes.

        Yields ``str`` chunks of the raw model stream (may include trailing PAGE_SUMMARY JSON).
        """
        if not self.api_key:
            yield self._fallback(question, bundle)
            return

        image_urls: List[str] = []
        for fig in bundle.figures:
            encoded = _encode_image(Path(fig.image_path))
            if encoded:
                image_urls.append(encoded)
        if not image_urls:
            yield self._fallback(question, bundle)
            return

        content: List[dict] = [
            {"type": "text", "text": build_multimodal_prompt(question, bundle, route=route)}
        ]
        for url in image_urls:
            content.append({"type": "image_url", "image_url": {"url": url}})

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": MULTIMODAL_SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ],
            "temperature": 0.1,
            "stream": True,
        }
        try:
            with requests.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=180,
                stream=True,
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines(decode_unicode=True):
                    if not line:
                        continue
                    if not line.startswith("data:"):
                        continue
                    data_str = line[5:].strip()
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
        except (requests.RequestException, KeyError, ValueError):
            yield self._fallback(question, bundle)

    def _fallback(self, question: str, bundle: EvidenceBundle) -> str:
        lines = [
            "未能调用视觉模型（VLM），以下为证据摘要模式，未读取流程图分支。",
            "",
            f"问题：{question}",
            "",
            "随附流程图页：",
        ]
        for fig in bundle.figures:
            label = fig.page_code or f"pdf_page={fig.pdf_page}"
            lines.append(f"- {label}: {fig.image_path}")
        lines.extend(["", "可用文本证据："])
        for idx, hit in enumerate(bundle.primary_hits, start=1):
            doc = hit.document
            snippet = doc.text.replace("\n", " ")[:240]
            page = doc.printed_page_code or f"pdf_page={doc.pdf_page}"
            lines.append(f"[S{idx}] {page}, {doc.page_type}: {snippet}")
        return "\n".join(lines)


def load_multimodal_client(
    api_key: Optional[str], base_url: str, model: str
) -> MultimodalClient:
    return MultimodalClient(api_key=api_key, base_url=base_url, model=model)
