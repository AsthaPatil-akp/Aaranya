from __future__ import annotations

import json
import re
from typing import Any

from app.models.schemas import EnvironmentalContext, EvidenceItem, RecommendationBlock, TimeHorizon

SYSTEM_PROMPT = """You are Darukaa.Earth's biodiversity intelligence assistant.

Use the retrieved evidence as the factual basis of your response.

Your job is not merely to summarize the evidence. Reason over the user's environmental context and explain how the relevant environmental variables may interact.

For complex environmental questions, produce a complete but understandable response.

Never invent evidence.

Never provide generic sustainability advice when the retrieved evidence supports a more specific intervention.

Explain uncertainty where appropriate.

Write for an intelligent non-specialist.

Do not mention RAG, embeddings, vector databases, chunks, prompts, OpenAlex, or other internal machinery.

Do not invent facts, studies, numerical values, citations, DOIs, authors, journals, percentages, pages, or environmental effects.
If evidence is insufficient, say so.
Distinguish between:
- evidence-supported conclusions
- reasonable inference
- uncertainty

Recommendations must be connected to the user's environmental conditions.

Rules:
- INTERNAL KNOWLEDGE BASE and EXTERNAL SCIENTIFIC EVIDENCE are separate. Synthesize them. If they disagree, say so.
- Do not pretend a Darukaa synthesis is an original FAO/IPCC/IPBES paper.
- Do not pretend an external paper came from the internal knowledge base.
- If evidence_level=abstract, treat it as abstract-level evidence. Never claim you read the full paper.
- If evidence_level=full_text, you may use that open-access text, still without inventing page numbers.
- Do not mention monoculture unless land_use=monoculture is in the environmental variables.
- Do not invent missing environmental values. If a land-detail field is listed as not provided, leave it unknown and ask for it when it is needed.
- Do not claim that one factor alone caused a biodiversity decline when several conditions are known. Use cautious wording such as "may contribute", "could be interacting with", "can place additional pressure", and "should be investigated" when causality is not established.
- Address every materially relevant environmental variable the user provided. If pesticide use or scarce flowering habitat is listed, mention it. Do not silently ignore it. Do not claim pesticides caused the decline unless a retrieved passage supports that causal claim.
- When three or more environmental variables are known, explain how they interact (for example soil condition → vegetation → insects → pollinators).
- Select only the interventions that fit this user's conditions and the retrieved passages. Split combined ideas into distinct recommendations (for example cover crops as one recommendation, widely spaced native trees or shrubs as another). Do not repeat the same intervention.
- For every major recommendation, name the environmental metrics it could affect. If the evidence is uncertain, write "potentially affected" rather than a guaranteed increase or decrease. Do not invent numerical improvement percentages.
- Time horizons only when evidence supports them. If the evidence only supports a multi-year or multi-season response, say "several seasons to multiple years". If no timeframe is supported, say so. Do not invent exact spans such as 10-20 years.
- Prefer hedges: "research suggests", "evidence indicates", "based on the studies I found", "there is limited evidence for".
- Candidate interventions are optional ideas, not facts. Use a candidate only if retrieved evidence supports it for these conditions.
- The retrieved passages must actually shape the recommendations. Do not mention evidence and then ignore it.
- In the Sources / Evidence close, list only documents that actually support the final answer. Do not list unused retrieved documents.

The "answer" field is the complete message the user will read. Do not hide the explanation in other JSON fields.

Write about 80-150 words for a simple question, 150-250 words for a normal environmental question, and about 250-450 words for complex environmental reasoning. A good shape for a complex question is:
- Start with: based on the conditions you described, several factors may be interacting...
- Explain the relationships in ordinary paragraphs.
- Then: what I would investigate first...
- Then distinct recommendations, each covering what to do, why it may help, which metrics it could affect, how long the effect might take if the evidence supports a horizon, and which retrieved evidence supports it.
- Close with a concise Sources / Evidence section and uncertainty.

If no external scientific evidence was retrieved, do not pretend it was.

Simple questions can be shorter.

Do not reveal hidden chain-of-thought or a private reasoning-steps list. Write only the concise final explanation.

Return JSON only with this shape:
{
  "recommendation": "primary action, or several actions separated by semicolons",
  "why_it_works": "plain-language why those actions fit these conditions",
  "environmental_relationships": "how the known variables may interact; do not blame one factor alone",
  "recommendations": [{"action": "...", "why": "...", "metrics": ["soil organic carbon"], "evidence_ids": ["kb-1"]}],
  "impacted_metrics": [{"name": "...", "direction": "up|down|neutral|unknown", "note": "..."}],
  "time_horizon": {"narrative": "...", "short_term": null, "medium_term": null, "long_term": null, "evidence_supported": false},
  "uncertainty": "limitations",
  "claims": [{"id": "c1", "text": "one scientific claim", "evidence_ids": ["kb-1"], "support": "direct"}],
  "evidence_used": ["kb-1"],
  "confidence": "high|medium|low",
  "confidence_rationale": "evidence strength, not statistical certainty",
  "knowledge_status": "grounded_in_knowledge_base|grounded_in_external_evidence|grounded_in_kb_and_external|insufficient_evidence",
  "answer": "complete conversational explanation the user should read, including a Sources / Evidence close"
}
"""

