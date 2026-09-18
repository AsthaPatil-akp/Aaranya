# Deployment

Aaranya is two systems: a static frontend and a FastAPI RAG backend. Netlify cannot run FastAPI, Ollama, SQLite, or ChromaDB.

## Frontend (Netlify)

Connect https://github.com/AsthaPatil-akp/Aaranya.

| Setting | Value |
|---|---|
| Base directory | `frontend` |
| Build command | `npm run build` |
| Publish directory | `dist` |

`netlify.toml` already sets Node 20 and the SPA fallback `/* → /index.html` (200).

Build-time environment variable:

```
VITE_API_URL=https://YOUR-BACKEND-URL
```

Leave **Contains secret values** unchecked. Do not add `GROQ_API_KEY`, `OPENAI_API_KEY`, `ADMIN_API_TOKEN`, or `OLLAMA_*` on Netlify.

Local `npm run dev` must leave `VITE_API_URL` empty so Vite can proxy `/api` to `http://127.0.0.1:8000`.

## Backend — local (Ollama)

```powershell
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Keep `LLM_PROVIDER=ollama` and Ollama running at `http://localhost:11434`.

## Backend — Render Free (hosted LLM)

Ollama does not run on Render Free. Use Groq (free API key from https://console.groq.com) or paid OpenAI.

`render.yaml` targets a Python web service:

- Build: `pip install -r backend/requirements.txt`
- Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- `PYTHONPATH=backend`
- `LLM_PROVIDER=groq`
- `GROQ_API_KEY` set in the Render dashboard (not in git)

Confirm:

- `GET https://YOUR-RENDER-URL/health` → `{"status":"ok"}`
- `GET https://YOUR-RENDER-URL/api/health` → `llm_provider=groq`, `llm_available=true`

Then set Netlify `VITE_API_URL` to that origin (no trailing slash) and trigger a cache-clearing redeploy.

## CORS

Set the exact Netlify origin (no trailing slash):

```
FRONTEND_ORIGIN=https://YOUR-NETLIFY-SITE.netlify.app
CORS_ORIGINS=https://YOUR-NETLIFY-SITE.netlify.app,http://127.0.0.1:5173,http://localhost:5173
```

`render.yaml` also sets `CORS_ORIGIN_REGEX=https://.*\.netlify\.app` for preview URLs.

## Not deployed by this repository

There is no live backend URL until you create the Render service.
