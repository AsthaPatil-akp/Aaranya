from fastapi.testclient import TestClient
import json

from app.main import app
from app.services.vectorstore import get_chroma


client = TestClient(app)
ADMIN = {"X-Admin-Token": "test-admin"}


def test_health_reports_live_stack():
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["embedding_backend"] == "sentence-transformers"
    assert "MiniLM" in body["embedding_model"]
    assert body["vector_database"] == "chromadb"
    assert body["collection"] == "darukaa_knowledge"
    assert body["vector_count"] >= 8
    assert body["chunks"] >= 8
    assert body["embedding_dimension"] == 384
    assert body["llm_provider"] == "ollama"
    assert "llm_available" in body
    assert "llm_configured" in body


def test_empty_chat_is_400():
    response = client.post("/api/chat", json={"message": ""})
    assert response.status_code == 400


def test_invalid_json_chat_is_400():
    response = client.post("/api/chat", json={"message": "hello", "structured_json": "{bad"})
    assert response.status_code == 400


def test_chat_clarification_and_search():
    response = client.post(
        "/api/chat",
        json={"message": "Biodiversity is declining on my farm.", "debug": True},
    )
    assert response.status_code == 200
    assert response.json()["mode"] == "clarification"
    search = client.post("/api/knowledge/search", json={"query": "soil organic carbon cover crops"})
    assert search.status_code == 200
    assert "accepted" in search.json()


def test_chat_stream_emits_final_event_and_timings():
    response = client.post(
        "/api/chat/stream",
        json={
            "message": (
                "My farm is 5 acres in a semi-arid region. I grow wheat as a monoculture. "
                "Soil pH is 8.1, organic carbon is 0.3%, soil moisture is low, rainfall is low. What should I do?"
            ),
            "debug": True,
        },
    )
    assert response.status_code == 200
    events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
    assert events
    assert any(item.get("type") == "final" for item in events)
    final = next(item for item in events if item.get("type") == "final")
    body = final["response"]
    assert body["assistant_message"]
    debug = body.get("debug") or {}
    assert debug.get("total_request_ms") is not None
    assert len(debug.get("evidence_selected_for_llm") or []) <= 5
    assert debug.get("openalex_ms") in {0, 0.0, None} or debug.get("external_search_triggered") is False


def test_knowledge_list():
    response = client.get("/api/knowledge")
    assert response.status_code == 200
    assert len(response.json()) >= 8


def test_ingest_requires_admin():
    response = client.post("/api/knowledge/rebuild")
    assert response.status_code == 401


def test_rebuild_with_admin():
    response = client.post("/api/knowledge/rebuild", headers=ADMIN)
    assert response.status_code == 200
    assert get_chroma().count() >= 8


def test_conversation_requires_admin():
    response = client.get("/api/conversation/unknown")
    assert response.status_code == 401
