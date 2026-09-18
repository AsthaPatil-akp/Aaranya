import json

from app.models.schemas import (
    BiodiversityContext,
    ChatRequest,
    ClaimEvidenceLink,
    EnvironmentalContext,
    EvidenceItem,
    HumanImpactContext,
    LandContext,
    SoilContext,
    StructuredInput,
)
from app.services.evidence import (
    UNSUPPORTED_DISCLAIMER,
    apply_context_grounding_rules,
    ground_answer,
    rewrite_unsupported_claims,
)
from app.services.llm import RecordingLLM, set_llm_client_override
from app.services.pipeline import handle_chat


KB = EvidenceItem(
    evidence_id="kb-1",
    source="01.md",
    document_name="01_soil_organic_carbon_biodiversity.md",
    title="Soil Organic Carbon, Soil pH, Moisture and Below-Ground Biodiversity",
    passage="Cover crops and residue retention are relevant where SOC and moisture are jointly low. Living roots support soil function.",
    origin="knowledge_base",
)


FARM_POLLINATOR = (
    "I have a wheat farm with intercropping. Soil moisture is high. "
    "Pesticide use is none. Bees and butterflies are declining. What should I do?"
)


def test_rewrite_removes_unsupported_claims_instead_of_disclaimer():
    draft = (
        "Cover crops can add living roots and residue that support soil function. "
        "High soil moisture causes biodiversity decline through plant crowding. "
        f"{UNSUPPORTED_DISCLAIMER}"
    )
    claims = [
        ClaimEvidenceLink(
            claim_id="c1",
            text="Cover crops can add living roots and residue that support soil function.",
            evidence_ids=["kb-1"],
            support="direct",
        ),
        ClaimEvidenceLink(
            claim_id="c2",
            text="High soil moisture causes biodiversity decline through plant crowding.",
            evidence_ids=[],
            support="unsupported",
        ),
    ]
    cleaned = rewrite_unsupported_claims(draft, claims)
    assert "causes biodiversity decline through plant crowding" not in cleaned.lower()
    assert UNSUPPORTED_DISCLAIMER.lower() not in cleaned.lower()
    assert "cover crops" in cleaned.lower()


def test_context_rules_drop_invented_rotation_and_current_pesticide():
    context = EnvironmentalContext(
        land=LandContext(crop="wheat", land_use="intercropping"),
        soil=SoilContext(moisture="high"),
        biodiversity=BiodiversityContext(pollinator_diversity="declining"),
        human_impact=HumanImpactContext(pesticide_use="none"),
    )
    draft = (
        "Switch from wheat intercropping to crop rotation. "
        "High soil moisture causes biodiversity decline through plant crowding. "
        "Pesticide exposure during the growing season is an existing factor reducing bees. "
        "Cover crops can add living roots and residue that support soil function."
    )
    cleaned = apply_context_grounding_rules(draft, context, [KB], FARM_POLLINATOR)
    lowered = cleaned.lower()
    assert "crop rotation" not in lowered
    assert "causes biodiversity decline through plant crowding" not in lowered
    assert "existing factor" not in lowered
    assert "historical pesticide" in lowered
    assert context.human_impact.pollution is None
    known = context.known_variables()
    assert known["pesticide_use"] == "none"
    assert "pollution" not in known


def test_ground_answer_does_not_expose_unsupported_claims():
    draft = (
        "You should switch from wheat intercropping to crop rotation. "
        "High soil moisture causes biodiversity decline through plant crowding. "
        "Pesticide exposure during the growing season is an existing factor reducing bees. "
        "Cover crops can add living roots and residue that support soil function. "
        f"{UNSUPPORTED_DISCLAIMER}"
    )
    context = EnvironmentalContext(
        land=LandContext(crop="wheat", land_use="intercropping"),
        soil=SoilContext(moisture="high"),
        biodiversity=BiodiversityContext(pollinator_diversity="declining"),
        human_impact=HumanImpactContext(pesticide_use="none"),
    )
    claims = [
        ClaimEvidenceLink(
            claim_id="c1",
            text="You should switch from wheat intercropping to crop rotation.",
            evidence_ids=[],
            support="unsupported",
        ),
        ClaimEvidenceLink(
            claim_id="c2",
            text="High soil moisture causes biodiversity decline through plant crowding.",
            evidence_ids=[],
            support="unsupported",
        ),
        ClaimEvidenceLink(
            claim_id="c3",
            text="Pesticide exposure during the growing season is an existing factor reducing bees.",
            evidence_ids=[],
            support="unsupported",
        ),
        ClaimEvidenceLink(
            claim_id="c4",
            text="Cover crops can add living roots and residue that support soil function.",
            evidence_ids=["kb-1"],
            support="direct",
        ),
    ]
    answer, verified = ground_answer(
        draft,
        [KB],
        user_message=FARM_POLLINATOR,
        context=context,
        claims=claims,
    )
    blob = answer.lower()
    assert "crop rotation" not in blob
    assert "causes biodiversity decline through plant crowding" not in blob
    assert "existing factor" not in blob
    assert UNSUPPORTED_DISCLAIMER.lower() not in blob
    assert all(claim.support != "unsupported" or "does not establish" in claim.text.lower() for claim in verified)
    assert "cover crops" in blob


