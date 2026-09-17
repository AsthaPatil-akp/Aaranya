from __future__ import annotations

import httpx

from app.core.config import get_settings
from app.models.schemas import EvidenceItem


def search_openalex(query: str, limit: int = 3) -> list[EvidenceItem]:
    settings = get_settings()
    if not settings.enable_openalex or not query.strip():
        return []
    try:
        response = httpx.get(
            "https://api.openalex.org/works",
            params={
                "search": query[:200],
                "per_page": limit,
                "mailto": settings.openalex_mailto,
                "sort": "relevance_score:desc",
            },
            timeout=12.0,
            headers={"User-Agent": f"Darukaa.Earth prototype ({settings.openalex_mailto})"},
        )
        response.raise_for_status()
        results = []
        for work in response.json().get("results", []):
            title = work.get("display_name") or "Untitled work"
            year = work.get("publication_year")
            doi = (work.get("doi") or "").replace("https://doi.org/", "") or None
            abstract = _restore_abstract(work.get("abstract_inverted_index"))
            host = ""
            primary = work.get("primary_location") or {}
            source = primary.get("source") or {}
            if source:
                host = source.get("display_name") or ""
            passage = abstract or "No abstract text was provided by OpenAlex for this record."
            results.append(
                EvidenceItem(
                    source=f"OpenAlex external record" + (f" — {host}" if host else ""),
                    document_name=title,
                    page=None,
                    topic="external_scientific_index",
                    document_type="openalex_work",
                    passage=passage[:900],
                    relevance_score=None,
                    origin="external_openalex",
                    doi=doi,
                    year=year,
                )
            )
        return results
    except Exception:
        return []


def _restore_abstract(inverted: dict | None) -> str:
    if not inverted:
        return ""
    max_pos = 0
    for positions in inverted.values():
        if positions:
            max_pos = max(max_pos, max(positions))
    words = [""] * (max_pos + 1)
    for word, positions in inverted.items():
        for pos in positions:
            if 0 <= pos < len(words):
                words[pos] = word
    return " ".join(token for token in words if token)


def insufficient_message(internal_hits: int, external_hits: int) -> str:
    if external_hits:
        return (
            "The internal knowledge base did not contain sufficiently relevant verified passages for this question. "
            "I searched an external scientific index (OpenAlex) and labelled those records separately. "
            "I will not treat them as internal knowledge-base evidence, and I will not invent papers, statistics, or page numbers."
        )
    if internal_hits:
        return (
            "I searched the knowledge base, but the retrieved passages scored below the relevance threshold. "
            "They are listed as unused/low-relevance only. The current knowledge base does not contain sufficient "
            "verified information to provide a scientifically grounded recommendation. Add a relevant PDF or rephrase the question."
        )
    return (
        "The current knowledge base does not contain sufficient verified information to provide a scientifically grounded "
        "recommendation, and no reliable external records were retrieved. I will not fabricate sources or quantitative claims."
    )
