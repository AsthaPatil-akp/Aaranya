from app.models.schemas import ChatRequest, StructuredInput
from app.services.pipeline import handle_chat
from app.services.retrieval import retriever


def test_low_rainfall_low_soc_monoculture_retrieves_relevant_docs():
    result = handle_chat(
        ChatRequest(
            message="Semi-arid wheat monoculture, soil organic carbon 0.3%, low rainfall and low soil moisture. What should I do?",
            debug=True,
        )
    )
    assert result.mode == "recommendation"
    names = " ".join(item.document_name.lower() for item in result.evidence)
    assert any(token in names for token in ["soil", "cover", "monoculture", "rainfall", "agroforest"])
    action = result.recommendation.action.lower() if result.recommendation else ""
    assert "cover" in action or "agroforest" in action or "intercrop" in action
    assert result.recommendation and len(result.recommendation.impacted_metrics) >= 3


def test_pollution_urban_species_richness():
    result = handle_chat(
        ChatRequest(
            message="High pollution, low species richness and urban expansion around the site.",
            debug=True,
        )
    )
    assert result.mode in {"recommendation", "fallback"}
    if result.mode == "recommendation":
        blob = (result.recommendation.action + result.recommendation.why_it_works).lower()
        assert "pollution" in blob or "corridor" in blob or "urban" in blob


def test_temperature_drought_low_vegetation():
    result = handle_chat(
        ChatRequest(
            message="High temperature 34C, drought, and low vegetation on degraded land.",
            debug=True,
        )
    )
    assert result.recommendation or result.mode == "fallback"
    if result.recommendation:
        assert "drought" in result.recommendation.action.lower() or "native" in result.recommendation.action.lower()


def test_deforestation_fragmentation():
    result = handle_chat(
        ChatRequest(
            message="Deforestation and habitat fragmentation are driving biodiversity decline in remaining patches.",
            debug=True,
        )
    )
    if result.recommendation:
        text = (result.recommendation.action + result.recommendation.why_it_works).lower()
        assert "fragment" in text or "corridor" in text or "forest" in text


def test_out_of_knowledge_after_context_still_refuses():
    first = handle_chat(
        ChatRequest(
            message="Please recommend an intervention for this farm.",
            structured=StructuredInput(
                region="semi-arid",
                soil_organic_carbon=0.3,
                rainfall="low",
                crop="wheat",
                land_use="monoculture",
                soil_moisture="low",
            ),
        )
    )
    assert first.mode == "recommendation"
    second = handle_chat(
        ChatRequest(
            session_id=first.session_id,
            message="How does Kepler-442b orbital resonance affect silicon wafer doping yields in hadal amphipod genomes?",
        )
    )
    assert second.mode == "fallback"
    assert second.knowledge_status in {
        "insufficient_verified_evidence",
        "partially_grounded_external_used",
    }
    result = handle_chat(
        ChatRequest(
            message="How does Kepler-442b orbital resonance affect silicon wafer doping yields in hadal amphipod genomes?",
            debug=True,
        )
    )
    assert result.mode == "fallback"
    assert result.knowledge_status in {
        "insufficient_verified_evidence",
        "partially_grounded_external_used",
    }
    assert "kepler" not in " ".join(item.document_name.lower() for item in result.evidence if item.origin == "knowledge_base")
    assert "I will not fabricate" in result.assistant_message or "does not contain sufficient" in result.assistant_message


def test_irrelevant_documents_are_rejected():
    hits = retriever.search("Kepler-442b silicon wafer doping hadal amphipod genomes")
    accepted, rejected = retriever.split_relevant(hits)
    assert len(accepted) == 0
    assert isinstance(rejected, list)


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
    assert result.evidence
    for item in result.evidence:
        assert item.document_name
        assert item.passage
        if item.origin == "knowledge_base":
            assert item.page is None or item.page >= 1
