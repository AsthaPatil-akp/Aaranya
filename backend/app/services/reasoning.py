from __future__ import annotations

import re
from typing import Any

from app.models.schemas import (
    EnvironmentalContext,
    HeuristicProfile,
    ImpactedMetric,
    RecommendationBlock,
    TimeHorizon,
)

INTENT_KEYWORDS = {
    "biodiversity": ["biodiversity", "species", "pollinator", "habitat", "wildlife"],
    "soil": ["soil", "carbon", "ph", "organic", "erosion"],
    "water": ["rainfall", "drought", "moisture", "water"],
    "land": ["monoculture", "forest", "land use", "crop", "fragmentation", "intercrop"],
    "pollution": ["pollution", "contaminant", "urban"],
    "climate": ["temperature", "climate", "heat", "drought"],
}

CLARIFY_PRIORITY = [
    ("soil_organic_carbon", "What is the soil organic carbon level (percent or low/moderate/high)?"),
    ("rainfall", "What is the rainfall pattern (low, moderate, high, or approximate mm)?"),
    ("land_use", "What is the land-use type (monoculture, intercropping, forest, grassland, urban)?"),
    ("crop", "What crop or vegetation is present?"),
    ("soil_moisture", "What is the soil moisture condition?"),
    ("soil_ph", "What is the soil pH?"),
    ("pollution", "What is the pollution level (low/moderate/high)?"),
    ("fragmentation", "Is habitat fragmentation present, and how severe is it?"),
    ("drought", "Is the site experiencing drought or climate stress?"),
]


def classify_intent(message: str, context: EnvironmentalContext) -> str:
    text = (message or "").lower()
    scores = {
        key: sum(1 for word in words if re.search(rf"\b{re.escape(word)}\b", text))
        for key, words in INTENT_KEYWORDS.items()
    }
    if context.human_impact.pollution or context.land.land_use == "urban land":
        scores["pollution"] = scores.get("pollution", 0) + 1
    if context.human_impact.deforestation or context.land.fragmentation:
        scores["land"] = scores.get("land", 0) + 1
    if max(scores.values() or [0]) == 0:
        if context.known_variable_count() >= 3:
            return "biodiversity"
        return "general"
    return max(scores, key=scores.get)


def missing_variables(context: EnvironmentalContext, intent: str) -> list[tuple[str, str]]:
    known = context.known_variables()
    if "soil_organic_carbon" in known and "soil_organic_carbon_label" in known:
        pass
    missing: list[tuple[str, str]] = []
    for key, question in CLARIFY_PRIORITY:
        if key == "soil_organic_carbon" and (
            "soil_organic_carbon" in known or "soil_organic_carbon_label" in known
        ):
            continue
        if key not in known:
            missing.append((key, question))
    if intent == "pollution":
        preferred = ["pollution", "species_richness", "land_use", "fragmentation"]
        missing = [item for item in missing if item[0] in preferred] + [
            item for item in missing if item[0] not in preferred
        ]
    return missing


def needs_clarification(context: EnvironmentalContext, intent: str, message: str) -> bool:
    known = context.known_variables()
    core_keys = {
        "soil_organic_carbon",
        "soil_organic_carbon_label",
        "rainfall",
        "land_use",
        "crop",
        "soil_moisture",
        "soil_ph",
        "pollution",
        "fragmentation",
        "drought",
        "temperature",
        "deforestation",
        "species_richness",
        "plant_diversity",
    }
    present_core = [key for key in known if key in core_keys]
    if len(present_core) >= 3:
        return False
    text = (message or "").lower()
    if re.search(r"\b(recommend|intervene)\b|what should i do|how do i restore", text):
        return len(present_core) < 3
    if re.search(r"\b(declin\w*|degrad\w*|problem|losing|poor|stress)\b", text):
        return True
    if intent == "general" and len(present_core) == 0:
        return False
    return len(present_core) < 2 and intent != "general"


def clarifying_questions(context: EnvironmentalContext, intent: str) -> list[str]:
    missing = missing_variables(context, intent)
    return [question for _, question in missing[:4]]


