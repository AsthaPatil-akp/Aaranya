from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator


KnowledgeStatus = Literal[
    "grounded_in_knowledge_base",
    "grounded_in_external_evidence",
    "grounded_in_kb_and_external",
    "insufficient_evidence",
    "awaiting_clarification",
]

ConfidenceLevel = Literal["high", "medium", "low"]
MetricDirection = Literal["up", "down", "neutral", "unknown"]
EvidenceOrigin = Literal["knowledge_base", "external_openalex", "unused_low_relevance"]
EvidenceLevel = Literal["full_text", "abstract", "passage", "metadata"]
ClaimSupport = Literal["direct", "inference", "unsupported"]


class LocationContext(BaseModel):
    region: Optional[str] = None
    location: Optional[str] = None
    farm_size: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class SoilContext(BaseModel):
    ph: Optional[float] = None
    organic_carbon: Optional[float] = None
    organic_carbon_label: Optional[str] = None
    moisture: Optional[str] = None


class LandContext(BaseModel):
    land_use: Optional[str] = None
    land_cover: Optional[str] = None
    crop: Optional[str] = None
    fragmentation: Optional[str] = None
    intercropping: Optional[str] = None


class BiodiversityContext(BaseModel):
    species_richness: Optional[str] = None
    habitat_diversity: Optional[str] = None
    plant_diversity: Optional[str] = None
    pollinator_diversity: Optional[str] = None
    microbial_diversity: Optional[str] = None
    species_survival: Optional[str] = None
    observations: Optional[str] = None


class ClimateContext(BaseModel):
    temperature: Optional[float] = None
    rainfall: Optional[str] = None
    drought: Optional[str] = None
    water_availability: Optional[str] = None
    climate_stress: Optional[str] = None


class HumanImpactContext(BaseModel):
    pollution: Optional[str] = None
    pesticide_use: Optional[str] = None
    deforestation: Optional[str] = None
    land_degradation: Optional[str] = None
    habitat_destruction: Optional[str] = None


class EnvironmentalContext(BaseModel):
    location: LocationContext = Field(default_factory=LocationContext)
    soil: SoilContext = Field(default_factory=SoilContext)
    land: LandContext = Field(default_factory=LandContext)
    biodiversity: BiodiversityContext = Field(default_factory=BiodiversityContext)
    climate: ClimateContext = Field(default_factory=ClimateContext)
    human_impact: HumanImpactContext = Field(default_factory=HumanImpactContext)
    notes: list[str] = Field(default_factory=list)

    def known_variable_count(self) -> int:
        return len(self.known_variables())

    def known_variables(self) -> dict[str, Any]:
        found: dict[str, Any] = {}
        mapping = {
            "region": self.location.region,
            "location": self.location.location,
            "farm_size": self.location.farm_size,
            "latitude": self.location.latitude,
            "longitude": self.location.longitude,
            "soil_ph": self.soil.ph,
            "soil_organic_carbon": self.soil.organic_carbon,
            "soil_organic_carbon_label": self.soil.organic_carbon_label,
            "soil_moisture": self.soil.moisture,
            "land_use": self.land.land_use,
            "land_cover": self.land.land_cover,
            "crop": self.land.crop,
            "fragmentation": self.land.fragmentation,
            "intercropping": self.land.intercropping,
            "species_richness": self.biodiversity.species_richness,
            "habitat_diversity": self.biodiversity.habitat_diversity,
            "plant_diversity": self.biodiversity.plant_diversity,
            "pollinator_diversity": self.biodiversity.pollinator_diversity,
            "microbial_diversity": self.biodiversity.microbial_diversity,
            "species_survival": self.biodiversity.species_survival,
            "biodiversity_observations": self.biodiversity.observations,
            "temperature": self.climate.temperature,
            "rainfall": self.climate.rainfall,
            "drought": self.climate.drought,
            "water_availability": self.climate.water_availability,
            "climate_stress": self.climate.climate_stress,
            "pollution": self.human_impact.pollution,
            "pesticide_use": self.human_impact.pesticide_use,
            "deforestation": self.human_impact.deforestation,
            "land_degradation": self.human_impact.land_degradation,
            "habitat_destruction": self.human_impact.habitat_destruction,
        }
        for key, value in mapping.items():
            if value is not None and value != "":
                found[key] = value
        return found


