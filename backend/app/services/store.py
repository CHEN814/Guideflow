from __future__ import annotations

import json
from pathlib import Path

from backend.app.models import SearchDocument, StructuredKnowledgeBase
from typing import Iterable, List


def save_knowledge_base(path: Path, kb: StructuredKnowledgeBase) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(kb.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")


def load_knowledge_base(path: Path) -> StructuredKnowledgeBase:
    data = json.loads(path.read_text(encoding="utf-8"))
    return StructuredKnowledgeBase.from_dict(data)


def filter_documents(
    documents: Iterable[SearchDocument],
    page_types: List[str] | None = None,
) -> List[SearchDocument]:
    if not page_types:
        return list(documents)
    allowed = set(page_types)
    return [doc for doc in documents if doc.page_type in allowed]
