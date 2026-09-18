import json
import re

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


def test_jowar_farm_then_what_is_agroforestry_stays_conversational(llm_recorder: RecordingLLM):
    farm = (
        "My jowar isn't growing well. My farm is 6 ha in Vasind, Maharashtra. "
        "Soil pH is 5.0, rainfall is low, soil organic carbon is low. "
        "Land use is monoculture. Soil moisture is low. What should I do?"
    )
    first = handle_chat(ChatRequest(message=farm, debug=True))
    assert first.known_variables.get("crop") == "jowar"
    assert "6" in str(first.known_variables.get("farm_size", ""))
    assert first.known_variables.get("rainfall") == "low"

    conceptual_answer = (
        "## What is agroforestry?\n\n"
        "Agroforestry is a farming system where trees or shrubs are grown together with crops or livestock.\n\n"
        "For your jowar farm in Vasind, agroforestry could involve maintaining or introducing suitable native "
        "trees or shrubs around or within the field.\n\n"
        "### How it could help\n\n"
        "- **Habitat:** Provides additional habitat for birds, insects, and other organisms.\n"
        "- **Soil health:** Leaf litter adds organic matter.\n"
        "- **Pollinators:** Flowering trees and shrubs can provide food and shelter.\n"
        "- **Microclimate:** Trees can provide shade and wind protection.\n"
        "- **Important consideration:** In your conditions, trees may also compete with jowar for water, so spacing and species selection matter.\n\n"
        "If you want, I can explain which agroforestry approach would fit your jowar farm."
    )

    def responder(_system: str, _user: str) -> str:
        return json.dumps(
            {
                "recommendation": "",
                "why_it_works": "",
                "environmental_relationships": "",
                "recommendations": [],
                "impacted_metrics": [],
                "time_horizon": {"narrative": "", "evidence_supported": False},
                "uncertainty": "",
                "claims": [],
                "evidence_used": [],
                "confidence": "medium",
                "confidence_rationale": "conceptual explanation",
                "knowledge_status": "grounded_in_knowledge_base",
                "answer": conceptual_answer,
            }
        )

    llm_recorder.responder = responder
    try:
        second = handle_chat(
            ChatRequest(session_id=first.session_id, message="What is agroforestry?", debug=True)
        )
    finally:
        llm_recorder.responder = None

    assert second.known_variables.get("crop") == "jowar"
    assert second.known_variables.get("rainfall") == "low"
    text = second.assistant_message or ""
    lowered = text.lower()
    assert "agroforestry" in lowered
    assert "trees" in lowered or "shrubs" in lowered
    assert "jowar" in lowered or "vasind" in lowered
    assert "## assessment summary" not in lowered
    assert "## what to investigate first" not in lowered
    assert "## recommendations" not in lowered
    assert "## why these work together" not in lowered
    assert "## next steps" not in lowered
    assert "## sources / evidence" not in lowered
    assert "## uncertainty" not in lowered
    assert lowered.count("## recommendations") == 0
    assert lowered.count("## sources") == 0
    assert lowered.count("## uncertainty") == 0
    assert not re.search(r"(?i)\b(?:kb|oa)[-:][A-Za-z0-9]+", text)
    assert not re.search(r"[^\n#][ \t]*#{1,6}[ \t]+\S", text)
    assert llm_recorder.prompts
    prompt = llm_recorder.prompts[-1].lower()
    assert "what is agroforestry?" in prompt
    assert "jowar" in prompt
    assert "conceptual follow-up" in prompt
    assert "250-450" not in llm_recorder.prompts[-1]
    if second.debug and second.debug.llm_prompt:
        debug_prompt = second.debug.llm_prompt.lower()
        assert "jowar" in debug_prompt
        assert "what is agroforestry?" in debug_prompt