ANSWER_EXPAND_SYSTEM = """You are Darukaa.Earth's biodiversity intelligence assistant.

Use the retrieved evidence as the factual basis of your response.
Your job is not merely to summarize the evidence. Reason over the user's environmental context and explain how the relevant environmental variables may interact.
For complex environmental questions, produce a complete but understandable response.
Never invent evidence.
Never provide generic sustainability advice when the retrieved evidence supports a more specific intervention.
Explain uncertainty where appropriate.
Write for an intelligent non-specialist.

Write the user-facing answer only. No JSON. No hidden chain-of-thought. Do not write a database-style list of fields.

Write about 250-450 words as a conversation:
1. Start with the conditions the user described and how several factors may be interacting.
2. Mention every materially relevant variable, including pesticide use and scarce flowering habitat when they were provided. Use "may contribute", "can place additional pressure", or "should be investigated" unless retrieved evidence supports a stronger causal claim.
3. Say what you would investigate first.
4. Give distinct recommendations. Split cover crops from agroforestry or native trees. Do not repeat the same intervention. For each: what to do, why it may help, metrics it could affect, time horizon only if evidence supports one, and which retrieved source supports it.
5. For metrics, prefer "potentially affected" over guaranteed increases.
6. For time, prefer "several seasons to multiple years" or "no specific timeframe is supported by the retrieved evidence". Never invent 10-20 years or similar exact spans.
7. Close with a concise Sources / Evidence section listing only documents you actually used, then uncertainty.

Do not invent studies, DOIs, percentages, timeframes, missing environmental values, or scientific findings.
If no external scientific evidence is listed, do not pretend it was used.
Name sources by document title, not internal ids such as kb-1.
"""


def _fmt_evidence(items: list[EvidenceItem]) -> str:
    lines = []
    for item in items:
        page = f"page {item.page}" if item.page and item.page_is_real else "page unavailable"
        level = item.evidence_level
        if level == "abstract":
            level = "abstract-level evidence"
        passage = re.sub(r"\s+", " ", item.passage or "").strip()[:520]
        lines.append(
            f"[{item.evidence_id}] {item.title or item.document_name}\n"
            f"origin={item.origin}; level={level}; {page}; year={item.year or 'unknown'}; "
            f"doi={item.doi or 'none'}; url={item.url or 'none'}\n"
            f"authors={item.authors or 'unknown'}\n"
            f"passage: {passage}"
        )
    return "\n\n".join(lines) or "(none)"


def answer_length_band(context: EnvironmentalContext, message: str) -> str:
    known = context.known_variable_count()
    text = (message or "").lower()
    if known >= 3 or (
        known >= 2 and re.search(r"\b(what should i do|causing|decline|biodiversity|recommend|interact)\b", text)
    ):
        return "complex"
    if known <= 1 and len(message or "") < 90 and not re.search(r"\bwhat should i do\b", text):
        return "simple"
    return "normal"


