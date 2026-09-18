import { ChatResponse, EvidenceItem } from "./api";
import { PDF_HEADING } from "./brand";
import { LandDetails } from "./landDetails";

export type ActionPlanMetric = { name: string; direction: string; note?: string | null };

export type ActionPlanRecommendation = {
  action: string;
  why: string;
  metrics: ActionPlanMetric[];
  timeHorizon: string;
  sources: string[];
};

export type ActionPlanProfileRow = { label: string; value: string };

export type ActionPlanSource = {
  title: string;
  origin: "knowledge_base" | "external";
  evidenceLevel: string;
  link: string;
};

export type ActionPlanMonitor = {
  metric: string;
  frequency: string;
};

export type ActionPlanDocument = {
  heading: string;
  generatedLabel: string;
  siteProfile: ActionPlanProfileRow[];
  assessment: string;
  recommendations: ActionPlanRecommendation[];
  monitoring: ActionPlanMonitor[];
  kbSources: ActionPlanSource[];
  externalSources: ActionPlanSource[];
  limitations: string[];
};

const PROFILE_LABELS: Record<string, string> = {
  location: "Location",
  latitude: "Latitude",
  longitude: "Longitude",
  farm_size: "Farm size",
  crop: "Crop / vegetation",
  land_use: "Land use",
  soil_ph: "Soil pH",
  soil_organic_carbon: "Soil organic carbon",
  soil_moisture: "Soil moisture",
  rainfall: "Rainfall",
  temperature: "Temperature",
  pollution: "Pollution",
  pesticide_use: "Pesticide use",
  biodiversity_observations: "Biodiversity observations",
  pollinator_diversity: "Pollinator diversity",
  plant_diversity: "Plant diversity",
  habitat_diversity: "Habitat diversity",
  species_richness: "Species richness",
  water_availability: "Water availability",
  drought: "Drought",
  fragmentation: "Fragmentation",
  region: "Region",
};

function uniqueTitles(values: Array<string | null | undefined>) {
  const titles: string[] = [];
  const seen = new Set<string>();
  for (const value of values) {
    const title = (value || "").trim();
    const key = title.toLowerCase();
    if (!title || seen.has(key)) continue;
    seen.add(key);
    titles.push(title);
  }
  return titles;
}

export function recommendationItems(response: ChatResponse): ActionPlanRecommendation[] {
  const rec = response.recommendation;
  if (!rec) return [];
  const parentHorizon = rec.time_horizon?.narrative || "";
  const raw = rec.items?.length
    ? rec.items
    : [
        {
          action: rec.action,
          why: rec.why_it_works,
          impacted_metrics: rec.impacted_metrics,
          time_horizon: parentHorizon,
          supporting_evidence: rec.supporting_evidence,
        },
      ];
  const cards: ActionPlanRecommendation[] = [];
  const seen = new Set<string>();
  for (const item of raw) {
    const action = (item.action || rec.action || "").trim();
    const key = action.toLowerCase().replace(/\s+/g, " ");
    if (!action || seen.has(key) || /^(kb|oa)[-:]/i.test(action)) continue;
    seen.add(key);
    cards.push({
      action,
      why: (item.why || rec.why_it_works || "").trim(),
      metrics: item.impacted_metrics?.length ? item.impacted_metrics : rec.impacted_metrics || [],
      timeHorizon: (item.time_horizon || parentHorizon).trim(),
      sources: uniqueTitles(
        item.supporting_evidence?.length ? item.supporting_evidence : rec.supporting_evidence || [],
      ),
    });
  }
  return cards;
}

function providedValue(value: unknown): string | null {
  if (value == null) return null;
  const text = String(value).trim();
  return text ? text : null;
}

