import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { ChatResponse, postChatStream } from "../api";
import { LandDetailsForm } from "../components/LandDetailsForm";
import { MarkdownMessage } from "../components/MarkdownMessage";
import { downloadActionPlanPdf } from "../actionPlanPdf";
import { recommendationItems } from "../actionPlan";
import {
  EMPTY_LAND_DETAILS,
  LandDetails,
  clearLandField,
  landDetailChips,
  mergeStructuredSources,
} from "../landDetails";
import { hideInternalEvidenceIds } from "../markdown";

type Turn = { role: "user" | "assistant"; text: string; payload?: ChatResponse };

function evidenceTitlesById(payload?: ChatResponse): Record<string, string> {
  const titles: Record<string, string> = {};
  for (const item of [...(payload?.kb_evidence || []), ...(payload?.external_evidence || [])]) {
    const id = (item.evidence_id || "").trim().toLowerCase();
    const title = (item.title || item.document_name || "").trim();
    if (!id || !title) continue;
    titles[id] = title;
    titles[id.replace(/-/g, "")] = title;
  }
  return titles;
}

async function copyText(text: string) {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    /* fall through to execCommand */
  }
  try {
    const node = document.createElement("textarea");
    node.value = text;
    node.setAttribute("readonly", "");
    node.style.position = "fixed";
    node.style.left = "-9999px";
    document.body.appendChild(node);
    node.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(node);
    return ok;
  } catch {
    return false;
  }
}

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

function metricDisplay(metric: { name: string; direction: string; note?: string | null }) {
  const note = (metric.note || "").trim();
  if (note) return note;
  if (metric.direction && metric.direction !== "unknown") return metric.direction;
  return "potentially affected";
}

function MetricList({
  metrics,
}: {
  metrics: { name: string; direction: string; note?: string | null }[];
}) {
  if (!metrics.length) {
    return <p className="tiny">No impacted metrics were returned for this recommendation.</p>;
  }
  return (
    <>
      {metrics.map((metric, index) => (
        <div className="metric" key={`${metric.name}-${index}`}>
          <span>
            {metric.name}: <b>{metricDisplay(metric)}</b>
          </span>
        </div>
      ))}
    </>
  );
}

