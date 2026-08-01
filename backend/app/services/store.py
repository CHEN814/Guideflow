from __future__ import annotations

import json
from pathlib import Path

from backend.app.models import KnowledgeChunk, SearchDocument, StructuredKnowledgeBase
from typing import Iterable, List


def save_knowledge_base(path: Path, kb: StructuredKnowledgeBase) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(kb.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")


def save_knowledge_chunks(path: Path, kb: StructuredKnowledgeBase) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "count": len(kb.to_chunks()),
        "chunks": [chunk.to_dict() for chunk in kb.to_chunks()],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_knowledge_chunks(path: Path) -> List[KnowledgeChunk]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        records = data.get("chunks", [])
    else:
        records = data
    return [KnowledgeChunk.from_dict(item) for item in records]


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
