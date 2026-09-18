from __future__ import annotations

import json
import re
from typing import Any

from app.models.schemas import EnvironmentalContext, StructuredInput

QUALITATIVE = {
    "very low": "very low",
    "low": "low",
    "poor": "low",
    "scarce": "low",
    "limited": "low",
    "moderate": "moderate",
    "medium": "moderate",
    "average": "moderate",
    "high": "high",
    "severe": "high",
    "heavy": "high",
    "intense": "high",
}

CROP_TERMS = (
    "wheat",
    "rice",
    "maize",
    "corn",
    "soy",
    "soybean",
    "cotton",
    "sugarcane",
    "barley",
    "millet",
    "jowar",
    "sorghum",
    "pulses",
    "coffee",
    "tea",
    "cocoa",
    "oil palm",
    "potato",
    "vegetable",
)

LAND_USE_PATTERNS = [
    (r"\bmono[\s-]?culture\b", "monoculture"),
    (r"\bintercrop(?:ping)?\b", "intercropping"),
    (r"\bagroforestry\b", "agroforestry"),
    (r"\bagricultural land\b|\bcropland\b|\bfarmland\b", "agricultural land"),
    (r"\bforest(?:ed|ry)?\b", "forest"),
    (r"\bgrassland\b|\bpasture\b|\bsavanna\b", "grassland"),
    (r"\burban\b|\bcity\b|\bbuilt[\s-]?up\b", "urban land"),
]

REGION_PATTERNS = [
    (r"\bsemi[\s-]?arid\b", "semi-arid"),
    (r"\barid\b", "arid"),
    (r"\bhumid\b", "humid"),
    (r"\btropical\b", "tropical"),
    (r"\btemperate\b", "temperate"),
    (r"\bmediterranean\b", "mediterranean"),
]


def _qual(text: str) -> str | None:
    lowered = text.lower()
    for key, value in QUALITATIVE.items():
        if key in lowered:
            return value
    return None


