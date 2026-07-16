from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, List, Sequence

import numpy as np

from backend.app.models import MetadataFilters, RetrievalHit, SearchDocument
from backend.app.services.embeddings import EmbeddingModel


class VectorStoreProtocol:
    degraded: List[str]

    def build(self, documents: Sequence[SearchDocument]) -> List[str]:
        raise NotImplementedError

    def load(self) -> List[str]:
        raise NotImplementedError

    def search(
        self,
        queries: Iterable[str],
        filters: MetadataFilters | None = None,
        top_k: int = 10,
    ) -> List[RetrievalHit]:
        raise NotImplementedError


class LocalVectorStore:
    def __init__(self, index_dir: Path, embedding_model: EmbeddingModel):
        self.index_dir = index_dir
        self.embedding_model = embedding_model
        self.documents: List[SearchDocument] = []
        self.vectors: np.ndarray | None = None
        self.degraded: List[str] = []

    @property
    def index_path(self) -> Path:
        return self.index_dir / "vectors.json"

    def build(self, documents: Sequence[SearchDocument]) -> List[str]:
        self.index_dir.mkdir(parents=True, exist_ok=True)
        vectors, degraded = self.embedding_model.embed([doc.text for doc in documents])
        self.documents = list(documents)
        self.vectors = np.asarray(vectors, dtype=np.float32)
        if degraded:
            self.degraded.append(degraded)
        payload = {
            "documents": [doc.to_dict() for doc in self.documents],
            "vectors": self.vectors.tolist(),
            "degraded": self.degraded,
        }
        self.index_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return self.degraded

    def load(self) -> List[str]:
        payload = json.loads(self.index_path.read_text(encoding="utf-8"))
        self.documents = [SearchDocument.from_dict(item) for item in payload["documents"]]
        self.vectors = np.asarray(payload["vectors"], dtype=np.float32)
        self.degraded = list(payload.get("degraded", []))
        return self.degraded

    def search(
        self,
        queries: Iterable[str],
        filters: MetadataFilters | None = None,
        top_k: int = 10,
    ) -> List[RetrievalHit]:
        if self.vectors is None:
            self.load()
        assert self.vectors is not None

        query_vectors, degraded = self.embedding_model.embed(list(queries))
        if degraded and degraded not in self.degraded:
            self.degraded.append(degraded)
        if not query_vectors:
            return []

        query_matrix = np.asarray(query_vectors, dtype=np.float32)
        scores = np.max(np.matmul(self.vectors, query_matrix.T), axis=1)
        candidates = []
        for index, score in enumerate(scores):
            document = self.documents[index]
            if filters and not filters.matches(document):
                continue
            candidates.append((float(score), index))
        candidates.sort(reverse=True, key=lambda item: item[0])
        return [
            RetrievalHit(
                document=self.documents[index],
                score=score,
                retriever="vector",
                rank=rank + 1,
                details={"degraded": self.degraded},
            )
            for rank, (score, index) in enumerate(candidates[:top_k])
        ]


