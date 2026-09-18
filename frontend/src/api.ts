export type EvidenceItem = {
  evidence_id?: string;
  source: string;
  document_name: string;
  title?: string | null;
  authors?: string | null;
  institution?: string | null;
  page: number | null;
  page_is_real?: boolean;
  topic: string | null;
  document_type: string | null;
  passage: string;
  relevance_score: number | null;
  origin: string;
  evidence_level?: string;
  doi?: string | null;
  url?: string | null;
  year?: number | null;
};

export type ChatResponse = {
  session_id: string;
  mode: string;
  assistant_message: string;
  clarifying_questions: string[];
  environmental_context: Record<string, unknown>;
  known_variables: Record<string, unknown>;
  profile: {
    soil_health: string;
    water_stress: string;
    habitat_condition: string;
    biodiversity_pressure: string;
    human_impact: string;
    disclaimer: string;
  } | null;
  recommendation: {
    action: string;
    why_it_works: string;
    environmental_relationships: string;
    impacted_metrics: { name: string; direction: string; note?: string | null }[];
    time_horizon: {
      short_term?: string | null;
      medium_term?: string | null;
      long_term?: string | null;
      narrative?: string | null;
      evidence_supported: boolean;
    };
    uncertainty?: string | null;
    confidence: string;
    confidence_rationale: string;
    items?: {
      action: string;
      why?: string;
      impacted_metrics?: { name: string; direction: string; note?: string | null }[];
      time_horizon?: string | null;
      supporting_evidence?: string[];
    }[];
    supporting_evidence?: string[];
  } | null;
  evidence: EvidenceItem[];
  kb_evidence?: EvidenceItem[];
  external_evidence?: EvidenceItem[];
  knowledge_status: string;
  knowledge_status_label: string;
  source_types?: string[];
  claims?: { claim_id: string; text: string; evidence_ids: string[]; support: string; sources: string[] }[];
  debug: Record<string, unknown> | null;
  warnings: string[];
  error?: string | null;
};

const API = String(import.meta.env.VITE_API_URL || import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");

async function readError(response: Response, fallback: string) {
  const detail = await response.text();
  try {
    const parsed = JSON.parse(detail);
    if (parsed.detail) return typeof parsed.detail === "string" ? parsed.detail : JSON.stringify(parsed.detail);
  } catch {
    /* text */
  }
  return detail || fallback;
}

export async function postChat(body: {
  message: string;
  session_id?: string | null;
  structured?: Record<string, unknown>;
  structured_json?: string;
  debug?: boolean;
}): Promise<ChatResponse> {
  const response = await fetch(`${API}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(await readError(response, "Chat request failed"));
  return response.json();
}

export async function postChatStream(
  body: {
    message: string;
    session_id?: string | null;
    structured?: Record<string, unknown>;
    structured_json?: string;
    debug?: boolean;
  },
  handlers: {
    onToken?: (text: string) => void;
  } = {},
): Promise<ChatResponse> {
  const response = await fetch(`${API}/api/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/x-ndjson" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(await readError(response, "Chat request failed"));
  if (!response.body) throw new Error("Streaming is not available");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let final: ChatResponse | null = null;
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) continue;
      const event = JSON.parse(trimmed) as { type?: string; text?: string; response?: ChatResponse; detail?: string };
      if (event.type === "token" && event.text) handlers.onToken?.(event.text);
      if (event.type === "final" && event.response) final = event.response;
      if (event.type === "error") throw new Error(event.detail || "Chat request failed");
    }
  }
  if (buffer.trim()) {
    const event = JSON.parse(buffer.trim()) as { type?: string; text?: string; response?: ChatResponse; detail?: string };
    if (event.type === "token" && event.text) handlers.onToken?.(event.text);
    if (event.type === "final" && event.response) final = event.response;
    if (event.type === "error") throw new Error(event.detail || "Chat request failed");
  }
  if (!final) throw new Error("The model stream ended without a final response.");
  return final;
}

export async function searchLocations(query: string): Promise<{ label: string; latitude: number; longitude: number }[]> {
  const text = query.trim();
  if (text.length < 2) return [];
  if (API) {
    try {
      const response = await fetch(`${API}/api/geocode?q=${encodeURIComponent(text)}`);
      if (response.ok) {
        const rows = await response.json();
        if (Array.isArray(rows) && rows.length) return rows;
      }
    } catch {
      /* Fall through to the public geocoder so the map still updates. */
    }
  }
  const response = await fetch(`https://photon.komoot.io/api/?q=${encodeURIComponent(text)}&limit=5`);
  if (!response.ok) throw new Error(await readError(response, "Location search failed"));
  const payload = (await response.json()) as {
    features?: Array<{ properties?: Record<string, string>; geometry?: { coordinates?: number[] } }>;
  };
  const rows: { label: string; latitude: number; longitude: number }[] = [];
  for (const feature of payload.features || []) {
    const coords = feature.geometry?.coordinates;
    if (!coords || coords.length < 2) continue;
    const longitude = Number(coords[0]);
    const latitude = Number(coords[1]);
    if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) continue;
    const props = feature.properties || {};
    const parts = ["name", "city", "county", "state", "country"]
      .map((key) => String(props[key] || "").trim())
      .filter((value, index, all) => value && all.indexOf(value) === index);
    rows.push({ label: parts.join(", ") || text, latitude, longitude });
  }
  return rows;
}

export async function listKnowledge() {
  const response = await fetch(`${API}/api/knowledge`);
  if (!response.ok) throw new Error("Could not load knowledge base");
  return response.json();
}

function adminHeaders(): HeadersInit {
  const token = sessionStorage.getItem("darukaa_admin_token") || "";
  return token ? { "X-Admin-Token": token } : {};
}

export async function ingestFile(file: File) {
  const data = new FormData();
  data.append("file", file);
  const response = await fetch(`${API}/api/knowledge/ingest`, {
    method: "POST",
    body: data,
    headers: adminHeaders(),
  });
  if (!response.ok) throw new Error(await readError(response, "Ingest failed"));
  return response.json();
}

export async function rebuildKnowledge() {
  const response = await fetch(`${API}/api/knowledge/rebuild`, {
    method: "POST",
    headers: adminHeaders(),
  });
  if (!response.ok) throw new Error(await readError(response, "Rebuild failed"));
  return response.json();
}

export async function searchKnowledge(query: string) {
  const response = await fetch(`${API}/api/knowledge/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
  });
  if (!response.ok) throw new Error(await readError(response, "Search failed"));
  return response.json();
}