def test_farm_pollinator_unsupported_claims_do_not_appear_in_final_answer(llm_recorder: RecordingLLM):
    draft_answer = (
        "Based on the conditions you described, several factors may be interacting. "
        "You should switch from wheat intercropping to crop rotation. "
        "High soil moisture causes biodiversity decline through plant crowding. "
        "Pesticide exposure during the growing season is an existing factor reducing bees. "
        "Cover crops can add living roots and residue that support soil function. "
        f"{UNSUPPORTED_DISCLAIMER}"
    )

    def responder(_system: str, _user: str) -> str:
        return json.dumps(
            {
                "answer": draft_answer,
                "recommendation": "Adopt crop rotation and reduce pesticide exposure.",
                "why_it_works": "Crop rotation and pesticide reduction will restore bees.",
                "environmental_relationships": "High moisture crowds plants.",
                "recommendations": [
                    {
                        "action": "Adopt crop rotation",
                        "why": "Invented mechanism",
                        "metrics": ["Pollinator diversity"],
                    },
                    {
                        "action": "Keep residue and add drought-tolerant cover crops",
                        "why": "Retrieved passages link cover and residue to soil function.",
                        "metrics": ["Soil organic carbon", "Soil moisture"],
                    },
                ],
                "impacted_metrics": [
                    {"name": "Pollinator diversity", "direction": "up", "note": "potentially affected"},
                    {"name": "Soil organic carbon", "direction": "unknown", "note": "potentially affected"},
                ],
                "time_horizon": {
                    "narrative": "Biodiversity will rise 40% in 18 months",
                    "evidence_supported": False,
                },
                "uncertainty": "Local trials are still needed.",
                "claims": [
                    {
                        "id": "c1",
                        "text": "You should switch from wheat intercropping to crop rotation.",
                        "evidence_ids": [],
                        "support": "unsupported",
                    },
                    {
                        "id": "c2",
                        "text": "High soil moisture causes biodiversity decline through plant crowding.",
                        "evidence_ids": [],
                        "support": "unsupported",
                    },
                    {
                        "id": "c3",
                        "text": "Pesticide exposure during the growing season is an existing factor reducing bees.",
                        "evidence_ids": [],
                        "support": "unsupported",
                    },
                    {
                        "id": "c4",
                        "text": "Cover crops can add living roots and residue that support soil function.",
                        "evidence_ids": ["kb-1"],
                        "support": "direct",
                    },
                ],
                "evidence_used": ["kb-1"],
                "confidence": "low",
                "confidence_rationale": "Some claims were unsupported.",
                "knowledge_status": "grounded_in_knowledge_base",
            }
        )

    fake = RecordingLLM(responder=responder)
    set_llm_client_override(fake)
    try:
        result = handle_chat(
            ChatRequest(
                message=FARM_POLLINATOR,
                structured=StructuredInput(
                    crop="wheat",
                    land_use="intercropping",
                    soil_moisture="high",
                    pesticide_use="none",
                    soil_organic_carbon=0.3,
                    rainfall="low",
                    pollinator_diversity="declining",
                ),
                debug=True,
            )
        )
    finally:
        set_llm_client_override(llm_recorder)

    blob = (result.assistant_message or "").lower()
    rec_blob = ""
    if result.recommendation:
        rec_blob = (
            f"{result.recommendation.action} {result.recommendation.why_it_works} "
            + " ".join(item.action for item in result.recommendation.items)
        ).lower()
    combined = f"{blob} {rec_blob}"
    assert result.mode == "recommendation"
    assert result.known_variables.get("pesticide_use") == "none"
    assert "pollution" not in result.known_variables
    assert "crop rotation" not in combined
    assert "causes biodiversity decline through plant crowding" not in combined
    assert "existing factor" not in combined
    assert "should not be treated as verified" not in blob
    assert "40%" not in blob
    assert "18 months" not in blob
    assert result.recommendation
    assert result.recommendation.impacted_metrics
    names = {metric.name.lower() for metric in result.recommendation.impacted_metrics}
    assert any("carbon" in name or "pollinator" in name or "moisture" in name for name in names)
    assert result.recommendation.supporting_evidence or any(
        item.supporting_evidence for item in result.recommendation.items
    )
    assert any("cover" in (item.action + result.recommendation.action).lower() for item in result.recommendation.items) or "cover" in result.recommendation.action.lower()
    assert "historical pesticide" in blob
