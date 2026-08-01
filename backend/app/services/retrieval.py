from __future__ import annotations

from typing import Dict, List, Tuple

from backend.app.models import MetadataFilters, NormalizedQuery, RetrievalHit, SearchDocument
from backend.app.services.bm25_store import BM25Store
from backend.app.services.chunk_embedding_index import ChunkEmbeddingIndex
from backend.app.services.disease_scope import DiseaseScope, get_active_disease_scope
from backend.app.services.reranker import Reranker
from backend.app.services.tracing import TraceLogger


FLOW_KEYWORDS = [
    "治疗路径", "下一步", "流程", "一线", "二线", "复发", "难治",
    "workup", "therapy", "treatment", "algorithm", "pathway",
]
EVIDENCE_KEYWORDS = [
    "预后", "意义", "突变", "reference", "证据", "分型",
    "prognosis", "mutation", "definition", "diagnosis",
]


def _apply_disease_scope(filters: MetadataFilters, scope: DiseaseScope) -> MetadataFilters:
    return MetadataFilters(
        page_types=list(filters.page_types),
        module_codes=list(scope.module_codes),
        article_ids=list(scope.article_ids),
        sections=list(filters.sections),
    )


def route_query(
    normalized: NormalizedQuery,
    disease_scope: DiseaseScope | None = None,
) -> Tuple[str, MetadataFilters, List[str]]:
    """Tag question style (flowchart / evidence / hybrid). Does not change page_types."""
    scope = disease_scope or get_active_disease_scope()
    text = " ".join(normalized.search_queries).lower()
    flow_hits = [kw for kw in FLOW_KEYWORDS if kw.lower() in text]
    evidence_hits = [kw for kw in EVIDENCE_KEYWORDS if kw.lower() in text]

    searchable_page_types = ["clinical_guideline", "discussion"]
    if flow_hits and evidence_hits:
        route = "hybrid"
        filters = MetadataFilters(page_types=searchable_page_types)
    elif flow_hits:
        route = "flowchart"
        filters = MetadataFilters(page_types=searchable_page_types)
    else:
        route = "evidence"
        filters = MetadataFilters(page_types=searchable_page_types)

    filters = _apply_disease_scope(filters, scope)
    triggers = sorted(set(flow_hits + evidence_hits))
    return route, filters, triggers


def resolve_scope(
    question: str,
    disease_scope: DiseaseScope | None = None,
) -> DiseaseScope:
    """Prefer an explicit scope; otherwise detect from the question text."""
    if disease_scope is not None:
        return disease_scope
    from backend.app.services.disease_scope import detect_disease_scope

    return detect_disease_scope(question)


class Bm25Retriever:
    """BM25 retrieve + lexical/cross-encoder rerank. No vector similarity path."""

    def __init__(
        self,
        bm25: BM25Store,
        reranker: Reranker,
        bm25_top_k: int,
        rerank_top_k: int,
        final_top_k: int,
    ):
        self.bm25 = bm25
        self.reranker = reranker
        self.bm25_top_k = bm25_top_k
        self.rerank_top_k = rerank_top_k
        self.final_top_k = final_top_k

    def retrieve(
        self,
        normalized: NormalizedQuery,
        trace: TraceLogger | None = None,
        disease_scope: DiseaseScope | None = None,
    ) -> Tuple[List[RetrievalHit], Dict[str, object]]:
        scope = resolve_scope(normalized.original, disease_scope)
        route, filters, triggers = route_query(normalized, disease_scope=scope)
        if trace:
            trace.log(
                "query_routed",
                {
                    "route": route,
                    "triggers": triggers,
                    "disease_scope": scope.key,
                    "retrieval_mode": "bm25",
                    "article_ids": list(scope.article_ids),
                    "module_codes": list(scope.module_codes),
                },
            )
            trace.log("metadata_filters", filters.to_dict())

        bm25_hits = self.bm25.search(normalized.search_queries, filters, self.bm25_top_k)
        if trace:
            trace.log(
                "retrieval_topk_raw",
                {"retriever": "bm25", "hits": [h.to_trace_dict() for h in bm25_hits]},
            )

        shortlist = bm25_hits[: self.rerank_top_k]
        reranked, degraded = self.reranker.rerank(normalized.original, shortlist, self.final_top_k)
        if trace:
            trace.log(
                "rerank_topk",
                {"degraded": degraded, "hits": [h.to_trace_dict() for h in reranked]},
            )
            trace.log("retrieval_topk_final", {"hits": [h.to_trace_dict() for h in reranked]})

        diagnostics = {
            "route": route,
            "triggers": triggers,
            "disease_scope": scope.key,
            "retrieval_mode": "bm25",
            "filters": filters.to_dict(),
            "degraded": [item for item in [degraded] if item],
        }
        return reranked, diagnostics


