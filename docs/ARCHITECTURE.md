# Architecture

Darukaa.Earth is a hybrid scientific assistant: internal RAG over ChromaDB, optional OpenAlex evidence, then an LLM that must cite retrieved passages.

```
USER
  → FastAPI /api/chat
  → environmental extraction + SQLite memory
  → clarification if the site picture is incomplete
  → context-aware query
  → ChromaDB (all-MiniLM-L6-v2) + BM25 rerank
  → relevance filter
  → OpenAlex only if KB is weak/missing or the user asked for studies
  → rank/filter external abstracts or open-access text
  → LLM draft
  → claim/evidence validation
  → remove or rewrite unsupported claims
  → grounded user-facing answer + separate source lists
```

The language model is a **local Ollama model** by default (`llama3.2:3b`). It is the author of the recommendation. The rule engine may suggest candidate interventions; it is not the final answer. OpenAI remains an optional paid provider behind `LLM_PROVIDER=openai`.

Internal syntheses are labelled as Darukaa syntheses. They are not original FAO/IPBES papers.
