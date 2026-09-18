from __future__ import annotations

from dataclasses import dataclass, field
import json
import logging
import time
from typing import Any, Iterator

from fastapi import HTTPException

from app.core.config import get_settings
from app.models.schemas import (
    ChatRequest,
    ChatResponse,
    ClaimEvidenceLink,
    DebugRetrieval,
    EnvironmentalContext,
    EvidenceItem,
    ImpactedMetric,
    RecommendationBlock,
    RecommendationItem,
    StructuredInput,
)
from app.services.evidence import (
    STATUS_LABELS,
    ground_answer,
    select_evidence,
    should_search_external,
    status_from_evidence,
)
from app.services.extraction import (
    extract_from_text,
    parse_structured_json,
    should_run_extraction,
    structured_to_dict,
)
from app.services.fallback import insufficient_message, search_openalex, wants_recent_literature
from app.services.ingest import knowledge_store
from app.services.llm import (
    LLMUnavailable,
    configured_llm_model,
    generate_recommendation,
    llm_is_available,
    llm_is_configured,
    stream_answer,
)
from app.services.memory import store
from app.services.prompting import (
    _answer_body,
    answer_length_band,
    build_stream_user_prompt,
    complete_recommendation,
    ensure_grounded_sources,
    ensure_material_variables,
    filter_evidence_for_answer,
    intervention_keys,
    is_conceptual_question,
    predict_budget,
    streaming_system_prompt,
)
from app.services.reasoning import (
    candidate_payload,
    classify_intent,
    clarifying_questions,
    confidence_for,
    describe_relationships,
    heuristic_profile,
    needs_clarification,
    retrieval_query,
)
from app.services.retrieval import retriever

LOGGER = logging.getLogger("darukaa.pipeline")


def _ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 1)


def _debug_base(payload: ChatRequest, settings, query: str, original: str) -> DebugRetrieval | None:
    if not payload.debug:
        return None
    embedder_backend = settings.embedding_backend
    dim = 0
    backend = embedder_backend
    model = settings.embedding_model
    vector_database = "chromadb"
    collection = settings.chroma_collection
    if settings.uses_vector_index:
        try:
            from app.services.embeddings import get_embedder

            embedder = get_embedder()
            dim = embedder.dim
            backend = embedder.backend
            model = embedder.model_name
        except Exception:
            dim = 0
    else:
        backend = "none"
        model = ""
        dim = 0
        vector_database = "bm25"
        collection = "sqlite-chunks"
    return DebugRetrieval(
        original_query=original,
        query=query,
        context_aware_query=query,
        threshold=settings.relevance_threshold,
        backend=backend,
        embedding_model=model,
        embedding_dimension=dim,
        vector_database=vector_database,
        collection=collection,
        llm_provider=settings.llm_provider,
        llm_model=configured_llm_model(),
        llm_configured=llm_is_configured(),
        llm_available=llm_is_available(),
    )


def _apply_timings(debug: DebugRetrieval | None, timings: dict[str, float], started: float) -> None:
    if debug is None:
        return
    debug.environment_extraction_ms = timings.get("environment_extraction_ms")
    debug.memory_ms = timings.get("memory_ms")
    debug.chroma_retrieval_ms = timings.get("chroma_retrieval_ms")
    debug.openalex_ms = timings.get("openalex_ms")
    debug.evidence_selection_ms = timings.get("evidence_selection_ms")
    debug.prompt_build_ms = timings.get("prompt_build_ms")
    debug.llm_first_token_ms = timings.get("llm_first_token_ms")
    debug.llm_total_ms = timings.get("llm_total_ms")
    debug.grounding_ms = timings.get("grounding_ms")
    debug.total_request_ms = _ms(started)


