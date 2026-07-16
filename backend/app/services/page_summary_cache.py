"""First-hit page summary cache (PageIndex-style, lazy).

Flowchart pages are indexed by their flattened (often scrambled) text, so they
can rank poorly. The first time the VLM reads a flowchart page it also emits a
concise, clean one-line summary; we cache it keyed by printed page code and
merge it into that page's searchable text so the page becomes findable next
time. Only pages that are actually used ever get a summary, so cost scales with
usage rather than corpus size.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Sequence

from backend.app.models import SearchDocument


class PageSummaryCache:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._summaries: Dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    self._summaries = {str(k): str(v) for k, v in data.items() if v}
            except (json.JSONDecodeError, OSError):
                self._summaries = {}

    @property
    def count(self) -> int:
        return len(self._summaries)

    def get(self, page_code: str) -> str:
        return self._summaries.get(page_code, "")

    def all_summaries(self) -> Dict[str, str]:
        return dict(self._summaries)

    def set_many(self, summaries: Dict[str, str]) -> bool:
        """Store new/updated summaries. Returns True if anything changed."""
        changed = False
        for code, summary in summaries.items():
            summary = (summary or "").strip()
            if not code or not summary:
                continue
            if self._summaries.get(code) != summary:
                self._summaries[code] = summary
                changed = True
        if changed:
            self._save()
        return changed

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._summaries, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def augment_documents(self, documents: Sequence[SearchDocument]) -> List[SearchDocument]:
        """Return a copy of documents with cached summaries appended to the
        matching clinical_guideline pages' searchable text."""
        if not self._summaries:
            return list(documents)
        out: List[SearchDocument] = []
        for doc in documents:
            summary = self._summaries.get(doc.printed_page_code or "")
            if summary and doc.page_type == "clinical_guideline":
                out.append(
                    SearchDocument(
                        source_id=doc.source_id,
                        page_type=doc.page_type,
                        pdf_page=doc.pdf_page,
                        text=f"{doc.text}\n[页面摘要] {summary}",
                        printed_page_code=doc.printed_page_code,
                        module_code=doc.module_code,
                        section=doc.section,
                        article_id=doc.article_id,
                        reference_ids=list(doc.reference_ids),
                        needs_review=doc.needs_review,
                    )
                )
            else:
                out.append(doc)
        return out
