import { useEffect, useState } from "react";
import { ingestFile, listKnowledge, rebuildKnowledge, searchKnowledge } from "../api";

type Doc = {
  id: number;
  name: string;
  title?: string | null;
  document_type: string;
  topic: string;
  source: string;
  pages: number;
  chunks: number;
};

export function Knowledge() {
  const [docs, setDocs] = useState<Doc[]>([]);
  const [query, setQuery] = useState("low soil organic carbon rainfall cover crops");
  const [hits, setHits] = useState<any>(null);
  const [status, setStatus] = useState<string>("");
  const [token, setToken] = useState(() => sessionStorage.getItem("darukaa_admin_token") || "");

  async function refresh() {
    setDocs(await listKnowledge());
  }

  useEffect(() => {
    refresh().catch((err) => setStatus(String(err)));
  }, []);

  function saveToken(value: string) {
    setToken(value);
    sessionStorage.setItem("darukaa_admin_token", value);
  }

  return (
    <main className="section">
      <p className="kicker">Knowledge base</p>
      <h1>Documents become searchable after processing.</h1>
      <p className="lede">
        Reports are extracted, chunked, and stored with source metadata. Internal syntheses are not original FAO or IPBES papers.
        Upload and rebuild require an admin token.
      </p>

      <label className="tiny">Admin token (stored in this browser session only)</label>
      <input
        type="password"
        value={token}
        onChange={(event) => saveToken(event.target.value)}
        placeholder="ADMIN_API_TOKEN"
        style={{ marginBottom: 16, maxWidth: 360 }}
      />

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
            setStatus("Rebuilding…");
            try {
              const result = await rebuildKnowledge();
              setStatus(`Rebuilt vectors for ${result.documents_processed} documents.`);
            } catch (err) {
              setStatus(err instanceof Error ? err.message : "Rebuild failed");
            }
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
                <td>{doc.title || doc.name}</td>
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
            onClick={async () => {
              try {
                setHits(await searchKnowledge(query));
              } catch (err) {
                setStatus(err instanceof Error ? err.message : "Search failed");
              }
            }}
          >
            Search
          </button>
        </div>
        {hits && <pre className="debug">{JSON.stringify(hits, null, 2)}</pre>}
      </div>
    </main>
  );
}
