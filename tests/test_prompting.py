from app.models.schemas import (
    ChatRequest,
    ClimateContext,
    EnvironmentalContext,
    EvidenceItem,
    ImpactedMetric,
    LandContext,
    RecommendationBlock,
    SoilContext,
    TimeHorizon,
)
from app.services.evidence import sanitize_answer_against_evidence
from app.services.llm import RecordingLLM
from app.services.pipeline import handle_chat, recommendation_from_answer
from app.services.prompting import (
    SYSTEM_PROMPT,
    build_user_prompt,
    compose_user_facing_answer,
    complete_recommendation,
    dedupe_recommendations,
    ensure_grounded_sources,
    extract_metrics_from_text,
    filter_evidence_for_answer,
    sanitize_time_horizon,
    word_count,
)


def test_ensure_grounded_sources_drops_unretrieved_citations():
    kb = EvidenceItem(
        evidence_id="kb-1",
        source="01.md",
        document_name="01.md",
        title="Soil Organic Carbon, Soil pH, Moisture and Below-Ground Biodiversity",
        passage="Cover crops can add residue.",
        origin="knowledge_base",
    )
    text = (
        "Cover crops may help in dry years.\n\n"
        "Sources:\n"
        "* USDA NRCS soil health principles\n"
        "* A paper that was never retrieved\n\n"
        "Uncertainty:\n"
        "Outcomes still depend on rainfall."
    )
    cleaned = ensure_grounded_sources(text, [kb], [])
    assert "USDA NRCS soil health principles" not in cleaned
    assert "never retrieved" not in cleaned
    assert "Internal Knowledge Base" in cleaned
    assert "Soil Organic Carbon" in cleaned
    assert "Outcomes still depend on rainfall" in cleaned
    assert "External Scientific Research" not in cleaned
    text = SYSTEM_PROMPT.lower()
    assert "darukaa.earth's biodiversity intelligence assistant" in text
    assert "retrieved evidence as the factual basis" in text
    assert "never invent evidence" in text
    assert "generic sustainability advice" in text
    assert "intelligent non-specialist" in text
    assert "chain-of-thought" in text
    assert "250-450" in SYSTEM_PROMPT


def test_user_prompt_has_internal_reasoning_structure():
    context = EnvironmentalContext(
        soil=SoilContext(organic_carbon=0.3, moisture="low"),
        land=LandContext(land_use="monoculture", crop="wheat"),
        climate=ClimateContext(rainfall="low"),
    )
    prompt = build_user_prompt(
        message="What should I do?",
        context=context,
        history=[],
        kb_evidence=[],
        external_evidence=[],
        candidates=[],
    )
    assert "USER CONTEXT" in prompt
    assert "USER QUESTION" in prompt
    assert "INTERACTING FACTORS" in prompt
    assert "INTERNAL KNOWLEDGE BASE" in prompt
    assert "EXTERNAL SCIENTIFIC EVIDENCE" in prompt
    assert "250-450" in prompt


def test_compose_uses_model_fields_and_real_sources_only():
    rec = RecommendationBlock(
        action="Keep residue and add drought-tolerant cover in the rainfall window.",
        why_it_works="The retrieved soil synthesis links low organic carbon with weak water holding.",
        environmental_relationships="Low carbon, low rainfall and simplified cropping may be interacting rather than acting alone.",
        impacted_metrics=[
            ImpactedMetric(name="Soil organic carbon", direction="up"),
            ImpactedMetric(name="Pollinator diversity", direction="up"),
        ],
        time_horizon=TimeHorizon(
            narrative="Soil organic carbon changes are usually assessed over multiple seasons.",
            evidence_supported=True,
        ),
        uncertainty="Local trials would still be needed before promising a specific yield or species response.",
    )
    kb = EvidenceItem(
        evidence_id="kb-1",
        source="01.md",
        document_name="01_soil_organic_carbon_biodiversity.md",
        title="Soil Organic Carbon, Soil pH, Moisture and Below-Ground Biodiversity",
        passage="Cover crops and residue retention are relevant where SOC and moisture are jointly low.",
        origin="knowledge_base",
        evidence_level="passage",
    )
    text = compose_user_facing_answer(
        data={"answer": "The decline may be coming from more than one farm condition at once."},
        rec=rec,
        kb_evidence=[kb],
        external_evidence=[],
    )
    assert "more than one farm condition" in text
    assert "interacting" in text.lower()
    assert "cover" in text.lower()
    assert "Internal Knowledge Base" in text
    assert "External Scientific Research" not in text
    assert "10.9999/fake" not in text


