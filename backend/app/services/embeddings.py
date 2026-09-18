from __future__ import annotations

from functools import lru_cache

import numpy as np

from app.core.config import get_settings


class Embedder:
    """Semantic embeddings. Production backend is sentence-transformers MiniLM."""

    def __init__(self) -> None:
        settings = get_settings()
        self.backend = settings.embedding_backend.lower().strip()
        self.model_name = settings.embedding_model
        self.dim = 384
        self._st_model = None
        if not settings.uses_vector_index:
            self.backend = "none"
            self.model_name = ""
            self.dim = 0
            return
        if self.backend in {"sentence-transformers", "minilm", "semantic"}:
            from sentence_transformers import SentenceTransformer

            self.backend = "sentence-transformers"
            self._st_model = SentenceTransformer(self.model_name)
            self.dim = int(self._st_model.get_sentence_embedding_dimension())
        elif self.backend == "openai":
            if not settings.openai_api_key:
                raise RuntimeError("EMBEDDING_BACKEND=openai requires OPENAI_API_KEY")
        else:
            raise RuntimeError(
                f"Unsupported embedding backend '{self.backend}'. "
                "Set EMBEDDING_BACKEND=sentence-transformers."
            )

    def encode(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, max(self.dim, 1)), dtype=np.float32)
        if self.backend in {"none", ""}:
            return np.zeros((len(texts), max(self.dim, 1)), dtype=np.float32)
        if self.backend == "openai":
            return self._openai_encode(texts)
        assert self._st_model is not None
        matrix = self._st_model.encode(
            texts,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return np.asarray(matrix, dtype=np.float32)

    def _openai_encode(self, texts: list[str]) -> np.ndarray:
        import httpx

        settings = get_settings()
        response = httpx.post(
            "https://api.openai.com/v1/embeddings",
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            json={"model": "text-embedding-3-small", "input": texts},
            timeout=45.0,
        )
        response.raise_for_status()
        data = response.json()["data"]
        vectors = np.array([item["embedding"] for item in data], dtype=np.float32)
        norms = np.linalg.norm(vectors, axis=1, keepdims=True) + 1e-12
        self.dim = vectors.shape[1]
        return vectors / norms


@lru_cache
def get_embedder() -> Embedder:
    return Embedder()


def content_checksum(text: str) -> str:
    from app.services.ingest import content_checksum as checksum

    return checksum(text)
