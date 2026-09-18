from fastapi.testclient import TestClient

from app.main import app
from app.models.schemas import ChatRequest
from app.services.pipeline import handle_chat


client = TestClient(app)


def test_sessions_are_isolated():
    a = handle_chat(ChatRequest(message="I grow wheat. Soil organic carbon is 0.3%. Rainfall is low."))
    b = handle_chat(ChatRequest(message="This is a forest with high rainfall."))
    assert a.session_id != b.session_id
    assert a.known_variables.get("crop") == "wheat"
    assert b.known_variables.get("crop") != "wheat"
    assert b.known_variables.get("rainfall") != "low" or b.known_variables.get("land_use") == "forest"


def test_health_does_not_include_api_keys():
    body = client.get("/api/health").json()
    dumped = str(body)
    assert "sk-" not in dumped
    assert "test-key-not-used" not in dumped
