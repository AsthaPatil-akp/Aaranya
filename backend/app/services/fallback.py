from __future__ import annotations

import logging
import re
import time
from html.parser import HTMLParser
from io import BytesIO

import httpx
import numpy as np
from pypdf import PdfReader

from app.core.config import get_settings
from app.models.schemas import EvidenceItem

LOGGER = logging.getLogger("darukaa.openalex")
_OPENALEX_CACHE: dict[str, tuple[float, list[EvidenceItem]]] = {}
_OPENALEX_CACHE_TTL = 600.0
_OA_HTTP: httpx.Client | None = None


def _openalex_http() -> httpx.Client:
    global _OA_HTTP
    if _OA_HTTP is None:
        _OA_HTTP = httpx.Client(
            timeout=15.0,
            headers={"User-Agent": "Darukaa.Earth research assistant"},
            follow_redirects=True,
        )
    return _OA_HTTP


def clear_openalex_cache() -> None:
    _OPENALEX_CACHE.clear()

WILDCARD_RE = re.compile(r"[?*]")
RECENT_RE = re.compile(
    r"\b(latest|recent|new findings|current evidence|newest|up to date|this year)\b",
    re.I,
)


class _HTMLText(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []
        self._skip = False

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip = True

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip = False

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self._chunks.append(data)

    def text(self) -> str:
        return re.sub(r"\s+", " ", " ".join(self._chunks)).strip()


def sanitize_openalex_query(query: str) -> str:
    text = WILDCARD_RE.sub(" ", query or "")
    text = re.sub(r"[?!]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:200]


def wants_recent_literature(message: str) -> bool:
    return bool(RECENT_RE.search(message or ""))


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


def _extract_pdf_bytes(payload: bytes) -> str:
    try:
        reader = PdfReader(BytesIO(payload))
    except Exception as exc:
        LOGGER.info("Open-access PDF could not be parsed: %s", exc)
        return ""
    pages = []
    for page in reader.pages[:8]:
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            continue
    return re.sub(r"\s+", " ", " ".join(pages)).strip()


def _extract_html(payload: bytes) -> str:
    parser = _HTMLText()
    try:
        parser.feed(payload.decode("utf-8", errors="ignore"))
    except Exception:
        return ""
    return parser.text()


def _fetch_open_text(url: str) -> tuple[str, str | None]:
    """Return (text, evidence_level) for legally available OA URLs only."""
    try:
        response = _openalex_http().get(
            url,
            timeout=12.0,
            headers={"User-Agent": "Darukaa.Earth research assistant"},
        )
        response.raise_for_status()
    except Exception as exc:
        LOGGER.info("Open-access fetch failed for %s: %s", url, exc)
        return "", None
    content_type = (response.headers.get("content-type") or "").lower()
    payload = response.content[: 2_000_000]
    if "pdf" in content_type or url.lower().endswith(".pdf"):
        text = _extract_pdf_bytes(payload)
        return text[:12000], "full_text" if text else None
    text = _extract_html(payload)
    if len(text) < 200:
        return "", None
    return text[:12000], "full_text"


def _authors(work: dict) -> str:
    names = []
    for item in (work.get("authorships") or [])[:6]:
        author = item.get("author") or {}
        name = author.get("display_name")
        if name:
            names.append(name)
    return ", ".join(names)


def _best_passages(text: str, query: str, limit: int = 2) -> list[str]:
    if not text:
        return []
    sentences = re.split(r"(?<=[.!?])\s+", text)
    if len(text) < 700:
        return [text[:900]]
    q = set(re.findall(r"[a-z0-9]{4,}", query.lower()))
    scored = []
    window = 3
    for i in range(len(sentences)):
        piece = " ".join(sentences[i : i + window]).strip()
        if len(piece) < 80:
            continue
        tokens = set(re.findall(r"[a-z0-9]{4,}", piece.lower()))
        overlap = len(q & tokens) / max(len(q), 1)
        scored.append((overlap, len(piece), piece))
    scored.sort(key=lambda item: (item[0], min(item[1], 900)), reverse=True)
    seen: list[str] = []
    for _, __, piece in scored:
        if piece not in seen:
            seen.append(piece[:900])
        if len(seen) >= limit:
            break
    return seen or [text[:900]]


def search_openalex(
    query: str,
    *,
    environmental_context: str = "",
    prefer_recent: bool = False,
    limit: int | None = None,
) -> list[EvidenceItem]:
    settings = get_settings()
    cleaned = sanitize_openalex_query(query)
    if not settings.enable_openalex or not cleaned:
        return []
    cache_key = f"{cleaned}|{int(prefer_recent)}|{environmental_context[:120]}|{settings.openalex_keep}"
    cached = _OPENALEX_CACHE.get(cache_key)
    now = time.monotonic()
    if cached and now - cached[0] < _OPENALEX_CACHE_TTL:
        return [item.model_copy() for item in cached[1]]
    try:
        response = _openalex_http().get(
            "https://api.openalex.org/works",
            params={
                "search": cleaned,
                "per_page": min(settings.openalex_max_results, 8),
                "mailto": settings.openalex_mailto,
            },
            timeout=15.0,
            headers={"User-Agent": f"Darukaa.Earth prototype ({settings.openalex_mailto})"},
        )
        if response.status_code >= 400:
            LOGGER.warning("OpenAlex HTTP %s: %s", response.status_code, response.text[:300])
            return []
        works = response.json().get("results") or []
    except Exception as exc:
        LOGGER.warning("OpenAlex request failed: %s", exc)
        return []

    use_vectors = settings.uses_vector_index
    query_vec = None
    embedder = None
    if use_vectors:
        from app.services.embeddings import get_embedder

        embedder = get_embedder()
        query_vec = embedder.encode([f"{cleaned} {environmental_context}".strip()])[0]
    query_tokens = set(re.findall(r"[a-z0-9]{4,}", f"{cleaned} {environmental_context}".lower()))
    keep = limit or settings.openalex_keep
    prelim: list[dict] = []
    for index, work in enumerate(works):
        title = work.get("display_name") or "Untitled work"
        year = work.get("publication_year")
        doi = (work.get("doi") or "").replace("https://doi.org/", "") or None
        landing = ((work.get("primary_location") or {}).get("landing_page_url")) or None
        host = ((work.get("primary_location") or {}).get("source") or {}).get("display_name") or ""
        cited = int(work.get("cited_by_count") or 0)
        abstract = _restore_abstract(work.get("abstract_inverted_index"))
        oa = work.get("open_access") or {}
        oa_url = oa.get("oa_url") if oa.get("is_oa") else None
        if not abstract:
            continue
        passages = _best_passages(abstract, f"{cleaned} {environmental_context}")
        if use_vectors and embedder is not None and query_vec is not None:
            passage_vec = embedder.encode(passages[:1])[0]
            relevance = float(np.dot(query_vec, passage_vec))
        else:
            pass_tokens = set(re.findall(r"[a-z0-9]{4,}", passages[0].lower()))
            relevance = len(query_tokens & pass_tokens) / max(len(query_tokens), 1) if query_tokens else 0.0
        recency = 0.0
        if isinstance(year, int):
            recency = max(0.0, min(1.0, (year - 2005) / 20.0))
        if prefer_recent:
            recency *= 1.4
        quality = min(1.0, (cited ** 0.5) / 30.0)
        env_tokens = set(re.findall(r"[a-z0-9]{4,}", environmental_context.lower()))
        pass_tokens = set(re.findall(r"[a-z0-9]{4,}", passages[0].lower()))
        applicability = len(env_tokens & pass_tokens) / max(len(env_tokens), 1) if env_tokens else 0.0
        recency_weight = 0.22 if prefer_recent else 0.08
        score = (
            0.52 * max(relevance, 0.0)
            + 0.18 * applicability
            + recency_weight * recency
            + 0.10 * quality
            + 0.06
        )
        if score < 0.28 or relevance < 0.22:
            continue
        prelim.append(
            {
                "index": index,
                "work": work,
                "title": title,
                "year": year,
                "doi": doi,
                "landing": landing,
                "host": host,
                "cited": cited,
                "oa_url": oa_url,
                "passages": passages,
                "evidence_level": "abstract",
                "relevance": relevance,
                "score": score,
            }
        )
    prelim.sort(key=lambda item: item["score"], reverse=True)
    shortlist = prelim[: max(keep, 3)]
    if settings.fetch_open_access_text and prefer_recent:
        for item in shortlist[:2]:
            oa_url = item.get("oa_url")
            if not oa_url:
                continue
            try:
                extracted, level = _fetch_open_text(oa_url)
            except Exception as exc:
                LOGGER.info("Open-access text fetch failed for %s: %s", oa_url, exc)
                extracted, level = "", None
            if not extracted:
                continue
            passages = _best_passages(extracted, f"{cleaned} {environmental_context}")
            if use_vectors and embedder is not None and query_vec is not None:
                passage_vec = embedder.encode(passages[:1])[0]
                relevance = float(np.dot(query_vec, passage_vec))
            else:
                pass_tokens = set(re.findall(r"[a-z0-9]{4,}", passages[0].lower()))
                relevance = len(query_tokens & pass_tokens) / max(len(query_tokens), 1) if query_tokens else 0.0
            item["passages"] = passages
            item["evidence_level"] = level or "full_text"
            item["relevance"] = relevance
            item["score"] = item["score"] + 0.06
    ranked: list[EvidenceItem] = []
    for item in sorted(shortlist, key=lambda row: row["score"], reverse=True):
        work = item["work"]
        ranked.append(
            EvidenceItem(
                evidence_id=f"oa-{work.get('id', item['index']).split('/')[-1] if isinstance(work.get('id'), str) else item['index']}",
                source=f"OpenAlex — {item['host']}" if item["host"] else "OpenAlex external record",
                document_name=item["title"],
                title=item["title"],
                authors=_authors(work) or None,
                institution=item["host"] or None,
                page=None,
                page_is_real=False,
                topic="external_scientific_index",
                document_type="openalex_work",
                passage=item["passages"][0],
                relevance_score=round(float(item["score"]), 4),
                origin="external_openalex",
                evidence_level=item["evidence_level"],  # type: ignore[arg-type]
                doi=item["doi"],
                url=item["oa_url"] or item["landing"],
                year=item["year"] if isinstance(item["year"], int) else None,
                cited_by_count=item["cited"],
            )
        )
    selected = ranked[:keep]
    _OPENALEX_CACHE[cache_key] = (now, selected)
    return selected


def insufficient_message(internal_hits: int, external_hits: int) -> str:
    if external_hits:
        return (
            "I searched the knowledge base and then looked for external scientific records. "
            "I still do not have enough verified evidence to give a confident recommendation, "
            "and I will not invent papers, statistics, or page numbers."
        )
    if internal_hits:
        return (
            "I searched the knowledge base, but the retrieved passages were not relevant enough. "
            "I could not find reliable external scientific text either. I will not fabricate sources."
        )
    return (
        "I could not find enough verified evidence to answer that confidently. "
        "I will not invent scientific claims or citations."
    )