def _label_soc(context: EnvironmentalContext) -> str | None:
    if context.soil.organic_carbon is not None:
        value = context.soil.organic_carbon
        if value < 0.5:
            return "very low"
        if value < 1.0:
            return "low"
        if value < 2.0:
            return "moderate"
        return "high"
    return context.soil.organic_carbon_label


def _is_low(value: str | None) -> bool:
    return (value or "").lower() in {"low", "very low", "poor", "scarce", "limited", "declining"}


def _is_high(value: str | None) -> bool:
    return (value or "").lower() in {"high", "severe", "heavy", "present", "intense"}


def heuristic_profile(context: EnvironmentalContext) -> HeuristicProfile:
    soc = _label_soc(context)
    ph = context.soil.ph
    moisture = context.soil.moisture
    soil_bits = []
    if soc and _is_low(soc):
        soil_bits.append("organic carbon is low")
    if ph is not None and (ph < 5.5 or ph > 7.8):
        soil_bits.append(f"pH {ph} is outside the typical productive range")
    if moisture and _is_low(moisture):
        soil_bits.append("moisture is constrained")
    soil_health = "stressed" if soil_bits else ("fair" if soc or ph or moisture else "unknown")
    if soc and not _is_low(soc) and not soil_bits:
        soil_health = "favourable"

    water = "unknown"
    if _is_low(context.climate.rainfall) or _is_low(moisture) or _is_high(context.climate.drought):
        water = "high stress"
    elif context.climate.rainfall or moisture:
        water = "moderate"

    habitat = "unknown"
    if context.land.land_use == "monoculture" or _is_high(context.land.fragmentation):
        habitat = "simplified / fragmented"
    elif context.land.land_use in {"forest", "agroforestry", "intercropping", "grassland"}:
        habitat = "structurally mixed"
    elif context.land.land_use == "urban land":
        habitat = "highly modified"

    bio = "unknown"
    if context.biodiversity.species_survival == "declining" or _is_low(context.biodiversity.species_richness):
        bio = "elevated pressure"
    elif context.land.land_use == "monoculture" or _is_high(context.human_impact.pollution):
        bio = "elevated pressure"
    elif context.known_variable_count() >= 3:
        bio = "watch"

    human = "unknown"
    if _is_high(context.human_impact.pollution) or context.human_impact.deforestation:
        human = "significant"
    elif context.land.land_use == "urban land":
        human = "significant"
    elif context.land.land_use:
        human = "agricultural / land-use driven"

    return HeuristicProfile(
        soil_health=soil_health,
        water_stress=water,
        habitat_condition=habitat,
        biodiversity_pressure=bio,
        human_impact=human,
    )


