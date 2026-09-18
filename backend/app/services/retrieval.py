from __future__ import annotations

import re

from rank_bm25 import BM25Okapi

from app.core.config import get_settings
from app.models.schemas import EvidenceItem
from app.services.vectorstore import get_chroma

STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "have", "has", "are", "was",
    "were", "been", "being", "does", "did", "how", "what", "when", "where", "which",
    "into", "onto", "over", "under", "about", "after", "before", "between", "through",
    "should", "would", "could", "their", "there", "then", "than", "them", "they",
    "your", "you", "our", "out", "not", "but", "can", "may", "will", "just", "also",
    "more", "most", "such", "only", "very", "some", "any", "each", "few", "own",
    "same", "other", "please", "recommend", "analyse", "analyze", "explain",
}


def _tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9%.-]{3,}", text.lower())
    return [token.strip(".-") for token in tokens if token.strip(".-") not in STOPWORDS]


def _passage_key(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower())[:160]


class Retriever:
    def __init__(self) -> None:
        self.settings = get_settings()

    def warmup(self) -> None:
        store = get_chroma()
        if store.count() == 0:
            return
        store.query("soil organic carbon cover crops pollinators", top_k=1)

    def search(self, query: str, top_k: int | None = None) -> list[EvidenceItem]:
        query = (query or "").strip()
        if not query:
            return []
        candidate_k = top_k or self.settings.retrieval_top_k
        hits = get_chroma().query(query, top_k=candidate_k)
        if not hits:
            return []
        query_tokens = _tokenize(query)
        tokenized = [_tokenize(hit.get("text") or "") for hit in hits]
        bm25_scores = [0.0] * len(hits)
        if query_tokens and any(tokenized):
            bm25 = BM25Okapi(tokenized)
            raw = bm25.get_scores(query_tokens)
            max_s = max(raw) if len(raw) else 0.0
            bm25_scores = [float(score / (max_s + 1e-12)) if max_s else 0.0 for score in raw]

        results: list[EvidenceItem] = []
        seen_passages: list[str] = []
        for hit, lexical in zip(hits, bm25_scores):
            text = hit.get("text") or ""
            key = _passage_key(text)
            if key and any(key == existing or key in existing or existing in key for existing in seen_passages):
                continue
            if key:
                seen_passages.append(key)
            overlap_tokens = set(query_tokens) & set(_tokenize(text))
            overlap = len(overlap_tokens) / max(len(query_tokens), 1)
            hybrid = 0.70 * max(float(hit["similarity"]), 0.0) + 0.20 * lexical + 0.10 * overlap
            page = hit.get("page")
            results.append(
                EvidenceItem(
                    evidence_id=f"kb-{hit['id']}",
                    source=hit.get("source") or hit.get("document_name") or "",
                    document_name=hit.get("document_name") or "",
                    title=hit.get("title") or None,
                    authors=hit.get("authors") or None,
                    institution=hit.get("institution") or None,
                    page=page,
                    page_is_real=bool(hit.get("page_is_real")) and page is not None,
                    topic=hit.get("topic") or None,
                    document_type=hit.get("document_type") or None,
                    passage=text[:900],
                    relevance_score=round(float(hybrid), 4),
                    origin="knowledge_base",
                    evidence_level="passage",
                    doi=hit.get("doi") or None,
                    url=hit.get("url") or None,
                    year=int(hit["year"]) if hit.get("year") not in (None, "", 0) else None,
                )
            )
        results.sort(key=lambda item: item.relevance_score or 0, reverse=True)
        return results

    def split_relevant(self, items: list[EvidenceItem]) -> tuple[list[EvidenceItem], list[EvidenceItem]]:
        threshold = self.settings.relevance_threshold
        accepted = [item for item in items if (item.relevance_score or 0) >= threshold]
        rejected = [item for item in items if (item.relevance_score or 0) < threshold]
        return accepted, rejected


retriever = Retriever()