class ChromaVectorStore:
    def __init__(self, index_dir: Path, embedding_model: EmbeddingModel):
        import chromadb

        self.index_dir = index_dir
        self.embedding_model = embedding_model
        self.client = chromadb.PersistentClient(path=str(index_dir))
        self.collection = self.client.get_or_create_collection("nccn_sources")
        self.degraded: List[str] = []

    def build(self, documents: Sequence[SearchDocument]) -> List[str]:
        if self.collection.count():
            existing = self.collection.get(include=[])
            ids = existing.get("ids", [])
            if ids:
                self.collection.delete(ids=ids)
        vectors, degraded = self.embedding_model.embed([doc.text for doc in documents])
        if degraded:
            self.degraded.append(degraded)
        self.collection.add(
            ids=[doc.source_id for doc in documents],
            documents=[doc.text for doc in documents],
            embeddings=vectors,
            metadatas=[_chroma_metadata(doc) for doc in documents],
        )
        (self.index_dir / "backend.txt").write_text("chromadb", encoding="utf-8")
        return self.degraded

    def load(self) -> List[str]:
        return self.degraded

    @property
    def documents(self) -> List[SearchDocument]:
        data = self.collection.get(include=["documents", "metadatas"])
        docs = []
        for source_id, text, metadata in zip(
            data.get("ids", []),
            data.get("documents", []),
            data.get("metadatas", []),
        ):
            docs.append(_document_from_chroma(source_id, text, metadata or {}))
        return docs

    def search(
        self,
        queries: Iterable[str],
        filters: MetadataFilters | None = None,
        top_k: int = 10,
    ) -> List[RetrievalHit]:
        query_list = list(queries)
        vectors, degraded = self.embedding_model.embed(query_list)
        if degraded and degraded not in self.degraded:
            self.degraded.append(degraded)
        results = self.collection.query(
            query_embeddings=vectors,
            n_results=max(top_k * 4, top_k),
            include=["documents", "metadatas", "distances"],
        )
        candidates = {}
        for row_ids, row_docs, row_metas, row_distances in zip(
            results.get("ids", []),
            results.get("documents", []),
            results.get("metadatas", []),
            results.get("distances", []),
        ):
            for source_id, text, metadata, distance in zip(
                row_ids, row_docs, row_metas, row_distances
            ):
                doc = _document_from_chroma(source_id, text, metadata or {})
                if filters and not filters.matches(doc):
                    continue
                score = 1.0 / (1.0 + float(distance))
                if source_id not in candidates or score > candidates[source_id][0]:
                    candidates[source_id] = (score, doc)
        ranked = sorted(candidates.values(), reverse=True, key=lambda item: item[0])[:top_k]
        return [
            RetrievalHit(
                document=doc,
                score=score,
                retriever="vector_chroma",
                rank=rank + 1,
                details={"degraded": self.degraded},
            )
            for rank, (score, doc) in enumerate(ranked)
        ]


def create_vector_store(index_dir: Path, embedding_model: EmbeddingModel) -> VectorStoreProtocol:
    # Prefer LocalVectorStore (pure local, no network) unless the index was explicitly
    # built with ChromaDB (signalled by backend.txt).
    if (index_dir / "vectors.json").exists():
        return LocalVectorStore(index_dir, embedding_model)
    backend_file = index_dir / "backend.txt"
    if backend_file.exists() and backend_file.read_text(encoding="utf-8").strip() == "chromadb":
        try:
            return ChromaVectorStore(index_dir, embedding_model)
        except Exception:
            store = LocalVectorStore(index_dir, embedding_model)
            store.degraded.append("chromadb_unavailable_local_vector_store")
            return store
    return LocalVectorStore(index_dir, embedding_model)


def _chroma_metadata(doc: SearchDocument) -> dict:
    return {
        "page_type": doc.page_type,
        "pdf_page": doc.pdf_page,
        "printed_page_code": doc.printed_page_code or "",
        "module_code": doc.module_code or "",
        "section": doc.section or "",
        "article_id": doc.article_id or "",
        "reference_ids": ",".join(doc.reference_ids),
        "needs_review": int(doc.needs_review),
    }


def _document_from_chroma(source_id: str, text: str, metadata: dict) -> SearchDocument:
    reference_ids = [
        item for item in str(metadata.get("reference_ids", "")).split(",") if item
    ]
    return SearchDocument(
        source_id=source_id,
        page_type=str(metadata.get("page_type", "")),
        pdf_page=int(metadata.get("pdf_page", 0)),
        text=text or "",
        printed_page_code=str(metadata.get("printed_page_code") or "") or None,
        module_code=str(metadata.get("module_code") or "") or None,
        section=str(metadata.get("section") or "") or None,
        article_id=str(metadata.get("article_id") or "") or None,
        reference_ids=reference_ids,
        needs_review=bool(int(metadata.get("needs_review", 0))),
    )
