export type EvidenceItem = {
  source: string;
  document_name: string;
  page: number | null;
  topic: string | null;
  document_type: string | null;
  passage: string;
  relevance_score: number | null;
  origin: string;
  doi?: string | null;
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
      evidence_supported: boolean;
    };
    confidence: string;
    confidence_rationale: string;
  } | null;
  evidence: EvidenceItem[];
  knowledge_status: string;
  knowledge_status_label: string;
  debug: {
    query: string;
    retrieved: EvidenceItem[];
    accepted: EvidenceItem[];
    rejected: EvidenceItem[];
    threshold: number;
    backend: string;
  } | null;
  warnings: string[];
  error?: string | null;
};

const API = "";

export async function postChat(body: {
  message: string;
  session_id?: string | null;
  structured_json?: string;
  debug?: boolean;
}): Promise<ChatResponse> {
  const response = await fetch(`${API}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || "Chat request failed");
  }
  return response.json();
}

export async function getHealth() {
  const response = await fetch(`${API}/api/health`);
  if (!response.ok) throw new Error("Health check failed");
  return response.json();
}

export async function listKnowledge() {
  const response = await fetch(`${API}/api/knowledge`);
  if (!response.ok) throw new Error("Could not load knowledge base");
  return response.json();
}

export async function ingestFile(file: File) {
  const data = new FormData();
  data.append("file", file);
  const response = await fetch(`${API}/api/knowledge/ingest`, { method: "POST", body: data });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || "Ingest failed");
  }
  return response.json();
}

export async function rebuildKnowledge() {
  const response = await fetch(`${API}/api/knowledge/rebuild`, { method: "POST" });
  if (!response.ok) throw new Error("Rebuild failed");
  return response.json();
}

export async function searchKnowledge(query: string) {
  const response = await fetch(`${API}/api/knowledge/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
  });
  if (!response.ok) throw new Error("Search failed");
  return response.json();
}
