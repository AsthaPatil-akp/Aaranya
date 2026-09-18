from __future__ import annotations

import re
from app.core.config import get_settings
from app.models.schemas import ClaimEvidenceLink, EnvironmentalContext, EvidenceItem, KnowledgeStatus
from app.services.fallback import wants_recent_literature

RESEARCH_INTENT = re.compile(
    r"\b(latest|recent studies|new findings|current evidence|peer[- ]reviewed|"
    r"scientific literature|research papers?|scientific papers?|published studies|"
    r"look up (?:papers|research|studies)|find (?:papers|studies))\b",
    re.I,
)
NUMERIC_RE = re.compile(r"\b\d+(?:\.\d+)?\s*%")
TIME_SPAN_RE = re.compile(r"\b\d{1,2}\s*[–\-to]+\s*\d{1,2}\s+(?:years?|months?)\b", re.I)
EXACT_TIME_RE = re.compile(r"\b\d+\s+(?:years?|months?|weeks?)\b", re.I)


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
        semantic = 0.0
        if get_settings().uses_vector_index:
            from app.services.embeddings import get_embedder

            embedder = get_embedder()
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
UNSUPPORTED_DISCLAIMER = (
    "Some generated statements were not supported by the retrieved passages and should not be treated as verified."
)
_ROTATION_RE = re.compile(r"\b(?:crop\s+rotations?|diversified\s+rotations?|rotational\s+cropping)\b", re.I)
_UNCERTAINTY_RE = re.compile(
    r"does not (?:confirm|support|establish)|retrieved (?:passages|evidence) do not|"
    r"\buncertain\b|was not provided|would help to know|ask(?:ed)? about|"
    r"listed as none|not treated as (?:an )?existing|historical pesticide",
    re.I,
)
_SOURCE_SPLIT_RE = re.compile(r"(?is)\n+\s*sources?\s*/?\s*evidence")


def _is_uncertainty_language(text: str) -> bool:
    return bool(_UNCERTAINTY_RE.search(text or ""))


def _is_moisture_crowding_claim(text: str) -> bool:
    lower = (text or "").lower()
    has_moisture = re.search(r"(?:high|elevated|excess(?:ive)?)\s+(?:soil\s+)?moisture", lower)
    has_crowd = re.search(r"crowd|compet(?:e|ition)|densit", lower)
    has_bio = re.search(r"biodivers|species|pollinator|\bplants?\b", lower)
    return bool(has_moisture and has_crowd and has_bio)


def _split_sentences(text: str) -> list[str]:
    body = _SOURCE_SPLIT_RE.split(text or "", maxsplit=1)[0]
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", body) if part.strip()]


def claims_from_answer(answer: str, evidence: list[EvidenceItem], limit: int = 8) -> list[ClaimEvidenceLink]:
    text = (answer or "").strip()
    if not text:
        return []
    sentences = [
        sentence
        for sentence in _split_sentences(text)
        if len(sentence) >= 40 and not _is_uncertainty_language(sentence)
    ]
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


def _evidence_blob(evidence: list[EvidenceItem]) -> str:
    return " ".join(
        f"{item.passage or ''} {item.title or ''} {item.document_name or ''}" for item in evidence
    ).lower()


def _allowed_rotation(user_message: str, evidence: list[EvidenceItem]) -> bool:
    blob = f"{user_message or ''} {_evidence_blob(evidence)}"
    return bool(_ROTATION_RE.search(blob))


def _uncertainty_rewrite(sentence: str) -> str:
    lower = (sentence or "").lower()
    if _ROTATION_RE.search(lower):
        return ""
    if _is_moisture_crowding_claim(sentence or ""):
        return (
            "The retrieved passages do not establish that high soil moisture reduces biodiversity "
            "through plant crowding. Has waterlogging or unusually dense vegetation actually been observed?"
        )
    if re.search(r"\b(?:pesticide|insecticide|herbicide|agrochemical)s?\b", lower):
        return ""
    return ""


def rewrite_unsupported_claims(answer: str, claims: list[ClaimEvidenceLink]) -> str:
    """Remove or rewrite unsupported claims instead of showing them with a disclaimer."""
    text = answer or ""
    text = text.replace(UNSUPPORTED_DISCLAIMER, "")
    for claim in claims:
        if claim.support != "unsupported":
            continue
        original = (claim.text or "").strip()
        if not original or _is_uncertainty_language(original):
            continue
        replacement = _uncertainty_rewrite(original)
        pattern = re.escape(original)
        if re.search(pattern, text):
            text = re.sub(pattern, replacement, text, count=1)
            continue
        compact = re.sub(r"\s+", " ", original)
        compact_text = re.sub(r"\s+", " ", text)
        if compact in compact_text:
            text = re.sub(re.escape(original[:80]), replacement, text, count=1)
    return re.sub(r"[ \t]+\n", "\n", re.sub(r"\n{3,}", "\n\n", text)).strip()