def length_instruction(band: str) -> str:
    if band == "simple":
        return "This is a simple question. Write about 80-150 words. Do not pad."
    if band == "normal":
        return "This is a normal environmental question. Write about 150-250 words."
    return (
        "This is a complex environmental question. The answer field must be about 250-450 words and must cover "
        "causes, interacting factors, specific recommendations, why they fit, metrics, time horizon if supported, "
        "sources, and uncertainty."
    )


def predict_budget(band: str) -> int:
    if band == "simple":
        return 320
    if band == "normal":
        return 620
    return 980


LAND_DETAIL_KEYS = (
    "farm_size",
    "location",
    "latitude",
    "longitude",
    "crop",
    "land_use",
    "soil_ph",
    "soil_organic_carbon",
    "soil_moisture",
    "rainfall",
    "temperature",
    "pollution",
    "biodiversity_observations",
)


def unprovided_land_fields(context: EnvironmentalContext) -> list[str]:
    known = context.known_variables()
    return [key for key in LAND_DETAIL_KEYS if key not in known]


def build_user_prompt(
    *,
    message: str,
    context: EnvironmentalContext,
    history: list[dict[str, Any]],
    kb_evidence: list[EvidenceItem],
    external_evidence: list[EvidenceItem],
    candidates: list[dict[str, Any]],
) -> str:
    known = context.known_variables()
    history_lines = []
    for turn in history[-4:]:
        role = turn.get("role")
        content = (turn.get("content") or "")[:220]
        history_lines.append(f"{role}: {content}")
    compact_candidates = [
        {"action": item.get("action") or item.get("idea"), "why": item.get("why") or item.get("why_candidate")}
        for item in (candidates or [])[:5]
        if isinstance(item, dict)
    ]
    candidate_text = json.dumps(compact_candidates, ensure_ascii=True) if compact_candidates else "[]"
    band = answer_length_band(context, message)
    length_hint = length_instruction(band)
    return (
        "SYSTEM INSTRUCTIONS:\n"
        "You are answering using retrieved scientific evidence. Do not invent facts.\n\n"
        "USER CONTEXT:\n"
        "USER QUESTION:\n"
        f"{message}\n\n"
        "CONVERSATION CONTEXT:\n"
        + ("\n".join(history_lines) or "(none)")
        + "\n\nENVIRONMENTAL VARIABLES:\n"
        + f"{json.dumps(known, ensure_ascii=True)}\n"
        + "FIELDS NOT PROVIDED (do not invent these; ask if they are needed):\n"
        + f"{json.dumps(unprovided_land_fields(context), ensure_ascii=True)}\n\n"
        + "INTERNAL KNOWLEDGE BASE:\n"
        + _fmt_evidence(kb_evidence)
        + "\n\nEXTERNAL SCIENTIFIC EVIDENCE:\n"
        + _fmt_evidence(external_evidence)
        + "\n\nREASONING REQUIREMENTS:\n"
        "Work through this internally, then write only the final explanation in the answer field:\n"
        "USER CONTEXT → ENVIRONMENTAL PROBLEM → INTERACTING FACTORS → EVIDENCE → RECOMMENDATIONS → METRICS → TIME HORIZON → UNCERTAINTY.\n"
        "Use the retrieved passages as the factual basis. Reason across at least three known environmental variables when available. "
        "Address every listed environmental variable. If pesticide use or scarce flowering plants are listed, include them with cautious wording. "
        "Split combined practices into distinct recommendations and do not repeat the same one. "
        "Connect each recommendation to this user's conditions and to specific retrieved evidence. "
        "If only an abstract is present, say so. "
        f"{length_hint}\n\n"
        "OPTIONAL CANDIDATE INTERVENTIONS (not facts; do not copy blindly; keep only those the evidence supports for these conditions):\n"
        + candidate_text
        + "\n\nOUTPUT FORMAT:\nWrite JSON now. Put the complete user-facing explanation in the answer field last."
    )


