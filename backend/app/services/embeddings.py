from __future__ import annotations

import hashlib
import re
from functools import lru_cache

import numpy as np
from sklearn.feature_extraction.text import HashingVectorizer

from app.core.config import get_settings

TOKEN_RE = re.compile(r"[a-z0-9%]+", re.I)


class Embedder:
    """Vector embeddings for scientific chunks.

    Default backend is a hashing n-gram encoder so the prototype runs offline.
    Optional backends: sentence-transformers, OpenAI embeddings.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self.backend = settings.embedding_backend.lower()
        self.model_name = settings.embedding_model
        self.dim = 384
        self._vectorizer = HashingVectorizer(
            n_features=self.dim,
            alternate_sign=False,
            ngram_range=(1, 2),
            norm="l2",
            lowercase=True,
        )
        self._st_model = None
        if self.backend == "sentence-transformers":
            try:
                from sentence_transformers import SentenceTransformer

                self._st_model = SentenceTransformer(self.model_name)
                self.dim = int(self._st_model.get_sentence_embedding_dimension())
            except Exception:
                self.backend = "hashing"

    def encode(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        if self.backend == "openai":
            vectors = self._openai_encode(texts)
            if vectors is not None:
                return vectors
        if self.backend == "sentence-transformers" and self._st_model is not None:
            matrix = self._st_model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
            return np.asarray(matrix, dtype=np.float32)
        matrix = self._vectorizer.transform(texts).astype(np.float32).toarray()
        return matrix

    def _openai_encode(self, texts: list[str]) -> np.ndarray | None:
        settings = get_settings()
        if not settings.openai_api_key:
            return None
        try:
            import httpx

            payload = {"model": "text-embedding-3-small", "input": texts}
            response = httpx.post(
                "https://api.openai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                json=payload,
                timeout=45.0,
            )
            response.raise_for_status()
            data = response.json()["data"]
            vectors = np.array([item["embedding"] for item in data], dtype=np.float32)
            norms = np.linalg.norm(vectors, axis=1, keepdims=True) + 1e-12
            self.dim = vectors.shape[1]
            return vectors / norms
        except Exception:
            return None


@lru_cache
def get_embedder() -> Embedder:
    return Embedder()


def content_checksum(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
