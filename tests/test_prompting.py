import re

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
    answer_length_band,
    build_user_prompt,
    compose_user_facing_answer,
    complete_recommendation,
    dedupe_recommendations,
    ensure_grounded_sources,
    extract_metrics_from_text,
    filter_evidence_for_answer,
    is_conceptual_question,
    normalize_chat_markdown,
    parse_answer_sections,
    replace_internal_evidence_ids,
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


def test_replace_internal_ids_with_document_titles():
    kb = EvidenceItem(
        evidence_id="kb-6",
        source="03.md",
        document_name="03.md",
        title="Monoculture, Agroforestry and Habitat Complexity",
        passage="Simplified cropping reduces habitat complexity.",
        origin="knowledge_base",
    )
    text = replace_internal_evidence_ids("Supported by kb-6 and kb-99.", [kb])
    assert "kb-6" not in text
    assert "kb-99" not in text
    assert "Monoculture, Agroforestry and Habitat Complexity" in text


def test_compose_hides_ids_and_keeps_one_recommendation_section():
    rec = RecommendationBlock(
        action="Keep residue and add drought-tolerant cover in the rainfall window.",
        why_it_works="The retrieved soil synthesis links low organic carbon with weak water holding.",
        environmental_relationships="Low carbon, low rainfall and simplified cropping may be interacting rather than acting alone.",
        impacted_metrics=[ImpactedMetric(name="Soil organic carbon", direction="up")],
        time_horizon=TimeHorizon(narrative="Several seasons to multiple years", evidence_supported=True),
        uncertainty="Local trials would still be needed.",
    )
    kb = EvidenceItem(
        evidence_id="kb-14",
        source="02.md",
        document_name="02.md",
        title="Cover Crops, Residue Retention and Water-Holding Capacity in Semi-Arid Farming",
        passage="Cover crops and residue can support water holding.",
        origin="knowledge_base",
    )
    text = compose_user_facing_answer(
        data={
            "answer": (
                "## Assessment Summary\nSeveral factors may be interacting.\n\n"
                "## Recommendations\nUse cover crops (kb-14).\n\n"
                "## Recommendations\nUse cover crops again.\n\n"
                "## Sources / Evidence\n- kb-14\n"
            )
        },
        rec=rec,
        kb_evidence=[kb],
        external_evidence=[],
    )
    assert text.lower().count("## recommendations") == 1
    assert "kb-14" not in text
    assert "Cover Crops, Residue Retention and Water-Holding Capacity in Semi-Arid Farming" in text
    assert "## Assessment Summary" in text
    assert "## Uncertainty" in text
    headings = [line[3:].strip() for line in text.splitlines() if line.startswith("## ")]
    assert headings.index("Assessment Summary") < headings.index("Recommendations")
    assert headings.index("Recommendations") < headings.index("Sources / Evidence")
    assert headings.index("Sources / Evidence") < headings.index("Uncertainty")


def test_parse_answer_sections_moves_unheaded_table_out_of_assessment():
    text = (
        "Low carbon and low rainfall can interact.\n\n"
        "| Action | Why it may help |\n"
        "| --- | --- |\n"
        "| Keep residue | Supports soil cover |\n\n"
        "## Sources / Evidence\n"
        "- Soil Organic Carbon, Soil pH, Moisture and Below-Ground Biodiversity\n"
    )
    sections = parse_answer_sections(text)
    assert "Keep residue" in sections["recommendations"]
    assert "|" not in sections["assessment_summary"]
    assert "Sources" not in sections["recommendations"]


def _rich_jowar_context() -> EnvironmentalContext:
    return EnvironmentalContext(
        soil=SoilContext(organic_carbon=0.3, moisture="low", ph=5.0),
        land=LandContext(land_use="monoculture", crop="jowar"),
        climate=ClimateContext(rainfall="low"),
    )


def _assert_valid_chat_markdown(text: str) -> None:
    assert text.strip()
    assert not re.search(r"[^\n#][ \t]*#{1,6}[ \t]+\S", text)
    assert not re.search(r"(?i)\b(?:kb|oa)[-:][A-Za-z0-9]+", text)
    for heading in ("Recommendations", "Sources / Evidence", "Uncertainty", "Assessment Summary"):
        assert text.lower().count(f"## {heading.lower()}") <= 1
    assert not re.search(r"(?<=[.!?;:])[ \t]+\d{1,2}[.)][ \t]+\S", text)
    assert not re.search(r"(?<=\S)[ \t]+[-*][ \t]+\*\*", text)


