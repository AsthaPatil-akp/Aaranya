from app.models.schemas import ChatRequest, StructuredInput
from app.services.pipeline import handle_chat


def test_incomplete_input_asks_questions():
    result = handle_chat(ChatRequest(message="Biodiversity is declining on my farm."))
    assert result.mode == "clarification"
    assert result.clarifying_questions
    assert "soil organic carbon" in " ".join(result.clarifying_questions).lower()
    assert result.knowledge_status == "awaiting_clarification"


def test_multiturn_remembers_and_does_not_reask_known_values():
    first = handle_chat(ChatRequest(message="Biodiversity is declining on my farm."))
    second = handle_chat(
        ChatRequest(
            session_id=first.session_id,
            message="Soil carbon is 0.3% and rainfall is low.",
        )
    )
    assert second.known_variables.get("soil_organic_carbon") == 0.3
    assert second.known_variables.get("rainfall") == "low"
    if second.clarifying_questions:
        joined = " ".join(second.clarifying_questions).lower()
        assert "organic carbon" not in joined
        assert "rainfall" not in joined


def test_structured_json_and_three_variable_reasoning():
    result = handle_chat(
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
            debug=True,
        )
    )
    assert result.mode == "recommendation"
    assert result.recommendation
    text = result.recommendation.environmental_relationships.lower()
    assert "organic carbon" in text
    assert "rainfall" in text
    assert "land use" in text or "monoculture" in text
    required = ["action", "why_it_works", "impacted_metrics", "time_horizon", "confidence"]
    for field in required:
        assert getattr(result.recommendation, field)
    assert result.knowledge_status == "grounded_in_knowledge_base"
    assert result.evidence
    assert all(item.document_name for item in result.evidence)
    assert result.recommendation.confidence in {"high", "medium", "low"}
