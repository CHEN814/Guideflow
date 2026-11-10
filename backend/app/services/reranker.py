from __future__ import annotations

import os
from typing import Iterable, List, Tuple

import requests

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


class BailianReranker(Reranker):
    """百炼重排：只走与问答相同的账号和 base_url，只打配置里的那一个模型。"""

    def __init__(
        self,
        model_name: str,
        api_key: str | None = None,
        base_url: str | None = None,
    ):
        self.model_name = model_name
        self.api_key = api_key or os.getenv("QWEN_API_KEY")
        raw = (base_url or os.getenv("QWEN_BASE_URL") or "").rstrip("/")
        if raw.endswith("/chat/completions"):
            raw = raw[: -len("/chat/completions")]
        self.base_url = raw
        self.endpoint = f"{self.base_url}/reranks" if self.base_url else ""

    def rerank(self, question: str, hits: Iterable[RetrievalHit], top_k: int) -> Tuple[List[RetrievalHit], str | None]:
        hits = list(hits)
        if not hits:
            return [], None
        if not self.api_key or not self.endpoint:
            fallback = LexicalReranker()
            ranked, _ = fallback.rerank(question, hits, top_k)
            return ranked, "bailian_rerank_no_key_lexical_fallback"
        documents = [(hit.document.text or "")[:4000] for hit in hits]
        payload = {
            "model": self.model_name,
            "query": question,
            "documents": documents,
            "top_n": min(top_k, len(documents)),
        }
        try:
            resp = requests.post(
                self.endpoint,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=30,
            )
            resp.raise_for_status()
            body = resp.json()
            results = body.get("results") or (body.get("output") or {}).get("results") or []
            if not results:
                raise ValueError("empty rerank results")
            scored: List[RetrievalHit] = []
            for item in results:
                idx = int(item.get("index", 0))
                if idx < 0 or idx >= len(hits):
                    continue
                hit = hits[idx]
                score = float(item.get("relevance_score", item.get("score", 0.0)))
                hit.details["pre_rerank_score"] = hit.score
                hit.details["rerank_score"] = score
                hit.score = score
                hit.retriever = f"{hit.retriever}+bailian_rerank"
                scored.append(hit)
            scored.sort(reverse=True, key=lambda item: item.score)
            for rank, hit in enumerate(scored[:top_k], start=1):
                hit.rank = rank
            return scored[:top_k], None
        except Exception as exc:
            fallback = LexicalReranker()
            ranked, _ = fallback.rerank(question, hits, top_k)
            return ranked, f"bailian_rerank_failed:{type(exc).__name__}"


def load_reranker(
    model_name: str,
    api_key: str | None = None,
    base_url: str | None = None,
) -> Reranker:
    name = (model_name or "lexical").strip()
    lowered = name.lower()
    if lowered in {"lexical", "lexical_reranker", "disabled", ""}:
        return LexicalReranker()
    if "rerank" in lowered or lowered.startswith("gte-"):
        return BailianReranker(name, api_key=api_key, base_url=base_url)
    try:
        return CrossEncoderReranker(name)
    except Exception:
        return LexicalReranker()
