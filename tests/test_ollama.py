import os
from unittest.mock import MagicMock

import httpx
import pytest
from fastapi import HTTPException

from app.core.config import get_settings
from app.models.schemas import ChatRequest, EvidenceItem
from app.api.routes import health
from app.services.llm import (
    LLMUnavailable,
    OllamaClient,
    OllamaProvider,
    OpenAICompatibleProvider,
    OpenAIProvider,
    GroqProvider,
    _coerce_confidence,
    _coerce_direction,
    _extract_json,
    clear_llm_client_override,
    configured_llm_model,
    generate_answer,
    get_llm_client,
    llm_is_available,
    llm_is_configured,
    probe_ollama,
    reset_ollama_probe_cache,
    set_llm_client_override,
)
from app.services.pipeline import handle_chat


@pytest.fixture
def real_ollama_client():
    clear_llm_client_override()
    reset_ollama_probe_cache()
    yield
    from tests.conftest import recorder

    set_llm_client_override(recorder)


def test_ollama_is_default_provider():
    settings = get_settings()
    assert settings.llm_provider == "ollama"
    assert not settings.openai_api_key
    assert settings.ollama_model == "llama3.2:3b"
    assert settings.ollama_base_url.rstrip("/") == "http://localhost:11434"


def test_provider_selection_ollama(real_ollama_client):
    client_obj = get_llm_client()
    assert isinstance(client_obj, OllamaProvider)
    assert isinstance(client_obj, OllamaClient)
    assert client_obj.model == "llama3.2:3b"


def test_ollama_configured_without_openai_key(real_ollama_client):
    assert llm_is_configured() is True


def test_openai_optional_requires_key(monkeypatch, real_ollama_client):
    monkeypatch.setattr(
        "app.services.llm.get_settings",
        lambda: type(
            "S",
            (),
            {
                "llm_provider": "openai",
                "openai_model": "gpt-4o-mini",
                "openai_api_key": "",
                "ollama_base_url": "http://localhost:11434",
                "ollama_model": "llama3.2:3b",
            },
        )(),
    )
    assert get_llm_client() is None
    with pytest.raises(LLMUnavailable):
        OpenAIProvider()


def test_groq_optional_requires_key(monkeypatch, real_ollama_client):
    monkeypatch.setattr(
        "app.services.llm.get_settings",
        lambda: type(
            "S",
            (),
            {
                "llm_provider": "groq",
                "groq_model": "llama-3.1-8b-instant",
                "groq_api_key": "",
                "openai_api_key": "",
                "openai_model": "gpt-4o-mini",
                "ollama_base_url": "http://localhost:11434",
                "ollama_model": "llama3.2:3b",
            },
        )(),
    )
    assert get_llm_client() is None
    assert llm_is_configured() is False
    with pytest.raises(LLMUnavailable):
        GroqProvider()


def test_groq_selected_when_key_present(monkeypatch, real_ollama_client):
    monkeypatch.setattr(
        "app.services.llm.get_settings",
        lambda: type(
            "S",
            (),
            {
                "llm_provider": "groq",
                "groq_model": "llama-3.1-8b-instant",
                "groq_api_key": "test-groq-placeholder",
                "openai_api_key": "",
                "openai_model": "gpt-4o-mini",
                "ollama_base_url": "http://localhost:11434",
                "ollama_model": "llama3.2:3b",
            },
        )(),
    )
    client_obj = get_llm_client()
    assert isinstance(client_obj, GroqProvider)
    assert llm_is_configured() is True
    assert llm_is_available() is True
    assert configured_llm_model() == "llama-3.1-8b-instant"


def test_openai_compatible_payload_caps_max_tokens():
    client = OpenAICompatibleProvider(
        model="llama-3.1-8b-instant",
        api_key="test",
        base_url="https://example.com/v1",
        label="Test",
        provider="test",
    )
    payload = client._payload(
        "sys",
        "user",
        json_mode=False,
        temperature=0.35,
        stream=True,
        num_predict=400,
    )
    assert payload["max_tokens"] == 400
    assert payload["stream"] is True


def test_extract_json_salvages_plain_text():
    data = _extract_json("Cover crops can help hold moisture.")
    assert "Cover crops" in data["answer"]
    assert data["confidence"] == "low"


def test_coerce_model_enums():
    assert _coerce_direction("increase") == "up"
    assert _coerce_direction("declining") == "down"
    assert _coerce_confidence("HIGH") == "high"
    assert _coerce_confidence("pretty sure") == "low"


def test_ollama_unavailable(monkeypatch, real_ollama_client):
    class Fake:
        def get(self, *args, **kwargs):
            raise httpx.ConnectError(
                "connection refused",
                request=httpx.Request("GET", "http://localhost:11434/api/tags"),
            )

    monkeypatch.setattr("app.services.llm.get_ollama_http", lambda: Fake())
    reset_ollama_probe_cache()
    ok, _detail = probe_ollama(force=True)
    assert ok is False
    assert llm_is_available() is False


