# Deployment

Aaranya is two systems: a static frontend and a Docker API stack. Netlify cannot run Ollama, FastAPI, SQLite, or ChromaDB.

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

Leave **Contains secret values** unchecked. Do not add backend secrets or `VITE_` keys for tokens.

Local `npm run dev` must leave `VITE_API_URL` empty so Vite can proxy `/api` to `http://127.0.0.1:8000`.

## Backend (Docker VM)

On a Linux host with Docker:

```bash
export ADMIN_API_TOKEN=your-long-random-admin-token-here
export FRONTEND_ORIGIN=https://YOUR-NETLIFY-SITE.netlify.app
export CORS_ORIGINS=https://YOUR-NETLIFY-SITE.netlify.app,http://127.0.0.1:5173,http://localhost:5173
docker compose up --build
```

Services:

- `api` — FastAPI, listens on `PORT` (Compose publishes `8000`)
- `ollama` — pulls `OLLAMA_MODEL` (default `llama3.2:3b`) on first start

Volumes:

- `aaranya-data` — SQLite, Chroma, uploaded PDFs
- `ollama-data` — model weights

Put TLS in front of port 8000 (Caddy, nginx, or the cloud load balancer). Then set Netlify `VITE_API_URL` to that HTTPS origin and redeploy the frontend.

Confirm:

- `GET https://YOUR-BACKEND-URL/health` → `{"status":"ok"}`
- `GET https://YOUR-BACKEND-URL/api/health` → `llm_available` true only when the model is loaded

## CORS

The API allow-list is `CORS_ORIGINS` plus `FRONTEND_ORIGIN`. Production does not enable a wildcard Netlify regex unless `CORS_ORIGIN_REGEX` is set. Custom domains must be listed explicitly.

## Not deployed by this repository

There is no live backend URL and no live Netlify URL in git. Hosting-account creation, DNS, TLS, and the first `VITE_API_URL` value are manual.
