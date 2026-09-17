# Darukaa.Earth — AI Biodiversity Intelligence

An evidence-grounded conversational system that behaves like an **AI environmental scientist**. It retrieves scientific passages from a local knowledge base, reasons across multiple environmental variables, remembers conversation context, and refuses to invent papers or statistics.

This is not `user question → LLM → generic answer`.

```
USER → extraction → memory → clarification or RAG → relevance check → multi-metric reasoning → structured recommendation
```

## What you get

- Chat + structured JSON input
- Environmental variable extraction and conversation memory
- Clarifying questions when the profile is incomplete
- PDF/markdown ingest → clean → chunk → embed → vector search
- Relevance threshold so weak hits are not treated as evidence
- Multi-metric reasoning (soil × water × land use, and other triples)
- Recommendations with action, mechanism, metrics, time horizon, confidence, sources
- Honest fallback (optional OpenAlex, clearly labelled as **external**)
- Simple nature-themed web app (cream, forest green, serif headlines)

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and [docs/DATABASE.md](docs/DATABASE.md).

## Local setup

### 1. Backend

Python 3.11+ recommended.

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r backend/requirements.txt
copy .env.example .env   # Windows
# cp .env.example .env   # macOS / Linux
```

No API key is required. The reasoning engine is retrieval + scientific rules. Optional LLM keys (OpenAI / Groq / Anthropic) only polish wording; they cannot add sources.

Build PDFs from the seed syntheses (optional but recommended):

```bash
python scripts/build_pdfs.py
python scripts/kb.py ingest
```

If you skip PDF build, markdown sources in `knowledge/sources/` are still ingested on first API start.

Start the API:

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

Health check: http://127.0.0.1:8000/api/health

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://127.0.0.1:5173 — the Vite dev server proxies `/api` to port 8000.

### 3. Tests

From the repo root, with the virtualenv active:

```bash
pytest -q
```

## Adding scientific documents

1. Upload a PDF on **Knowledge Base** in the UI, or
2. Copy a file into `knowledge/pdfs/` and run:

```bash
python scripts/kb.py ingest path/to/paper.pdf
```

Rebuild the vector index after bulk edits:

```bash
python scripts/kb.py rebuild
```

Every chunk keeps **document name, page, topic, document type**.

The seed files in `knowledge/sources/` are original Darukaa synthesis reports grounded in public institutional science (FAO, IPBES, IPCC, USDA NRCS, CBD). They are not copies of copyrighted papers. Replace or extend them with your own PDFs for production use.

## Demo script (judges)

1. Open the Intelligence Lab.
2. Enter: `Biodiversity is declining on my farm.`
3. See targeted clarifying questions (soil carbon, rainfall, land use, …).
4. Reply with: `Soil organic carbon is 0.3%, pH 8.1, rainfall is low, soil moisture is low, wheat monoculture, semi-arid region.`
5. Confirm the variable panel stored those values.
6. Inspect **Scientific evidence used** (document + page + passage).
7. Read the recommendation, relationships among ≥3 variables, metrics, time horizon, confidence.
8. Ask a follow-up such as `What does that mean for pollinators?` — context is retained.
9. Ask something outside the corpus, e.g. `How does Kepler-442b orbital resonance affect silicon wafer doping in hadal amphipod genomes?`
10. Confirm the system reports **insufficient verified evidence** instead of inventing a paper.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Status, document/chunk counts |
| POST | `/api/chat` | Conversational pipeline |
| POST | `/api/analyze` | Same pipeline with debug retrieval |
| GET | `/api/conversation/{id}` | Memory + history |
| GET | `/api/knowledge` | Document list |
| POST | `/api/knowledge/search` | Raw retrieval |
| POST | `/api/knowledge/ingest` | Upload PDF/MD or ingest directories |
| POST | `/api/knowledge/rebuild` | Rebuild vectors |

### Chat body

```json
{
  "message": "Biodiversity is declining on my farm.",
  "session_id": null,
  "structured_json": null,
  "debug": true
}
```

Structured environmental input can be sent as `structured` or `structured_json`.

## Security

- Secrets live in `.env` only. Never the frontend.
- `.gitignore` excludes `.env`, data directories, and virtualenvs.
- Use `.env.example` as the template.

## Design

The interface borrows the cream field, forest green type, serif headlines, lime call-to-action, and photographic nature cards from the supplied environmental / botanical references, without copying brand names or product photography.

## License

Prototype code is provided for the Darukaa.Earth challenge. Seed knowledge reports are original educational syntheses; cited institutions retain their own rights in their publications.