def test_sanitize_drops_invented_doi_and_percent():
    evidence = [
        EvidenceItem(
            evidence_id="kb-1",
            source="01.md",
            document_name="01.md",
            title="Soil carbon",
            passage="Cover crops can add residue. No percentage improvement is given.",
            origin="knowledge_base",
        )
    ]
    cleaned = sanitize_answer_against_evidence(
        "Cover crops may help. A 25% jump is expected (DOI 10.9999/not-real).",
        evidence,
        user_message="My soil carbon is low.",
    )
    assert "25%" not in cleaned
    assert "10.9999/not-real" not in cleaned
    assert "cover crops" in cleaned.lower()


def test_composed_farm_answer_is_longer_than_raw_json_stub(llm_recorder: RecordingLLM):
    result = handle_chat(
        ChatRequest(
            message=(
                "I have a 5-acre farm in a semi-arid region. I grow wheat as a monoculture. "
                "My soil pH is 8.1, organic carbon is 0.3%, and soil moisture is low. "
                "Rainfall is low and irregular, with temperatures around 30C. "
                "I have noticed fewer bees and butterflies. What should I do?"
            ),
            debug=True,
        )
    )
    assert result.mode == "recommendation"
    assert word_count(result.assistant_message) > 40
    assert "Internal Knowledge Base" in result.assistant_message
    assert result.debug and "biodiversity intelligence assistant" in (result.debug.llm_prompt or "").lower()


def test_dedupe_splits_cover_crops_and_agroforestry():
    unique = dedupe_recommendations(
        [
            {
                "action": "Drought-tolerant cover crops and widely spaced native trees or shrubs where water allows",
                "why": "Both add cover",
            },
            {"action": "Agroforestry with native shrubs", "why": "duplicate trees"},
        ]
    )
    actions = " ".join(item["action"].lower() for item in unique)
    assert "cover crop" in actions
    tree_items = [
        item
        for item in unique
        if "tree" in item["action"].lower() or "shrub" in item["action"].lower() or "agroforest" in item["action"].lower()
    ]
    assert len(unique) >= 2
    assert len(tree_items) == 1


def test_sanitize_time_horizon_drops_invented_years():
    horizon = sanitize_time_horizon(
        TimeHorizon(narrative="10-20 years", short_term="Long-term", evidence_supported=True),
        [
            EvidenceItem(
                evidence_id="kb-1",
                source="01.md",
                document_name="01.md",
                title="Soil carbon",
                passage="Time scales are typically seasonal for cover and multi-year for measurable SOC change.",
                origin="knowledge_base",
            )
        ],
    )
    assert "10-20" not in (horizon.narrative or "")
    assert "several seasons" in (horizon.narrative or "").lower() or "multiple years" in (horizon.narrative or "").lower()
    assert horizon.short_term is None


def test_filter_drops_unused_deforestation_source():
    answer = "Cover crops and residue can help in a dry wheat field with low soil organic carbon."
    kept_kb, _ext = filter_evidence_for_answer(
        answer,
        [],
        [],
        [
            EvidenceItem(
                evidence_id="kb-soil",
                source="01.md",
                document_name="01_soil_organic_carbon_biodiversity.md",
                title="Soil Organic Carbon",
                passage="Cover crops and residue retention are relevant where SOC and moisture are jointly low.",
                origin="knowledge_base",
            ),
            EvidenceItem(
                evidence_id="kb-forest",
                source="07.md",
                document_name="07_deforestation_fragmentation_biodiversity.md",
                title="Deforestation and fragmentation",
                passage="Forest remnants and canopy corridors affect area-sensitive forest species.",
                origin="knowledge_base",
            ),
        ],
        [],
    )
    names = " ".join(item.document_name for item in kept_kb)
    assert "soil_organic_carbon" in names
    assert "deforestation" not in names


def test_extract_metrics_keeps_known_names_only():
    answer = (
        "Cover crops may help where soil organic carbon is low.\n"
        "Metrics these changes could affect: Soil organic carbon: possible change: gradual if residue is kept; "
        "Soil moisture: possible local improvement, depending on establishment and landscape context. Cover can appear in a season; "
        "soil carbon usually takes years. These are evidence-informed suggestions, not guaranteed field outcomes.\n\n"
        "Sources / Evidence\n"
        "- Rainfall, Drought and Species Survival\n"
    )
    names = [metric.name.lower() for metric in extract_metrics_from_text(answer)]
    assert "soil organic carbon" in names
    assert "soil moisture" in names
    assert not any("depending on establishment" in name for name in names)
    assert not any("sources" in name for name in names)
    assert "species survival" not in names


