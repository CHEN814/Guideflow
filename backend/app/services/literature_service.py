"""Orchestrate PubMed abstract search: Q2Q → ladder ESearch → EFetch → rerank."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from backend.app.models import LiteratureHit
from backend.app.services.literature_query import (
    LiteratureConcepts,
    build_pubmed_query,
    extract_concepts,
)
from backend.app.services.literature_ranker import rank_articles
from backend.app.services.pubmed_client import PubmedClient


@dataclass
class LiteratureSearchResult:
    hits: List[LiteratureHit] = field(default_factory=list)
    degraded: Optional[str] = None
    diagnostics: Dict[str, Any] = field(default_factory=dict)


class LiteratureSearchService:
    def __init__(
        self,
        *,
        pubmed: PubmedClient,
        qwen_client: Any = None,
        candidate_k: int = 30,
        final_top_k: int = 5,
        recent_years: int = 5,
        min_count_l1: int = 5,
        min_count_l2: int = 3,
        max_count_tighten: int = 300,
    ):
        self.pubmed = pubmed
        self.qwen = qwen_client
        self.candidate_k = candidate_k
        self.final_top_k = final_top_k
        self.recent_years = recent_years
        self.min_count_l1 = min_count_l1
        self.min_count_l2 = min_count_l2
        self.max_count_tighten = max_count_tighten

    def search(self, question: str) -> LiteratureSearchResult:
        diagnostics: Dict[str, Any] = {
            "question": question,
            "ladder": [],
            "final_term": None,
            "count": 0,
            "concepts_source": None,
        }
        try:
            concepts = extract_concepts(question, self.qwen)
            diagnostics["concepts_source"] = concepts.source
            diagnostics["concepts"] = {
                "disease": concepts.disease,
                "biomarker": concepts.biomarker,
                "intervention": concepts.intervention,
                "outcome": concepts.outcome,
                "line_of_therapy": concepts.line_of_therapy,
                "focus": concepts.focus,
                "disease_keys": concepts.disease_keys,
            }

            pmids, term, count, ladder_trace = self._ladder_search(concepts)
            diagnostics["ladder"] = ladder_trace
            diagnostics["final_term"] = term
            diagnostics["count"] = count

            if not pmids:
                return LiteratureSearchResult(
                    hits=[],
                    degraded="literature_no_hits",
                    diagnostics=diagnostics,
                )

            articles = self.pubmed.efetch(pmids)
            diagnostics["fetched"] = len(articles)
            hits = rank_articles(articles, concepts, top_k=self.final_top_k)
            diagnostics["kept_pmids"] = [h.pmid for h in hits]
            return LiteratureSearchResult(hits=hits, diagnostics=diagnostics)
        except Exception as exc:
            diagnostics["error"] = f"{type(exc).__name__}:{exc}"
            return LiteratureSearchResult(
                hits=[],
                degraded="literature_unavailable",
                diagnostics=diagnostics,
            )

    def _ladder_search(
        self, concepts: LiteratureConcepts
    ) -> Tuple[List[str], Optional[str], int, List[Dict[str, Any]]]:
        ladder: List[Dict[str, Any]] = []
        last_pmids: List[str] = []
        last_term: Optional[str] = None
        last_count = 0

        for level in (1, 2, 3):
            term = build_pubmed_query(
                concepts, level=level, recent_years=self.recent_years, tighten=False
            )
            result = self.pubmed.esearch(term, retmax=self.candidate_k)
            count = int(result["count"])
            pmids = list(result["pmids"])
            entry = {
                "level": level,
                "term": term,
                "count": count,
                "pmid_count": len(pmids),
                "cached": result.get("cached"),
                "action": "accept",
            }

            if count > self.max_count_tighten and pmids:
                tight_term = build_pubmed_query(
                    concepts, level=level, recent_years=self.recent_years, tighten=True
                )
                tight = self.pubmed.esearch(tight_term, retmax=self.candidate_k)
                entry["tighten_term"] = tight_term
                entry["tighten_count"] = int(tight["count"])
                if tight["pmids"]:
                    term = tight_term
                    count = int(tight["count"])
                    pmids = list(tight["pmids"])
                    entry["action"] = "tighten"
                else:
                    entry["action"] = "tighten_empty_keep_broad"

            ladder.append(entry)
            last_pmids, last_term, last_count = pmids, term, count

            if level == 1 and count >= self.min_count_l1 and pmids:
                break
            if level == 2 and count >= self.min_count_l2 and pmids:
                break
            if level == 3:
                break
            # else relax to next level
            entry["action"] = f"relax_to_l{level + 1}"

        return last_pmids, last_term, last_count, ladder


def build_literature_service(
    settings: Any,
    qwen_client: Any = None,
) -> LiteratureSearchService:
    cache_dir = Path(getattr(settings, "literature_cache_dir", None) or "")
    if not cache_dir.parts:
        cache_dir = Path(settings.root_dir) / "data" / "cache" / "pubmed"
    client = PubmedClient(
        email=str(getattr(settings, "ncbi_email", None) or "guideflow@example.com"),
        api_key=getattr(settings, "ncbi_api_key", None),
        tool=str(getattr(settings, "ncbi_tool", None) or "guideflow"),
        cache_dir=cache_dir,
        esearch_timeout_s=float(getattr(settings, "literature_esearch_timeout_s", 2.0)),
        efetch_timeout_s=float(getattr(settings, "literature_efetch_timeout_s", 3.0)),
    )
    return LiteratureSearchService(
        pubmed=client,
        qwen_client=qwen_client,
        candidate_k=int(getattr(settings, "literature_candidate_k", 30)),
        final_top_k=int(getattr(settings, "literature_final_top_k", 5)),
        recent_years=int(getattr(settings, "literature_recent_years", 5)),
    )


_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="lit")


def submit_literature_search(
    service: LiteratureSearchService, question: str
):
    """Run literature search on a background thread; returns a Future."""
    return _EXECUTOR.submit(service.search, question)
