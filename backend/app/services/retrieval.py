from __future__ import annotations

import re

import numpy as np
from rank_bm25 import BM25Okapi

from app.core.config import get_settings
from app.models.schemas import EvidenceItem
from app.services.embeddings import get_embedder
from app.services.ingest import knowledge_store

STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "have", "has", "are", "was",
    "were", "been", "being", "does", "did", "how", "what", "when", "where", "which",
    "into", "onto", "over", "under", "about", "after", "before", "between", "through",
    "should", "would", "could", "their", "there", "then", "than", "them", "they",
    "your", "you", "our", "out", "not", "but", "can", "may", "will", "just", "also",
    "more", "most", "such", "only", "very", "some", "any", "each", "few", "own",
    "same", "other", "into", "affect", "effect", "yields", "yield", "please",
    "recommend", "analyse", "analyze", "explain",
}


def _tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9%.-]{3,}", text.lower())
    return [token.strip(".-") for token in tokens if token.strip(".-") not in STOPWORDS]


def _overlap(query_tokens: list[str], doc_tokens: list[str]) -> float:
    if not query_tokens:
        return 0.0
    q = set(query_tokens)
    d = set(doc_tokens)
    return len(q & d) / len(q)


class Retriever:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.embedder = get_embedder()

    def search(self, query: str, top_k: int | None = None) -> list[EvidenceItem]:
        query = (query or "").strip()
        if not query:
            return []
        chunks = knowledge_store.load_chunks()
        if not chunks:
            return []
        vectors, ids = knowledge_store.load_vectors()
        if vectors.size == 0:
            return []

        query_vec = self.embedder.encode([query])[0]
        # Cosine similarity (vectors are L2-normalized for hashing/ST backends)
        denom = (np.linalg.norm(vectors, axis=1) * (np.linalg.norm(query_vec) + 1e-12)) + 1e-12
        cosine = (vectors @ query_vec) / denom
        cosine = np.nan_to_num(cosine)

        query_tokens = _tokenize(query)
        tokenized = [_tokenize(row["text"]) for row in chunks]
        bm25 = BM25Okapi(tokenized) if any(tokenized) else None
        if bm25 is not None and query_tokens:
            bm25_scores = np.array(bm25.get_scores(query_tokens), dtype=np.float32)
        else:
            bm25_scores = np.zeros(len(chunks), dtype=np.float32)
        if bm25_scores.max() > 0:
            bm25_norm = bm25_scores / (bm25_scores.max() + 1e-12)
        else:
            bm25_norm = bm25_scores

        id_to_index = {int(chunk_id): idx for idx, chunk_id in enumerate(ids.tolist())}
        hybrid = np.zeros(len(chunks), dtype=np.float32)
        for idx, row in enumerate(chunks):
            vec_idx = id_to_index.get(int(row["id"]))
            cos = float(cosine[vec_idx]) if vec_idx is not None else 0.0
            lexical = float(bm25_norm[idx])
            overlap = _overlap(query_tokens, tokenized[idx])
            if overlap <= 0:
                hybrid[idx] = 0.0
            else:
                hybrid[idx] = 0.50 * max(cos, 0.0) + 0.35 * lexical + 0.15 * overlap

        k = top_k or self.settings.retrieval_top_k
        order = np.argsort(hybrid)[::-1][: max(k, 8)]
        results: list[EvidenceItem] = []
        for idx in order:
            row = chunks[int(idx)]
            score = float(hybrid[int(idx)])
            results.append(
                EvidenceItem(
                    source=row["source"],
                    document_name=row["document_name"],
                    page=row["page"],
                    topic=row["topic"] or row["doc_topic"],
                    document_type=row["document_type"],
                    passage=row["text"][:900],
                    relevance_score=round(score, 4),
                    origin="knowledge_base",
                )
            )
        return results

    def split_relevant(self, items: list[EvidenceItem]) -> tuple[list[EvidenceItem], list[EvidenceItem]]:
        threshold = self.settings.relevance_threshold
        accepted = [item for item in items if (item.relevance_score or 0) >= threshold]
        rejected = [item for item in items if (item.relevance_score or 0) < threshold]
        return accepted, rejected


retriever = Retriever()
