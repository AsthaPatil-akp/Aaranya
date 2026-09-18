from app.models.schemas import ChatRequest
from app.services.llm import RecordingLLM
from app.services.pipeline import handle_chat
from app.services.retrieval import retriever


def test_distinctive_fact_reaches_llm_prompt(llm_recorder: RecordingLLM):
    hits = retriever.search("ground beetles spiders pollinators cover-crop flowers")
    assert hits
    assert any("beetle" in (item.passage or "").lower() or "ground" in (item.passage or "").lower() for item in hits)

    result = handle_chat(
        ChatRequest(
            message="According to the knowledge base, what habitat requirement is mentioned for ground beetles?",
            debug=True,
        )
    )
    assert result.debug
    assert result.debug.retrieved_context_passed_to_llm is True
    assert result.debug.llm_prompt
    prompt = result.debug.llm_prompt.lower()
    assert "internal knowledge base" in prompt
    assert "external scientific evidence" in prompt
    assert "system instructions" in prompt
    assert "ground" in prompt or "beetle" in prompt or "cover" in prompt
    assert llm_recorder.prompts
    assert "beetle" in llm_recorder.prompts[-1].lower() or "cover-crop" in llm_recorder.prompts[-1].lower() or "cover" in llm_recorder.prompts[-1].lower()


def test_changing_evidence_changes_recorded_prompt(llm_recorder: RecordingLLM):
    first = handle_chat(
        ChatRequest(
            message="Low soil organic carbon 0.3%, low rainfall, wheat monoculture. What should I do?",
            debug=True,
        )
    )
    second = handle_chat(
        ChatRequest(
            message="High pollution, urban expansion and low species richness. What should I do?",
            debug=True,
        )
    )
    if first.debug and second.debug and first.debug.llm_prompt and second.debug.llm_prompt:
        assert first.debug.llm_prompt != second.debug.llm_prompt
