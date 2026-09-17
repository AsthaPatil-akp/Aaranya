import { FormEvent, useMemo, useState } from "react";
import { ChatResponse, postChat } from "../api";

type Turn = { role: "user" | "assistant"; text: string; payload?: ChatResponse };

const SAMPLE_JSON = `{
  "region": "semi-arid",
  "soil_ph": 8.1,
  "soil_organic_carbon": 0.3,
  "soil_moisture": "low",
  "rainfall": "low",
  "temperature": 29,
  "crop": "wheat",
  "land_use": "monoculture",
  "pollution": "moderate"
}`;

function arrow(direction: string) {
  if (direction === "up") return "↑";
  if (direction === "down") return "↓";
  return "neutral";
}

export function Lab() {
  const [message, setMessage] = useState("Biodiversity is declining on my farm.");
  const [jsonInput, setJsonInput] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [latest, setLatest] = useState<ChatResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showDebug, setShowDebug] = useState(true);

  const variables = useMemo(() => latest?.known_variables ?? {}, [latest]);

  async function send(event?: FormEvent) {
    event?.preventDefault();
    const text = message.trim();
    const structured = jsonInput.trim();
    if (!text && !structured) return;
    setBusy(true);
    setError(null);
    const userText = text || "Structured environmental profile submitted.";
    setTurns((current) => [...current, { role: "user", text: userText }]);
    try {
      const result = await postChat({
        message: text,
        session_id: sessionId,
        structured_json: structured || undefined,
        debug: true,
      });
      setSessionId(result.session_id);
      setLatest(result);
      setTurns((current) => [...current, { role: "assistant", text: result.assistant_message, payload: result }]);
      setMessage("");
    } catch (err) {
      const detail = err instanceof Error ? err.message : "Request failed";
      setError(detail);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="lab-layout">
      <section className="panel">
        <p className="kicker">Intelligence Lab</p>
        <h2>Speak like a field scientist.</h2>
        <p className="tiny">
          Natural language or structured JSON. The system keeps an environmental context, asks for missing variables,
          retrieves evidence, then reasons across at least three metrics.
        </p>
        <div className="chat-log">
          {turns.length === 0 && (
            <div className="bubble assistant">
              Describe a landscape, a farm, or a pressure you are seeing. If the picture is incomplete, I will ask
              for soil carbon, rainfall, land use and related variables before recommending anything.
            </div>
          )}
          {turns.map((turn, index) => (
            <div key={index} className={`bubble ${turn.role}`}>
              {turn.text}
            </div>
          ))}
        </div>
        <form className="composer" onSubmit={send}>
          <textarea
            rows={3}
            value={message}
            onChange={(event) => setMessage(event.target.value)}
            placeholder="My farm has low rainfall, soil organic carbon of 0.3%, pH 8.1 and wheat monoculture."
          />
          <div className="composer-row">
            <button className="btn primary" disabled={busy} type="submit">
              {busy ? "Reasoning…" : "Send"}
            </button>
            <button
              className="btn ghost"
              type="button"
              onClick={() => {
                setMessage("Biodiversity is declining on my farm.");
                setJsonInput("");
              }}
            >
              Demo: incomplete
            </button>
            <button
              className="btn ghost"
              type="button"
              onClick={() => {
                setMessage("Soil organic carbon is 0.3%, pH 8.1, rainfall is low, soil moisture is low, wheat monoculture, semi-arid region.");
              }}
            >
              Demo: farm profile
            </button>
          </div>
          <label className="tiny">Optional structured JSON</label>
          <textarea
            className="json-box"
            rows={8}
            value={jsonInput}
            onChange={(event) => setJsonInput(event.target.value)}
            placeholder={SAMPLE_JSON}
          />
          <button
            className="btn ghost"
            type="button"
            onClick={() => setJsonInput(SAMPLE_JSON)}
          >
            Load example JSON
          </button>
          {error && <p className="tiny" style={{ color: "#a15c32" }}>{error}</p>}
        </form>
      </section>

      <aside className="side-stack">
        <section className="panel">
          <p className="kicker">Knowledge status</p>
          <span className={`badge ${latest?.knowledge_status === "insufficient_verified_evidence" ? "warn" : ""}`}>
            {latest?.knowledge_status_label || "Waiting for a question"}
          </span>
          {latest?.recommendation && (
            <p className="tiny" style={{ marginTop: 8 }}>
              Confidence: <b>{latest.recommendation.confidence}</b> — {latest.recommendation.confidence_rationale}
            </p>
          )}
        </section>

        <section className="panel">
          <p className="kicker">Environmental variables</p>
          <h3>Conversation context</h3>
          {Object.keys(variables).length === 0 && <p className="tiny">Nothing stored yet.</p>}
          {Object.entries(variables).map(([key, value]) => (
            <div className="kv" key={key}>
              <span>{key.replace(/_/g, " ")}: <b>{String(value)}</b></span>
            </div>
          ))}
        </section>

        {latest?.profile && (
          <section className="panel">
            <p className="kicker">Heuristic profile</p>
            <div className="kv"><span>Soil health: <b>{latest.profile.soil_health}</b></span></div>
            <div className="kv"><span>Water stress: <b>{latest.profile.water_stress}</b></span></div>
            <div className="kv"><span>Habitat: <b>{latest.profile.habitat_condition}</b></span></div>
            <div className="kv"><span>Biodiversity pressure: <b>{latest.profile.biodiversity_pressure}</b></span></div>
            <div className="kv"><span>Human impact: <b>{latest.profile.human_impact}</b></span></div>
            <p className="tiny">{latest.profile.disclaimer}</p>
          </section>
        )}

        {latest?.recommendation && (
          <section className="panel">
            <p className="kicker">Recommendation</p>
            <h3>{latest.recommendation.action}</h3>
            <p className="tiny">{latest.recommendation.why_it_works}</p>
            <h4>Impacted metrics</h4>
            {latest.recommendation.impacted_metrics.map((metric) => (
              <div className="metric" key={metric.name}>
                <span>
                  {metric.name}:{" "}
                  <b className={metric.direction === "up" ? "up" : metric.direction === "down" ? "down" : ""}>
                    {arrow(metric.direction)}
                  </b>
                </span>
              </div>
            ))}
            <h4>Time horizon</h4>
            <p className="tiny"><b>Short:</b> {latest.recommendation.time_horizon.short_term || "Not estimated"}</p>
            <p className="tiny"><b>Medium:</b> {latest.recommendation.time_horizon.medium_term || "Not estimated"}</p>
            <p className="tiny"><b>Long:</b> {latest.recommendation.time_horizon.long_term || "Not estimated"}</p>
          </section>
        )}

        <section className="panel">
          <p className="kicker">Scientific evidence used</p>
          {(latest?.evidence || []).filter((item) => item.origin === "knowledge_base").length === 0 && (
            <p className="tiny">No knowledge-base passages have been accepted yet.</p>
          )}
          {(latest?.evidence || []).map((item, index) => (
            <article className="evidence" key={`${item.document_name}-${index}`}>
              <h4>{item.document_name}</h4>
              <p className="tiny">
                {item.origin === "knowledge_base" ? "Knowledge base" : item.origin.replace(/_/g, " ")}
                {item.page ? ` · page ${item.page}` : ""} · {item.topic}
                {item.relevance_score != null ? ` · score ${item.relevance_score}` : ""}
              </p>
              <p className="tiny">{item.passage}</p>
            </article>
          ))}
        </section>

        <section className="panel">
          <p className="kicker">Developer retrieval view</p>
          <button className="btn ghost" type="button" onClick={() => setShowDebug((value) => !value)}>
            {showDebug ? "Hide" : "Show"} query, chunks and scores
          </button>
          {showDebug && latest?.debug && (
            <pre className="debug">{JSON.stringify(latest.debug, null, 2)}</pre>
          )}
        </section>
      </aside>
    </main>
  );
}