def test_ollama_model_unavailable(monkeypatch, real_ollama_client):
    response = MagicMock()
    response.raise_for_status = lambda: None
    response.json.return_value = {"models": [{"name": "qwen2.5:7b"}]}

    class Fake:
        def get(self, *args, **kwargs):
            return response

    monkeypatch.setattr("app.services.llm.get_ollama_http", lambda: Fake())
    reset_ollama_probe_cache()
    ok, detail = probe_ollama(force=True)
    assert ok is False
    assert "not installed" in detail.lower() or "llama" in detail.lower()


def test_successful_ollama_response_mocked(monkeypatch, real_ollama_client):
    class FakeResponse:
        status_code = 200

        def json(self):
            return {"message": {"content": '{"answer":"Use cover crops.","recommendation":"cover crops"}'}}

    class Fake:
        def post(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr("app.services.llm.get_ollama_http", lambda: Fake())
    reset_ollama_probe_cache()
    text = generate_answer(
        "SYSTEM INSTRUCTIONS",
        "INTERNAL KNOWLEDGE BASE:\ncover crops\nEXTERNAL SCIENTIFIC EVIDENCE:\n(none)",
    )
    assert "cover crops" in text.lower()


def test_ollama_connect_error_is_friendly(monkeypatch, real_ollama_client):
    class Fake:
        def post(self, *args, **kwargs):
            raise httpx.ConnectError("refused", request=httpx.Request("POST", "http://localhost:11434/api/chat"))

    monkeypatch.setattr("app.services.llm.get_ollama_http", lambda: Fake())
    reset_ollama_probe_cache()
    with pytest.raises(LLMUnavailable) as exc:
        OllamaClient().complete("sys", "user")
    assert "Ollama" in exc.value.message or "local AI model" in exc.value.message
    assert "Traceback" not in exc.value.message


def test_ollama_timeout_is_friendly(monkeypatch, real_ollama_client):
    class Fake:
        def post(self, *args, **kwargs):
            raise httpx.TimeoutException("timeout")

    monkeypatch.setattr("app.services.llm.get_ollama_http", lambda: Fake())
    reset_ollama_probe_cache()
    with pytest.raises(LLMUnavailable) as exc:
        OllamaClient().complete("sys", "user")
    assert exc.value.status_code == 504
    assert "Traceback" not in exc.value.message


def test_chat_returns_friendly_error_when_ollama_down(monkeypatch, real_ollama_client):
    kb = EvidenceItem(
        evidence_id="kb-1",
        source="01.md",
        document_name="01.md",
        title="Soil organic carbon",
        passage="Cover crops can help retain soil moisture when organic carbon is low.",
        relevance_score=0.9,
        origin="knowledge_base",
        evidence_level="passage",
    )
    monkeypatch.setattr("app.services.pipeline.retriever.search", lambda query: [kb])
    monkeypatch.setattr("app.services.pipeline.retriever.split_relevant", lambda items: (items, []))
    monkeypatch.setattr("app.services.pipeline.should_search_external", lambda *a, **k: (False, "kb_sufficient"))
    monkeypatch.setattr("app.services.pipeline.llm_is_configured", lambda: True)
    monkeypatch.setattr("app.services.pipeline.llm_is_available", lambda: False)
    with pytest.raises(HTTPException) as exc:
        handle_chat(
            ChatRequest(
                message=(
                    "My farm is 5 acres in a semi-arid region. I grow wheat as a monoculture. "
                    "Soil pH is 8.1, organic carbon is 0.3%, soil moisture is low, rainfall is low. What should I do?"
                ),
                debug=True,
            )
        )
    assert exc.value.status_code == 503
    assert "Ollama" in str(exc.value.detail)
    assert "Traceback" not in str(exc.value.detail)


def test_health_reports_ollama_unavailable(monkeypatch, real_ollama_client):
    monkeypatch.setattr("app.services.llm.probe_ollama", lambda force=False: (False, "Ollama is not reachable."))
    body = health().model_dump()
    assert body["llm_provider"] == "ollama"
    assert body["llm_model"] == "llama3.2:3b"
    assert body["llm_configured"] is True
    assert body["llm_available"] is False
    assert "OPENAI_API_KEY" not in str(body)
    assert "ADMIN_API_TOKEN" not in str(body)


@pytest.mark.integration
def test_live_ollama_optional(real_ollama_client):
    if os.environ.get("RUN_OLLAMA_INTEGRATION") != "1":
        pytest.skip("Set RUN_OLLAMA_INTEGRATION=1 to run the live Ollama check.")
    reset_ollama_probe_cache()
    ok, detail = probe_ollama(force=True)
    if not ok:
        pytest.skip(f"Live Ollama not available: {detail}")
    text = OllamaProvider().complete(
        "Return JSON only.",
        '{"task":"reply with JSON {\\"ok\\": true, \\"answer\\": \\"hello\\"}"}',
    )
    assert text.strip()
    assert "Traceback" not in text
