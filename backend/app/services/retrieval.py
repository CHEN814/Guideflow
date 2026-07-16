from __future__ import annotations

from typing import Dict, Iterable, List, Tuple

from backend.app.models import MetadataFilters, NormalizedQuery, RetrievalHit
from backend.app.services.bm25_store import BM25Store
from backend.app.services.disease_scope import DiseaseScope, get_active_disease_scope
from backend.app.services.reranker import Reranker
from backend.app.services.tracing import TraceLogger
from backend.app.services.vector_store import VectorStoreProtocol


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


def reciprocal_rank_fusion(
    hit_groups: Iterable[List[RetrievalHit]], k: int = 60
) -> List[RetrievalHit]:
    by_source: Dict[str, RetrievalHit] = {}
    scores: Dict[str, float] = {}
    retrievers: Dict[str, List[str]] = {}

    for group in hit_groups:
        for hit in group:
            source_id = hit.document.source_id
            scores[source_id] = scores.get(source_id, 0.0) + 1.0 / (k + hit.rank)
            retrievers.setdefault(source_id, []).append(hit.retriever)
            if source_id not in by_source or hit.score > by_source[source_id].score:
                by_source[source_id] = hit

    fused = []
    for source_id, hit in by_source.items():
        hit.score = scores[source_id]
        hit.retriever = "+".join(sorted(set(retrievers[source_id])))
        hit.details["fusion_score"] = scores[source_id]
        fused.append(hit)
    fused.sort(reverse=True, key=lambda item: item.score)
    for rank, hit in enumerate(fused, start=1):
        hit.rank = rank
    return fused


class HybridRetriever:
    def __init__(
        self,
        bm25: BM25Store,
        vector_store: VectorStoreProtocol | None,
        reranker: Reranker,
        bm25_top_k: int,
        vector_top_k: int,
        rerank_top_k: int,
        final_top_k: int,
    ):
        self.bm25 = bm25
        # ``vector_store`` is None in BM25-only mode (default). When present the
        # retriever runs hybrid BM25 + vector with RRF fusion.
        self.vector_store = vector_store
        self.reranker = reranker
        self.bm25_top_k = bm25_top_k
        self.vector_top_k = vector_top_k
        self.rerank_top_k = rerank_top_k
        self.final_top_k = final_top_k

    def retrieve(
        self,
        normalized: NormalizedQuery,
        trace: TraceLogger | None = None,
    ) -> Tuple[List[RetrievalHit], Dict[str, object]]:
        route, filters, triggers = route_query(normalized)
        scope = get_active_disease_scope()
        mode = "hybrid" if self.vector_store is not None else "bm25"
        if trace:
            trace.log(
                "query_routed",
                {"route": route, "triggers": triggers, "disease_scope": scope.key, "retrieval_mode": mode},
            )
            trace.log("metadata_filters", filters.to_dict())

        bm25_hits = self.bm25.search(normalized.search_queries, filters, self.bm25_top_k)
        if trace:
            trace.log("retrieval_topk_raw", {"retriever": "bm25", "hits": [h.to_trace_dict() for h in bm25_hits]})

        vector_degraded: List[str] = []
        if self.vector_store is not None:
            vector_hits = self.vector_store.search(normalized.search_queries, filters, self.vector_top_k)
            vector_degraded = list(self.vector_store.degraded)
            if trace:
                trace.log("retrieval_topk_raw", {"retriever": "vector", "hits": [h.to_trace_dict() for h in vector_hits]})
            fused = reciprocal_rank_fusion([bm25_hits, vector_hits])[: self.rerank_top_k]
            if trace:
                trace.log("retrieval_fusion", {"hits": [h.to_trace_dict() for h in fused]})
        else:
            # BM25-only: a single ranked list, so RRF is a no-op and is skipped.
            fused = bm25_hits[: self.rerank_top_k]

        reranked, degraded = self.reranker.rerank(normalized.original, fused, self.final_top_k)
        if trace:
            trace.log("rerank_topk", {"degraded": degraded, "hits": [h.to_trace_dict() for h in reranked]})
            trace.log("retrieval_topk_final", {"hits": [h.to_trace_dict() for h in reranked]})

        diagnostics = {
            "route": route,
            "triggers": triggers,
            "disease_scope": scope.key,
            "retrieval_mode": mode,
            "filters": filters.to_dict(),
            "degraded": [item for item in [degraded, *vector_degraded] if item],
        }
        return reranked, diagnostics
