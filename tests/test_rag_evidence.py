from app.models.schemas import ChatRequest, EvidenceItem
from app.services import pipeline
from app.services.evidence import select_evidence, status_from_evidence
from app.services.fallback import clear_openalex_cache, search_openalex
from app.services.llm import RecordingLLM
from app.services.pipeline import handle_chat
from app.core.config import get_settings


FARM = (
    "I have a 5-acre farm in a semi-arid region. I grow wheat as a monoculture. "
    "My soil pH is 8.1, organic carbon is 0.3%, and soil moisture is low. "
    "Rainfall is low and irregular, with temperatures around 30C. "
    "I have noticed fewer bees and butterflies. What should I do?"
)

EXTERNAL = EvidenceItem(
    evidence_id="oa-micro1",
    source="OpenAlex — Soil Biology",
    document_name="Microplastics reduce soil microbial diversity",
    title="Microplastics reduce soil microbial diversity",
    authors="Example, A.",
    passage=(
        "Abstract-level evidence: field soils exposed to polyethylene fragments "
        "showed lower bacterial richness than untreated agricultural controls."
    ),
    relevance_score=0.81,
    origin="external_openalex",
    evidence_level="abstract",
    year=2024,
    url="https://example.org/microplastics",
    doi="10.1234/example.microplastics",
)


def _kb(evidence_id: str, passage: str, score: float = 0.88) -> EvidenceItem:
    return EvidenceItem(
        evidence_id=evidence_id,
        source="01_soil_organic_carbon_biodiversity.md",
        document_name="01_soil_organic_carbon_biodiversity.md",
        title="Soil organic carbon and biodiversity",
        passage=passage,
        relevance_score=score,
        origin="knowledge_base",
        evidence_level="passage",
        year=2023,
    )


def test_rag_prompt_contains_internal_evidence(llm_recorder: RecordingLLM):
    result = handle_chat(ChatRequest(message=FARM, debug=True))
    assert result.debug and result.debug.llm_prompt
    prompt = result.debug.llm_prompt
    assert "SYSTEM INSTRUCTIONS" in prompt
    assert "USER QUESTION" in prompt
    assert "CONVERSATION CONTEXT" in prompt
    assert "ENVIRONMENTAL VARIABLES" in prompt
    assert "INTERNAL KNOWLEDGE BASE" in prompt
    assert "EXTERNAL SCIENTIFIC EVIDENCE" in prompt
    assert "REASONING REQUIREMENTS" in prompt
    assert "OUTPUT FORMAT" in prompt
    assert "0.3" in prompt
    assert result.debug.retrieved_context_passed_to_llm is True
    assert result.knowledge_status == "grounded_in_knowledge_base"


def test_internal_only_answer(llm_recorder: RecordingLLM):
    result = handle_chat(ChatRequest(message=FARM, debug=True))
    assert result.mode == "recommendation"
    assert result.kb_evidence
    assert not result.external_evidence
    assert result.source_types == ["knowledge_base"]
    assert "(none)" in (result.debug.llm_prompt or "")
    assert "INTERNAL KNOWLEDGE BASE" in (result.debug.llm_prompt or "")


def test_rag_prompt_contains_external_evidence(monkeypatch, llm_recorder: RecordingLLM):
    monkeypatch.setattr(pipeline, "should_search_external", lambda *a, **k: (True, "user_requested_research_or_recency"))
    monkeypatch.setattr(pipeline, "search_openalex", lambda *a, **k: [EXTERNAL])
    result = handle_chat(
        ChatRequest(
            message="What does recent research say about microplastics affecting soil microbial diversity in agricultural soils?",
            debug=True,
        )
    )
    prompt = (result.debug.llm_prompt if result.debug else "") or ""
    assert "EXTERNAL SCIENTIFIC EVIDENCE" in prompt
    assert "microplastics" in prompt.lower()
    assert "oa-micro1" in prompt
    assert result.external_evidence
    assert any(item.evidence_level == "abstract" for item in result.external_evidence)


