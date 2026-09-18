# Aaranya — AI Biodiversity Intelligence

Repository: https://github.com/AsthaPatil-akp/Aaranya

An evidence-grounded conversational system that behaves like an **AI environmental scientist**. It retrieves scientific passages from a local knowledge base, optionally adds OpenAlex research, then asks a **free local LLM** (Ollama) to explain the evidence in plain language.

This is not `user question → LLM → generic answer`. No paid OpenAI API key is required.

```
USER
  → FastAPI /api/chat
  → environmental extraction + conversation memory
  → clarification if the site picture is incomplete
  → context-aware query
  → ChromaDB (all-MiniLM-L6-v2) + BM25 rerank
  → relevance filter
  → OpenAlex only if the knowledge base is weak/missing or the user asked for studies
  → rank/filter abstracts or open-access text
  → local Ollama LLM (retrieved evidence in the prompt)
  → claim-level grounding
  → natural answer + separate source lists
```

## What you get

- Chat + optional **Add Land Details** form + structured JSON
- Environmental variable extraction and conversation memory
- Clarifying questions when the profile is incomplete — empty form fields are left unknown, never invented
- PDF/markdown ingest → clean → chunk → embed → Chroma search
- Relevance threshold so weak hits are not treated as evidence
- Multi-metric reasoning (soil × water × land use, and other triples)
- Recommendations with action, mechanism, metrics, time horizon, confidence, sources
- Honest fallback (optional OpenAlex, clearly labelled as **external**)
- Local LLM via Ollama (`llama3.2:3b` by default; `qwen2.5:7b` optional)
- Simple nature-themed web app (cream, forest green, serif headlines)

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and [docs/DATABASE.md](docs/DATABASE.md).

## Local setup (Windows)

### 1. Install Ollama (required for chat)

1. Download Ollama from https://ollama.com/download and install it.
2. Start Ollama (the installer usually starts the background service). On Windows you can also run:

```powershell
ollama serve
```

3. Pull the default model (already downloaded if you used `llama3.2:3b`):

```powershell
ollama pull llama3.2:3b
```

Optional larger model:

```powershell
ollama pull qwen2.5:7b
```

Then set `OLLAMA_MODEL=qwen2.5:7b` in `.env`.

Leave Ollama running. The API talks to `http://localhost:11434`.

**Notes**

- No OpenAI API key is required. Chat uses the local model.
- The first model download needs several GB of disk space.
- RAM/GPU needs depend on the model: `qwen2.5:7b` is heavier; `llama3.2:3b` is lighter.
- Internet is still required for **OpenAlex** external research. Internal knowledge-base answers work offline once the model is downloaded.
- If Ollama is not running, chat returns an error instead of inventing an answer.

### 2. Backend

Python 3.11+ recommended.

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r backend/requirements.txt
copy .env.example .env
```

macOS / Linux:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cp .env.example .env
```

Default LLM settings in `.env`:

```
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2:3b
OLLAMA_TIMEOUT_SECONDS=120
EMBEDDING_BACKEND=sentence-transformers
EMBEDDING_MODEL=all-MiniLM-L6-v2
CHROMA_PATH=./data/chroma
ENABLE_OPENALEX=true
ADMIN_API_TOKEN=dev-admin-token
```

OpenAI is optional only. Do not set `LLM_PROVIDER=openai` unless you want that paid provider.

Set `ADMIN_API_TOKEN` for ingest, rebuild, and conversation lookup.

Seed markdown in `knowledge/sources/` is ingested into ChromaDB (`darukaa_knowledge`) with MiniLM embeddings.

Start the API:

```powershell
cd backend
uvicorn app.main:app --reload --port 8000
```

Health check: http://127.0.0.1:8000/api/health

Confirm `llm_provider=ollama`, `llm_model=llama3.2:3b`, and `llm_available=true` only when Ollama and the model are actually reachable.

### 3. Frontend

```powershell
cd frontend
npm install
npm run test
npm run dev
```

Open http://127.0.0.1:5173 — the Vite dev server proxies `/api` to port 8000.

### 4. Tests

From the repo root, with the virtualenv active:

```powershell
pytest -q
```

Frontend unit tests (optional land-details form, chips, and chat payload):

```powershell
cd frontend
npm test
```

