from __future__ import annotations

import math
import pickle
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

from backend.app.models import MetadataFilters, RetrievalHit, SearchDocument

try:
    import jieba
except ImportError:  # pragma: no cover
    jieba = None


TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9-]*|[0-9]+|[\u4e00-\u9fff]+")


def tokenize(text: str) -> List[str]:
    tokens = [token.lower() for token in TOKEN_RE.findall(text)]
    if jieba and re.search(r"[\u4e00-\u9fff]", text):
        tokens.extend(token.lower() for token in jieba.cut(text) if token.strip())
    return [token for token in tokens if len(token) > 1]


class BM25Store:
    def __init__(
        self,
        documents: Sequence[SearchDocument],
        tokenized: Sequence[List[str]] | None = None,
    ):
        self.documents = list(documents)
        self.tokenized = (
            list(tokenized)
            if tokenized is not None
            else [tokenize(doc.text) for doc in self.documents]
        )
        self.doc_freq: Dict[str, int] = defaultdict(int)
        self.term_freqs: List[Counter] = []
        self.doc_lengths: List[int] = []
        self.avgdl = 0.0
        self._build()

    def _build(self) -> None:
        total_len = 0
        for tokens in self.tokenized:
            tf = Counter(tokens)
            self.term_freqs.append(tf)
            self.doc_lengths.append(len(tokens))
            total_len += len(tokens)
            for token in tf:
                self.doc_freq[token] += 1
        self.avgdl = total_len / max(len(self.documents), 1)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as handle:
            pickle.dump({"documents": self.documents, "tokenized": self.tokenized}, handle)

    @classmethod
    def load(cls, path: Path) -> "BM25Store":
        with path.open("rb") as handle:
            data = pickle.load(handle)
        return cls(data["documents"], data["tokenized"])

    def search(
        self,
        queries: Iterable[str],
        filters: MetadataFilters | None = None,
        top_k: int = 10,
    ) -> List[RetrievalHit]:
        query_tokens = []
        for query in queries:
            query_tokens.extend(tokenize(query))
        query_tokens = list(dict.fromkeys(query_tokens))

        scores = []
        for index, document in enumerate(self.documents):
            if filters and not filters.matches(document):
                continue
            score = self._score(query_tokens, index)
            if score > 0:
                scores.append((score, index))
        scores.sort(reverse=True, key=lambda item: item[0])
        return [
            RetrievalHit(
                document=self.documents[index],
                score=float(score),
                retriever="bm25",
                rank=rank + 1,
                details={"matched_query_tokens": query_tokens},
            )
            for rank, (score, index) in enumerate(scores[:top_k])
        ]

    def _score(self, query_tokens: List[str], index: int) -> float:
        k1 = 1.5
        b = 0.75
        score = 0.0
        tf = self.term_freqs[index]
        doc_len = self.doc_lengths[index] or 1
        doc_count = len(self.documents)
        for token in query_tokens:
            freq = tf.get(token, 0)
            if not freq:
                continue
            df = self.doc_freq.get(token, 0)
            idf = math.log(1 + (doc_count - df + 0.5) / (df + 0.5))
            denom = freq + k1 * (1 - b + b * doc_len / max(self.avgdl, 1))
            score += idf * (freq * (k1 + 1) / denom)
        return score


def build_bm25_store(documents: Sequence[SearchDocument]) -> BM25Store:
    return BM25Store(documents)
