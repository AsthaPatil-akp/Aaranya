import { useEffect, useState } from "react";
import { ingestFile, listKnowledge, rebuildKnowledge, searchKnowledge } from "../api";

type Doc = {
  id: number;
  name: string;
  document_type: string;
  topic: string;
  source: string;
  pages: number;
  chunks: number;
};

export function Knowledge() {
  const [docs, setDocs] = useState<Doc[]>([]);
  const [query, setQuery] = useState("low soil organic carbon rainfall monoculture cover crops");
  const [hits, setHits] = useState<any>(null);
  const [status, setStatus] = useState<string>("");

  async function refresh() {
    setDocs(await listKnowledge());
  }

  useEffect(() => {
    refresh().catch((err) => setStatus(String(err)));
  }, []);

  return (
    <main className="section">
      <p className="kicker">Knowledge base</p>
      <h1>Documents become searchable after processing.</h1>
      <p className="lede">
        PDFs and markdown reports are extracted, cleaned, chunked, embedded and stored with source, page, topic and
        document type. Adding a new PDF here updates the vector index.
      </p>

      <div className="pill-row" style={{ marginBottom: 24 }}>
        <label className="btn primary">
          Upload PDF
          <input
            type="file"
            accept=".pdf,.md,.txt"
            hidden
            onChange={async (event) => {
              const file = event.target.files?.[0];
              if (!file) return;
              setStatus("Ingesting…");
              try {
                const result = await ingestFile(file);
                setStatus(`Processed ${result.documents_processed} document(s), ${result.chunks_added} chunks.`);
                await refresh();
              } catch (err) {
                setStatus(err instanceof Error ? err.message : "Ingest failed");
              }
            }}
          />
        </label>
        <button
          className="btn ghost"
          onClick={async () => {
            const result = await rebuildKnowledge();
            setStatus(`Rebuilt vectors for ${result.documents_processed} documents.`);
          }}
        >
          Rebuild vectors
        </button>
      </div>
      {status && <p className="tiny">{status}</p>}

      <div className="panel" style={{ marginBottom: 24 }}>
        <table className="knowledge-table">
          <thead>
            <tr>
              <th>Document</th>
              <th>Type</th>
              <th>Topic</th>
              <th>Pages</th>
              <th>Chunks</th>
            </tr>
          </thead>
          <tbody>
            {docs.map((doc) => (
              <tr key={doc.id}>
                <td>{doc.name}</td>
                <td>{doc.document_type}</td>
                <td>{doc.topic}</td>
                <td>{doc.pages}</td>
                <td>{doc.chunks}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="panel">
        <h3>Try retrieval</h3>
        <div className="composer-row">
          <input value={query} onChange={(event) => setQuery(event.target.value)} />
          <button
            className="btn primary"
            onClick={async () => setHits(await searchKnowledge(query))}
          >
            Search
          </button>
        </div>
        {hits && <pre className="debug">{JSON.stringify(hits, null, 2)}</pre>}
      </div>
    </main>
  );
}
