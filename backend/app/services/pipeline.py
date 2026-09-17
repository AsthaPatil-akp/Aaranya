from __future__ import annotations

import re

from app.core.config import get_settings
from app.models.schemas import (
    ChatRequest,
    ChatResponse,
    DebugRetrieval,
    StructuredInput,
)
from app.services.extraction import extract_from_text, parse_structured_json, structured_to_dict
from app.services.fallback import insufficient_message, search_openalex
from app.services.ingest import knowledge_store
from app.services.llm import polish_recommendation
from app.services.memory import store
from app.services.reasoning import (
    build_recommendation,
    classify_intent,
    clarifying_questions,
    heuristic_profile,
    needs_clarification,
    retrieval_query,
)
from app.services.retrieval import retriever

STATUS_LABELS = {
    "grounded_in_knowledge_base": "Grounded in knowledge base",
    "partially_grounded_external_used": "Partially grounded / external information used",
    "insufficient_verified_evidence": "Insufficient verified evidence",
    "awaiting_clarification": "Awaiting additional environmental information",
}


def _looks_like_case_followup(message: str, context) -> bool:
    if context.known_variable_count() < 3:
        return False
    text = (message or "").lower()
    return bool(
        re.search(
            r"\b(why|pollinator|habitat|rainfall|carbon|crop|monoculture|cover|agroforest|recommend|intervention|metric|moisture|species|what about|how does that)\b",
            text,
        )
    )


def _format_recommendation_text(response: ChatResponse) -> str:
    rec = response.recommendation
    if not rec:
        return response.assistant_message
    metrics = "\n".join(
        f"• {item.name}: {'↑' if item.direction == 'up' else '↓' if item.direction == 'down' else 'neutral'}"
        + (f" — {item.note}" if item.note else "")
        for item in rec.impacted_metrics
    )
    evidence_lines = []
    for item in response.evidence:
        page = f", page {item.page}" if item.page else ""
        origin = "KB" if item.origin == "knowledge_base" else "EXTERNAL"
        evidence_lines.append(f"• [{origin}] {item.document_name}{page}: {item.passage[:220]}")
    horizon = rec.time_horizon
    return (
        f"RECOMMENDATION\n{rec.action}\n\n"
        f"WHY THIS WORKS\n{rec.why_it_works}\n\n"
        f"ENVIRONMENTAL RELATIONSHIPS\n{rec.environmental_relationships}\n\n"
        f"IMPACTED METRICS\n{metrics}\n\n"
        f"TIME HORIZON\nShort term: {horizon.short_term or 'Not estimated'}\n"
        f"Medium term: {horizon.medium_term or 'Not estimated'}\n"
        f"Long term: {horizon.long_term or 'Not estimated'}\n\n"
        f"CONFIDENCE\n{rec.confidence.capitalize()} — {rec.confidence_rationale}\n\n"
        f"EVIDENCE\n" + ("\n".join(evidence_lines) or "No qualifying evidence.") + "\n\n"
        f"KNOWLEDGE STATUS\n{response.knowledge_status_label}"
    )


def handle_chat(payload: ChatRequest) -> ChatResponse:
    warnings: list[str] = []
    message = (payload.message or "").strip()
    structured: StructuredInput | None = payload.structured

    if payload.structured_json:
        try:
            structured = parse_structured_json(payload.structured_json)
        except ValueError as exc:
            return ChatResponse(
                session_id=payload.session_id or "",
                mode="error",
                assistant_message=str(exc),
                knowledge_status="insufficient_verified_evidence",
                knowledge_status_label=STATUS_LABELS["insufficient_verified_evidence"],
                error=str(exc),
            )

    if not message and structured is None:
        return ChatResponse(
            session_id=payload.session_id or "",
            mode="error",
            assistant_message="Please enter a question, environmental description, or structured JSON.",
            knowledge_status="insufficient_verified_evidence",
            knowledge_status_label=STATUS_LABELS["insufficient_verified_evidence"],
            error="empty_input",
        )

    session_id = store.get_or_create(payload.session_id)
    updates = extract_from_text(message)
    if structured is not None:
        updates.update(structured_to_dict(structured))
    context = store.merge_updates(session_id, updates, message)
    store.add_message(session_id, "user", message or structured.model_dump_json())

    intent = classify_intent(message, context)
    docs, chunks = knowledge_store.stats()
    if chunks == 0:
        warnings.append("Knowledge base is empty. Ingest PDFs or seed documents before expecting grounded answers.")

    if needs_clarification(context, intent, message):
        questions = clarifying_questions(context, intent)
        assistant = (
            "I can investigate likely environmental pressures, but I need a few site variables first so the reasoning is not generic. "
            + " ".join(questions)
        )
        response = ChatResponse(
            session_id=session_id,
            mode="clarification",
            assistant_message=assistant,
            clarifying_questions=questions,
            environmental_context=context,
            known_variables=context.known_variables(),
            profile=heuristic_profile(context),
            knowledge_status="awaiting_clarification",
            knowledge_status_label=STATUS_LABELS["awaiting_clarification"],
            warnings=warnings,
        )
        store.add_message(session_id, "assistant", assistant)
        return response

    query = retrieval_query(message, context, include_intervention=False, include_context=False)
    retrieved = retriever.search(query)
    accepted, rejected = retriever.split_relevant(retrieved)
    if (not accepted) and _looks_like_case_followup(message, context):
        query = retrieval_query(message, context, include_intervention=True, include_context=True)
        retrieved = retriever.search(query)
        accepted, rejected = retriever.split_relevant(retrieved)
    settings = get_settings()

    debug = None
    if payload.debug:
        debug = DebugRetrieval(
            query=query,
            retrieved=retrieved,
            accepted=accepted,
            rejected=rejected,
            threshold=settings.relevance_threshold,
            backend=settings.embedding_backend,
        )

    if not accepted:
        external = search_openalex(message or query)
        status = (
            "partially_grounded_external_used" if external else "insufficient_verified_evidence"
        )
        unused = [
            item.model_copy(update={"origin": "unused_low_relevance"}) for item in rejected[:4]
        ]
        assistant = insufficient_message(len(retrieved), len(external))
        if context.known_variable_count() >= 3:
            assistant += (
                " I can still share a heuristic environmental profile from your inputs, but I will not present it as retrieved science."
            )
        response = ChatResponse(
            session_id=session_id,
            mode="fallback",
            assistant_message=assistant,
            environmental_context=context,
            known_variables=context.known_variables(),
            profile=heuristic_profile(context),
            evidence=external + unused,
            knowledge_status=status,
            knowledge_status_label=STATUS_LABELS[status],
            debug=debug,
            warnings=warnings,
        )
        store.add_message(session_id, "assistant", assistant)
        return response

    rec = build_recommendation(context, accepted)
    rec = polish_recommendation(rec, context, accepted)
    response = ChatResponse(
        session_id=session_id,
        mode="recommendation",
        assistant_message="",
        environmental_context=context,
        known_variables=context.known_variables(),
        profile=heuristic_profile(context),
        recommendation=rec,
        evidence=accepted,
        knowledge_status="grounded_in_knowledge_base",
        knowledge_status_label=STATUS_LABELS["grounded_in_knowledge_base"],
        debug=debug,
        warnings=warnings,
    )
    response.assistant_message = _format_recommendation_text(response)
    store.add_message(session_id, "assistant", response.assistant_message)
    return response