Automated tests mock Ollama over HTTP. They do **not** require a running Ollama server.

Optional live check (requires Ollama + a pulled model):

```powershell
$env:RUN_OLLAMA_INTEGRATION="1"
pytest -q tests/test_ollama.py::test_live_ollama_optional
```

## Adding scientific documents

1. Upload a PDF on **Knowledge Base** in the UI, or
2. Copy a file into `knowledge/pdfs/` and run:

```powershell
python scripts/kb.py ingest path/to/paper.pdf
```

Rebuild the vector index after bulk edits:

```powershell
python scripts/kb.py rebuild
```

Every chunk keeps **document name, page, topic, document type**.

The seed files in `knowledge/sources/` are original Darukaa synthesis reports grounded in public institutional science (FAO, IPBES, IPCC, USDA NRCS, CBD). They are not copies of copyrighted papers. Replace or extend them with your own PDFs for production use.

## Demo script (judges)

1. Open the Intelligence Lab.
2. Enter: `Biodiversity is declining on my farm.` (or open **Add Land Details** and fill only what you know — every field is optional)
3. See targeted clarifying questions (soil carbon, rainfall, land use, …). Empty form fields stay empty.
4. Reply with: `Soil organic carbon is 0.3%, pH 8.1, rainfall is low, soil moisture is low, wheat monoculture, semi-arid region.`
5. Confirm the variable panel stored those values.
6. Inspect **Knowledge base sources** and **External scientific sources**.
7. Read the recommendation, relationships among ≥3 variables, metrics, time horizon, confidence.
8. Ask a follow-up such as `What should I do?` — context is retained.
9. Ask something outside the corpus, e.g. `How does Kepler-442b orbital resonance affect silicon wafer doping in hadal amphipod genomes?`
10. Confirm the system reports **insufficient verified evidence** instead of inventing a paper.
11. In debug view, confirm the RAG prompt sent to Ollama includes INTERNAL vs EXTERNAL evidence.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Status, embeddings, Chroma counts, LLM availability, OpenAlex flag |
| POST | `/api/chat` | Conversational pipeline |
| POST | `/api/chat/stream` | Same pipeline, streamed NDJSON tokens |
| GET | `/api/geocode` | Optional place search for the land-details map (Nominatim) |
| POST | `/api/analyze` | Same pipeline with debug retrieval |
| GET | `/api/conversation/{id}` | Memory + history (admin token) |
| GET | `/api/knowledge` | Document list |
| POST | `/api/knowledge/search` | Raw retrieval |
| POST | `/api/knowledge/ingest` | Upload PDF/MD or ingest directories |
| POST | `/api/knowledge/rebuild` | Rebuild vectors |

### Chat body

```json
{
  "message": "Biodiversity is declining on my farm.",
  "session_id": null,
  "structured": {
    "farm_size": "5 acres",
    "location": "Pune, India",
    "latitude": 18.52,
    "longitude": 73.85,
    "crop": "wheat"
  },
  "structured_json": null,
  "debug": true
}
```

Structured environmental input can be sent as `structured` or `structured_json`. Empty fields are omitted and are not invented.

## Optional land details

In the Intelligence Lab, **Add Land Details** sits beside the demo buttons. It is optional. Users can fill any mix of farm size, location, crop, land-use, soil pH, soil organic carbon, soil moisture, rainfall, temperature, pesticide use, and biodiversity observations.

Location can be typed, searched, or picked on the map. A map click stores latitude and longitude. Entered values appear as editable chips and are merged with the chat message into the same extraction → memory → ChromaDB → OpenAlex → evidence → Ollama → grounding pipeline. There is no separate recommendation path.

If a field is left blank, the chatbot may ask for it later. It must not invent a value.

## Security

- Secrets live in `.env` only. Never the frontend.
- `.gitignore` excludes `.env`, data directories, and virtualenvs.
- Use `.env.example` as the template. It does not contain real secrets.
- Health and chat responses never return API keys or environment variables.

## Design

The interface borrows the cream field, forest green type, serif headlines, lime call-to-action, and photographic nature cards from the supplied environmental / botanical references, without copying brand names or product photography.

## License

Prototype code is provided for the Darukaa.Earth challenge. Seed knowledge reports are original educational syntheses; cited institutions retain their own rights in their publications.