def build_expansion_prompt(
    *,
    message: str,
    context: EnvironmentalContext,
    kb_evidence: list[EvidenceItem],
    external_evidence: list[EvidenceItem],
    structured: dict[str, Any],
) -> str:
    compact = {
        "recommendation": structured.get("recommendation") or structured.get("action"),
        "recommendations": structured.get("recommendations") or [],
        "why_it_works": structured.get("why_it_works"),
        "environmental_relationships": structured.get("environmental_relationships"),
        "impacted_metrics": structured.get("impacted_metrics") or [],
        "time_horizon": structured.get("time_horizon"),
        "uncertainty": structured.get("uncertainty"),
        "evidence_used": structured.get("evidence_used") or [],
        "draft_answer": structured.get("answer") or structured.get("_answer"),
    }
    return (
        "USER CONTEXT:\n"
        f"{message}\n\n"
        "ENVIRONMENTAL VARIABLES:\n"
        f"{json.dumps(context.known_variables(), ensure_ascii=True)}\n"
        "FIELDS NOT PROVIDED (do not invent these; ask if they are needed):\n"
        f"{json.dumps(unprovided_land_fields(context), ensure_ascii=True)}\n\n"
        "ENVIRONMENTAL PROBLEM / INTERACTING FACTORS / EVIDENCE / RECOMMENDATIONS / METRICS / TIME HORIZON / UNCERTAINTY\n"
        "Use the structured findings only as notes. The retrieved passages are the factual basis.\n"
        "Mention every listed environmental variable. Do not omit pesticide use or scarce flowering habitat if they appear above.\n"
        "Write naturally: based on the conditions you described... then what I would investigate first... then distinct recommendations.\n"
        f"{length_instruction(answer_length_band(context, message))}\n\n"
        "STRUCTURED FINDINGS:\n"
        f"{json.dumps(compact, ensure_ascii=True)}\n\n"
        "INTERNAL KNOWLEDGE BASE:\n"
        + _fmt_evidence(kb_evidence)
        + "\n\nEXTERNAL SCIENTIFIC EVIDENCE:\n"
        + _fmt_evidence(external_evidence)
        + "\n\nWrite the complete conversational answer now."
    )


def streaming_system_prompt(band: str) -> str:
    if band == "simple":
        length = "Write about 80-150 words. Do not pad a simple question."
    elif band == "normal":
        length = "Write about 150-250 words as a conversation."
    else:
        length = "Write about 250-350 words as a conversation."
    return ANSWER_EXPAND_SYSTEM.replace("Write about 250-450 words as a conversation:", length, 1)


def build_stream_user_prompt(
    *,
    message: str,
    context: EnvironmentalContext,
    history: list[dict[str, Any]],
    kb_evidence: list[EvidenceItem],
    external_evidence: list[EvidenceItem],
    candidates: list[dict[str, Any]],
) -> str:
    history_lines = []
    for turn in history[-4:]:
        role = turn.get("role")
        content = (turn.get("content") or "")[:220]
        history_lines.append(f"{role}: {content}")
    compact_candidates = [
        {"action": item.get("action") or item.get("idea"), "why": item.get("why") or item.get("why_candidate")}
        for item in (candidates or [])[:5]
        if isinstance(item, dict)
    ]
    band = answer_length_band(context, message)
    return (
        "USER QUESTION:\n"
        f"{message}\n\n"
        "CONVERSATION CONTEXT:\n"
        + ("\n".join(history_lines) or "(none)")
        + "\n\nENVIRONMENTAL VARIABLES:\n"
        + f"{json.dumps(context.known_variables(), ensure_ascii=True)}\n"
        + "FIELDS NOT PROVIDED (do not invent these; ask if they are needed):\n"
        + f"{json.dumps(unprovided_land_fields(context), ensure_ascii=True)}\n\n"
        + "INTERNAL KNOWLEDGE BASE:\n"
        + _fmt_evidence(kb_evidence)
        + "\n\nEXTERNAL SCIENTIFIC EVIDENCE:\n"
        + _fmt_evidence(external_evidence)
        + "\n\nOPTIONAL CANDIDATE INTERVENTIONS (not facts; use only if retrieved evidence supports them):\n"
        + json.dumps(compact_candidates, ensure_ascii=True)
        + "\n\n"
        + length_instruction(band)
        + "\nUse the retrieved passages as the factual basis. Address every listed environmental variable. "
        "If pesticide use or scarce flowering habitat is listed, include it with cautious wording. "
        "Do not invent studies, DOIs, percentages, timeframes, or missing environmental values.\n"
        "Write the complete conversational answer now."
    )


