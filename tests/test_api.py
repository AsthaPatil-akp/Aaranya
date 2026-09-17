from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health():
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["chunks"] >= 1


def test_empty_chat():
    response = client.post("/api/chat", json={"message": ""})
    assert response.status_code == 200
    assert response.json()["error"] == "empty_input"


def test_invalid_json_chat():
    response = client.post("/api/chat", json={"message": "hello", "structured_json": "{bad"})
    assert response.status_code == 200
    assert "Invalid JSON" in response.json()["assistant_message"]


def test_chat_and_knowledge_search():
    response = client.post(
        "/api/chat",
        json={"message": "Biodiversity is declining on my farm.", "debug": True},
    )
    assert response.status_code == 200
    assert response.json()["mode"] == "clarification"
    search = client.post("/api/knowledge/search", json={"query": "soil organic carbon cover crops"})
    assert search.status_code == 200
    assert "accepted" in search.json()


def test_knowledge_list():
    response = client.get("/api/knowledge")
    assert response.status_code == 200
    assert len(response.json()) >= 1
