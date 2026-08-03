"""Offline VLM table transcription for paper-style guideline PDFs.

Renders candidate table pages to PNG and asks a vision model to emit Markdown
tables. Results are cached on disk so rebuilds do not re-burn tokens.
"""
from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import requests

from backend.app.services.page_image import PageImageRenderer

TABLE_TRANSCRIBE_SYSTEM = """You are a careful OCR/transcription assistant for clinical guideline tables.
Given a page image that contains one or more tables, output ONLY Markdown tables
(and a short bold caption line before each table if visible).

Rules:
1. Preserve every cell's clinical content, including recommendation grades like [I, A] or [III, B].
2. Preserve superscript citation numbers as plain digits after the cell text (e.g. text^12 → text 12).
3. Do not invent rows/columns; if a cell is blank keep it empty.
4. If the page has multiple tables, output them in reading order separated by a blank line.
5. Do not output prose explanations outside the tables/captions.
"""


def _encode_image(path: Path) -> Optional[str]:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    b64 = base64.b64encode(data).decode("ascii")
    suffix = path.suffix.lower().lstrip(".") or "png"
    mime = "jpeg" if suffix in {"jpg", "jpeg"} else suffix
    return f"data:image/{mime};base64,{b64}"


def _cache_key(pdf_page: int, caption: str) -> str:
    cap = re.sub(r"\s+", " ", (caption or "").strip().lower())
    return f"p{pdf_page}:{cap}"


def load_table_cache(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items() if isinstance(v, str) and v.strip()}


def save_table_cache(path: Path, cache: Dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def _call_vlm(
    *,
    image_path: Path,
    caption: str,
    api_key: str,
    base_url: str,
    model: str,
    timeout: int = 120,
) -> Optional[str]:
    encoded = _encode_image(image_path)
    if not encoded:
        return None
    prompt = (
        f"Transcribe the clinical table(s) on this page to Markdown.\n"
        f"Expected caption hint: {caption or '(unknown)'}\n"
        f"Output Markdown only."
    )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": TABLE_TRANSCRIBE_SYSTEM},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": encoded}},
                ],
            },
        ],
        "temperature": 0.0,
    }
    try:
        response = requests.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=timeout,
        )
        response.raise_for_status()
        data = response.json()
        text = data["choices"][0]["message"]["content"]
        return (text or "").strip() or None
    except (requests.RequestException, KeyError, ValueError, IndexError, TypeError):
        return None


def _looks_like_markdown_table(text: str) -> bool:
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    pipe_rows = [ln for ln in lines if ln.count("|") >= 2]
    return len(pipe_rows) >= 2


def transcribe_tables(
    *,
    pdf_path: Path,
    table_targets: Sequence[Tuple[int, str]],
    cache_path: Path,
    page_image_dir: Path,
    api_key: Optional[str],
    base_url: str,
    model: str,
    dpi: int = 160,
    skip_vlm: bool = False,
) -> Dict[int, List[str]]:
    """Return ``{pdf_page: [markdown, ...]}`` for requested table pages.

    ``table_targets`` is a sequence of ``(pdf_page, caption_hint)``.
    """
    cache = load_table_cache(cache_path)
    by_page: Dict[int, List[str]] = {}
    renderer = PageImageRenderer(pdf_path=pdf_path, cache_dir=page_image_dir, dpi=dpi)

    # Deduplicate pages while preserving first caption hint.
    page_caption: Dict[int, str] = {}
    for pdf_page, caption in table_targets:
        page_caption.setdefault(int(pdf_page), caption or "")

    dirty = False
    for pdf_page, caption in sorted(page_caption.items()):
        key = _cache_key(pdf_page, caption)
        # Also accept any cached entry for this page regardless of caption drift.
        cached = cache.get(key)
        if not cached:
            for ck, cv in cache.items():
                if ck.startswith(f"p{pdf_page}:"):
                    cached = cv
                    break
        if cached and _looks_like_markdown_table(cached):
            by_page.setdefault(pdf_page, []).append(cached)
            continue

        if skip_vlm or not api_key:
            continue

        image_path = renderer.render(pdf_page)
        if image_path is None:
            continue
        md = _call_vlm(
            image_path=image_path,
            caption=caption,
            api_key=api_key,
            base_url=base_url,
            model=model,
        )
        if md and _looks_like_markdown_table(md):
            # Prefer caption prefix for UI.
            if caption and not md.lstrip().startswith("**"):
                md = f"**{caption}**\n\n{md}"
            cache[key] = md
            by_page.setdefault(pdf_page, []).append(md)
            dirty = True

    if dirty:
        save_table_cache(cache_path, cache)
    return by_page
