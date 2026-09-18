# Database and vector schema

## SQLite

Path: `SQLITE_PATH` or `{DATA_DIR}/darukaa.sqlite` (Docker: `/data/darukaa.sqlite`).

| Table | Purpose |
|---|---|
| `conversations` | `id` (session), timestamps, `context_json` |
| `messages` | chat turns keyed by `session_id` |
| `documents` | ingested file catalog and bibliographic metadata |
| `chunks` | chunk text, page, `page_is_real` |

Conversations are never mixed across `session_id` values. WAL is enabled when SQLite allows it.

## ChromaDB

Path: `CHROMA_PATH` or `{DATA_DIR}/chroma`. Collection: `CHROMA_COLLECTION` (default `darukaa_knowledge`).

Each embedding is one chunk with metadata: document name, source, page, `page_is_real`, topic, document type, checksum, title, authors, URL, DOI, year, origin.

Embeddings: `sentence-transformers` `all-MiniLM-L6-v2`, 384 dimensions, cosine space.

Rebuild with `POST /api/knowledge/rebuild` (`X-Admin-Token`) or `python scripts/kb.py rebuild`.

Runtime files under `data/` are gitignored. Seed Markdown under `knowledge/sources/` is committed.