class StructuredInput(BaseModel):
    region: Optional[str] = None
    location: Optional[str] = None
    farm_size: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    soil_ph: Optional[float] = Field(default=None, ge=0, le=14)
    soil_organic_carbon: Optional[float] = Field(default=None, ge=0, le=20)
    soil_moisture: Optional[str] = None
    rainfall: Optional[str] = None
    temperature: Optional[float] = Field(default=None, ge=-40, le=60)
    crop: Optional[str] = None
    land_use: Optional[str] = None
    land_cover: Optional[str] = None
    fragmentation: Optional[str] = None
    pollution: Optional[str] = None
    pesticide_use: Optional[str] = None
    drought: Optional[str] = None
    deforestation: Optional[str] = None
    species_richness: Optional[str] = None
    habitat_diversity: Optional[str] = None
    water_availability: Optional[str] = None
    land_degradation: Optional[str] = None
    habitat_destruction: Optional[str] = None
    climate_stress: Optional[str] = None
    plant_diversity: Optional[str] = None
    pollinator_diversity: Optional[str] = None
    microbial_diversity: Optional[str] = None
    biodiversity_observations: Optional[str] = None

    @field_validator(
        "soil_moisture",
        "rainfall",
        "pollution",
        "pesticide_use",
        "drought",
        "fragmentation",
        "water_availability",
        mode="before",
    )
    @classmethod
    def normalize_ordinal(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip().lower()
        return value


class ChatRequest(BaseModel):
    message: str = ""
    session_id: Optional[str] = None
    structured: Optional[StructuredInput] = None
    structured_json: Optional[str] = None
    debug: bool = False


class EvidenceItem(BaseModel):
    evidence_id: str = ""
    source: str
    document_name: str
    title: Optional[str] = None
    authors: Optional[str] = None
    institution: Optional[str] = None
    page: Optional[int] = None
    page_is_real: bool = False
    topic: Optional[str] = None
    document_type: Optional[str] = None
    passage: str
    relevance_score: Optional[float] = None
    origin: EvidenceOrigin = "knowledge_base"
    evidence_level: EvidenceLevel = "passage"
    doi: Optional[str] = None
    url: Optional[str] = None
    year: Optional[int] = None
    cited_by_count: Optional[int] = None


class ClaimEvidenceLink(BaseModel):
    claim_id: str
    text: str
    evidence_ids: list[str] = Field(default_factory=list)
    support: ClaimSupport = "direct"
    sources: list[str] = Field(default_factory=list)


class ImpactedMetric(BaseModel):
    name: str
    direction: MetricDirection
    note: Optional[str] = None


class TimeHorizon(BaseModel):
    short_term: Optional[str] = None
    medium_term: Optional[str] = None
    long_term: Optional[str] = None
    narrative: Optional[str] = None
    evidence_supported: bool = False


class HeuristicProfile(BaseModel):
    soil_health: str
    water_stress: str
    habitat_condition: str
    biodiversity_pressure: str
    human_impact: str
    disclaimer: str = (
        "These scores are heuristic readings of the inputs you provided, "
        "not scientifically validated predictions."
    )


class RecommendationItem(BaseModel):
    action: str
    why: str = ""
    impacted_metrics: list[ImpactedMetric] = Field(default_factory=list)
    time_horizon: Optional[str] = None
    supporting_evidence: list[str] = Field(default_factory=list)


class RecommendationBlock(BaseModel):
    action: str
    why_it_works: str
    environmental_relationships: str
    impacted_metrics: list[ImpactedMetric] = Field(default_factory=list)
    time_horizon: TimeHorizon = Field(default_factory=TimeHorizon)
    uncertainty: Optional[str] = None
    confidence: ConfidenceLevel = "low"
    confidence_rationale: str = ""
    items: list[RecommendationItem] = Field(default_factory=list)
    supporting_evidence: list[str] = Field(default_factory=list)


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)


class DebugRetrieval(BaseModel):
    original_query: str = ""
    query: str
    context_aware_query: str = ""
    retrieved: list[EvidenceItem] = Field(default_factory=list)
    accepted: list[EvidenceItem] = Field(default_factory=list)
    rejected: list[EvidenceItem] = Field(default_factory=list)
    threshold: float
    backend: str
    embedding_model: str = ""
    embedding_dimension: int = 0
    vector_database: str = ""
    collection: str = ""
    llm_provider: str = ""
    llm_model: str = ""
    llm_configured: bool = False
    llm_available: bool = False
    llm_raw_response: Optional[str] = None
    conversation_context_used: bool = False
    retrieved_context_passed_to_llm: bool = False
    external_search_triggered: bool = False
    external_search_reason: Optional[str] = None
    external_retrieved: list[EvidenceItem] = Field(default_factory=list)
    evidence_selected_for_llm: list[str] = Field(default_factory=list)
    llm_prompt: Optional[str] = None
    claims: list[ClaimEvidenceLink] = Field(default_factory=list)
    knowledge_status: Optional[str] = None
    environment_extraction_ms: Optional[float] = None
    memory_ms: Optional[float] = None
    chroma_retrieval_ms: Optional[float] = None
    openalex_ms: Optional[float] = None
    evidence_selection_ms: Optional[float] = None
    prompt_build_ms: Optional[float] = None
    llm_first_token_ms: Optional[float] = None
    llm_total_ms: Optional[float] = None
    grounding_ms: Optional[float] = None
    total_request_ms: Optional[float] = None


class ChatResponse(BaseModel):
    session_id: str
    mode: Literal["clarification", "recommendation", "fallback", "error", "answer"]
    assistant_message: str
    clarifying_questions: list[str] = Field(default_factory=list)
    environmental_context: EnvironmentalContext = Field(default_factory=EnvironmentalContext)
    known_variables: dict[str, Any] = Field(default_factory=dict)
    profile: Optional[HeuristicProfile] = None
    recommendation: Optional[RecommendationBlock] = None
    evidence: list[EvidenceItem] = Field(default_factory=list)
    kb_evidence: list[EvidenceItem] = Field(default_factory=list)
    external_evidence: list[EvidenceItem] = Field(default_factory=list)
    knowledge_status: KnowledgeStatus = "awaiting_clarification"
    knowledge_status_label: str = ""
    source_types: list[str] = Field(default_factory=list)
    claims: list[ClaimEvidenceLink] = Field(default_factory=list)
    debug: Optional[DebugRetrieval] = None
    warnings: list[str] = Field(default_factory=list)
    error: Optional[str] = None


class IngestResponse(BaseModel):
    documents_processed: int
    chunks_added: int
    skipped: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    rebuilt: bool = False


class DocumentInfo(BaseModel):
    id: int
    name: str
    title: Optional[str] = None
    document_type: str
    topic: str
    source: str
    pages: int
    chunks: int
    year: Optional[int] = None
    doi: Optional[str] = None
    url: Optional[str] = None
    origin: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    app: str
    documents: int
    chunks: int
    embedding_backend: str
    embedding_model: str
    embedding_dimension: int
    vector_database: str
    collection: str
    vector_count: int
    llm_provider: str
    llm_model: str
    llm_configured: bool
    llm_available: bool
    openalex_enabled: bool
