from app.services.extraction import apply_updates, extract_from_text, parse_structured_json
from app.models.schemas import EnvironmentalContext


def test_extracts_farm_sentence():
    found = extract_from_text(
        "My farm has low rainfall, soil organic carbon of 0.3%, pH 8.1 and wheat monoculture."
    )
    assert found["rainfall"] == "low"
    assert found["soil_organic_carbon"] == 0.3
    assert found["soil_ph"] == 8.1
    assert found["crop"] == "wheat"
    assert found["land_use"] == "monoculture"


def test_does_not_overwrite_unless_update():
    ctx = EnvironmentalContext()
    ctx = apply_updates(ctx, {"rainfall": "low", "crop": "wheat"})
    ctx = apply_updates(ctx, {"rainfall": "high", "crop": "maize"}, overwrite=False)
    assert ctx.climate.rainfall == "low"
    assert ctx.land.crop == "wheat"


def test_invalid_json():
    try:
        parse_structured_json("{not json")
        assert False, "should have failed"
    except ValueError as exc:
        assert "Invalid JSON" in str(exc)