def word_count(text: str) -> int:
    return len(re.findall(r"\S+", text or ""))


def _already_said(fragment: str, existing: str) -> bool:
    key = re.sub(r"\s+", " ", (fragment or "").strip().lower())[:90]
    if len(key) < 24:
        return False
    return key in re.sub(r"\s+", " ", (existing or "").lower())


def format_sources_section(
    kb_evidence: list[EvidenceItem],
    external_evidence: list[EvidenceItem],
) -> str:
    if not kb_evidence and not external_evidence:
        return ""
    lines = ["Sources / Evidence"]
    if kb_evidence:
        lines.append("Internal Knowledge Base")
        seen: set[str] = set()
        for item in kb_evidence:
            title = (item.title or item.document_name or "Internal synthesis").strip()
            if title in seen:
                continue
            seen.add(title)
            lines.append(f"- {title}")
    if external_evidence:
        lines.append("External Scientific Research")
        seen: set[str] = set()
        for item in external_evidence:
            title = (item.title or item.document_name or "External source").strip()
            if title in seen:
                continue
            seen.add(title)
            extras = []
            if item.year:
                extras.append(str(item.year))
            if item.evidence_level == "abstract":
                extras.append("abstract-level evidence")
            elif item.evidence_level == "full_text":
                extras.append("open-access text")
            if item.doi:
                extras.append(f"DOI {item.doi}")
            suffix = f" ({'; '.join(extras)})" if extras else ""
            lines.append(f"- {title}{suffix}")
    return "\n".join(lines)


def _metric_line(rec: RecommendationBlock) -> str:
    if not rec.impacted_metrics:
        return ""
    bits = []
    for metric in rec.impacted_metrics:
        note = (metric.note or "").strip()
        if note:
            bits.append(f"{metric.name}: {note}")
        else:
            bits.append(f"Potentially affected: {metric.name}")
    return "Metrics these changes could affect: " + "; ".join(bits) + "."


def _horizon_line(rec: RecommendationBlock) -> str:
    horizon = rec.time_horizon
    text = (horizon.narrative or "").strip()
    if not text:
        return ""
    if re.search(r"^(short|medium|long)[-\s]?term$", text, re.I):
        return ""
    return text


_INTERVENTION_PATTERNS = [
    ("cover", re.compile(r"cover crops?|green manure", re.I)),
    ("trees", re.compile(r"agroforest|native (?:trees?|shrubs?)|widely spaced", re.I)),
    ("residue", re.compile(r"residues?", re.I)),
    ("tillage", re.compile(r"tillage", re.I)),
    ("flower", re.compile(r"flower|floral|field margins?|hedgerow", re.I)),
    ("pesticide", re.compile(r"pesticide|insecticide|herbicide|agrochemical", re.I)),
    ("diversify", re.compile(r"intercrop|diversif|rotation", re.I)),
]


def intervention_keys(text: str) -> set[str]:
    found = {name for name, pattern in _INTERVENTION_PATTERNS if pattern.search(text or "")}
    return found


def split_recommendation_text(text: str) -> list[str]:
    raw = (text or "").strip()
    if not raw:
        return []
    chunks = [part.strip(" ;,") for part in re.split(r";+|,\s+plus\s+", raw) if part.strip()]
    split: list[str] = []
    for chunk in chunks:
        keys = intervention_keys(chunk)
        if len(keys) >= 2 and re.search(r"\sand\s", chunk, re.I):
            pieces = [part.strip(" ;,") for part in re.split(r",?\s+and\s+", chunk) if part.strip()]
            if len(pieces) >= 2:
                split.extend(pieces)
                continue
        split.append(chunk)
    return split or [raw]