def test_conceptual_question_detection_and_length_band():
    context = _rich_jowar_context()
    assert is_conceptual_question("What is agroforestry?")
    assert is_conceptual_question("What's agroforestry?")
    assert not is_conceptual_question("What should I do?")
    assert not is_conceptual_question("Explain how low soil organic carbon, low rainfall and monoculture affect biodiversity.")
    assert answer_length_band(context, "What is agroforestry?") == "conceptual"
    assert answer_length_band(context, "What should I do?") == "complex"


def test_conceptual_user_prompt_keeps_farm_context_without_action_plan_quota():
    prompt = build_user_prompt(
        message="What is agroforestry?",
        context=_rich_jowar_context(),
        history=[
            {
                "role": "user",
                "content": "My jowar isn't growing well. My farm is 6 ha in Vasind, Maharashtra.",
            }
        ],
        kb_evidence=[],
        external_evidence=[],
        candidates=[],
    )
    lowered = prompt.lower()
    assert "what is agroforestry?" in lowered
    assert "jowar" in lowered
    assert "conceptual follow-up" in lowered
    assert "250-450" not in prompt
    assert "current question vs context" in lowered
    assert "do not write assessment summary" in lowered


def test_normalize_chat_markdown_splits_runons_and_hides_ids():
    text = normalize_chat_markdown(
        "## What is agroforestry? Agroforestry is trees with crops. "
        "## Recommendations 1. Cover crops. 2. Native trees. ## Recommendations "
        "- **Habitat:** birds - **Soil health:** litter See kb-99 leftover."
    )
    assert "## What is agroforestry?" in text
    assert "Agroforestry is trees" in text
    assert text.split("## What is agroforestry?")[1].lstrip().startswith("Agroforestry")
    assert "\n- **Habitat:**" in text or text.count("\n- ") >= 1
    assert "1. Cover crops." in text
    assert "2. Native trees." in text
    assert text.lower().count("## recommendations") == 1
    assert "kb-99" not in text
    _assert_valid_chat_markdown(text)


def test_conceptual_compose_skips_action_plan_sections():
    rec = RecommendationBlock(
        action="Use drought-tolerant cover crops.",
        why_it_works="Low carbon and low rainfall can interact.",
        environmental_relationships="Several farm conditions may be interacting.",
        impacted_metrics=[ImpactedMetric(name="Soil organic carbon", direction="up")],
        time_horizon=TimeHorizon(narrative="Several seasons to multiple years", evidence_supported=True),
        uncertainty="Local trials would still be needed.",
    )
    kb = EvidenceItem(
        evidence_id="kb-14",
        source="02.md",
        document_name="02.md",
        title="Cover Crops, Residue Retention and Water-Holding Capacity in Semi-Arid Farming",
        passage="Cover crops and residue can support water holding.",
        origin="knowledge_base",
    )
    text = compose_user_facing_answer(
        data={
            "answer": (
                "## What is agroforestry?\n\n"
                "Agroforestry is a farming system where trees or shrubs are grown together with crops or livestock.\n\n"
                "For your jowar farm, agroforestry could involve native trees around the field (kb-14)."
            )
        },
        rec=rec,
        kb_evidence=[kb],
        external_evidence=[],
        message="What is agroforestry?",
    )
    lowered = text.lower()
    assert "what is agroforestry" in lowered
    assert "jowar" in lowered
    assert "trees or shrubs" in lowered
    assert "## assessment summary" not in lowered
    assert "## recommendations" not in lowered
    assert "## sources / evidence" not in lowered
    assert "## uncertainty" not in lowered
    assert "kb-14" not in text
    _assert_valid_chat_markdown(text)


def test_conceptual_ensure_grounded_sources_does_not_regenerate_action_plan():
    kb = EvidenceItem(
        evidence_id="kb-6",
        source="03.md",
        document_name="03.md",
        title="Monoculture, Agroforestry and Habitat Complexity",
        passage="Simplified cropping reduces habitat complexity.",
        origin="knowledge_base",
    )
    messy = (
        "## What is agroforestry? Agroforestry is trees grown with crops. "
        "## Assessment Summary Several factors may be interacting. "
        "## Recommendations 1. Cover crops. 2. Native trees. ## Recommendations "
        "## Sources / Evidence - kb-6 ## Uncertainty Unknown. ## Uncertainty "
        "- **Habitat:** birds - **Soil health:** litter"
    )
    cleaned = ensure_grounded_sources(messy, [kb], [], message="What is agroforestry?")
    lowered = cleaned.lower()
    assert "agroforestry is trees" in lowered
    assert "## assessment summary" not in lowered
    assert "## recommendations" not in lowered
    assert "## sources / evidence" not in lowered
    assert "## uncertainty" not in lowered
    assert lowered.count("## recommendations") == 0
    assert "kb-6" not in cleaned
    _assert_valid_chat_markdown(cleaned)

