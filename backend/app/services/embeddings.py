from __future__ import annotations

import hashlib
import logging
import math
import warnings
from typing import Iterable, List, Tuple

import numpy as np

logger = logging.getLogger(__name__)


class EmbeddingModel:
    def embed(self, texts: Iterable[str]) -> Tuple[List[List[float]], str | None]:
        raise NotImplementedError


class SentenceTransformerEmbedding(EmbeddingModel):
    def __init__(self, model_name: str):
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name
        self.model = SentenceTransformer(model_name)

    def embed(self, texts: Iterable[str]) -> Tuple[List[List[float]], str | None]:
        vectors = self.model.encode(list(texts), normalize_embeddings=True)
        return vectors.tolist(), None


class HashEmbedding(EmbeddingModel):
    def __init__(self, dim: int = 384):
        self.dim = dim

    def embed(self, texts: Iterable[str]) -> Tuple[List[List[float]], str | None]:
        vectors = []
        for text in texts:
            vector = np.zeros(self.dim, dtype=np.float32)
            for token in text.lower().split():
                digest = hashlib.md5(token.encode("utf-8")).hexdigest()
                index = int(digest[:8], 16) % self.dim
                sign = 1 if int(digest[8:10], 16) % 2 == 0 else -1
                vector[index] += sign
            norm = math.sqrt(float(np.dot(vector, vector))) or 1.0
            vectors.append((vector / norm).tolist())
        return vectors, "hash_embedding_fallback"


def load_embedding_model(model_name: str) -> EmbeddingModel:
    if model_name.lower() in {"hash", "hash_embedding", "local_hash"}:
        return HashEmbedding()

    try:
        return SentenceTransformerEmbedding(model_name)
    except Exception as exc:
        warnings.warn(
            f"Failed to load embedding model {model_name!r}: {exc}. "
            "Falling back to hash embedding (hash_embedding_fallback).",
            stacklevel=2,
        )
        logger.warning("Embedding model load failed for %s: %s", model_name, exc)
        return HashEmbedding()
