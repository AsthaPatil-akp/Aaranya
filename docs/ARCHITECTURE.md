# Architecture

Darukaa.Earth is split into retrieval, reasoning, conversation, and presentation layers. An optional LLM is a language polisher only.

```
                USER
                 ↓
          CHAT / INPUT UI
                 ↓
         BACKEND API  (/api/chat, /analyze, /knowledge)
                 ↓
      INPUT UNDERSTANDING
                 ↓
   ENVIRONMENTAL DATA EXTRACTION
                 ↓
       CONVERSATION MEMORY (SQLite)
                 ↓
      MISSING DATA CHECK
          ↙          ↘
      Missing       Complete
         ↓             ↓
 Clarifying Q     RAG Retrieval
                       ↓
                Relevance Check
                  ↙          ↘
              Relevant     Not Relevant
                 ↓              ↓
               RAG          Fallback
                 ↓         (OpenAlex or refusal)
                 └──────┬───────┘
                        ↓
             MULTI-METRIC REASONING
                        ↓
              EVIDENCE VALIDATION
                        ↓
             RECOMMENDATION ENGINE
                        ↓
            STRUCTURED RESPONSE
```

## Layers

| Layer | Module | Responsibility |
| --- | --- | --- |
| Presentation | `frontend/` | Chat, JSON input, variables, evidence, metrics |
| API | `backend/app/api/routes.py` | HTTP surface |
| Pipeline | `backend/app/services/pipeline.py` | Orchestrates the flow above |
| Extraction | `extraction.py` | NL + JSON → environmental variables |
| Memory | `memory.py` | Session context; no overwrite unless user updates |
| Ingest | `ingest.py` | PDF/MD extract, clean, chunk, metadata |
| Embeddings | `embeddings.py` | Hashing n-grams by default; ST / OpenAI optional |
| Retrieval | `retrieval.py` | Hybrid cosine + BM25, relevance threshold |
| Reasoning | `reasoning.py` | ≥3-variable relationships, intervention matching |
| Fallback | `fallback.py` | External OpenAlex, labelled separately |
| LLM | `llm.py` | Optional wording polish; cannot add citations |

## Knowledge pipeline

1. **Documents** land in `knowledge/pdfs/` or `knowledge/sources/`.
2. **Text extraction** via pypdf (per page) or markdown paging.
3. **Cleaning** strips nulls and collapsed whitespace.
4. **Chunking** (~900 characters, 140 overlap) keeps page numbers.
5. **Embeddings** stored in `data/vectors.npz`.
6. **Metadata** (name, page, topic, type) stored in SQLite.
7. **Semantic search** hybridises vector cosine and BM25.
8. **Relevance** drops chunks below `RELEVANCE_THRESHOLD`.

Adding a PDF through the UI or `python scripts/kb.py ingest file.pdf` makes it searchable after processing. `rebuild` refreshes the vector file from stored chunks.

## Grounding rules

- Knowledge-base passages are labelled `knowledge_base`.
- OpenAlex records are `external_openalex`.
- Low-scoring hits are `unused_low_relevance` and are not used as proof.
- If nothing relevant is found, the API says so. It does not mint authors, journals, percentages, or page numbers.

## Heuristic profile

Soil health, water stress, habitat condition, biodiversity pressure, and human impact are **AI-derived heuristic assessments**, not validated numerical models. The UI and API both carry that disclaimer.

## Spatial extension

`location.region`, `location.location`, `latitude`, and `longitude` are already on the environmental context model. A future GIS layer can join those fields to spatial datasets without changing the chat contract.
