from app.models.schemas import ChatRequest, StructuredInput
from app.services.llm import RecordingLLM
from app.services.pipeline import handle_chat, handle_chat_stream
from app.services.retrieval import retriever

FARM_PROFILE_MESSAGE = (
    "My farm is 5 acres in a semi-arid region. I grow wheat as a monoculture. "
    "Soil pH is 8.1, organic carbon is 0.3%, soil moisture is low, rainfall is low and irregular, "
    "and I've noticed fewer bees and butterflies. What should I do?"
)


def _assert_recommendation_panel(rec, evidence):
    assert rec
    assert rec.action.strip()
    assert rec.why_it_works.strip()
    assert rec.impacted_metrics
    names = [metric.name.lower() for metric in rec.impacted_metrics]
    assert any("carbon" in name or "pollinator" in name or "habitat" in name or "moisture" in name for name in names)
    assert all(len(name) < 60 for name in names)
    assert all("depending on establishment" not in name for name in names)
    assert rec.time_horizon.narrative
    assert rec.supporting_evidence
    allowed = {(item.title or item.document_name) for item in evidence}
    for title in rec.supporting_evidence:
        assert title in allowed
    items = rec.items
    assert items
    seen = set()
    for item in items:
        key = " ".join(item.action.lower().split())
        assert key not in seen
        seen.add(key)
        assert item.why.strip()
        assert item.impacted_metrics
        assert item.time_horizon
        assert item.supporting_evidence
        for title in item.supporting_evidence:
            assert title in allowed
        assert all("potentially affected" in (metric.note or "").lower() or "possible" in (metric.note or "").lower() for metric in item.impacted_metrics)


def test_farm_profile_retrieves_and_reasons(llm_recorder: RecordingLLM):
    result = handle_chat(
        ChatRequest(
            message=FARM_PROFILE_MESSAGE,
            debug=True,
        )
    )
    assert result.mode in {"recommendation", "fallback"}
    known = result.known_variables
    assert known.get("crop") == "wheat"
    assert known.get("soil_organic_carbon") == 0.3
    assert known.get("rainfall") == "low"
    assert known.get("pollinator_diversity") == "declining"
    if result.mode == "recommendation":
        assert result.recommendation
        assert result.debug and result.debug.retrieved_context_passed_to_llm
        assert llm_recorder.prompts
        prompt = llm_recorder.prompts[-1]
        assert "INTERNAL KNOWLEDGE BASE" in prompt
        assert "EXTERNAL SCIENTIFIC EVIDENCE" in prompt
        assert "0.3" in prompt
        rel = result.recommendation.environmental_relationships.lower()
        assert "carbon" in rel or "rainfall" in rel or "wheat" in rel
        _assert_recommendation_panel(result.recommendation, result.evidence)


def test_farm_profile_stream_fills_recommendation_panel(llm_recorder: RecordingLLM):
    final = None
    for event in handle_chat_stream(ChatRequest(message=FARM_PROFILE_MESSAGE, debug=True)):
        if event.get("type") == "final":
            final = event["response"]
    assert final and final["mode"] in {"recommendation", "fallback"}
    rec = final.get("recommendation")
    assert rec
    assert rec.get("why_it_works", "").strip()
    metrics = rec.get("impacted_metrics") or []
    assert metrics
    names = [str(metric.get("name") or "").lower() for metric in metrics]
    assert any("carbon" in name or "pollinator" in name or "habitat" in name or "moisture" in name for name in names)
    assert all("depending on establishment" not in name for name in names)
    horizon = rec.get("time_horizon") or {}
    assert str(horizon.get("narrative") or "").strip()
    assert rec.get("supporting_evidence")
    items = rec.get("items") or []
    assert items
    actions = [" ".join(str(item.get("action") or "").lower().split()) for item in items]
    assert len(actions) == len(set(actions))
    for item in items:
        assert str(item.get("why") or "").strip()
        assert item.get("impacted_metrics")
        assert str(item.get("time_horizon") or "").strip()
        assert item.get("supporting_evidence")


def test_pollution_urban_species_richness():
    result = handle_chat(
        ChatRequest(
            message="High pollution, low species richness and urban expansion around the site. What should I do?",
            debug=True,
        )
    )
    assert result.mode in {"recommendation", "clarification", "fallback"}
    if result.recommendation:
        blob = (result.recommendation.action + result.recommendation.why_it_works).lower()
        assert "pollution" in blob or "corridor" in blob or "urban" in blob or "habitat" in blob


def test_out_of_knowledge_does_not_fabricate_kb_papers():
    result = handle_chat(
        ChatRequest(
            message="How does Kepler-442b orbital resonance affect silicon wafer doping yields in hadal amphipod genomes?",
            debug=True,
        )
    )
    assert result.mode in {"fallback", "recommendation", "clarification"}
    kb_names = " ".join(item.document_name.lower() for item in result.evidence if item.origin == "knowledge_base")
    assert "kepler" not in kb_names
    if result.mode == "fallback":
        assert result.knowledge_status == "insufficient_evidence"
        assert "fabricate" in result.assistant_message.lower() or "enough verified" in result.assistant_message.lower() or "confident" in result.assistant_message.lower()


def test_irrelevant_documents_are_rejected():
    hits = retriever.search("Kepler-442b silicon wafer doping hadal amphipod genomes")
    accepted, rejected = retriever.split_relevant(hits)
    assert isinstance(rejected, list)
    if accepted:
        assert all("kepler" not in (item.document_name or "").lower() for item in accepted)


def test_unsupported_percent_claim_is_not_fabricated():
    result = handle_chat(
        ChatRequest(
            message="My semi-arid wheat monoculture has 0.3% soil carbon and low rainfall. Will organic carbon increase by 25% in three months if I plant cover crops?",
            debug=True,
        )
    )
    blob = (result.assistant_message or "").lower()
    if result.recommendation:
        blob += result.recommendation.why_it_works.lower()
        blob += (result.recommendation.time_horizon.short_term or "").lower()
    assert "increase by 25%" not in blob
    assert "25 percent in three months" not in blob


def test_sources_preserved():
    result = handle_chat(
        ChatRequest(
            message="Explain how low soil organic carbon, low rainfall and monoculture affect biodiversity.",
            structured=StructuredInput(
                soil_organic_carbon=0.3,
                rainfall="low",
                land_use="monoculture",
                crop="wheat",
            ),
            debug=True,
        )
    )
    if result.evidence:
        for item in result.evidence:
            assert item.document_name
            assert item.passage
