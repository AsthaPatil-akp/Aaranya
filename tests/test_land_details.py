import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

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
        "pesticide_use",
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


def test_pesticide_use_none_stays_separate_from_pollution():
    result = handle_chat(
        ChatRequest(
            message="Bees are declining on my wheat farm.",
            structured=StructuredInput(
                crop="wheat",
                land_use="intercropping",
                pesticide_use="none",
                soil_organic_carbon=0.3,
            ),
        )
    )
    assert result.known_variables.get("pesticide_use") == "none"
    assert "pollution" not in result.known_variables


def test_plain_chat_without_land_details_is_unchanged():
    result = handle_chat(ChatRequest(message="Biodiversity is declining on my farm."))
    assert result.mode == "clarification"
    assert result.clarifying_questions
    assert "crop" not in result.known_variables
    assert "soil_ph" not in result.known_variables
    assert "latitude" not in result.known_variables


def test_geocode_returns_coordinates(monkeypatch):
    monkeypatch.setattr(
        "app.api.routes.search_places",
        lambda q, limit=5: [
            {"label": "Pune, Maharashtra, India", "latitude": 18.5204, "longitude": 73.8567}
        ],
    )
    response = client.get("/api/geocode", params={"q": "Pune"})
    assert response.status_code == 200
    body = response.json()
    assert body[0]["label"].startswith("Pune")
    assert body[0]["latitude"] == 18.5204
    assert body[0]["longitude"] == 73.8567


def test_geocode_falls_back_to_photon_when_nominatim_denies(monkeypatch):
    class FakeResponse:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self._payload = payload

        def json(self):
            return self._payload

    def fake_get(url, **_kwargs):
        if "nominatim" in url:
            return FakeResponse(403, "Access denied")
        return FakeResponse(
            200,
            {
                "features": [
                    {
                        "properties": {"name": "Shahapur", "state": "Maharashtra", "country": "India"},
                        "geometry": {"coordinates": [73.3266, 19.4518]},
                    }
                ]
            },
        )

    monkeypatch.setattr("app.services.geocode.httpx.get", fake_get)
    from app.services.geocode import search_places

    rows = search_places("shahapur, maharashtra")
    assert rows[0]["label"].startswith("Shahapur")
    assert rows[0]["latitude"] == 19.4518
    assert rows[0]["longitude"] == 73.3266


def test_geocode_short_query_is_empty():
    response = client.get("/api/geocode", params={"q": "a"})
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.parametrize("value", [60, 65, 80])
def test_structured_temperature_accepts_environmental_range(value):
    parsed = StructuredInput(temperature=value)
    assert parsed.temperature == value


def test_structured_temperature_rejects_above_80():
    with pytest.raises(ValidationError) as exc:
        StructuredInput(temperature=80.1)
    assert "less_than_equal" in str(exc.value)
    assert "80" in str(exc.value)


def test_chat_accepts_temperature_65():
    response = client.post(
        "/api/chat",
        json={
            "message": "Biodiversity is declining on my farm.",
            "structured": {"temperature": 65},
        },
    )
    assert response.status_code == 200
    assert response.json()["known_variables"]["temperature"] == 65


def test_chat_rejects_temperature_above_80():
    response = client.post(
        "/api/chat",
        json={
            "message": "Biodiversity is declining on my farm.",
            "structured": {"temperature": 81},
        },
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail[0]["loc"] == ["body", "structured", "temperature"]
    assert detail[0]["type"] == "less_than_equal"
