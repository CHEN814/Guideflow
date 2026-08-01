from __future__ import annotations

import json
import hashlib
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence

import numpy as np

try:
    import faiss  # type: ignore
except ImportError:  # pragma: no cover
    faiss = None

try:
    from sentence_transformers import SentenceTransformer  # type: ignore
except Exception:  # pragma: no cover
    SentenceTransformer = None

from backend.app.models import KnowledgeChunk


@dataclass
class ChunkEmbeddingRecord:
    chunk_id: str
    source_id: str
    page_type: str
    pdf_page: int
    section: str | None
    printed_page_code: str | None
    module_code: str | None
    article_id: str | None
    reference_ids: List[str]
    order: int
    text: str
    embedding_model: str
    embedding_dim: int
    text_hash: str

    def to_dict(self) -> Dict[str, object]:
        return {
            "chunk_id": self.chunk_id,
            "source_id": self.source_id,
            "page_type": self.page_type,
            "pdf_page": self.pdf_page,
            "section": self.section,
            "printed_page_code": self.printed_page_code,
            "module_code": self.module_code,
            "article_id": self.article_id,
            "reference_ids": list(self.reference_ids),
            "order": self.order,
            "text": self.text,
            "embedding_model": self.embedding_model,
            "embedding_dim": self.embedding_dim,
            "text_hash": self.text_hash,
        }


class ChunkEmbeddingIndex:
    def __init__(self, model_name: str = "bge-m3") -> None:
        self.model_name = model_name
        self.model = SentenceTransformer(model_name) if SentenceTransformer is not None else None
        self.index = None
        self.records: List[ChunkEmbeddingRecord] = []
        self.embeddings: np.ndarray | None = None
        self.vocab: Dict[str, int] = {}

    @staticmethod
    def _hash_text(text: str) -> str:
        return hashlib.sha1(text.encode("utf-8")).hexdigest()

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        return [t.lower() for t in re.findall(r"[A-Za-z][A-Za-z0-9-]*|[\u4e00-\u9fff]+|[0-9]+", text) if len(t) > 1]

    def _fallback_embed(self, texts: Sequence[str]) -> np.ndarray:
        vocab: Dict[str, int] = {}
        tokenized = [self._tokenize(text) for text in texts]
        for toks in tokenized:
            for tok in toks:
                vocab.setdefault(tok, len(vocab))
        dim = max(64, min(256, len(vocab) * 2 or 64))
        vectors = np.zeros((len(texts), dim), dtype="float32")
        for i, toks in enumerate(tokenized):
            if not toks:
                continue
            counts = Counter(toks)
            for tok, cnt in counts.items():
                j = abs(hash(tok)) % dim
                vectors[i, j] += float(cnt)
            norm = np.linalg.norm(vectors[i]) or 1.0
            vectors[i] /= norm
        self.vocab = vocab
        return vectors

    def build(self, chunks: Sequence[KnowledgeChunk]) -> None:
        texts = [chunk.text.strip() for chunk in chunks if chunk.text.strip()]
        if not texts:
            self.records = []
            self.embeddings = np.zeros((0, 0), dtype="float32")
            self.index = None
            return
        if self.model is not None:
            vectors = self.model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
            vectors = np.asarray(vectors, dtype="float32")
            embedding_model = self.model_name
        else:
            vectors = self._fallback_embed(texts)
            embedding_model = f"fallback:{self.model_name}"
        self.embeddings = vectors
        self.index = faiss.IndexFlatIP(vectors.shape[1]) if faiss is not None else None
        if self.index is not None:
            self.index.add(vectors)
        self.records = [
            ChunkEmbeddingRecord(
                chunk_id=chunk.chunk_id,
                source_id=chunk.source_id,
                page_type=chunk.page_type,
                pdf_page=chunk.pdf_page,
                section=chunk.section,
                printed_page_code=chunk.printed_page_code,
                module_code=chunk.module_code,
                article_id=chunk.article_id,
                reference_ids=list(chunk.reference_ids),
                order=chunk.order,
                text=chunk.text,
                embedding_model=embedding_model,
                embedding_dim=int(vectors.shape[1]),
                text_hash=self._hash_text(chunk.text),
            )
            for chunk in chunks
            if chunk.text.strip()
        ]

    def save(self, index_path: Path, meta_path: Path) -> None:
        if self.index is None or self.embeddings is None:
            raise RuntimeError("index has not been built")
        index_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        if faiss is not None:
            payload = faiss.serialize_index(self.index)
            with index_path.open("wb") as handle:
                handle.write(bytes(payload))
        else:
            np.save(index_path.with_suffix(".npy"), self.embeddings)
        meta_path.write_text(
            json.dumps({"model_name": self.model_name, "records": [r.to_dict() for r in self.records]}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, index_path: Path, meta_path: Path) -> "ChunkEmbeddingIndex":
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        model_name = meta.get("model_name", "bge-m3")
        inst = cls(model_name=model_name)
        inst.records = [ChunkEmbeddingRecord(**item) for item in meta.get("records", [])]
        if faiss is not None and index_path.exists():
            try:
                inst.index = faiss.deserialize_index(index_path.read_bytes())
            except Exception:
                inst.index = faiss.read_index(str(index_path))
        elif index_path.with_suffix(".npy").exists():
            inst.embeddings = np.load(index_path.with_suffix(".npy"))
        return inst

    def search(self, query: str, top_k: int = 8) -> List[Dict[str, object]]:
        if self.index is None:
            raise RuntimeError("FAISS index is not built")
        if self.model is not None:
            q = np.asarray(self.model.encode([query], normalize_embeddings=True, show_progress_bar=False), dtype="float32")
        else:
            q = self._fallback_embed([query])
        scores, ids = self.index.search(q, top_k)
        results: List[Dict[str, object]] = []
        for score, idx in zip(scores[0].tolist(), ids[0].tolist()):
            if idx < 0 or idx >= len(self.records):
                continue
            rec = self.records[idx]
            results.append({"score": float(score), **rec.to_dict()})
        return results
