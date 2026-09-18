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

const API = "";

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
  const response = await fetch(`${API}/api/geocode?q=${encodeURIComponent(query)}`);
  if (!response.ok) return [];
  const rows = await response.json();
  return Array.isArray(rows) ? rows : [];
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