def describe_relationships(context: EnvironmentalContext) -> tuple[str, list[str]]:
    """Explain links among at least three variables when available."""
    soc = _label_soc(context)
    parts: list[str] = []
    used: list[str] = []

    if soc:
        used.append("soil organic carbon")
        parts.append(
            f"Soil organic carbon is {soc}"
            + (f" ({context.soil.organic_carbon}%)" if context.soil.organic_carbon is not None else "")
            + ", which reduces aggregation, water-holding capacity, and the carbon substrate that supports soil biota."
        )
    if context.climate.rainfall:
        used.append("rainfall")
        parts.append(
            f"Rainfall is {context.climate.rainfall}, limiting recharge of soil moisture and increasing drought exposure for plants and soil organisms."
        )
    if context.soil.moisture:
        used.append("soil moisture")
        parts.append(
            f"Soil moisture is {context.soil.moisture}, so vegetation stress and microbial activity are both constrained."
        )
    if context.land.land_use:
        used.append("land use")
        if context.land.land_use == "monoculture":
            parts.append(
                f"Land use is {context.land.land_use}"
                + (f" ({context.land.crop})" if context.land.crop else "")
                + ", which simplifies plant architecture, floral resources, and habitat niches."
            )
        else:
            parts.append(f"Land use is {context.land.land_use}, which shapes habitat structure and edge effects.")
    elif context.land.crop:
        used.append("crop")
        parts.append(f"The dominant crop is {context.land.crop}, which determines seasonal cover and disturbance regime.")
    if context.soil.ph is not None:
        used.append("soil pH")
        parts.append(
            f"Soil pH is {context.soil.ph}, affecting nutrient availability and microbial community composition."
        )
    if context.human_impact.pollution:
        used.append("pollution")
        parts.append(
            f"Pollution is {context.human_impact.pollution}, adding chemical stress that can reduce sensitive taxa and soil biological function."
        )
    if context.human_impact.deforestation or context.land.fragmentation:
        used.append("habitat fragmentation")
        parts.append(
            "Deforestation and habitat fragmentation reduce patch size and connectivity, raising extinction risk for area-sensitive species."
        )
    if context.climate.temperature is not None or context.climate.drought:
        used.append("climate stress")
        temp = f" Temperature is {context.climate.temperature}°C." if context.climate.temperature is not None else ""
        drought = f" Drought condition is {context.climate.drought}." if context.climate.drought else ""
        parts.append("Climate stress is compounding water limitation." + temp + drought)
    if context.location.region:
        used.append("region")
        parts.append(f"The region is {context.location.region}, which sets baseline aridity and restoration feasibility.")

    if len(used) >= 3:
        synthesis = (
            "Together these variables interact: water limitation and low soil carbon reinforce each other through poor infiltration and weak aggregation; "
            "simplified land use then removes habitat and living roots that would otherwise rebuild carbon and microclimates. "
            "Biodiversity pressure is therefore a system outcome, not a single-factor symptom."
        )
        if context.human_impact.pollution or context.land.land_use == "urban land":
            synthesis = (
                "Together these variables interact: chemical and physical disturbance reduce habitat quality, while simplified or sealed land cover "
                "cuts connectivity. Species richness declines when pollution, habitat loss, and climate or water stress coincide."
            )
        if context.human_impact.deforestation:
            synthesis = (
                "Together these variables interact: forest loss fragments remaining habitat, microclimates become hotter and drier at edges, "
                "and species that need contiguous canopy or soil biota associated with forest litter decline."
            )
        return " ".join(parts + [synthesis]), used
    return " ".join(parts) if parts else "Insufficient paired variables to describe multi-metric relationships yet.", used