def test_external_only_answer(monkeypatch, llm_recorder: RecordingLLM):
    monkeypatch.setattr(pipeline.retriever, "search", lambda query: [])
    monkeypatch.setattr(pipeline.retriever, "split_relevant", lambda items: ([], []))
    monkeypatch.setattr(pipeline, "should_search_external", lambda *a, **k: (True, "kb_insufficient"))
    monkeypatch.setattr(pipeline, "search_openalex", lambda *a, **k: [EXTERNAL])
    result = handle_chat(
        ChatRequest(
            message="What does recent research say about microplastics affecting soil microbial diversity?",
            debug=True,
        )
    )
    assert result.mode == "recommendation"
    assert not result.kb_evidence
    assert result.external_evidence
    assert result.knowledge_status == "grounded_in_external_evidence"
    assert result.debug and result.debug.external_search_triggered is True


def test_kb_and_external_answer(monkeypatch, llm_recorder: RecordingLLM):
    kb = _kb("kb-9", "Cover crops and residue can support soil organisms where carbon is low.")
    monkeypatch.setattr(pipeline.retriever, "search", lambda query: [kb])
    monkeypatch.setattr(pipeline.retriever, "split_relevant", lambda items: (items, []))
    monkeypatch.setattr(pipeline, "should_search_external", lambda *a, **k: (True, "user_requested_research_or_recency"))
    monkeypatch.setattr(pipeline, "search_openalex", lambda *a, **k: [EXTERNAL])
    result = handle_chat(
        ChatRequest(
            message="Low soil carbon 0.3%, low rainfall, wheat monoculture. Also find recent studies on cover crops.",
            debug=True,
        )
    )
    assert result.kb_evidence
    assert result.external_evidence
    assert result.knowledge_status == "grounded_in_kb_and_external"
    prompt = result.debug.llm_prompt if result.debug else ""
    assert "kb-9" in prompt
    assert "oa-micro1" in prompt


def test_insufficient_evidence(monkeypatch, llm_recorder: RecordingLLM):
    monkeypatch.setattr(pipeline.retriever, "search", lambda query: [])
    monkeypatch.setattr(pipeline.retriever, "split_relevant", lambda items: ([], []))
    monkeypatch.setattr(pipeline, "search_openalex", lambda *a, **k: [])
    result = handle_chat(
        ChatRequest(
            message="How does Kepler-442b orbital resonance affect silicon wafer doping in hadal amphipod genomes?",
            debug=True,
        )
    )
    assert result.mode == "fallback"
    assert result.knowledge_status == "insufficient_evidence"
    assert "enough" in result.assistant_message.lower() or "will not invent" in result.assistant_message.lower()
    assert result.debug is None or not result.debug.llm_prompt


def test_conversation_context_reaches_retrieval(llm_recorder: RecordingLLM):
    first = handle_chat(ChatRequest(message="My farm has very low soil moisture.", debug=True))
    second = handle_chat(
        ChatRequest(session_id=first.session_id, message="What should I do?", debug=True)
    )
    assert second.known_variables.get("soil_moisture") == "low"
    if second.mode == "clarification":
        joined = " ".join(second.clarifying_questions).lower()
        assert "moisture" not in joined
    else:
        query = ((second.debug.context_aware_query if second.debug else "") or "").lower()
        assert "moisture" in query
        if second.mode == "recommendation":
            prompt = llm_recorder.prompts[-1].lower()
            assert "moisture" in prompt


def test_claim_evidence_grounding(llm_recorder: RecordingLLM):
    result = handle_chat(ChatRequest(message=FARM, debug=True))
    assert result.mode == "recommendation"
    assert result.claims
    selected_ids = {item.evidence_id for item in result.evidence}
    for claim in result.claims:
        if claim.support == "direct":
            assert claim.evidence_ids
            assert all(eid in selected_ids for eid in claim.evidence_ids)


def test_no_fabricated_citations(llm_recorder: RecordingLLM):
    result = handle_chat(ChatRequest(message=FARM, debug=True))
    blob = (result.assistant_message or "") + " " + " ".join(
        item.doi or "" for item in result.evidence
    )
    known_dois = {item.doi for item in result.evidence if item.doi}
    import re

    found = set(re.findall(r"10\.\d{4,}/[^\s]+", result.assistant_message or ""))
    assert found <= known_dois
    assert "I analyzed the full paper" not in (result.assistant_message or "")


