from __future__ import annotations

import re
from app.core.config import get_settings
from app.models.schemas import ClaimEvidenceLink, EvidenceItem, KnowledgeStatus
from app.services.embeddings import get_embedder
from app.services.fallback import wants_recent_literature

RESEARCH_INTENT = re.compile(
    r"\b(latest|recent studies|new findings|current evidence|peer[- ]reviewed|"
    r"scientific literature|research papers?|scientific papers?|published studies|"
    r"look up (?:papers|research|studies)|find (?:papers|studies))\b",
    re.I,
)
NUMERIC_RE = re.compile(r"\b\d+(?:\.\d+)?\s*%")


def kb_is_weak(accepted: list[EvidenceItem]) -> bool:
    settings = get_settings()
    if not accepted:
        return True
    best = max((item.relevance_score or 0) for item in accepted)
    return best < settings.weak_kb_threshold


def should_search_external(
    message: str,
    accepted: list[EvidenceItem],
    rejected: list[EvidenceItem],
) -> tuple[bool, str]:
    if RESEARCH_INTENT.search(message or "") or wants_recent_literature(message):
        return True, "user_requested_research_or_recency"
    if not accepted:
        return True, "kb_insufficient"
    if kb_is_weak(accepted):
        return True, "kb_evidence_weak"
    return False, "kb_sufficient"


def select_evidence(
    kb_accepted: list[EvidenceItem],
    external: list[EvidenceItem],
    max_items: int | None = None,
) -> list[EvidenceItem]:
    settings = get_settings()
    limit = max_items if max_items is not None else max(3, min(settings.llm_evidence_k, 5))
    combined = sorted(
        [*kb_accepted, *external],
        key=lambda item: item.relevance_score or 0,
        reverse=True,
    )
    selected: list[EvidenceItem] = []
    seen_ids: set[str] = set()
    seen_passages: list[str] = []
    for item in combined:
        key = item.evidence_id or item.document_name
        if key in seen_ids:
            continue
        prefix = re.sub(r"\s+", " ", (item.passage or "").lower())[:160]
        if prefix and any(prefix == existing or prefix in existing or existing in prefix for existing in seen_passages):
            continue
        seen_ids.add(key)
        if prefix:
            seen_passages.append(prefix)
        selected.append(item)
        if len(selected) >= limit:
            break
    if external:
        has_ext = any(item.origin == "external_openalex" for item in selected)
        if not has_ext:
            best_ext = max(external, key=lambda item: item.relevance_score or 0)
            if selected:
                selected[-1] = best_ext
                selected.sort(key=lambda item: item.relevance_score or 0, reverse=True)
            else:
                selected.append(best_ext)
    return selected


def status_from_evidence(selected: list[EvidenceItem], claims: list[ClaimEvidenceLink]) -> KnowledgeStatus:
    used_ids = {eid for claim in claims if claim.support == "direct" for eid in claim.evidence_ids}
    used = [item for item in selected if item.evidence_id in used_ids] or selected
    origins = {item.origin for item in used}
    has_kb = "knowledge_base" in origins
    has_ext = "external_openalex" in origins
    if has_kb and has_ext:
        return "grounded_in_kb_and_external"
    if has_kb:
        return "grounded_in_knowledge_base"
    if has_ext:
        return "grounded_in_external_evidence"
    return "insufficient_evidence"


def _content_tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-zA-Z]{4,}", (text or "").lower()))


def _overlap(a: set[str], b: set[str]) -> float:
    if not a:
        return 0.0
    return len(a & b) / len(a)