def select_intervention(context: EnvironmentalContext) -> dict[str, Any]:
    soc_low = _is_low(_label_soc(context)) or (
        context.soil.organic_carbon is not None and context.soil.organic_carbon < 1.0
    )
    rain_low = _is_low(context.climate.rainfall) or _is_low(context.soil.moisture) or _is_high(context.climate.drought)
    mono = context.land.land_use == "monoculture"
    urban = context.land.land_use == "urban land"
    polluted = _is_high(context.human_impact.pollution)
    fragmented = _is_high(context.land.fragmentation) or bool(context.human_impact.deforestation)
    hot = (context.climate.temperature is not None and context.climate.temperature >= 28) or _is_high(
        context.climate.climate_stress
    )
    low_veg = _is_low(context.biodiversity.plant_diversity) or _is_low(context.biodiversity.habitat_diversity)

    if polluted and (urban or _is_low(context.biodiversity.species_richness)):
        return {
            "id": "urban_green_corridors",
            "action": "Establish native vegetation buffers and habitat corridors along field margins, drains, and leftover urban-edge patches, while cutting local pollutant loads at source.",
            "why": "Pollution and urban expansion jointly remove habitat and add chemical stress. Native buffers intercept contaminants, restore floral and nesting resources, and reconnect remaining patches so species can move rather than persist in isolated remnants.",
            "keywords": ["pollution", "urban", "corridor", "native vegetation", "species richness"],
            "metrics": [
                ImpactedMetric(name="Species richness", direction="up", note="if toxin load falls and habitat is restored"),
                ImpactedMetric(name="Habitat diversity", direction="up"),
                ImpactedMetric(name="Pollution pressure", direction="down"),
                ImpactedMetric(name="Soil biological activity", direction="up"),
            ],
        }
    if fragmented and (context.human_impact.deforestation or context.biodiversity.species_survival == "declining"):
        return {
            "id": "habitat_corridors_reforestation",
            "action": "Restore native tree and understory belts that reconnect fragmented patches, prioritizing riparian strips and shortest gaps between remaining forest remnants.",
            "why": "Deforestation and fragmentation shrink effective habitat area and increase edge drying. Corridors and native restoration rebuild structural complexity, movement pathways, and microclimates that support species survival.",
            "keywords": ["deforestation", "fragmentation", "corridor", "reforestation", "habitat"],
            "metrics": [
                ImpactedMetric(name="Habitat diversity", direction="up"),
                ImpactedMetric(name="Species survival", direction="up"),
                ImpactedMetric(name="Edge-related climate stress", direction="down"),
                ImpactedMetric(name="Plant diversity", direction="up"),
            ],
        }
    if hot and rain_low and low_veg:
        return {
            "id": "drought_native_restoration",
            "action": "Restore drought-tolerant native groundcover and shrubs, add organic mulch, and install simple water-harvesting microcatchments rather than irrigating water-demanding exotics.",
            "why": "High temperature plus drought and sparse vegetation create a heat–water–habitat trap. Native drought-adapted plants and surface residue reduce evaporation, shade soil, and restart habitat structure without assuming abundant rainfall.",
            "keywords": ["drought", "temperature", "native", "water harvesting", "vegetation"],
            "metrics": [
                ImpactedMetric(name="Soil moisture", direction="up"),
                ImpactedMetric(name="Climate stress at surface", direction="down"),
                ImpactedMetric(name="Plant diversity", direction="up"),
                ImpactedMetric(name="Habitat diversity", direction="up"),
            ],
        }
    if soc_low and rain_low and (mono or context.land.crop):
        crop = context.land.crop or "the current staple"
        return {
            "id": "covercrop_agroforestry",
            "action": f"Shift {crop} monoculture toward a diversified rotation with drought-tolerant cover crops, plus widely spaced native trees or shrubs (agroforestry strips) on contours to hold soil and water.",
            "why": "Low soil organic carbon, low rainfall, and monoculture interact: little residue means weak aggregation and poor infiltration, so scarce rain is lost, roots and soil biota decline, and habitat is uniformly simple. Cover crops add living roots and residue; agroforestry adds shade, litter, and structural habitat.",
            "keywords": ["cover crop", "agroforestry", "organic carbon", "rainfall", "monoculture", "intercrop"],
            "metrics": [
                ImpactedMetric(name="Soil organic carbon", direction="up"),
                ImpactedMetric(name="Soil moisture", direction="up"),
                ImpactedMetric(name="Habitat diversity", direction="up"),
                ImpactedMetric(name="Species richness", direction="up"),
                ImpactedMetric(name="Pollinator diversity", direction="up"),
            ],
        }
    if mono:
        return {
            "id": "intercropping_diversification",
            "action": "Replace continuous monoculture with intercropping or a diversified rotation that includes legumes and flowering strips.",
            "why": "Monoculture reduces habitat heterogeneity and often soil biological function. Crop diversification increases rooting patterns, floral resources, and pest–predator habitat.",
            "keywords": ["intercropping", "crop diversification", "habitat", "pollinator"],
            "metrics": [
                ImpactedMetric(name="Habitat diversity", direction="up"),
                ImpactedMetric(name="Plant diversity", direction="up"),
                ImpactedMetric(name="Pollinator diversity", direction="up"),
                ImpactedMetric(name="Soil organic carbon", direction="up"),
            ],
        }
    return {
        "id": "native_restoration_general",
        "action": "Restore native vegetation in unused margins, reduce disturbance intensity, and rebuild soil cover with residue or cover plants matched to local water availability.",
        "why": "Biodiversity responds to the combined effects of soil condition, water, and habitat structure. Rebuilding cover and native plant diversity addresses those coupled constraints rather than a single symptom.",
        "keywords": ["native vegetation", "soil", "habitat", "restoration"],
        "metrics": [
            ImpactedMetric(name="Habitat diversity", direction="up"),
            ImpactedMetric(name="Soil moisture", direction="up"),
            ImpactedMetric(name="Species richness", direction="up"),
        ],
    }


