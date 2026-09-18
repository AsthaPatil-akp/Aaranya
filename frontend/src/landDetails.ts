export type LandDetails = {
  farm_size: string;
  location: string;
  latitude: string;
  longitude: string;
  crop: string;
  land_use: string;
  soil_ph: string;
  soil_organic_carbon: string;
  soil_moisture: string;
  rainfall: string;
  temperature: string;
  pollution: string;
  biodiversity_observations: string;
};

export const EMPTY_LAND_DETAILS: LandDetails = {
  farm_size: "",
  location: "",
  latitude: "",
  longitude: "",
  crop: "",
  land_use: "",
  soil_ph: "",
  soil_organic_carbon: "",
  soil_moisture: "",
  rainfall: "",
  temperature: "",
  pollution: "",
  biodiversity_observations: "",
};

export const LAND_USE_OPTIONS = [
  "",
  "monoculture",
  "intercropping",
  "agroforestry",
  "forest",
  "grassland",
  "urban land",
  "agricultural land",
];

export const LEVEL_OPTIONS = ["", "low", "moderate", "high"];

export const PESTICIDE_OPTIONS = ["", "none", "low", "moderate", "high", "pesticide use"];

const CHIP_LABELS: Record<keyof LandDetails, string> = {
  farm_size: "Farm size",
  location: "Location",
  latitude: "Latitude",
  longitude: "Longitude",
  crop: "Crop",
  land_use: "Land use",
  soil_ph: "Soil pH",
  soil_organic_carbon: "Soil organic carbon",
  soil_moisture: "Soil moisture",
  rainfall: "Rainfall",
  temperature: "Temperature",
  pollution: "Pesticide use",
  biodiversity_observations: "Biodiversity",
};

function parseOptionalNumber(value: string): number | undefined {
  const trimmed = value.trim();
  if (!trimmed) return undefined;
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? parsed : undefined;
}

export function toStructuredPayload(details: LandDetails): Record<string, string | number> {
  const payload: Record<string, string | number> = {};
  const textFields: (keyof LandDetails)[] = [
    "farm_size",
    "location",
    "crop",
    "land_use",
    "soil_moisture",
    "rainfall",
    "pollution",
    "biodiversity_observations",
  ];
  for (const key of textFields) {
    const value = details[key].trim();
    if (value) payload[key] = value;
  }
  const soilPh = parseOptionalNumber(details.soil_ph);
  const carbon = parseOptionalNumber(details.soil_organic_carbon);
  const temperature = parseOptionalNumber(details.temperature);
  const latitude = parseOptionalNumber(details.latitude);
  const longitude = parseOptionalNumber(details.longitude);
  if (soilPh !== undefined) payload.soil_ph = soilPh;
  if (carbon !== undefined) payload.soil_organic_carbon = carbon;
  if (temperature !== undefined) payload.temperature = temperature;
  if (latitude !== undefined) payload.latitude = latitude;
  if (longitude !== undefined) payload.longitude = longitude;
  return payload;
}

export function isLandDetailsEmpty(details: LandDetails): boolean {
  return Object.keys(toStructuredPayload(details)).length === 0;
}

export type LandChip = { key: keyof LandDetails; label: string; value: string };

export function landDetailChips(details: LandDetails): LandChip[] {
  const chips: LandChip[] = [];
  const payload = toStructuredPayload(details);
  if (payload.latitude !== undefined && payload.longitude !== undefined) {
    chips.push({
      key: "latitude",
      label: "Map point",
      value: `${Number(payload.latitude).toFixed(4)}, ${Number(payload.longitude).toFixed(4)}`,
    });
  }
  (Object.keys(CHIP_LABELS) as (keyof LandDetails)[]).forEach((key) => {
    if (key === "latitude" || key === "longitude") return;
    const value = details[key].trim();
    if (value) chips.push({ key, label: CHIP_LABELS[key], value });
  });
  return chips;
}

export function clearLandField(details: LandDetails, key: keyof LandDetails): LandDetails {
  if (key === "latitude" || key === "longitude") {
    return { ...details, latitude: "", longitude: "" };
  }
  return { ...details, [key]: "" };
}

export function mergeStructuredSources(
  details: LandDetails,
  jsonText: string,
): Record<string, unknown> | undefined {
  const fromForm = toStructuredPayload(details);
  let fromJson: Record<string, unknown> = {};
  const raw = jsonText.trim();
  if (raw) {
    const parsed = JSON.parse(raw) as unknown;
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      throw new Error("Structured JSON must be an object.");
    }
    fromJson = parsed as Record<string, unknown>;
  }
  const combined = { ...fromJson, ...fromForm };
  return Object.keys(combined).length ? combined : undefined;
}