def dedupe_recommendations(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    expanded: list[dict[str, Any]] = []
    for item in items:
        action = str(item.get("action") or "").strip()
        why = str(item.get("why") or "").strip()
        metrics = item.get("metrics") or []
        evidence_ids = item.get("evidence_ids") or []
        if not action:
            continue
        parts = split_recommendation_text(action)
        if len(parts) == 1:
            expanded.append(item)
            continue
        for part in parts:
            expanded.append(
                {
                    "action": part[0].upper() + part[1:] if part else part,
                    "why": why,
                    "metrics": metrics,
                    "evidence_ids": evidence_ids,
                }
            )
    unique: list[dict[str, Any]] = []
    seen: list[set[str]] = []
    for item in expanded:
        keys = intervention_keys(str(item.get("action") or ""))
        if not keys:
            unique.append(item)
            continue
        if any(keys <= existing or existing <= keys for existing in seen):
            continue
        seen.append(keys)
        unique.append(item)
    return unique


def soften_metrics(metrics: list) -> list:
    softened = []
    for metric in metrics:
        note = (getattr(metric, "note", None) or "").strip()
        if not note:
            note = "possible local improvement, depending on establishment and landscape context"
        elif not re.search(r"may|possible|potential|uncertain|depend", note, re.I):
            note = f"possible change: {note}"
        softened.append(type(metric)(name=metric.name, direction="unknown", note=note))
    return softened


_YEAR_SPAN = re.compile(r"\b\d{1,2}\s*[–\-to]+\s*\d{1,2}\s+years?\b", re.I)
_EXACT_YEARS = re.compile(r"\b\d+\s+years?\b", re.I)
_BARE_HORIZON_LABEL = re.compile(r"^(short|medium|long)[-\s]?term$", re.I)


def sanitize_time_horizon(horizon: TimeHorizon, evidence: list[EvidenceItem]) -> TimeHorizon:
    blob = " ".join((item.passage or "") + " " + (item.title or "") for item in evidence).lower()

    def allowed(text: str | None) -> str | None:
        cleaned = (text or "").strip()
        if not cleaned or _BARE_HORIZON_LABEL.match(cleaned):
            return None
        spans = [match.group(0) for match in list(_YEAR_SPAN.finditer(cleaned)) + list(_EXACT_YEARS.finditer(cleaned))]
        if spans and not any(span.lower() in blob for span in spans):
            return None
        return cleaned

    narrative = allowed(horizon.narrative) or allowed(horizon.short_term) or allowed(horizon.medium_term) or allowed(
        horizon.long_term
    )
    if not narrative:
        if re.search(r"multi-year|multiple years|several season|gradual", blob):
            narrative = "Several seasons to multiple years"
            supported = True
        else:
            narrative = "No specific timeframe is supported by the retrieved evidence."
            supported = False
    else:
        supported = bool(horizon.evidence_supported and not _YEAR_SPAN.search(narrative))
        if re.search(r"season|year|gradual", narrative, re.I) and re.search(r"season|year|gradual", blob):
            supported = True
        if _YEAR_SPAN.search(narrative) and narrative.lower() not in blob:
            narrative = "Several seasons to multiple years"
            supported = True
    return TimeHorizon(narrative=narrative, short_term=None, medium_term=None, long_term=None, evidence_supported=supported)


def ensure_material_variables(answer: str, context: EnvironmentalContext) -> str:
    text = answer or ""
    lowered = text.lower()
    extras: list[str] = []
    pollution = str(context.human_impact.pollution or "").lower()
    if pollution and not re.search(r"pesticide|insecticide|herbicide|agrochemical|chemical pressure|pollution", lowered):
        if "pesticide" in pollution:
            extras.append(
                "Pesticide use during the growing season can place additional pressure on insects and should be investigated. "
                "That does not, by itself, prove pesticides caused the decline."
            )
        else:
            extras.append(
                f"Chemical pressure ({context.human_impact.pollution}) can place additional stress on sensitive species and should be investigated alongside the other site conditions."
            )
    if (
        (context.biodiversity.plant_diversity or "").lower() in {"low", "very low"}
        or (context.biodiversity.habitat_diversity or "").lower() in {"low", "very low"}
    ) and not re.search(r"flower|floral", lowered):
        extras.append(
            "Very few flowering plants around the fields is consistent with limited floral resources for bees and butterflies, "
            "and may contribute together with simplified cropping and dry soils rather than acting alone."
        )
    if context.soil.ph is not None and context.soil.ph >= 7.8 and not re.search(r"\bph\b", lowered):
        extras.append(
            f"Soil pH of {context.soil.ph} can constrain nutrient availability and which restoration plants are feasible, "
            "and is better treated as a constraint than as something to correct in isolation."
        )
    if context.climate.temperature is not None and context.climate.temperature >= 28 and not re.search(
        r"temperature|\bheat\b|\bhot\b", lowered
    ):
        extras.append(
            f"Typical temperatures around {context.climate.temperature:.0f}°C can add heat stress on top of irregular rainfall, "
            "which may further limit flowering and soil moisture."
        )
    if extras:
        text = text.rstrip() + "\n\n" + "\n\n".join(extras)
    return text


def filter_evidence_for_answer(
    answer: str,
    claims: list,
    recommendation_ids: list[str],
    kb_evidence: list[EvidenceItem],
    external_evidence: list[EvidenceItem],
) -> tuple[list[EvidenceItem], list[EvidenceItem]]:
    answer_l = (answer or "").lower()
    used_ids = {str(eid) for eid in recommendation_ids if eid}
    for claim in claims:
        support = getattr(claim, "support", None) or (claim.get("support") if isinstance(claim, dict) else None)
        ids = getattr(claim, "evidence_ids", None) or (claim.get("evidence_ids") if isinstance(claim, dict) else [])
        if support in {"direct", "inference"}:
            used_ids.update(str(eid) for eid in (ids or []))

    def is_unused_offtopic(item: EvidenceItem) -> bool:
        name = f"{item.document_name or ''} {item.title or ''}".lower()
        if item.evidence_id in used_ids:
            return False
        if "deforest" in name or "fragment" in name:
            return not re.search(r"deforest|fragment|forest remnant|canopy corridor", answer_l)
        if "urban" in name and "pollution" in name:
            return not re.search(r"urban|pesticide|pollution|agrochemical|chemical", answer_l)
        return False

    def overlaps(item: EvidenceItem) -> bool:
        if item.evidence_id in used_ids:
            return True
        blob = f"{item.title or ''} {item.document_name or ''} {item.passage or ''}".lower()
        tokens = set(re.findall(r"[a-z]{5,}", blob))
        answer_tokens = set(re.findall(r"[a-z]{5,}", answer_l))
        return len(tokens & answer_tokens) >= 4

    kb_kept = [item for item in kb_evidence if not is_unused_offtopic(item) and overlaps(item)]
    ext_kept = [item for item in external_evidence if not is_unused_offtopic(item) and overlaps(item)]
    if not kb_kept and kb_evidence:
        kb_kept = [item for item in kb_evidence if item.evidence_id in used_ids] or [
            item for item in kb_evidence if not is_unused_offtopic(item)
        ][:3]
    return kb_kept, ext_kept


def _recommendation_paragraphs(data: dict[str, Any], rec: RecommendationBlock) -> list[str]:
    paragraphs: list[str] = []
    raw_recs = data.get("recommendations") or []
    items: list[tuple[str, str]] = []
    if isinstance(raw_recs, list):
        for item in raw_recs:
            if isinstance(item, dict):
                action = str(item.get("action") or item.get("recommendation") or "").strip()
                why = str(item.get("why") or item.get("why_it_works") or "").strip()
                if action:
                    items.append((action, why))
            elif isinstance(item, str) and item.strip():
                items.append((item.strip(), ""))
    if items:
        bullets = []
        for action, why in items:
            if why:
                bullets.append(f"- {action.rstrip('.')} — {why}")
            else:
                bullets.append(f"- {action}")
        paragraphs.append("What I would investigate first, based on the retrieved evidence:\n" + "\n".join(bullets))
        return paragraphs
    if rec.action:
        text = rec.action
        if rec.why_it_works:
            text = f"{rec.action.rstrip('.')} {rec.why_it_works}"
        paragraphs.append(text)
    return paragraphs


def compose_user_facing_answer(
    *,
    data: dict[str, Any],
    rec: RecommendationBlock,
    kb_evidence: list[EvidenceItem],
    external_evidence: list[EvidenceItem],
) -> str:
    """Build the chat answer from the model's own fields plus retrieved source metadata.

    This does not inject farm-specific advice. It only rearranges model text and
    lists the evidence that was actually retrieved.
    """
    parts: list[str] = []
    answer = str(data.get("answer") or data.get("_answer") or rec.action or "").strip()
    if answer:
        parts.append(answer)
    combined = answer
    already_complete = word_count(answer) >= 200 and "based on the conditions" in answer.lower()

    if not already_complete:
        relationships = (rec.environmental_relationships or "").strip()
        if relationships and not _already_said(relationships, combined):
            parts.append(relationships)
            combined = "\n\n".join(parts)

        for paragraph in _recommendation_paragraphs(data, rec):
            if paragraph and not _already_said(paragraph, combined):
                if rec.action and rec.action.lower() in combined.lower() and "What I would investigate first" not in paragraph:
                    if rec.why_it_works and not _already_said(rec.why_it_works, combined):
                        parts.append(rec.why_it_works)
                        combined = "\n\n".join(parts)
                    continue
                parts.append(paragraph)
                combined = "\n\n".join(parts)

        metric_line = _metric_line(rec)
        if metric_line and not _already_said(metric_line, combined):
            names = [metric.name.lower() for metric in rec.impacted_metrics]
            if not any(name in combined.lower() for name in names[:2] if name):
                parts.append(metric_line)
                combined = "\n\n".join(parts)

        horizon = _horizon_line(rec)
        if horizon and not _already_said(horizon, combined):
            parts.append(horizon)
            combined = "\n\n".join(parts)

        uncertainty = (rec.uncertainty or "").strip()
        if uncertainty and not _already_said(uncertainty, combined):
            parts.append(uncertainty)
            combined = "\n\n".join(parts)

    body = "\n\n".join(part.strip() for part in parts if part and part.strip())
    sources = format_sources_section(kb_evidence, external_evidence)
    if sources and "internal knowledge base" not in body.lower() and "sources / evidence" not in body.lower():
        body = f"{body}\n\n{sources}" if body else sources
    return body.strip()


_SOURCE_HEADING = re.compile(
    r"(?is)\n+(?:sources(?:\s*/\s*evidence)?|references)\s*:?\s*\n"
)
_UNCERTAINTY_HEADING = re.compile(r"(?is)\n+uncertainty:\s*\n")


def ensure_grounded_sources(
    text: str,
    kb_evidence: list[EvidenceItem],
    external_evidence: list[EvidenceItem],
) -> str:
    """Keep the model's explanation, but list only retrieved sources."""
    body = text or ""
    uncertainty = ""
    unc_split = _UNCERTAINTY_HEADING.split(body, maxsplit=1)
    if len(unc_split) == 2:
        body = unc_split[0]
        uncertainty = _SOURCE_HEADING.split(unc_split[1], maxsplit=1)[0].strip()
    body = _SOURCE_HEADING.split(body, maxsplit=1)[0].rstrip()
    if uncertainty and "uncertain" not in body.lower() and "limitation" not in body.lower():
        body = f"{body}\n\n{uncertainty}"
    sources = format_sources_section(kb_evidence, external_evidence)
    if sources:
        body = f"{body}\n\n{sources}" if body else sources
    return body.strip()


def is_complex_environmental_case(context: EnvironmentalContext, message: str) -> bool:
    if context.known_variable_count() >= 3:
        return True
    text = (message or "").lower()
    return bool(
        context.known_variable_count() >= 2
        and re.search(r"\b(what should i do|causing|decline|biodiversity|recommend)\b", text)
    )


def needs_answer_expansion(answer: str, context: EnvironmentalContext, message: str) -> bool:
    return False
