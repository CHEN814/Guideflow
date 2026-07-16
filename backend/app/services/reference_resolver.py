from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple

from backend.app.models import ReferenceEntry, RetrievalHit, StructuredKnowledgeBase
from backend.app.services.store import load_knowledge_base


class ReferenceResolver:
    def __init__(
        self,
        knowledge_base: StructuredKnowledgeBase,
        max_attached_refs: int = 15,
    ):
        self.max_attached_refs = max_attached_refs
        self._index: Dict[Tuple[str, str], ReferenceEntry] = {}
        for entry in knowledge_base.reference_entries:
            self._index[(entry.article_id, entry.ref_number)] = entry

    @classmethod
    def from_path(cls, path: Path, max_attached_refs: int = 15) -> "ReferenceResolver":
        return cls(load_knowledge_base(path), max_attached_refs=max_attached_refs)

    def resolve_references(
        self,
        discussion_hits: List[RetrievalHit],
    ) -> Tuple[List[ReferenceEntry], Dict[str, List[str]]]:
        """Resolve reference entries cited by discussion chunks.

        Returns attached references and a mapping from source_id to ref_numbers.
        """
        attached: List[ReferenceEntry] = []
        seen: set[Tuple[str, str]] = set()
        source_links: Dict[str, List[str]] = {}
        truncated = False

        for hit in discussion_hits:
            doc = hit.document
            if doc.page_type != "discussion" or not doc.reference_ids:
                continue

            linked_numbers: List[str] = []
            for ref_number in sorted(doc.reference_ids, key=lambda value: int(value)):
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
