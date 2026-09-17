export function About() {
  return (
    <main className="section">
      <p className="kicker">Architecture</p>
      <h1>Not a generic chatbot.</h1>
      <p className="lede">
        User input is parsed for environmental variables, merged into conversation memory, checked for missing data,
        searched against a vector index, filtered by relevance, then passed to a multi-metric reasoning layer.
      </p>
      <div className="panel">
        <pre className="debug">{`USER
  → CHAT / STRUCTURED INPUT
  → VARIABLE EXTRACTION
  → CONVERSATION MEMORY
  → MISSING DATA CHECK
        ↙                 ↘
  Clarifying questions    RAG retrieval
                              → relevance check
                                ↙            ↘
                          Grounded RAG     Fallback (OpenAlex or honest refusal)
                                ↘            ↙
                          MULTI-METRIC REASONING
                          → recommendation, metrics, time horizon, confidence, sources`}</pre>
      </div>
      <div className="split" style={{ marginTop: 28 }}>
        <div>
          <h3>What the model is allowed to do</h3>
          <p>Polish explanations when an optional LLM key is present.</p>
          <p>Never invent papers, authors, percentages, or page numbers.</p>
          <p>Never present general model memory as knowledge-base evidence.</p>
        </div>
        <div>
          <h3>How to grow the science</h3>
          <p>Drop a PDF into the Knowledge page or run <code>python scripts/kb.py ingest path/to/file.pdf</code>.</p>
          <p>Rebuild vectors after bulk changes. Spatial fields (lat/lon/region) are already in the data model.</p>
        </div>
      </div>
    </main>
  );
}