export function siteProfileRows(response: ChatResponse, landDetails: LandDetails): ActionPlanProfileRow[] {
  const known = response.known_variables || {};
  const merged: Record<string, string> = {};
  for (const [key, value] of Object.entries(known)) {
    const text = providedValue(value);
    if (text) merged[key] = text;
  }
  (Object.keys(landDetails) as (keyof LandDetails)[]).forEach((key) => {
    const text = providedValue(landDetails[key]);
    if (text) merged[key] = text;
  });
  const rows: ActionPlanProfileRow[] = [];
  const lat = providedValue(merged.latitude);
  const lng = providedValue(merged.longitude);
  if (merged.location) rows.push({ label: "Location", value: merged.location });
  if (lat && lng) rows.push({ label: "Map coordinates", value: `${lat}, ${lng}` });
  else if (lat) rows.push({ label: "Latitude", value: lat });
  else if (lng) rows.push({ label: "Longitude", value: lng });
  const order = [
    "farm_size",
    "crop",
    "land_use",
    "soil_ph",
    "soil_organic_carbon",
    "soil_moisture",
    "rainfall",
    "temperature",
    "pollution",
    "pesticide_use",
    "biodiversity_observations",
    "pollinator_diversity",
    "plant_diversity",
    "habitat_diversity",
    "region",
  ];
  const used = new Set(["location", "latitude", "longitude"]);
  for (const key of order) {
    if (!merged[key] || used.has(key)) continue;
    used.add(key);
    rows.push({ label: PROFILE_LABELS[key] || key.replace(/_/g, " "), value: merged[key] });
  }
  for (const [key, value] of Object.entries(merged)) {
    if (used.has(key) || key === "notes") continue;
    rows.push({ label: PROFILE_LABELS[key] || key.replace(/_/g, " "), value });
  }
  return rows;
}

export function groundedAssessment(response: ChatResponse): string {
  const text = (response.assistant_message || "").trim();
  if (!text) return "";
  return text.split(/(?:\n+|[.!?]\s+)sources?\s*\/?\s*evidence\b/i)[0].trim();
}

function evidenceLevelLabel(item: EvidenceItem): string {
  if (item.origin === "knowledge_base") return "internal synthesis";
  if (item.evidence_level === "abstract") return "abstract-level evidence";
  if (item.evidence_level === "full_text") return "open-access text";
  return item.evidence_level || "external";
}

function sourceLink(item: EvidenceItem): string {
  if (item.url) return item.url;
  if (item.doi) return item.doi.startsWith("http") ? item.doi : `https://doi.org/${item.doi}`;
  return "";
}

function mapSources(items: EvidenceItem[], origin: "knowledge_base" | "external"): ActionPlanSource[] {
  const out: ActionPlanSource[] = [];
  const seen = new Set<string>();
  for (const item of items) {
    const title = (item.title || item.document_name || "").trim();
    const key = title.toLowerCase();
    if (!title || seen.has(key)) continue;
    seen.add(key);
    out.push({
      title,
      origin,
      evidenceLevel: evidenceLevelLabel(item),
      link: sourceLink(item),
    });
  }
  return out;
}

function monitoringItems(response: ChatResponse, recommendations: ActionPlanRecommendation[]): ActionPlanMonitor[] {
  const horizon = response.recommendation?.time_horizon;
  const supported = Boolean(horizon?.evidence_supported);
  const narrative = (horizon?.narrative || "").trim();
  const noTime = /no specific timeframe is supported/i.test(narrative);
  const frequency = supported && narrative && !noTime ? narrative : "";
  const seen = new Set<string>();
  const rows: ActionPlanMonitor[] = [];
  for (const rec of recommendations) {
    for (const metric of rec.metrics) {
      const name = (metric.name || "").trim();
      const key = name.toLowerCase();
      if (!name || seen.has(key)) continue;
      seen.add(key);
      rows.push({ metric: name, frequency });
    }
  }
  return rows;
}

function limitationLines(response: ChatResponse): string[] {
  const lines: string[] = [];
  const uncertainty = (response.recommendation?.uncertainty || "").trim();
  if (uncertainty) lines.push(uncertainty);
  const rationale = (response.recommendation?.confidence_rationale || "").trim();
  if (rationale) {
    const confidence = response.recommendation?.confidence;
    lines.push(confidence ? `Confidence: ${confidence}. ${rationale}` : rationale);
  }
  if (response.knowledge_status_label) lines.push(`Knowledge status: ${response.knowledge_status_label}.`);
  if (response.mode === "clarification") {
    lines.push("This response asked for more site information before a complete action plan could be given.");
  }
  return lines;
}

export function buildActionPlan(response: ChatResponse, landDetails: LandDetails): ActionPlanDocument {
  const recommendations = recommendationItems(response);
  return {
    heading: PDF_HEADING,
    generatedLabel: "Prepared from the grounded Lab response. Unsupported values are omitted.",
    siteProfile: siteProfileRows(response, landDetails),
    assessment: groundedAssessment(response),
    recommendations,
    monitoring: monitoringItems(response, recommendations),
    kbSources: mapSources(response.kb_evidence || [], "knowledge_base"),
    externalSources: mapSources(response.external_evidence || [], "external"),
    limitations: limitationLines(response),
  };
}