def recommendation_from_answer(
    answer: str,
    context: EnvironmentalContext,
    evidence: list[EvidenceItem],
    rec: RecommendationBlock | None = None,
    *,
    user_message: str = "",
) -> RecommendationBlock:
    relationships, used = describe_relationships(context)
    mentioned: list[str] = []
    seed_items: list[RecommendationItem] = []
    body = _answer_body(answer).lower()
    body_keys = intervention_keys(body)
    for item in candidate_payload(context):
        action = str(item.get("action") or item.get("idea") or "").strip()
        keywords = [str(token).lower() for token in (item.get("keywords") or []) if token]
        keys = intervention_keys(action)
        keyword_hits = sum(1 for token in keywords if token in body)
        if action and (
            action.lower()[:24] in body
            or keyword_hits >= 2
            or (keys and keys <= body_keys)
            or (keys and (keys & body_keys) and keyword_hits >= 1)
        ):
            if action not in mentioned:
                mentioned.append(action)
            why = str(item.get("why") or item.get("why_candidate") or "").strip()
            raw_metrics = item.get("metrics") or []
            metrics: list[ImpactedMetric] = []
            for metric in raw_metrics:
                if isinstance(metric, ImpactedMetric):
                    metrics.append(metric)
                elif isinstance(metric, dict) and metric.get("name"):
                    metrics.append(
                        ImpactedMetric(
                            name=str(metric["name"]),
                            direction="unknown",
                            note=str(metric.get("note") or "potentially affected"),
                        )
                    )
            seed_items.append(
                RecommendationItem(
                    action=action,
                    why=why,
                    impacted_metrics=metrics,
                )
            )
    first_line = next(
        (line.strip() for line in _answer_body(answer).splitlines() if len(line.strip()) > 40),
        _answer_body(answer)[:280],
    )
    action = "; ".join(mentioned[:4]) if mentioned else first_line[:400]
    distinct_sources = len({item.document_name for item in evidence})
    confidence, rationale = confidence_for(context, len(evidence), distinct_sources, len(used))
    seed = rec or RecommendationBlock(
        action=action,
        why_it_works="",
        environmental_relationships=relationships,
        impacted_metrics=[],
        uncertainty=None,
        confidence=confidence,  # type: ignore[arg-type]
        confidence_rationale=rationale,
        items=seed_items,
    )
    if not seed.action:
        seed.action = action
    if not seed.environmental_relationships:
        seed.environmental_relationships = relationships
    if not seed.confidence_rationale:
        seed.confidence = confidence  # type: ignore[arg-type]
        seed.confidence_rationale = rationale
    if not seed.items and seed_items:
        seed.items = seed_items
    if not (seed.why_it_works or "").strip():
        seed.why_it_works = " ".join(item.why for item in (seed.items or seed_items) if item.why).strip()
    if not seed.impacted_metrics:
        merged: list[ImpactedMetric] = []
        for item in seed.items or seed_items:
            for metric in item.impacted_metrics:
                if all(existing.name.lower() != metric.name.lower() for existing in merged):
                    merged.append(metric)
        seed.impacted_metrics = merged
    return complete_recommendation(
        seed,
        answer,
        context,
        evidence,
        user_message=user_message,
    )


def _apply_grounding(
    prepared: PreparedChat,
    draft: str,
    rec: RecommendationBlock | None = None,
    claims: list[ClaimEvidenceLink] | None = None,
) -> tuple[str, list[ClaimEvidenceLink], RecommendationBlock, list[EvidenceItem], list[EvidenceItem]]:
    answer, claims = ground_answer(
        draft,
        prepared.selected,
        user_message=prepared.message,
        context=prepared.context,
        claims=claims,
    )
    if not is_conceptual_question(prepared.message):
        answer = ensure_material_variables(answer, prepared.context)
    answer, claims = ground_answer(
        answer,
        prepared.selected,
        user_message=prepared.message,
        context=prepared.context,
        claims=claims,
    )
    used_kb, used_ext = filter_evidence_for_answer(
        answer,
        claims,
        [],
        prepared.kb_selected,
        prepared.ext_selected,
    )
    answer = ensure_grounded_sources(answer, used_kb, used_ext, message=prepared.message)
    rec = recommendation_from_answer(
        answer,
        prepared.context,
        [*used_kb, *used_ext],
        rec,
        user_message=prepared.message,
    )
    return answer, claims, rec, used_kb, used_ext


@dataclass
class PreparedChat:
    payload: ChatRequest
    session_id: str
    message: str
    context: EnvironmentalContext
    history: list[dict[str, Any]]
    query: str
    retrieved: list[EvidenceItem]
    accepted: list[EvidenceItem]
    rejected: list[EvidenceItem]
    external: list[EvidenceItem]
    selected: list[EvidenceItem]
    kb_selected: list[EvidenceItem]
    ext_selected: list[EvidenceItem]
    need_external: bool
    external_reason: str | None
    warnings: list[str]
    debug: DebugRetrieval | None
    timings: dict[str, float]
    started: float
    candidates: list[dict[str, Any]] = field(default_factory=list)
    early_response: ChatResponse | None = None


