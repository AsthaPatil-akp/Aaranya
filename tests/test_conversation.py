from app.models.schemas import ChatRequest
from app.services.llm import RecordingLLM
from app.services.pipeline import handle_chat


def test_incomplete_input_asks_questions():
    result = handle_chat(ChatRequest(message="Biodiversity is declining on my farm."))
    assert result.mode == "clarification"
    assert result.clarifying_questions
    joined = " ".join(result.clarifying_questions).lower()
    assert "organic carbon" in joined or "rainfall" in joined or "land-use" in joined or "land use" in joined
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


def test_four_turn_memory_builds_context_aware_query(llm_recorder: RecordingLLM):
    t1 = handle_chat(ChatRequest(message="My farm is 5 acres and I grow wheat.", debug=True))
    t2 = handle_chat(ChatRequest(session_id=t1.session_id, message="My soil organic carbon is 0.3%.", debug=True))
    t3 = handle_chat(ChatRequest(session_id=t1.session_id, message="Rainfall is low and irregular.", debug=True))
    t4 = handle_chat(ChatRequest(session_id=t1.session_id, message="What should I do?", debug=True))
    assert t4.known_variables.get("crop") == "wheat"
    assert t4.known_variables.get("soil_organic_carbon") == 0.3
    assert t4.known_variables.get("rainfall") == "low"
    assert "5" in str(t4.known_variables.get("farm_size", ""))
    if t4.debug:
        query = (t4.debug.context_aware_query or t4.debug.query).lower()
        assert "what should i do" not in query or "wheat" in query
        assert "wheat" in query
        assert "0.3" in query or "organic carbon" in query
        assert t4.debug.conversation_context_used is True
    if t4.mode == "recommendation":
        assert llm_recorder.prompts
        prompt = llm_recorder.prompts[-1].lower()
        assert "wheat" in prompt
        assert "0.3" in prompt