export function Lab() {
  const [message, setMessage] = useState("");
  const [jsonInput, setJsonInput] = useState("");
  const [landDetails, setLandDetails] = useState<LandDetails>(EMPTY_LAND_DETAILS);
  const [showLandForm, setShowLandForm] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [latest, setLatest] = useState<ChatResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [showDebug, setShowDebug] = useState(false);
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null);
  const chatLogRef = useRef<HTMLDivElement | null>(null);

  const variables = useMemo(() => latest?.known_variables ?? {}, [latest]);

  useEffect(() => {
    const node = chatLogRef.current;
    if (!node) return;
    node.scrollTop = node.scrollHeight;
  }, [turns, draft, busy]);

  async function send(event?: FormEvent) {
    event?.preventDefault();
    const text = message.trim();
    const jsonText = jsonInput.trim();
    let structured: Record<string, unknown> | undefined;
    try {
      structured = mergeStructuredSources(landDetails, jsonText);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Structured JSON must be an object.");
      return;
    }
    if ((!text && !structured) || busy) return;
    setBusy(true);
    setDraft("");
    setError(null);
    const userText = text || "Structured environmental profile submitted.";
    setTurns((current) => [...current, { role: "user", text: userText }]);
    setMessage("");
    try {
      const result = await postChatStream(
        {
          message: text,
          session_id: sessionId,
          structured,
          debug: showDebug,
        },
        {
          onToken: (token) => {
            setDraft((current) => current + token);
          },
        },
      );
      setSessionId(result.session_id);
      setLatest(result);
      setTurns((current) => [...current, { role: "assistant", text: result.assistant_message, payload: result }]);
      setDraft("");
    } catch (err) {
      const detail = err instanceof Error ? err.message : "Request failed";
      setError(detail);
      setMessage(text);
    } finally {
      setBusy(false);
    }
  }

  async function copyAnswer(text: string, index: number) {
    const copied = await copyText(hideInternalEvidenceIds(text, evidenceTitlesById(latest || undefined)));
    setCopiedIndex(copied ? index : null);
    if (!copied) return;
    window.setTimeout(() => {
      setCopiedIndex((current) => (current === index ? null : current));
    }, 1600);
  }

  return (
    <main className="lab-layout">
      <section className="panel lab-column chat-column">
        <div className="chat-column-header">
          <p className="kicker">Intelligence Lab</p>
        </div>
        <div className="chat-log" ref={chatLogRef}>
          {turns.length === 0 && (
            <div className="bubble assistant">
              Describe a landscape, a farm, or a pressure you are seeing. If the picture is incomplete, I will ask
              for soil carbon, rainfall, land use and related variables before recommending anything.
            </div>
          )}
          {turns.map((turn, index) => (
            <div key={index} className={turn.role === "assistant" ? "answer-block" : undefined}>
              <div className={`bubble ${turn.role}${turn.role === "assistant" ? " has-copy" : ""}`}>
                {turn.role === "assistant" && (
                  <button
                    type="button"
                    className="copy-answer"
                    aria-label={copiedIndex === index ? "Answer copied" : "Copy answer"}
                    title={copiedIndex === index ? "Copied" : "Copy answer"}
                    onClick={() => void copyAnswer(turn.text, index)}
                  >
                    {copiedIndex === index ? (
                      <span className="copy-answer-label">Copied</span>
                    ) : (
                      <svg viewBox="0 0 24 24" aria-hidden="true">
                        <rect x="8" y="8" width="12" height="14" rx="2" fill="none" stroke="currentColor" strokeWidth="1.8" />
                        <path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h2" fill="none" stroke="currentColor" strokeWidth="1.8" />
                      </svg>
                    )}
                  </button>
                )}
                {turn.role === "assistant" ? (
                  <MarkdownMessage text={turn.text} titlesById={evidenceTitlesById(turn.payload)} />
                ) : (
                  <div className="bubble-text">{turn.text}</div>
                )}
              </div>
              {turn.role === "assistant" && turn.payload && (
                <button
                  type="button"
                  className="btn inverse download-plan"
                  data-testid="download-action-plan"
                  onClick={() => {
                    void downloadActionPlanPdf(turn.payload!, landDetails);
                  }}
                >
                  Download Action Plan PDF
                </button>
              )}
            </div>
          ))}
          {busy && !draft && <div className="bubble assistant">Reasoning… looking at your conditions and the evidence.</div>}
          {busy && draft && (
            <div className="bubble assistant">
              <MarkdownMessage text={draft} />
            </div>
          )}
        </div>
        <form className="composer" onSubmit={send}>
          {landDetailChips(landDetails).length > 0 && (
            <div className="land-chips" data-testid="land-detail-chips">
              {landDetailChips(landDetails).map((chip) => (
                <button
                  key={chip.key}
                  type="button"
                  className="land-chip"
                  disabled={busy}
                  onClick={() => setShowLandForm(true)}
                >
                  <span>
                    {chip.label}: <b>{chip.value}</b>
                  </span>
                  <span
                    className="land-chip-remove"
                    role="button"
                    aria-label={`Remove ${chip.label}`}
                    onClick={(event) => {
                      event.stopPropagation();
                      setLandDetails((current) => clearLandField(current, chip.key));
                    }}
                  >
                    ×
                  </span>
                </button>
              ))}
            </div>
          )}
          <textarea
            rows={2}
            value={message}
            onChange={(event) => setMessage(event.target.value)}
            placeholder="Type a new question about your land, soil, rainfall, or biodiversity…"
            disabled={busy}
          />
          <div className="composer-row">
            <button className="btn primary" type="submit" disabled={busy}>
              Send
            </button>
            <button
              className="btn ghost"
              type="button"
              disabled={busy}
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
              disabled={busy}
              onClick={() => {
                setMessage("My farm is 5 acres in a semi-arid region. I grow wheat as a monoculture. Soil pH is 8.1, organic carbon is 0.3%, soil moisture is low, rainfall is low and irregular, and I've noticed fewer bees and butterflies. What should I do?");
              }}
            >
              Demo: farm profile
            </button>
            <button
              className="btn inverse"
              type="button"
              data-testid="add-land-details"
              disabled={busy}
              onClick={() => setShowLandForm(true)}
              aria-haspopup="dialog"
            >
              Add Land Details
            </button>
          </div>
          <details className="composer-extras">
            <summary className="tiny">Optional structured JSON</summary>
            <textarea
              className="json-box"
              rows={6}
              value={jsonInput}
              onChange={(event) => setJsonInput(event.target.value)}
              placeholder={SAMPLE_JSON}
              disabled={busy}
            />
            <button
              className="btn ghost"
              type="button"
              disabled={busy}
              onClick={() => setJsonInput(SAMPLE_JSON)}
            >
              Load example JSON
            </button>
          </details>
          {error && <p className="tiny" style={{ color: "#a15c32" }}>{error}</p>}
        </form>
        {showLandForm && (
          <LandDetailsForm
            details={landDetails}
            onChange={setLandDetails}
            onClose={() => setShowLandForm(false)}
          />
        )}
      </section>

      <aside className="side-stack lab-column">
        <section className="panel">
          <p className="kicker">Knowledge status</p>
          <span className={`badge ${latest?.knowledge_status === "insufficient_evidence" ? "warn" : ""}`}>
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
          <section className="panel" data-testid="recommendation-panel">
            <p className="kicker">Recommendation</p>
            {recommendationItems(latest).map((card, index) => (
              <article className="recommendation-item" key={`${card.action}-${index}`}>
                <h3>{card.action}</h3>
                <p className="tiny">
                  <b>Why:</b>{" "}
                  {card.why || "The retrieved evidence does not support a more specific explanation for this action."}
                </p>
                <h4>Impacted metrics</h4>
                <MetricList metrics={card.metrics} />
                <h4>Time horizon</h4>
                <p className="tiny">
                  {card.timeHorizon || "No specific timeframe is supported by the retrieved evidence."}
                </p>
                <h4>Supporting evidence</h4>
                {card.sources.length === 0 ? (
                  <p className="tiny">No supporting evidence titles were returned.</p>
                ) : (
                  <ul className="tiny">
                    {card.sources.map((source) => (
                      <li key={source}>{source}</li>
                    ))}
                  </ul>
                )}
              </article>
            ))}
            {latest.recommendation.uncertainty && (
              <p className="tiny" style={{ marginTop: 8 }}>{latest.recommendation.uncertainty}</p>
            )}
          </section>
        )}

        <section className="panel">
          <p className="kicker">Knowledge base sources</p>
          {(latest?.kb_evidence || []).length === 0 && (
            <p className="tiny">No internal knowledge-base passages were used.</p>
          )}
          {(latest?.kb_evidence || []).map((item, index) => (
            <article className="evidence" key={`${item.evidence_id}-${index}`}>
              <h4>{item.title || item.document_name}</h4>
              <p className="tiny">
                Internal synthesis
                {item.page_is_real && item.page ? ` · page ${item.page}` : " · page unavailable"}
                {item.year ? ` · ${item.year}` : ""}
                {item.doi ? ` · DOI ${item.doi}` : ""}
                {item.relevance_score != null ? ` · score ${item.relevance_score}` : ""}
              </p>
              {item.url && <p className="tiny">{item.url}</p>}
              <p className="tiny">{item.passage}</p>
            </article>
          ))}
        </section>

        <section className="panel">
          <p className="kicker">External scientific sources</p>
          {(latest?.external_evidence || []).length === 0 && (
            <p className="tiny">No external scientific passages were used.</p>
          )}
          {(latest?.external_evidence || []).map((item, index) => (
            <article className="evidence" key={`${item.evidence_id}-${index}`}>
              <h4>{item.title || item.document_name}</h4>
              <p className="tiny">
                External · {item.evidence_level === "abstract" ? "abstract only" : item.evidence_level === "full_text" ? "open-access text" : item.evidence_level}
                {item.authors ? ` · ${item.authors}` : ""}
                {item.year ? ` · ${item.year}` : ""}
                {item.doi ? ` · DOI ${item.doi}` : ""}
              </p>
              {item.url && <p className="tiny">{item.url}</p>}
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
            <>
              <p className="tiny" style={{ marginTop: 8 }}>
                Model: <b>{String(latest.debug.llm_provider || "")}</b>
                {latest.debug.llm_model ? ` / ${String(latest.debug.llm_model)}` : ""}
                {" · configured="}
                {String(latest.debug.llm_configured)}
                {" · available="}
                {String(latest.debug.llm_available)}
              </p>
              <p className="tiny">Grounding: {String(latest.debug.knowledge_status || latest.knowledge_status)}</p>
              {(latest.debug.total_request_ms != null || latest.debug.llm_first_token_ms != null) && (
                <p className="tiny">
                  Timing ms: first token {String(latest.debug.llm_first_token_ms ?? "—")}
                  {" · chroma "}{String(latest.debug.chroma_retrieval_ms ?? "—")}
                  {" · openalex "}{String(latest.debug.openalex_ms ?? "—")}
                  {" · llm "}{String(latest.debug.llm_total_ms ?? "—")}
                  {" · grounding "}{String(latest.debug.grounding_ms ?? "—")}
                  {" · total "}{String(latest.debug.total_request_ms ?? "—")}
                </p>
              )}
              <pre className="debug">{JSON.stringify(latest.debug, null, 2)}</pre>
            </>
          )}
        </section>
      </aside>
    </main>
  );
}