def test_stream_answer_maps_recommendation_panel_fields():
    context = EnvironmentalContext(
        soil=SoilContext(organic_carbon=0.3, moisture="low"),
        land=LandContext(land_use="monoculture", crop="wheat"),
        climate=ClimateContext(rainfall="low"),
    )
    kb = [
        EvidenceItem(
            evidence_id="kb-soil",
            source="01.md",
            document_name="01_soil_organic_carbon_biodiversity.md",
            title="Soil Organic Carbon, Soil pH, Moisture and Below-Ground Biodiversity",
            passage="Cover crops and residue retention are relevant where SOC and moisture are jointly low over multiple years.",
            origin="knowledge_base",
        ),
        EvidenceItem(
            evidence_id="kb-cover",
            source="02.md",
            document_name="02_cover_crops_residue.md",
            title="Cover Crops, Residue Retention and Water-Holding Capacity in Semi-Arid Farming",
            passage="Drought-tolerant cover crops and residue can support water holding in semi-arid systems.",
            origin="knowledge_base",
        ),
        EvidenceItem(
            evidence_id="kb-forest",
            source="07.md",
            document_name="07_deforestation_fragmentation_biodiversity.md",
            title="Deforestation and fragmentation",
            passage="Forest remnants and canopy corridors affect area-sensitive forest species.",
            origin="knowledge_base",
        ),
    ]
    answer = (
        "Based on the conditions you described, several factors may be interacting. "
        "Low soil carbon and low rainfall can interact, so living roots and residue may help. "
        "Drought-tolerant cover crops and residue can help rebuild soil function. "
        "Impacted metrics these changes could affect: soil organic carbon; soil moisture. "
        "No specific timeframe is supported by the retrieved evidence.\n\n"
        "Sources / Evidence\n"
        "- Soil Organic Carbon, Soil pH, Moisture and Below-Ground Biodiversity\n"
        "- Cover Crops, Residue Retention and Water-Holding Capacity in Semi-Arid Farming\n"
    )
    rec = complete_recommendation(None, answer, context, kb, user_message="What should I do on my wheat farm?")
    assert rec.why_it_works
    names = {metric.name.lower() for metric in rec.impacted_metrics}
    assert "soil organic carbon" in names
    assert rec.time_horizon.narrative
    assert rec.supporting_evidence
    assert all("deforest" not in title.lower() for title in rec.supporting_evidence)
    assert rec.items
    assert all(item.why for item in rec.items)
    assert all(item.impacted_metrics for item in rec.items)
    assert all(item.supporting_evidence for item in rec.items)


def test_recommendation_does_not_use_source_titles_as_actions():
    context = EnvironmentalContext(
        soil=SoilContext(organic_carbon=0.3, moisture="low"),
        land=LandContext(land_use="monoculture", crop="wheat"),
        climate=ClimateContext(rainfall="low"),
    )
    evidence = [
        EvidenceItem(
            evidence_id="kb-cover",
            source="02.md",
            document_name="02_cover_crops_residue.md",
            title="Cover Crops, Residue Retention and Water-Holding Capacity in Semi-Arid Farming",
            passage="Cover crops and residue retention can support water holding in dry seasons.",
            origin="knowledge_base",
        )
    ]
    answer = (
        "Low soil carbon and low rainfall can interact in this wheat field. "
        "Sources / Evidence\n"
        "- Cover Crops, Residue Retention and Water-Holding Capacity in Semi-Arid Farming\n"
    )
    rec = recommendation_from_answer(answer, context, evidence, user_message="What should I do?")
    blob = (rec.action + " " + " ".join(item.action for item in rec.items)).lower()
    assert "drought-tolerant cover crops matched to the rainfall window" not in blob
    assert rec.why_it_works
    assert rec.supporting_evidence


def test_complete_recommendation_drops_evidence_id_bullets():
    context = EnvironmentalContext(
        soil=SoilContext(organic_carbon=0.3, moisture="low"),
        land=LandContext(land_use="monoculture", crop="wheat"),
        climate=ClimateContext(rainfall="low"),
    )
    kb = [
        EvidenceItem(
            evidence_id="kb-76",
            source="01.md",
            document_name="01_soil_organic_carbon_biodiversity.md",
            title="Soil Organic Carbon, Soil pH, Moisture and Below-Ground Biodiversity",
            passage="Cover crops and residue can support soil function over multiple years.",
            origin="knowledge_base",
        )
    ]
    rec = complete_recommendation(
        RecommendationBlock(
            action="Keep residue and add drought-tolerant cover crops",
            why_it_works="Low soil carbon and low rainfall can interact.",
            environmental_relationships="",
            items=[],
        ),
        (
            "Drought-tolerant cover crops and residue can help rebuild soil function.\n"
            "1. Keep residue and add drought-tolerant cover crops — Low soil carbon and low rainfall can interact.\n"
            "2. kb-76: Soil Organic Carbon, Soil pH, Moisture and Below-Ground Biodiversity\n"
            "3. kb-80: Rainfall, Drought and Species Survival\n"
        ),
        context,
        kb,
        user_message="What should I do?",
    )
    actions = " ".join(item.action for item in rec.items).lower()
    assert "kb-76" not in actions
    assert "kb-80" not in actions
    assert rec.items
    assert all(item.why for item in rec.items)
