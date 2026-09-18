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


def test_extracts_pesticides_flowering_and_temperature_range():
    found = extract_from_text(
        "I manage a 10-acre farm in a semi-arid region. The farm is mostly a wheat monoculture. "
        "Soil pH is 8.2, organic carbon is 0.25%, soil moisture is low, rainfall is irregular, "
        "and temperatures are usually around 30–32°C. There are very few flowering plants around "
        "the farm and I have observed a decline in bees, butterflies and other insects over the "
        "last three years. Pesticides are also used during the growing season."
    )
    assert found["region"] == "semi-arid"
    assert found["farm_size"].startswith("10")
    assert found["crop"] == "wheat"
    assert found["land_use"] == "monoculture"
    assert found["soil_ph"] == 8.2
    assert found["soil_organic_carbon"] == 0.25
    assert found["soil_moisture"] == "low"
    assert found["rainfall"] == "low"
    assert found["temperature"] == 30.0
    assert found["plant_diversity"] == "low"
    assert found["pollinator_diversity"] == "declining"
    assert found["pollution"] == "pesticide use"
    found = extract_from_text(
        "My farm is 5 acres. There are fewer bees and butterflies. Water availability is poor."
    )
    assert found["farm_size"].startswith("5")
    assert found["pollinator_diversity"] == "declining"
    assert found["water_availability"] == "low"


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


def test_skips_extraction_for_simple_followup():
    from app.models.schemas import ClimateContext, LandContext, SoilContext
    from app.services.extraction import should_run_extraction

    context = EnvironmentalContext(
        soil=SoilContext(organic_carbon=0.3, moisture="low"),
        land=LandContext(land_use="monoculture", crop="wheat"),
        climate=ClimateContext(rainfall="low"),
    )
    assert should_run_extraction("What should I do?", context) is False
    assert should_run_extraction(
        "My farm is 5 acres in a semi-arid region with wheat monoculture and soil carbon 0.3%.",
        EnvironmentalContext(),
    ) is True

