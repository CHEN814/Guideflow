from __future__ import annotations

from typing import Dict, List, Tuple

from backend.app.models import MetadataFilters, NormalizedQuery, RetrievalHit
from backend.app.services.bm25_store import BM25Store
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


# Backward-compatible alias used by older imports/tests.
HybridRetriever = Bm25Retriever