class HybridRetriever(Bm25Retriever):
    """BM25 + embedding hybrid retriever."""

    def __init__(
        self,
        bm25: BM25Store,
        reranker: Reranker,
        bm25_top_k: int,
        rerank_top_k: int,
        final_top_k: int,
        chunk_index: ChunkEmbeddingIndex | None = None,
        embedding_weight: float = 0.4,
        bm25_weight: float = 0.6,
    ):
        super().__init__(bm25=bm25, reranker=reranker, bm25_top_k=bm25_top_k, rerank_top_k=rerank_top_k, final_top_k=final_top_k)
        self.chunk_index = chunk_index
        self.embedding_weight = embedding_weight
        self.bm25_weight = bm25_weight

    @staticmethod
    def _doc_key(hit: RetrievalHit) -> str:
        return hit.document.source_id

    @staticmethod
    def _to_hit(record: Dict[str, object], rank: int) -> RetrievalHit:
        doc = SearchDocument(
            source_id=str(record.get("source_id", "")),
            page_type=str(record.get("page_type", "discussion")),
            pdf_page=int(record.get("pdf_page", 0)),
            text=str(record.get("text", "")),
            printed_page_code=record.get("printed_page_code") if record.get("printed_page_code") is not None else None,
            module_code=record.get("module_code") if record.get("module_code") is not None else None,
            section=record.get("section") if record.get("section") is not None else None,
            article_id=record.get("article_id") if record.get("article_id") is not None else None,
            reference_ids=list(record.get("reference_ids", []) or []),
            needs_review=False,
        )
        return RetrievalHit(
            document=doc,
            score=float(record.get("score", 0.0)),
            retriever="embedding",
            rank=rank,
            details={
                "chunk_id": record.get("chunk_id"),
                "embedding_model": record.get("embedding_model"),
                "embedding_dim": record.get("embedding_dim"),
                "text_hash": record.get("text_hash"),
            },
        )

    def _embedding_search(self, query: str, top_k: int) -> List[RetrievalHit]:
        if self.chunk_index is None:
            return []
        try:
            results = self.chunk_index.search(query, top_k=top_k)
        except Exception:
            return []
        hits: List[RetrievalHit] = []
        for rank, record in enumerate(results, start=1):
            hits.append(self._to_hit(record, rank))
        return hits

    def _merge_hits(self, bm25_hits: List[RetrievalHit], embedding_hits: List[RetrievalHit]) -> List[RetrievalHit]:
        merged: Dict[str, RetrievalHit] = {}
        for hit in bm25_hits:
            merged[self._doc_key(hit)] = hit
        for hit in embedding_hits:
            key = self._doc_key(hit)
            existing = merged.get(key)
            if existing is None:
                merged[key] = hit
                continue
            merged[key] = RetrievalHit(
                document=existing.document,
                score=max(existing.score * self.bm25_weight, hit.score * self.embedding_weight),
                retriever="hybrid",
                rank=min(existing.rank, hit.rank),
                details={**existing.details, **hit.details, "bm25_score": existing.score, "embedding_score": hit.score},
            )
        return sorted(merged.values(), key=lambda h: (h.score, h.document.needs_review is False), reverse=True)

    def retrieve(
        self,
        normalized: NormalizedQuery,
        trace: TraceLogger | None = None,
        disease_scope: DiseaseScope | None = None,
    ) -> Tuple[List[RetrievalHit], Dict[str, object]]:
        scope = resolve_scope(normalized.original, disease_scope)
        route, filters, triggers = route_query(normalized, disease_scope=scope)
        if trace:
            trace.log(
                "query_routed",
                {
                    "route": route,
                    "triggers": triggers,
                    "disease_scope": scope.key,
                    "retrieval_mode": "hybrid",
                    "article_ids": list(scope.article_ids),
                    "module_codes": list(scope.module_codes),
                },
            )
            trace.log("metadata_filters", filters.to_dict())

        bm25_hits = self.bm25.search(normalized.search_queries, filters, self.bm25_top_k)
        embedding_hits = self._embedding_search(normalized.original, top_k=self.bm25_top_k)
        if trace:
            trace.log(
                "retrieval_topk_raw",
                {
                    "retriever": "bm25",
                    "hits": [h.to_trace_dict() for h in bm25_hits],
                },
            )
            trace.log(
                "retrieval_topk_embedding",
                {
                    "retriever": "embedding",
                    "hits": [
                        {
                            **h.to_trace_dict(),
                            "details": {**h.details, "hybrid_score": h.score},
                        }
                        for h in embedding_hits
                    ],
                },
            )

        merged = self._merge_hits(bm25_hits[: self.rerank_top_k], embedding_hits[: self.rerank_top_k])
        shortlist = merged[: self.rerank_top_k]
        reranked, degraded = self.reranker.rerank(normalized.original, shortlist, self.final_top_k)
        if trace:
            trace.log(
                "rerank_topk",
                {"degraded": degraded, "hits": [h.to_trace_dict() for h in reranked]},
            )
            trace.log("retrieval_topk_final", {"hits": [h.to_trace_dict() for h in reranked]})

        diagnostics = {
            "route": route,
            "triggers": triggers,
            "disease_scope": scope.key,
            "retrieval_mode": "hybrid",
            "filters": filters.to_dict(),
            "degraded": [item for item in [degraded] if item],
            "bm25_count": len(bm25_hits),
            "embedding_count": len(embedding_hits),
            "merged_count": len(merged),
        }
        return reranked, diagnostics


# Backward-compatible alias used by older imports/tests.
BaseRetriever = Bm25Retriever