def verify_claims(
    claims: list[ClaimEvidenceLink],
    evidence: list[EvidenceItem],
) -> list[ClaimEvidenceLink]:
    by_id = {item.evidence_id: item for item in evidence if item.evidence_id}
    embedder = get_embedder()
    verified: list[ClaimEvidenceLink] = []
    for claim in claims:
        valid_ids = [eid for eid in claim.evidence_ids if eid in by_id]
        if not valid_ids:
            claim.support = "unsupported"
            claim.evidence_ids = []
            verified.append(claim)
            continue
        claim.evidence_ids = valid_ids
        claim.sources = [
            by_id[eid].title or by_id[eid].document_name for eid in valid_ids
        ]
        passages = [by_id[eid].passage for eid in valid_ids]
        claim_tokens = _content_tokens(claim.text)
        lexical = max(_overlap(claim_tokens, _content_tokens(p)) for p in passages)
        vectors = embedder.encode([claim.text, *passages])
        semantic = max(float(vectors[0] @ vectors[i]) for i in range(1, len(vectors)))
        numbers = NUMERIC_RE.findall(claim.text)
        numbers_ok = all(any(num.lower() in p.lower() for p in passages) for num in numbers)
        if numbers and not numbers_ok:
            claim.support = "unsupported"
        elif lexical >= 0.18 or semantic >= 0.45:
            claim.support = "direct"
        else:
            claim.support = "inference"
        verified.append(claim)
    return verified


DOI_RE = re.compile(r"10\.\d{4,}/[^\s\]\)]+")


def claims_from_answer(answer: str, evidence: list[EvidenceItem], limit: int = 6) -> list[ClaimEvidenceLink]:
    text = (answer or "").strip()
    if not text:
        return []
    body = re.split(r"(?is)\n+\s*sources?\s*/?\s*evidence", text, maxsplit=1)[0]
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", body) if len(part.strip()) >= 40]
    claims: list[ClaimEvidenceLink] = []
    for index, sentence in enumerate(sentences[:limit]):
        sent_tokens = _content_tokens(sentence)
        ranked: list[tuple[float, str]] = []
        for item in evidence:
            overlap = _overlap(sent_tokens, _content_tokens(item.passage))
            if overlap > 0:
                ranked.append((overlap, item.evidence_id))
        ranked.sort(reverse=True)
        evidence_ids = [eid for _score, eid in ranked[:3] if eid]
        claims.append(
            ClaimEvidenceLink(
                claim_id=f"c{index + 1}",
                text=sentence,
                evidence_ids=evidence_ids,
                support="direct" if evidence_ids else "unsupported",
            )
        )
    return claims


def strip_unsupported_language(answer: str, claims: list[ClaimEvidenceLink]) -> str:
    text = answer
    for claim in claims:
        if claim.support == "unsupported" and claim.text and claim.text in text:
            text = text.replace(claim.text, "")
        if claim.support == "unsupported":
            for num in NUMERIC_RE.findall(claim.text):
                if num.lower() not in " ".join(claim.sources).lower():
                    text = text.replace(num, "an unquantified change")
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def sanitize_answer_against_evidence(
    answer: str,
    evidence: list[EvidenceItem],
    *,
    user_message: str = "",
) -> str:
    """Remove invented DOIs and improvement percentages that are not in retrieved text."""
    text = answer or ""
    allowed = " ".join(
        [
            user_message or "",
            *[
                " ".join(
                    filter(
                        None,
                        [
                            item.passage,
                            item.doi,
                            item.title,
                            item.document_name,
                            str(item.year or ""),
                        ],
                    )
                )
                for item in evidence
            ],
        ]
    ).lower()
    known_dois = {item.doi for item in evidence if item.doi}
    for doi in set(DOI_RE.findall(text)):
        if doi not in known_dois:
            text = text.replace(doi, "")
    for num in set(NUMERIC_RE.findall(text)):
        if num.lower() not in allowed:
            text = text.replace(num, "an unquantified change")
    return re.sub(r"[ \t]+\n", "\n", re.sub(r"\n{3,}", "\n\n", text)).strip()


STATUS_LABELS = {
    "grounded_in_knowledge_base": "Grounded in knowledge base",
    "grounded_in_external_evidence": "Grounded in external scientific evidence",
    "grounded_in_kb_and_external": "Grounded in knowledge base and external evidence",
    "insufficient_evidence": "Insufficient verified evidence",
    "awaiting_clarification": "Awaiting additional environmental information",
}