def _resolve_structured(payload: ChatRequest) -> StructuredInput | None:
    structured = payload.structured
    from_json: StructuredInput | None = None
    if payload.structured_json:
        try:
            from_json = parse_structured_json(payload.structured_json)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    if structured is not None and from_json is not None:
        merged = {**structured_to_dict(from_json), **structured_to_dict(structured)}
        return StructuredInput.model_validate(merged)
    return structured if structured is not None else from_json


def prepare_chat(payload: ChatRequest) -> PreparedChat:
    warnings: list[str] = []
    timings: dict[str, float] = {}
    started = time.perf_counter()
    message = (payload.message or "").strip()
    settings = get_settings()
    structured = _resolve_structured(payload)

    if not message and structured is None:
        raise HTTPException(status_code=400, detail="Please enter a question, environmental description, or structured JSON.")

    t_mem = time.perf_counter()
    session_id, context = store.ensure_session(payload.session_id)
    timings["memory_ms"] = _ms(t_mem)

    t_ext = time.perf_counter()
    updates: dict[str, Any] = {}
    if should_run_extraction(message, context):
        updates = extract_from_text(message)
    if structured is not None:
        updates.update(structured_to_dict(structured))
    timings["environment_extraction_ms"] = _ms(t_ext)

    t_mem2 = time.perf_counter()
    context = store.merge_updates(session_id, updates, message, context=context)
    store.add_message(session_id, "user", message or structured.model_dump_json())
    history = store.history(session_id, limit=settings.history_window)
    timings["memory_ms"] = round(timings.get("memory_ms", 0.0) + _ms(t_mem2), 1)

    intent = classify_intent(message, context)
    docs, chunks = knowledge_store.stats()
    if chunks == 0:
        warnings.append("Knowledge base is empty. Ingest documents before expecting grounded answers.")

    debug = _debug_base(payload, settings, retrieval_query(message, context, include_context=True), message)

    if needs_clarification(context, intent, message):
        questions = clarifying_questions(context, intent)
        assistant = (
            "I can look into this with you, but I need a little more about the site so I am not guessing. "
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
            debug=debug,
        )
        store.add_message(session_id, "assistant", assistant)
        _apply_timings(debug, timings, started)
        return PreparedChat(
            payload=payload,
            session_id=session_id,
            message=message,
            context=context,
            history=history,
            query="",
            retrieved=[],
            accepted=[],
            rejected=[],
            external=[],
            selected=[],
            kb_selected=[],
            ext_selected=[],
            need_external=False,
            external_reason=None,
            warnings=warnings,
            debug=debug,
            timings=timings,
            started=started,
            early_response=response,
        )

    query = retrieval_query(message, context, include_context=True)
    t_chroma = time.perf_counter()
    retrieved = retriever.search(query)
    accepted, rejected = retriever.split_relevant(retrieved)
    timings["chroma_retrieval_ms"] = _ms(t_chroma)

    need_external, external_reason = should_search_external(message, accepted, rejected)
    external: list[EvidenceItem] = []
    t_oa = time.perf_counter()
    if need_external:
        env_blob = " ".join(f"{k} {v}" for k, v in context.known_variables().items())
        external = search_openalex(
            f"{message} {query}",
            environmental_context=env_blob,
            prefer_recent=wants_recent_literature(message),
        )
    timings["openalex_ms"] = _ms(t_oa) if need_external else 0.0

    t_sel = time.perf_counter()
    selected = select_evidence(accepted, external)
    kb_selected = [item for item in selected if item.origin == "knowledge_base"]
    ext_selected = [item for item in selected if item.origin == "external_openalex"]
    timings["evidence_selection_ms"] = _ms(t_sel)

    if debug:
        debug.query = query
        debug.context_aware_query = query
        debug.retrieved = retrieved
        debug.accepted = accepted
        debug.rejected = rejected
        debug.external_search_triggered = need_external
        debug.external_search_reason = external_reason if need_external else None
        debug.external_retrieved = external
        debug.conversation_context_used = bool(context.known_variables() or history)
        debug.evidence_selected_for_llm = [item.evidence_id for item in selected]

    prepared = PreparedChat(
        payload=payload,
        session_id=session_id,
        message=message,
        context=context,
        history=history,
        query=query,
        retrieved=retrieved,
        accepted=accepted,
        rejected=rejected,
        external=external,
        selected=selected,
        kb_selected=kb_selected,
        ext_selected=ext_selected,
        need_external=need_external,
        external_reason=external_reason if need_external else None,
        warnings=warnings,
        debug=debug,
        timings=timings,
        started=started,
        candidates=candidate_payload(context),
    )

    if not selected:
        unused = [
            item.model_copy(update={"origin": "unused_low_relevance"}) for item in rejected[:4]
        ]
        assistant = insufficient_message(len(retrieved), len(external))
        response = ChatResponse(
            session_id=session_id,
            mode="fallback",
            assistant_message=assistant,
            environmental_context=context,
            known_variables=context.known_variables(),
            profile=heuristic_profile(context),
            evidence=unused,
            kb_evidence=[],
            external_evidence=[],
            knowledge_status="insufficient_evidence",
            knowledge_status_label=STATUS_LABELS["insufficient_evidence"],
            debug=debug,
            warnings=warnings,
        )
        store.add_message(session_id, "assistant", assistant)
        _apply_timings(debug, timings, started)
        prepared.early_response = response
        return prepared

    return prepared