def test_openalex_failure_falls_back_to_kb(monkeypatch, llm_recorder: RecordingLLM):
    kb = _kb("kb-12", "Low soil organic carbon and low rainfall reduce habitat quality for insects.")
    monkeypatch.setattr(pipeline.retriever, "search", lambda query: [kb])
    monkeypatch.setattr(pipeline.retriever, "split_relevant", lambda items: (items, []))
    monkeypatch.setattr(pipeline, "should_search_external", lambda *a, **k: (True, "user_requested_research_or_recency"))
    monkeypatch.setattr(pipeline, "search_openalex", lambda *a, **k: [])
    result = handle_chat(ChatRequest(message=FARM + " Please cite recent studies.", debug=True))
    assert result.mode == "recommendation"
    assert result.kb_evidence
    assert not result.external_evidence
    assert result.knowledge_status == "grounded_in_knowledge_base"


def test_external_evidence_ranking_and_level(monkeypatch):
    clear_openalex_cache()
    settings = get_settings()
    monkeypatch.setattr(settings, "enable_openalex", True)
    monkeypatch.setattr(settings, "fetch_open_access_text", False)

    works = {
        "results": [
            {
                "id": "https://openalex.org/W111",
                "display_name": "Microplastics and soil microbes in farmland",
                "publication_year": 2024,
                "doi": "https://doi.org/10.1234/soil-micro",
                "cited_by_count": 40,
                "abstract_inverted_index": {
                    "Microplastics": [0],
                    "reduced": [1],
                    "soil": [2],
                    "microbial": [3],
                    "diversity": [4],
                    "in": [5],
                    "agricultural": [6],
                    "soils": [7],
                },
                "open_access": {"is_oa": False, "oa_url": None},
                "primary_location": {
                    "landing_page_url": "https://example.org/soil-micro",
                    "source": {"display_name": "Soil Biology"},
                },
                "authorships": [{"author": {"display_name": "Ada Example"}}],
            },
            {
                "id": "https://openalex.org/W222",
                "display_name": "Galactic dust near a distant quasar",
                "publication_year": 1991,
                "doi": None,
                "cited_by_count": 1,
                "abstract_inverted_index": {
                    "Quasar": [0],
                    "spectra": [1],
                    "from": [2],
                    "galactic": [3],
                    "dust": [4],
                },
                "open_access": {"is_oa": False, "oa_url": None},
                "primary_location": {"landing_page_url": None, "source": {"display_name": "Astro"}},
                "authorships": [],
            },
        ]
    }

    class FakeResponse:
        status_code = 200

        def json(self):
            return works

    monkeypatch.setattr("app.services.fallback.httpx.get", lambda *a, **k: FakeResponse())
    ranked = search_openalex(
        "microplastics soil microbial diversity agricultural soils",
        environmental_context="agricultural soil microbial diversity",
        prefer_recent=True,
    )
    assert ranked
    assert ranked[0].title and "microplastics" in ranked[0].title.lower()
    assert ranked[0].evidence_level == "abstract"
    assert all("quasar" not in (item.title or "").lower() for item in ranked)


def test_evidence_level_labeling_in_prompt(monkeypatch, llm_recorder: RecordingLLM):
    monkeypatch.setattr(pipeline.retriever, "search", lambda query: [])
    monkeypatch.setattr(pipeline.retriever, "split_relevant", lambda items: ([], []))
    monkeypatch.setattr(pipeline, "search_openalex", lambda *a, **k: [EXTERNAL])
    result = handle_chat(
        ChatRequest(
            message="What does recent research say about microplastics affecting soil microbial diversity?",
            debug=True,
        )
    )
    prompt = result.debug.llm_prompt if result.debug else ""
    assert "abstract-level evidence" in prompt.lower()
    assert all(item.evidence_level == "abstract" for item in result.external_evidence)


def test_select_evidence_prefers_higher_scores():
    weak_ext = EXTERNAL.model_copy(update={"relevance_score": 0.3, "evidence_id": "oa-weak"})
    strong_kb = _kb("kb-1", "Cover crops help retain moisture.", 0.9)
    selected = select_evidence([strong_kb], [weak_ext, EXTERNAL])
    assert selected[0].evidence_id == "kb-1"
    status = status_from_evidence(selected, [])
    assert status in {"grounded_in_knowledge_base", "grounded_in_kb_and_external"}


def test_select_evidence_keeps_three_to_five_unique_passages():
    items = [_kb(f"kb-{i}", f"Cover crops help retain moisture in dry soils {i}.", 0.9 - i * 0.01) for i in range(8)]
    selected = select_evidence(items, [])
    assert 3 <= len(selected) <= 5
    assert selected[0].evidence_id == "kb-0"