def strip_unsupported_language(answer: str, claims: list[ClaimEvidenceLink]) -> str:
    return rewrite_unsupported_claims(answer, claims)


def pesticide_use_is_none(context: EnvironmentalContext | None) -> bool:
    if context is None:
        return False
    value = str(getattr(context.human_impact, "pesticide_use", None) or "").strip().lower()
    return value in {"none", "no", "not used", "zero", "absent"}


def apply_context_grounding_rules(
    answer: str,
    context: EnvironmentalContext | None,
    evidence: list[EvidenceItem],
    user_message: str = "",
) -> str:
    """Drop invented mechanisms that the retrieved evidence and user inputs do not support."""
    text = answer or ""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    allowed_rotation = _allowed_rotation(user_message, evidence)
    if context is not None and context.land.land_use == "intercropping" and not re.search(
        r"crop rotation|diversified rotation|rotational cropping", user_message or "", re.I
    ):
        allowed_rotation = False
    evidence_text = _evidence_blob(evidence)
    kept: list[str] = []
    asked_history = False
    for sentence in sentences:
        raw = sentence.strip()
        if not raw:
            continue
        if not allowed_rotation and _ROTATION_RE.search(raw):
            continue
        if _is_moisture_crowding_claim(raw) and not re.search(
            r"crowd|compet(?:e|ition)|plant crowding", evidence_text
        ):
            if not any("plant crowding" in item.lower() for item in kept):
                kept.append(
                    "The retrieved passages do not establish that high soil moisture reduces biodiversity "
                    "through plant crowding. Has waterlogging or unusually dense vegetation actually been observed?"
                )
            continue
        if pesticide_use_is_none(context) and re.search(
            r"\b(?:pesticide|insecticide|herbicide|agrochemical)s?\b", raw, re.I
        ):
            if _is_uncertainty_language(raw) and "historical" in raw.lower():
                kept.append(raw)
                asked_history = True
            continue
        kept.append(raw)
    text = " ".join(kept).strip()
    if (
        pesticide_use_is_none(context)
        and not asked_history
        and context is not None
        and (
            (context.biodiversity.pollinator_diversity or "").lower() in {"declining", "low"}
            or re.search(r"bees|butterfl|pollinator", user_message or "", re.I)
        )
        and "historical pesticide" not in text.lower()
    ):
        text = (
            text.rstrip()
            + " Current pesticide use is listed as none, so pesticide exposure should not be treated as an existing "
            "pressure. If insecticides were used in earlier seasons, that history would help interpret insect "
            "declines — was there historical pesticide use?"
        )
    return re.sub(r"[ \t]+\n", "\n", re.sub(r"\n{3,}", "\n\n", text)).strip()


def ground_answer(
    draft: str,
    evidence: list[EvidenceItem],
    *,
    user_message: str = "",
    context: EnvironmentalContext | None = None,
    claims: list[ClaimEvidenceLink] | None = None,
) -> tuple[str, list[ClaimEvidenceLink]]:
    """LLM draft → claim/evidence validation → remove/rewrite unsupported claims → grounded answer."""
    working = (draft or "").replace(UNSUPPORTED_DISCLAIMER, "").strip()
    working_claims = claims or claims_from_answer(working, evidence)
    working_claims = verify_claims(working_claims, evidence)
    working = rewrite_unsupported_claims(working, working_claims)
    working = sanitize_answer_against_evidence(working, evidence, user_message=user_message)
    working = apply_context_grounding_rules(working, context, evidence, user_message)
    working = working.replace(UNSUPPORTED_DISCLAIMER, "").strip()
    final_claims = claims_from_answer(working, evidence)
    final_claims = verify_claims(final_claims, evidence)
    leftover = [claim for claim in final_claims if claim.support == "unsupported"]
    if leftover:
        working = rewrite_unsupported_claims(working, leftover)
        final_claims = verify_claims(claims_from_answer(working, evidence), evidence)
    working = re.sub(r"\n{3,}", "\n\n", working).strip()
    return working, final_claims


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
    for span in set(TIME_SPAN_RE.findall(text) + EXACT_TIME_RE.findall(text)):
        if span.lower() not in allowed:
            text = text.replace(span, "no specific timeframe supported by the retrieved evidence")
    return re.sub(r"[ \t]+\n", "\n", re.sub(r"\n{3,}", "\n\n", text)).strip()


STATUS_LABELS = {
    "grounded_in_knowledge_base": "Grounded in knowledge base",
    "grounded_in_external_evidence": "Grounded in external scientific evidence",
    "grounded_in_kb_and_external": "Grounded in knowledge base and external evidence",
    "insufficient_evidence": "Insufficient verified evidence",
    "awaiting_clarification": "Awaiting additional environmental information",
}