def extract_from_text(message: str) -> dict[str, Any]:
    """Pull environmental variables from natural language without overwriting later."""
    if not message:
        return {}
    text = message.strip()
    found: dict[str, Any] = {}

    soc = re.search(
        r"(?:soil\s+)?(?:organic\s+)?carbon(?:\s+level)?(?:\s+is|\s+of|:)?\s*([0-9]+(?:\.[0-9]+)?)\s*%",
        text,
        re.I,
    )
    if not soc:
        soc = re.search(r"\bSOC\b(?:\s+is|\s+of|:)?\s*([0-9]+(?:\.[0-9]+)?)\s*%?", text, re.I)
    if soc:
        found["soil_organic_carbon"] = float(soc.group(1))
    elif re.search(r"(?:soil\s+)?(?:organic\s+)?carbon.{0,20}\b(low|high|moderate|poor|very low)\b", text, re.I):
        match = re.search(r"(?:soil\s+)?(?:organic\s+)?carbon.{0,20}\b(low|high|moderate|poor|very low)\b", text, re.I)
        if match:
            found["soil_organic_carbon_label"] = _qual(match.group(1)) or match.group(1).lower()

    ph = re.search(r"\bpH\b(?:\s+is|\s+of|:)?\s*([0-9]+(?:\.[0-9]+)?)", text, re.I)
    if ph:
        value = float(ph.group(1))
        if 0 <= value <= 14:
            found["soil_ph"] = value

    rainfall = re.search(
        r"rainfall(?:\s+pattern)?(?:\s+is|\s+of|:)?\s*(low|high|moderate|poor|limited|scarce|very low)",
        text,
        re.I,
    )
    if rainfall:
        found["rainfall"] = _qual(rainfall.group(1))
    elif re.search(r"\b(low|high|moderate|poor|limited|scarce)\s+rainfall\b", text, re.I):
        match = re.search(r"\b(low|high|moderate|poor|limited|scarce)\s+rainfall\b", text, re.I)
        found["rainfall"] = _qual(match.group(1)) if match else None

    rain_mm = re.search(r"rainfall(?:\s+is|\s+of|:)?\s*([0-9]{2,5})\s*mm", text, re.I)
    if rain_mm:
        mm = float(rain_mm.group(1))
        found["rainfall"] = "low" if mm < 500 else "moderate" if mm < 1000 else "high"

    moisture = re.search(
        r"soil\s+moisture(?:\s+is|\s+of|:)?\s*(low|high|moderate|poor|limited|very low)",
        text,
        re.I,
    )
    if moisture:
        found["soil_moisture"] = _qual(moisture.group(1))
    elif re.search(r"\b(low|high|moderate)\s+soil\s+moisture\b", text, re.I):
        match = re.search(r"\b(low|high|moderate)\s+soil\s+moisture\b", text, re.I)
        found["soil_moisture"] = _qual(match.group(1)) if match else None

    temp = re.search(
        r"(?:temperatures?|temp).{0,48}?([0-9]+(?:\.[0-9]+)?)(?:\s*[–\-to]+\s*[0-9]+(?:\.[0-9]+)?)?\s*°?\s*c",
        text,
        re.I,
    )
    if temp:
        found["temperature"] = float(temp.group(1))
    elif re.search(r"\b(high|hot|extreme)\s+temperature", text, re.I):
        found["climate_stress"] = "high"

    if re.search(r"\bdrought\b", text, re.I):
        drought_qual = re.search(r"\b(severe|high|moderate|low)\s+drought\b", text, re.I)
        found["drought"] = _qual(drought_qual.group(1)) if drought_qual else "high"

    for pattern, label in LAND_USE_PATTERNS:
        if re.search(pattern, text, re.I):
            found["land_use"] = label
            break

    for crop in CROP_TERMS:
        if re.search(rf"\b{re.escape(crop)}\b", text, re.I):
            found["crop"] = crop
            break

    for pattern, label in REGION_PATTERNS:
        if re.search(pattern, text, re.I):
            found["region"] = label
            break

    pollution = re.search(r"pollution(?:\s+is|\s+level)?(?:\s+is|\s+of|:)?\s*(low|moderate|medium|high|severe)", text, re.I)
    if pollution:
        found["pollution"] = _qual(pollution.group(1))
    elif re.search(r"\b(high|severe|heavy|moderate|low)\s+pollution\b", text, re.I):
        match = re.search(r"\b(high|severe|heavy|moderate|low)\s+pollution\b", text, re.I)
        found["pollution"] = _qual(match.group(1)) if match else None

    none_pesticide = re.search(
        r"(?:pesticide(?:s|_use)?(?:\s+use)?(?:\s+is|\s*=|:)?\s*(?:none|not used|no)|"
        r"(?:no|without|not using|do not use)\s+(?:pesticides?|insecticides?|herbicides?|agrochemicals?))",
        text,
        re.I,
    )
    pesticide_level = re.search(
        r"\b(low|moderate|medium|high|severe)\s+(?:pesticide|insecticide|herbicide|agrochemical)\b",
        text,
        re.I,
    )
    if none_pesticide:
        found["pesticide_use"] = "none"
    elif pesticide_level:
        found["pesticide_use"] = _qual(pesticide_level.group(1)) or pesticide_level.group(1).lower()
    elif re.search(r"\b(pesticides?|insecticides?|herbicides?|agrochemicals?)\b", text, re.I):
        found["pesticide_use"] = "pesticide use"

    if re.search(r"\bdeforestation\b", text, re.I):
        found["deforestation"] = "present"
        found["habitat_destruction"] = "present"

    frag = re.search(r"habitat\s+fragmentation(?:\s+is)?(?:\s+is|\s+of|:)?\s*(low|moderate|high|severe)?", text, re.I)
    if re.search(r"\bfragmentation\b", text, re.I):
        found["fragmentation"] = _qual(frag.group(1)) if frag and frag.group(1) else "high"

    if re.search(r"\burban expansion\b|\burbanis(?:z|s)ation\b", text, re.I):
        found["land_use"] = found.get("land_use") or "urban land"
        found["habitat_destruction"] = "present"

    richness = re.search(
        r"species richness(?:\s+is)?(?:\s+is|\s+of|:)?\s*(low|moderate|high|declining)",
        text,
        re.I,
    )
    if richness:
        found["species_richness"] = richness.group(1).lower()
    elif re.search(r"biodiversity\s+(?:is\s+)?declin", text, re.I):
        found["species_survival"] = "declining"

    if re.search(r"\blow vegetation\b|\bsparse vegetation\b|\bdegraded vegetation\b", text, re.I):
        found["plant_diversity"] = "low"
        found["habitat_diversity"] = found.get("habitat_diversity") or "low"
    if re.search(
        r"(few|lack of|little|no|without|scarce)\s+(flowering plants?|flowers?|floral (?:resources?|habitat))",
        text,
        re.I,
    ):
        found["plant_diversity"] = "low"
        found["habitat_diversity"] = found.get("habitat_diversity") or "low"

    if re.search(r"\bnative vegetation\b", text, re.I) and re.search(r"\b(lost|cleared|removed|low)\b", text, re.I):
        found["habitat_destruction"] = "present"

    lat = re.search(r"\blat(?:itude)?[:\s]+(-?[0-9]+(?:\.[0-9]+)?)", text, re.I)
    lon = re.search(r"\blon(?:gitude)?[:\s]+(-?[0-9]+(?:\.[0-9]+)?)", text, re.I)
    if lat:
        found["latitude"] = float(lat.group(1))
    if lon:
        found["longitude"] = float(lon.group(1))

    acres = re.search(r"\b([0-9]+(?:\.[0-9]+)?)\s*-?\s*(acres?|hectares?|ha)\b", text, re.I)
    if acres:
        found["farm_size"] = f"{acres.group(1)} {acres.group(2).lower()}"

    if re.search(
        r"(?:declin\w*|fewer|few).{0,48}(?:bees|butterflies|pollinators|insects)|"
        r"(?:bees|butterflies|pollinators|insects).{0,48}(?:declin\w*|fewer)",
        text,
        re.I,
    ) or re.search(r"\bpollinators?\s+(are|is)\s+(declining|fewer|low)\b", text, re.I):
        found["pollinator_diversity"] = "declining"
    if re.search(r"\b(low|poor|declining)\s+microbial\b", text, re.I):
        found["microbial_diversity"] = "low"
    if re.search(r"\b(bare\s+soil|sparse\s+cover|closed\s+canopy|grass\s+cover)\b", text, re.I):
        cover = re.search(r"\b(bare soil|sparse cover|closed canopy|grass cover)\b", text, re.I)
        if cover:
            found["land_cover"] = cover.group(1).lower()
    water = re.search(r"water availability(?:\s+is)?(?:\s+is|\s+of|:)?\s*(low|poor|limited|high|moderate)", text, re.I)
    if water:
        found["water_availability"] = _qual(water.group(1)) or water.group(1).lower()
    elif re.search(r"\b(low|poor|limited)\s+water availability\b", text, re.I):
        found["water_availability"] = "low"
    if re.search(r"\bland degradation\b|\bdegraded land\b", text, re.I):
        found["land_degradation"] = "present"
    if re.search(r"\birregular rainfall\b|\brainfall is irregular\b", text, re.I):
        found["rainfall"] = found.get("rainfall") or "low"

    return {k: v for k, v in found.items() if v is not None}


