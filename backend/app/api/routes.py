from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pathlib import Path
import json

from app.core.config import get_settings
from app.core.security import require_admin, sanitize_filename
from app.models.schemas import (
    ChatRequest,
    ChatResponse,
    DocumentInfo,
    HealthResponse,
    IngestResponse,
    SearchRequest,
)
from app.services.geocode import search_places
from app.services.ingest import knowledge_store
from app.services.llm import configured_llm_model, llm_is_available, llm_is_configured
from app.services.memory import store
from app.services.pipeline import handle_chat, handle_chat_stream
from app.services.retrieval import retriever

router = APIRouter(prefix="/api")


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    docs, chunks = knowledge_store.stats()
    if settings.uses_vector_index:
        from app.services.embeddings import get_embedder
        from app.services.vectorstore import get_chroma

        embedder = get_embedder()
        try:
            vector_count = get_chroma().count()
        except Exception:
            vector_count = 0
        embedding_backend = embedder.backend
        embedding_model = embedder.model_name
        embedding_dimension = embedder.dim
        vector_database = "chromadb"
        collection = settings.chroma_collection
    else:
        vector_count = chunks
        embedding_backend = "none"
        embedding_model = ""
        embedding_dimension = 0
        vector_database = "bm25"
        collection = "sqlite-chunks"
    return HealthResponse(
        status="ok",
        app=settings.app_name,
        documents=docs,
        chunks=chunks,
        embedding_backend=embedding_backend,
        embedding_model=embedding_model,
        embedding_dimension=embedding_dimension,
        vector_database=vector_database,
        collection=collection,
        vector_count=vector_count,
        llm_provider=settings.llm_provider,
        llm_model=configured_llm_model(),
        llm_configured=llm_is_configured(),
        llm_available=llm_is_available(),
        openalex_enabled=settings.enable_openalex,
    )


@router.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest) -> ChatResponse:
    return handle_chat(payload)


@router.post("/chat/stream")
def chat_stream(payload: ChatRequest) -> StreamingResponse:
    def events():
        try:
            for event in handle_chat_stream(payload):
                yield json.dumps(event, ensure_ascii=True) + "\n"
        except HTTPException as exc:
            yield json.dumps({"type": "error", "detail": exc.detail}, ensure_ascii=True) + "\n"
        except Exception:
            yield json.dumps(
                {"type": "error", "detail": "The language model could not complete this request. Please try again."},
                ensure_ascii=True,
            ) + "\n"

    return StreamingResponse(
        events(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/geocode")
def geocode(q: str = "") -> list[dict]:
    return search_places(q)


@router.post("/analyze", response_model=ChatResponse)
def analyze(payload: ChatRequest) -> ChatResponse:
    if not payload.message:
        payload.message = "Please analyse this environmental profile and recommend an evidence-supported intervention."
    payload.debug = True
    return handle_chat(payload)


@router.get("/conversation/{session_id}")
def conversation(session_id: str, _: None = Depends(require_admin)) -> dict:
    return {
        "session_id": session_id,
        "context": store.load_context(session_id).model_dump(),
        "history": store.history(session_id),
    }


@router.get("/knowledge", response_model=list[DocumentInfo])
def list_knowledge() -> list[DocumentInfo]:
    rows = []
    for row in knowledge_store.list_documents():
        rows.append(DocumentInfo(**{k: row.get(k) for k in DocumentInfo.model_fields}))
    return rows


@router.post("/knowledge/search")
def search_knowledge(payload: SearchRequest) -> dict:
    hits = retriever.search(payload.query)
    accepted, rejected = retriever.split_relevant(hits)
    return {
        "query": payload.query,
        "accepted": [item.model_dump() for item in accepted],
        "rejected": [item.model_dump() for item in rejected],
    }


@router.post("/knowledge/ingest", response_model=IngestResponse)
async def ingest(
    file: UploadFile | None = File(default=None),
    rebuild: bool = False,
    _: None = Depends(require_admin),
) -> IngestResponse:
    settings = get_settings()
    if file is not None:
        if not file.filename:
            raise HTTPException(status_code=400, detail="Uploaded file must have a name")
        filename = sanitize_filename(file.filename)
        suffix = Path(filename).suffix.lower()
        if suffix not in {".pdf", ".md", ".txt"}:
            raise HTTPException(status_code=400, detail="Only PDF, Markdown, and text files are supported")
        target = settings.pdf_dir / filename if suffix == ".pdf" else settings.source_dir / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")
        target.write_bytes(content)
        try:
            result = knowledge_store.ingest_path(target)
            return IngestResponse(
                documents_processed=0 if result.get("skipped") else 1,
                chunks_added=int(result.get("chunks") or 0),
                skipped=[filename] if result.get("skipped") else [],
                rebuilt=True,
            )
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"Ingest failed: {exc}") from exc
    if rebuild:
        knowledge_store.rebuild_vectors()
        docs, chunks = knowledge_store.stats()
        return IngestResponse(documents_processed=docs, chunks_added=chunks, rebuilt=True)
    result = knowledge_store.ingest_directory()
    return IngestResponse(**result)


@router.post("/knowledge/rebuild", response_model=IngestResponse)
def rebuild(_: None = Depends(require_admin)) -> IngestResponse:
    knowledge_store.rebuild_vectors()
    docs, chunks = knowledge_store.stats()
    return IngestResponse(documents_processed=docs, chunks_added=chunks, rebuilt=True)
