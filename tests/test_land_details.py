from fastapi.testclient import TestClient

from app.main import app
from app.models.schemas import ChatRequest, LandContext, StructuredInput
from app.models.schemas import EnvironmentalContext
from app.services.extraction import apply_updates, structured_to_dict
from app.services.pipeline import handle_chat
from app.services.prompting import build_stream_user_prompt, unprovided_land_fields


client = TestClient(app)


def test_partial_structured_details_reach_backend_and_memory():
    result = handle_chat(
        ChatRequest(
            message="Biodiversity is declining on my farm.",
            structured=StructuredInput(
                farm_size="5 acres",
                location="Pune, India",
                latitude=18.52,
                longitude=73.85,
                crop="wheat",
            ),
            debug=True,
        )
    )
    known = result.known_variables
    assert known["farm_size"] == "5 acres"
    assert known["location"] == "Pune, India"
    assert known["latitude"] == 18.52
    assert known["longitude"] == 73.85
    assert known["crop"] == "wheat"
    assert result.mode == "clarification"
    assert result.clarifying_questions


def test_empty_land_fields_are_not_invented():
    result = handle_chat(
        ChatRequest(
            message="Biodiversity is declining on my farm.",
            structured=StructuredInput(farm_size="10 acres", latitude=12.97, longitude=77.59),
            debug=True,
        )
    )
    known = result.known_variables
    assert known["farm_size"] == "10 acres"
    assert known["latitude"] == 12.97
    assert known["longitude"] == 77.59
    for key in (
        "soil_ph",
        "soil_organic_carbon",
        "soil_moisture",
        "rainfall",
        "temperature",
        "pollution",
        "crop",
        "land_use",
        "biodiversity_observations",
    ):
        assert key not in known
    prompt = build_stream_user_prompt(
        message="Biodiversity is declining on my farm.",
        context=result.environmental_context,
        history=[],
        kb_evidence=[],
        external_evidence=[],
        candidates=[],
    )
    assert "FIELDS NOT PROVIDED" in prompt
    assert "soil_ph" in prompt
    assert "8.1" not in prompt
    assert "0.3" not in prompt


def test_structured_to_dict_omits_empty_fields():
    payload = structured_to_dict(StructuredInput(crop="wheat"))
    assert payload == {"crop": "wheat"}


def test_unprovided_fields_exclude_known_values():
    context = EnvironmentalContext(land=LandContext(crop="wheat"))
    missing = unprovided_land_fields(context)
    assert "crop" not in missing
    assert "soil_ph" in missing
    assert "latitude" in missing


def test_biodiversity_observations_are_stored():
    context = apply_updates(
        EnvironmentalContext(),
        {"biodiversity_observations": "fewer bees and butterflies"},
    )
    assert context.biodiversity.observations == "fewer bees and butterflies"
    assert context.known_variables()["biodiversity_observations"] == "fewer bees and butterflies"


def test_form_and_json_merge_prefers_structured_object():
    result = handle_chat(
        ChatRequest(
            message="What should I do about declining insects?",
            structured=StructuredInput(crop="wheat", latitude=18.5, longitude=73.8),
            structured_json='{"crop": "maize", "rainfall": "low"}',
        )
    )
    known = result.known_variables
    assert known["crop"] == "wheat"
    assert known["rainfall"] == "low"
    assert known["latitude"] == 18.5
    assert known["longitude"] == 73.8


def test_plain_chat_without_land_details_is_unchanged():
    result = handle_chat(ChatRequest(message="Biodiversity is declining on my farm."))
    assert result.mode == "clarification"
    assert result.clarifying_questions
    assert "crop" not in result.known_variables
    assert "soil_ph" not in result.known_variables
    assert "latitude" not in result.known_variables


def test_geocode_returns_coordinates(monkeypatch):
    class FakeResponse:
        status_code = 200

        def json(self):
            return [{"display_name": "Pune, Maharashtra, India", "lat": "18.5204", "lon": "73.8567"}]

    def fake_get(*_args, **_kwargs):
        return FakeResponse()

    monkeypatch.setattr("httpx.get", fake_get)
    response = client.get("/api/geocode", params={"q": "Pune"})
    assert response.status_code == 200
    body = response.json()
    assert body[0]["label"].startswith("Pune")
    assert body[0]["latitude"] == 18.5204
    assert body[0]["longitude"] == 73.8567


def test_geocode_short_query_is_empty():
    response = client.get("/api/geocode", params={"q": "a"})
    assert response.status_code == 200
    assert response.json() == []
