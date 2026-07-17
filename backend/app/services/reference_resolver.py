from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from backend.app.models import ReferenceEntry, RetrievalHit, StructuredKnowledgeBase
from backend.app.services.store import load_knowledge_base

_CITATION_RE = re.compile(
    r"(?:[\.,](\d{1,3})(?:-(\d{1,3}))?|[\[\(](\d{1,3})[\]\)])"
)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.。!?！？])\s+|\n+")


def _ref_numbers_in_text(text: str) -> List[str]:
    ids: set[str] = set()
    for m in _CITATION_RE.finditer(text or ""):
        start = int(m.group(1) or m.group(3))
        end = int(m.group(2)) if m.group(2) else start
        for n in range(start, min(end + 1, start + 20)):
            ids.add(str(n))
    return sorted(ids, key=int)


def _best_sentence_and_window(
    text: str,
    keywords: Sequence[str],
    window_chars: int = 420,
) -> Tuple[str, str]:
    """Return (best_sentence, expanded_window) for citation harvesting."""
    text = text or ""
    if not text.strip():
        return "", ""
    sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if s and s.strip()]
    if not sentences:
        snippet = text[:window_chars]
        return snippet, snippet

    kw = [k.lower() for k in keywords if k and len(k) > 1]
    best_idx = 0
    best_score = -1
    if kw:
        for idx, sent in enumerate(sentences):
            lower = sent.lower()
            score = sum(1 for k in kw if k in lower)
            if score > best_score:
                best_score = score
                best_idx = idx

    best = sentences[best_idx]
    # Expand neighbours only for context text; citation preference stays on best.
    pieces = [best]
    total = len(best)
    left = best_idx - 1
    right = best_idx + 1
    while total < window_chars and (left >= 0 or right < len(sentences)):
        progressed = False
        if right < len(sentences):
            add = sentences[right]
            if total + len(add) <= window_chars or len(pieces) == 1:
                pieces.append(add)
                total += len(add)
                right += 1
                progressed = True
        if left >= 0 and total < window_chars:
            add = sentences[left]
            if total + len(add) <= window_chars or len(pieces) == 1:
                pieces.insert(0, add)
                total += len(add)
                left -= 1
                progressed = True
        if not progressed:
            break
    return best, " ".join(pieces)


class ReferenceResolver:
    def __init__(
        self,
        knowledge_base: StructuredKnowledgeBase,
        max_attached_refs: int = 6,
    ):
        self.max_attached_refs = max_attached_refs
        self._index: Dict[Tuple[str, str], ReferenceEntry] = {}
        for entry in knowledge_base.reference_entries:
            self._index[(entry.article_id, entry.ref_number)] = entry

    @classmethod
    def from_path(cls, path: Path, max_attached_refs: int = 6) -> "ReferenceResolver":
        return cls(load_knowledge_base(path), max_attached_refs=max_attached_refs)

    def resolve_references(
        self,
        discussion_hits: List[RetrievalHit],
        question: Optional[str] = None,
    ) -> Tuple[List[ReferenceEntry], Dict[str, List[str]]]:
        """Resolve reference entries cited near the matched window of each hit.

        Prefer citation numbers appearing in the sentence window most relevant to
        the question; fall back to the document's ``reference_ids`` if the window
        yields none. Caps at ``max_attached_refs``.
        """
        attached: List[ReferenceEntry] = []
        seen: set[Tuple[str, str]] = set()
        source_links: Dict[str, List[str]] = {}
        truncated = False
        keywords = re.findall(r"[A-Za-z][A-Za-z0-9-]+|[\u4e00-\u9fff]{2,}", question or "")

        for hit in discussion_hits:
            doc = hit.document
            if doc.page_type != "discussion" or not doc.reference_ids:
                continue

            best_sent, _window = _best_sentence_and_window(doc.text or "", keywords)
            # Prefer citations in the best-matching sentence; then the window.
            best_refs = _ref_numbers_in_text(best_sent)
            window_refs = _ref_numbers_in_text(_window)
            allowed = set(doc.reference_ids)
            ordered: List[str] = []
            for n in best_refs + window_refs:
                if n in allowed and n not in ordered:
                    ordered.append(n)
            candidate_nums = ordered
            if not candidate_nums:
                # Fall back to a small prefix of chunk-level refs (not the whole list).
                candidate_nums = sorted(doc.reference_ids, key=lambda v: int(v))[
                    : min(3, self.max_attached_refs)
                ]

            linked_numbers: List[str] = []
            for ref_number in candidate_nums:
                key = (doc.article_id or "", ref_number)
                if key in seen:
                    if ref_number not in linked_numbers:
                        linked_numbers.append(ref_number)
                    continue
                entry = self._index.get(key)
                if entry is None:
                    continue
                if len(attached) >= self.max_attached_refs:
                    truncated = True
                    break
                seen.add(key)
                attached.append(entry)
                linked_numbers.append(ref_number)

            if linked_numbers:
                source_links[doc.source_id] = linked_numbers
            if truncated:
                break

        return attached, source_links