def time_horizon_for(intervention_id: str, evidence_supported: bool) -> TimeHorizon:
    if not evidence_supported:
        return TimeHorizon(
            short_term="Not estimated: retrieved evidence does not support a specific timeline.",
            medium_term=None,
            long_term=None,
            evidence_supported=False,
        )
    mapping = {
        "covercrop_agroforestry": TimeHorizon(
            short_term="Within 1–2 seasons: improved ground cover, reduced splash erosion, and slightly better moisture retention if rains occur.",
            medium_term="Over 2–5 years: measurable soil organic carbon and biological activity gains are commonly discussed in agricultural soil literature as gradual, not immediate.",
            long_term="Over 5–15 years: tree components can add habitat structure and microclimate buffering if survival is successful.",
            evidence_supported=True,
        ),
        "urban_green_corridors": TimeHorizon(
            short_term="Within 1–2 years: floral and nesting resources can appear once native plants establish.",
            medium_term="Over 3–7 years: corridor use and local species composition may shift if pollution is also reduced.",
            long_term="Over a decade: connectivity benefits depend on landscape-scale protection of patches.",
            evidence_supported=True,
        ),
        "habitat_corridors_reforestation": TimeHorizon(
            short_term="Early years: reduced further clearing and edge planting can slow ongoing loss.",
            medium_term="5–10 years: canopy and understory structure begin to reconnect patches.",
            long_term="Decadal: area-sensitive species respond only if remnants remain and hunting/pollution are controlled.",
            evidence_supported=True,
        ),
        "drought_native_restoration": TimeHorizon(
            short_term="First seasons: mulch and microcatchments can reduce evaporation where rainfall is received.",
            medium_term="2–6 years: drought-adapted native cover can stabilize soil and habitat if mortality is managed.",
            long_term="Longer-term vegetation recovery remains contingent on climate trajectory and grazing/fire pressure.",
            evidence_supported=True,
        ),
        "intercropping_diversification": TimeHorizon(
            short_term="Same season: floral resources and canopy complexity can increase.",
            medium_term="2–4 years: soil and invertebrate responses accumulate with repeated diversified seasons.",
            long_term=None,
            evidence_supported=True,
        ),
    }
    return mapping.get(
        intervention_id,
        TimeHorizon(
            short_term="Near-term effects are mainly protective (cover, reduced disturbance).",
            medium_term="Soil and habitat responses typically require multiple years.",
            long_term=None,
            evidence_supported=True,
        ),
    )


def confidence_for(context: EnvironmentalContext, relevant_count: int, distinct_sources: int, used_vars: int) -> tuple[str, str]:
    completeness = context.known_variable_count()
    if relevant_count >= 2 and distinct_sources >= 2 and completeness >= 4 and used_vars >= 3:
        return "high", "Multiple relevant knowledge-base passages, more than one document, and a relatively complete environmental profile."
    if relevant_count >= 1 and completeness >= 3 and used_vars >= 3:
        return "medium", "At least one relevant knowledge-base passage and three or more environmental variables, but evidence breadth is limited."
    return "low", "Limited relevant evidence and/or incomplete environmental inputs. Treat as a working hypothesis, not a validated prediction."


def build_recommendation(context: EnvironmentalContext, relevant: list[Any]) -> RecommendationBlock:
    intervention = select_intervention(context)
    relationships, used = describe_relationships(context)
    distinct_sources = len({item.document_name for item in relevant})
    evidence_supported = len(relevant) > 0
    confidence, rationale = confidence_for(context, len(relevant), distinct_sources, len(used))
    why = intervention["why"]
    if used:
        why += f" This recommendation is conditioned on the observed combination of {', '.join(used[:6])}."
    return RecommendationBlock(
        action=intervention["action"],
        why_it_works=why,
        environmental_relationships=relationships,
        impacted_metrics=intervention["metrics"],
        time_horizon=time_horizon_for(intervention["id"], evidence_supported),
        confidence=confidence,  # type: ignore[arg-type]
        confidence_rationale=rationale,
    )


def retrieval_query(
    message: str,
    context: EnvironmentalContext,
    include_intervention: bool = False,
    include_context: bool = False,
) -> str:
    bits = [message]
    known = context.known_variables()
    if include_context:
        bits.extend(f"{k} {v}" for k, v in known.items() if k != "notes")
    if include_intervention and len(known) >= 3:
        intervention = select_intervention(context)
        bits.append(" ".join(intervention["keywords"]))
    return " ".join(str(bit) for bit in bits if bit)
