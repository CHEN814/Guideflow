from __future__ import annotations

from typing import Iterable, List, Tuple

from backend.app.models import RetrievalHit
from backend.app.services.bm25_store import tokenize


class Reranker:
    def rerank(self, question: str, hits: Iterable[RetrievalHit], top_k: int) -> Tuple[List[RetrievalHit], str | None]:
        raise NotImplementedError


class CrossEncoderReranker(Reranker):
    def __init__(self, model_name: str):
        from sentence_transformers import CrossEncoder

        self.model = CrossEncoder(model_name)

    def rerank(self, question: str, hits: Iterable[RetrievalHit], top_k: int) -> Tuple[List[RetrievalHit], str | None]:
        hits = list(hits)
        pairs = [(question, hit.document.text) for hit in hits]
        scores = self.model.predict(pairs)
        reranked = []
        for hit, score in zip(hits, scores):
            hit.score = float(score)
            hit.retriever = f"{hit.retriever}+reranker"
            hit.details["rerank_score"] = float(score)
            reranked.append(hit)
        reranked.sort(reverse=True, key=lambda item: item.score)
        for rank, hit in enumerate(reranked[:top_k], start=1):
            hit.rank = rank
        return reranked[:top_k], None


class LexicalReranker(Reranker):
    def rerank(self, question: str, hits: Iterable[RetrievalHit], top_k: int) -> Tuple[List[RetrievalHit], str | None]:
        q_tokens = set(tokenize(question))
        reranked = []
        for hit in hits:
            d_tokens = set(tokenize(hit.document.text))
            overlap = len(q_tokens & d_tokens) / max(len(q_tokens), 1)
            combined = hit.score + overlap
            hit.details["lexical_overlap"] = overlap
            hit.details["pre_rerank_score"] = hit.score
            hit.score = combined
            hit.retriever = f"{hit.retriever}+lexical_reranker"
            reranked.append(hit)
        reranked.sort(reverse=True, key=lambda item: item.score)
        for rank, hit in enumerate(reranked[:top_k], start=1):
            hit.rank = rank
        return reranked[:top_k], "reranker_disabled_lexical_fallback"


def load_reranker(model_name: str) -> Reranker:
    if model_name.lower() in {"lexical", "lexical_reranker", "disabled"}:
        return LexicalReranker()

    try:
        return CrossEncoderReranker(model_name)
    except Exception:
        return LexicalReranker()