def _require_llm(settings) -> None:
    if llm_is_configured() and llm_is_available():
        return
    provider = settings.llm_provider.lower()
    if provider == "openai":
        detail = (
            "The optional OpenAI provider is not available. "
            "Set OPENAI_API_KEY, or switch to LLM_PROVIDER=ollama for the free local model."
        )
    elif provider == "groq":
        detail = (
            "The Groq provider is not available. "
            "Set GROQ_API_KEY, or switch to LLM_PROVIDER=ollama for the free local model."
        )
    else:
        detail = (
            "The local AI model is not running. Please start Ollama and make sure the configured model is installed."
        )
    raise HTTPException(status_code=503, detail=detail)


def _finalize_response(
    *,
    prepared: PreparedChat,
    rec: RecommendationBlock,
    answer: str,
    claims: list[ClaimEvidenceLink],
    kb_selected: list[EvidenceItem],
    ext_selected: list[EvidenceItem],
    prompt: str | None,
    raw_preview: str,
) -> ChatResponse:
    status = status_from_evidence([*kb_selected, *ext_selected], claims)
    if not rec.action:
        rec.action = answer
    if prepared.debug:
        prepared.debug.retrieved_context_passed_to_llm = True
        prepared.debug.llm_prompt = prompt
        prepared.debug.llm_raw_response = raw_preview[:8000]
        prepared.debug.claims = claims
        prepared.debug.knowledge_status = status
    source_types = []
    if kb_selected:
        source_types.append("knowledge_base")
    if ext_selected:
        source_types.append("external_openalex")
    _apply_timings(prepared.debug, prepared.timings, prepared.started)
    response = ChatResponse(
        session_id=prepared.session_id,
        mode="recommendation",
        assistant_message=answer,
        environmental_context=prepared.context,
        known_variables=prepared.context.known_variables(),
        profile=heuristic_profile(prepared.context),
        recommendation=rec,
        evidence=[*kb_selected, *ext_selected],
        kb_evidence=kb_selected,
        external_evidence=ext_selected,
        knowledge_status=status,
        knowledge_status_label=STATUS_LABELS[status],
        source_types=source_types,
        claims=claims,
        debug=prepared.debug,
        warnings=prepared.warnings,
    )
    store.add_message(prepared.session_id, "assistant", response.assistant_message)
    return response


