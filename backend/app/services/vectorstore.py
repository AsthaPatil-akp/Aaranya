from __future__ import annotations

from typing import Any

import numpy as np

from app.core.config import get_settings
from app.services.embeddings import get_embedder


def _chroma_client():
    import chromadb
    from chromadb.config import Settings as ChromaSettings

    settings = get_settings()
    path = str(settings.resolved_chroma_path)
    return chromadb.PersistentClient(
        path=path,
        settings=ChromaSettings(anonymized_telemetry=False),
    )


def _meta_value(value: Any) -> str | int | float | bool:
    if value is None:
        return ""
    if isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


class ChromaStore:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.embedder = get_embedder()
        self.collection_name = self.settings.chroma_collection
        self.client = _chroma_client()
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        self._count_cache: int | None = None

    def reset(self) -> None:
        try:
            self.client.delete_collection(self.collection_name)
        except Exception:
            pass
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        self._count_cache = None

    def count(self) -> int:
        if self._count_cache is None:
            self._count_cache = int(self.collection.count())
        return self._count_cache

    def upsert_chunks(self, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        texts = [row["text"] for row in rows]
        vectors = self.embedder.encode(texts)
        ids = [str(row["id"]) for row in rows]
        metadatas = []
        for row in rows:
            metadatas.append(
                {
                    "chunk_id": _meta_value(row.get("id")),
                    "document_name": _meta_value(row.get("document_name")),
                    "source": _meta_value(row.get("source")),
                    "page": int(row["page"]) if row.get("page") not in (None, "") else -1,
                    "page_is_real": bool(row.get("page_is_real")),
                    "topic": _meta_value(row.get("topic")),
                    "document_type": _meta_value(row.get("document_type")),
                    "checksum": _meta_value(row.get("checksum")),
                    "title": _meta_value(row.get("title")),
                    "authors": _meta_value(row.get("authors")),
                    "institution": _meta_value(row.get("institution")),
                    "url": _meta_value(row.get("url")),
                    "doi": _meta_value(row.get("doi")),
                    "year": int(row["year"]) if row.get("year") not in (None, "") else 0,
                    "origin": _meta_value(row.get("origin") or "knowledge_base"),
                }
            )
        self.collection.upsert(
            ids=ids,
            embeddings=vectors.tolist(),
            documents=texts,
            metadatas=metadatas,
        )
        self._count_cache = None

    def query(self, text: str, top_k: int | None = None) -> list[dict[str, Any]]:
        query = (text or "").strip()
        if not query or self.count() == 0:
            return []
        k = min(top_k or self.settings.retrieval_top_k, max(self.count(), 1))
        vector = self.embedder.encode([query])[0]
        result = self.collection.query(
            query_embeddings=[vector.tolist()],
            n_results=k,
            include=["documents", "metadatas", "distances"],
        )
        hits: list[dict[str, Any]] = []
        docs = (result.get("documents") or [[]])[0]
        metas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        ids = (result.get("ids") or [[]])[0]
        for doc, meta, dist, item_id in zip(docs, metas, distances, ids):
            meta = meta or {}
            distance = float(dist)
            # cosine space: Chroma distance is 1 - cosine similarity for cosine metric
            similarity = 1.0 - distance
            page = meta.get("page")
            hits.append(
                {
                    "id": item_id,
                    "text": doc or "",
                    "similarity": float(similarity),
                    "document_name": meta.get("document_name") or "",
                    "source": meta.get("source") or meta.get("document_name") or "",
                    "page": None if page in (-1, "-1", None, "") else int(page),
                    "page_is_real": bool(meta.get("page_is_real")),
                    "topic": meta.get("topic") or "",
                    "document_type": meta.get("document_type") or "",
                    "checksum": meta.get("checksum") or "",
                    "title": meta.get("title") or "",
                    "authors": meta.get("authors") or "",
                    "institution": meta.get("institution") or "",
                    "url": meta.get("url") or "",
                    "doi": meta.get("doi") or "",
                    "year": meta.get("year") or None,
                    "origin": meta.get("origin") or "knowledge_base",
                }
            )
        return hits


_store: ChromaStore | None = None


def get_chroma() -> ChromaStore:
    global _store
    if _store is None:
        _store = ChromaStore()
    return _store


def reset_chroma_singleton() -> None:
    global _store
    _store = None
