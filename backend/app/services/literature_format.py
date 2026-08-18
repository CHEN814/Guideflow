"""Format PubMed secondary hits into an answer appendix (isolated from [Sn])."""
from __future__ import annotations

import json
import re
from typing import Any, List, Optional, Sequence

from backend.app.models import LiteratureHit
from backend.app.prompts import LITERATURE_BLURB_SYSTEM


def format_literature_section(
    hits: Sequence[LiteratureHit],
    *,
    question: str = "",
    qwen_client: Any = None,
) -> str:
    """Build the isolated appendix. Never emits [Sn] citations."""
    if not hits:
        return ""
    _fill_blurbs(hits, question=question, qwen_client=qwen_client)
    lines = [
        "",
        "## 指南外最新文献（供参考）",
        "",
        "以下条目来自 PubMed **摘要**检索，标注为二级参考；**未经指南收录，不构成诊疗推荐**。",
        "",
    ]
    for hit in hits:
        label = f"[L{hit.rank}]" if hit.rank else "[L]"
        meta_bits = [b for b in [hit.journal, hit.year] if b]
        if hit.journal_if is not None:
            meta_bits.append(f"IF {hit.journal_if:g}")
        if hit.journal_quartile:
            meta_bits.append(hit.journal_quartile)
        meta = f" ({', '.join(meta_bits)})" if meta_bits else ""
        # Doctor-facing appendix: study design only — do not expose E1–E5 algorithm tier.
        design_bit = f"；{hit.study_design_zh}" if hit.study_design_zh else ""
        lines.append(f"{label} {hit.title}{meta}{design_bit}. PMID {hit.pmid}")
        if hit.summary_zh:
            lines.append(f"  - {hit.summary_zh}")
        if hit.in_guideline and hit.guideline_ref:
            source_line = f"PubMed · 仅摘要 · 已被{hit.guideline_ref}引用"
        elif hit.in_guideline:
            source_line = "PubMed · 仅摘要 · 已被指南引用"
        else:
            source_line = "PubMed · 仅摘要 · 未经指南收录"
        if hit.study_design_zh:
            source_line = f"{hit.study_design_zh} · {source_line}"
        lines.append(f"  - 来源：{source_line}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _fill_blurbs(
    hits: Sequence[LiteratureHit],
    *,
    question: str,
    qwen_client: Any,
) -> None:
    if not hits:
        return
    blurbs = _llm_blurbs(hits, question=question, qwen_client=qwen_client) or {}
    for hit in hits:
        if hit.summary_zh:
            continue
        if hit.pmid in blurbs:
            hit.summary_zh = blurbs[hit.pmid]
            continue
        # Deterministic fallback: first abstract sentence / title echo
        abstract = (hit.abstract or "").strip()
        if abstract:
            # Prefer RESULTS / CONCLUSION labeled section
            m = re.search(
                r"(?:RESULTS?|CONCLUSIONS?|CONCLUSION)\s*:\s*([^.\n]+)",
                abstract,
                flags=re.I,
            )
            snippet = (m.group(1) if m else abstract.split("\n")[0]).strip()
            snippet = re.sub(r"\s+", " ", snippet)
            if len(snippet) > 120:
                snippet = snippet[:117].rstrip() + "…"
            hit.summary_zh = snippet
        else:
            hit.summary_zh = "（无摘要正文，仅题录）"


def _llm_blurbs(
    hits: Sequence[LiteratureHit],
    *,
    question: str,
    qwen_client: Any,
) -> Optional[dict]:
    if qwen_client is None or not getattr(qwen_client, "api_key", None):
        return None
    payload = {
        "question": question,
        "articles": [
            {
                "pmid": h.pmid,
                "title": h.title,
                "abstract": (h.abstract or "")[:800],
                "year": h.year,
            }
            for h in hits
        ],
    }
    try:
        text = qwen_client._chat_text(
            [
                {"role": "system", "content": LITERATURE_BLURB_SYSTEM},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            temperature=0.0,
            timeout=15,
        )
    except Exception:
        return None
    match = re.search(r"\{.*\}", text or "", flags=re.S)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    out = {}
    for item in data.get("blurbs") or []:
        if not isinstance(item, dict):
            continue
        pmid = str(item.get("pmid") or "").strip()
        blurb = str(item.get("text") or "").strip()
        if pmid and blurb:
            out[pmid] = blurb[:80]
    return out or None