def parse_structured_json(raw: str) -> StructuredInput:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Structured input must be a JSON object.")
    return StructuredInput.model_validate(payload)


def structured_to_dict(data: StructuredInput) -> dict[str, Any]:
    return {k: v for k, v in data.model_dump().items() if v is not None}


def normalize_structured_updates(updates: dict[str, Any]) -> dict[str, Any]:
    """Keep pesticide_use and pollution as separate variables."""
    data = dict(updates)
    pollution = str(data.get("pollution") or "").strip().lower()
    if "pesticide_use" not in data and pollution in {"none", "pesticide use"}:
        data["pesticide_use"] = pollution
        data.pop("pollution", None)
    return data


def apply_updates(context: EnvironmentalContext, updates: dict[str, Any], overwrite: bool = False) -> EnvironmentalContext:
    """Merge new values. Do not overwrite existing valid values unless overwrite=True."""
    ctx = context.model_copy(deep=True)
    updates = normalize_structured_updates(updates)

    def set_if(obj: Any, field: str, key: str) -> None:
        if key not in updates:
            return
        current = getattr(obj, field)
        incoming = updates[key]
        generic_land = {"agricultural land"}
        specific_land = {"monoculture", "intercropping", "agroforestry", "forest", "grassland", "urban land"}
        if current is None or overwrite:
            setattr(obj, field, incoming)
        elif key == "land_use" and current in generic_land and incoming in specific_land:
            setattr(obj, field, incoming)

    set_if(ctx.location, "region", "region")
    set_if(ctx.location, "location", "location")
    set_if(ctx.location, "farm_size", "farm_size")
    set_if(ctx.location, "latitude", "latitude")
    set_if(ctx.location, "longitude", "longitude")
    set_if(ctx.soil, "ph", "soil_ph")
    set_if(ctx.soil, "organic_carbon", "soil_organic_carbon")
    set_if(ctx.soil, "organic_carbon_label", "soil_organic_carbon_label")
    set_if(ctx.soil, "moisture", "soil_moisture")
    set_if(ctx.land, "land_use", "land_use")
    set_if(ctx.land, "land_cover", "land_cover")
    set_if(ctx.land, "crop", "crop")
    set_if(ctx.land, "fragmentation", "fragmentation")
    set_if(ctx.land, "intercropping", "intercropping")
    set_if(ctx.biodiversity, "species_richness", "species_richness")
    set_if(ctx.biodiversity, "habitat_diversity", "habitat_diversity")
    set_if(ctx.biodiversity, "plant_diversity", "plant_diversity")
    set_if(ctx.biodiversity, "pollinator_diversity", "pollinator_diversity")
    set_if(ctx.biodiversity, "microbial_diversity", "microbial_diversity")
    set_if(ctx.biodiversity, "species_survival", "species_survival")
    set_if(ctx.biodiversity, "observations", "biodiversity_observations")
    set_if(ctx.climate, "temperature", "temperature")
    set_if(ctx.climate, "rainfall", "rainfall")
    set_if(ctx.climate, "drought", "drought")
    set_if(ctx.climate, "water_availability", "water_availability")
    set_if(ctx.climate, "climate_stress", "climate_stress")
    set_if(ctx.human_impact, "pollution", "pollution")
    set_if(ctx.human_impact, "pesticide_use", "pesticide_use")
    set_if(ctx.human_impact, "deforestation", "deforestation")
    set_if(ctx.human_impact, "land_degradation", "land_degradation")
    set_if(ctx.human_impact, "habitat_destruction", "habitat_destruction")
    return ctx


def looks_like_update(message: str) -> bool:
    return bool(re.search(r"\b(actually|update|change|correct that|now it is|instead)\b", message, re.I))


FOLLOWUP_RE = re.compile(
    r"^(what should i do\??|why(?: is that)?\??|and then\??|go on\.?|continue\.?|"
    r"tell me more\.?|what about that\??)$",
    re.I,
)
NEW_FACT_RE = re.compile(
    r"\d|pH|pesticide|rainfall|carbon|moisture|acre|bees|flower|monoculture|drought",
    re.I,
)


def should_run_extraction(message: str, context: EnvironmentalContext) -> bool:
    text = (message or "").strip()
    if not text:
        return False
    if looks_like_update(text):
        return True
    if FOLLOWUP_RE.match(text) and context.known_variable_count() >= 2:
        return False
    if context.known_variable_count() >= 3 and len(text) < 50 and not NEW_FACT_RE.search(text):
        return False
    return True