def handle_chat(payload: ChatRequest) -> ChatResponse:
    prepared = prepare_chat(payload)
    if prepared.early_response is not None:
        return prepared.early_response

    settings = get_settings()
    _require_llm(settings)

    t_prompt = time.perf_counter()
    try:
        rec, raw, prompt, _model = generate_recommendation(
            message=prepared.message,
            context=prepared.context,
            history=prepared.history,
            kb_evidence=prepared.kb_selected,
            external_evidence=prepared.ext_selected,
            candidates=prepared.candidates,
        )
    except LLMUnavailable as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    except Exception:
        LOGGER.exception("Language model request failed")
        raise HTTPException(
            status_code=502,
            detail="The language model could not complete this request. Please try again.",
        )
    prepared.timings["prompt_build_ms"] = _ms(t_prompt)
    prepared.timings["llm_total_ms"] = prepared.timings.get("prompt_build_ms", 0.0)
    prepared.timings["llm_first_token_ms"] = prepared.timings["llm_total_ms"]

    t_ground = time.perf_counter()
    claims = [ClaimEvidenceLink(**item) for item in raw.get("_claims") or []]
    answer, claims, rec, used_kb, used_ext = _apply_grounding(
        prepared,
        str(raw.get("_answer") or rec.action),
        rec,
        claims,
    )
    prepared.kb_selected = used_kb or raw.get("_kb_used") or prepared.kb_selected
    prepared.ext_selected = used_ext or raw.get("_ext_used") or prepared.ext_selected
    prepared.timings["grounding_ms"] = _ms(t_ground)
    return _finalize_response(
        prepared=prepared,
        rec=rec,
        answer=answer,
        claims=claims,
        kb_selected=prepared.kb_selected,
        ext_selected=prepared.ext_selected,
        prompt=prompt,
        raw_preview=str(raw.get("_raw") or ""),
    )


def handle_chat_stream(payload: ChatRequest) -> Iterator[dict[str, Any]]:
    prepared = prepare_chat(payload)
    if prepared.early_response is not None:
        yield {"type": "final", "response": prepared.early_response.model_dump()}
        return

    settings = get_settings()
    try:
        _require_llm(settings)
    except HTTPException as exc:
        yield {"type": "error", "detail": exc.detail}
        return

    band = answer_length_band(prepared.context, prepared.message)
    t_prompt = time.perf_counter()
    system = streaming_system_prompt(band)
    user = build_stream_user_prompt(
        message=prepared.message,
        context=prepared.context,
        history=prepared.history,
        kb_evidence=prepared.kb_selected,
        external_evidence=prepared.ext_selected,
        candidates=prepared.candidates,
    )
    prepared.timings["prompt_build_ms"] = _ms(t_prompt)
    if prepared.debug:
        prepared.debug.llm_prompt = f"SYSTEM INSTRUCTIONS:\n{system}\n\n{user}"
        prepared.debug.retrieved_context_passed_to_llm = True

    t_llm = time.perf_counter()
    chunks: list[str] = []
    first_token_at: float | None = None
    try:
        for token in stream_answer(
            system,
            user,
            json_mode=False,
            temperature=0.35,
            num_predict=predict_budget(band),
        ):
            if not token:
                continue
            if first_token_at is None:
                first_token_at = time.perf_counter()
                prepared.timings["llm_first_token_ms"] = round((first_token_at - t_llm) * 1000, 1)
            chunks.append(token)
            yield {"type": "token", "text": token}
    except LLMUnavailable as exc:
        yield {"type": "error", "detail": exc.message}
        return
    except Exception:
        LOGGER.exception("Language model stream failed")
        yield {"type": "error", "detail": "The language model could not complete this request. Please try again."}
        return

    prepared.timings["llm_total_ms"] = _ms(t_llm)
    if "llm_first_token_ms" not in prepared.timings:
        prepared.timings["llm_first_token_ms"] = prepared.timings["llm_total_ms"]
    draft = "".join(chunks).strip()
    if not draft:
        yield {"type": "error", "detail": "The local AI model returned an empty response."}
        return

    t_ground = time.perf_counter()
    answer, claims, rec, used_kb, used_ext = _apply_grounding(prepared, draft)
    prepared.timings["grounding_ms"] = _ms(t_ground)
    response = _finalize_response(
        prepared=prepared,
        rec=rec,
        answer=answer,
        claims=claims,
        kb_selected=used_kb,
        ext_selected=used_ext,
        prompt=f"SYSTEM INSTRUCTIONS:\n{system}\n\n{user}" if prepared.debug else None,
        raw_preview=draft,
    )
    yield {"type": "final", "response": response.model_dump()}
