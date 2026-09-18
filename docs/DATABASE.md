# Database and vector schema

## SQLite `data/darukaa.sqlite`

Kept for conversations, messages, environmental context, and a document catalog.

Conversations and messages are never mixed across `session_id` values.

## ChromaDB `data/chroma`

Collection: `darukaa_knowledge` (configurable).

Each vector is one chunk, with metadata: document name, source, page, whether the page is a real PDF page, topic, type, checksum, title, authors, URL/DOI, year, origin.

Embeddings are produced by `sentence-transformers` (`all-MiniLM-L6-v2`, 384 dimensions) and stored with the collection. HashingVectorizer is not used in production.

Rebuild with `POST /api/knowledge/rebuild` (admin token) or `python scripts/kb.py rebuild`.
