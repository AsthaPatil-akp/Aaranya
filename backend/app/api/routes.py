from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile
from pathlib import Path

from app.core.config import get_settings
from app.models.schemas import ChatRequest, ChatResponse, DocumentInfo, HealthResponse, IngestResponse
from app.services.ingest import knowledge_store
from app.services.memory import store
from app.services.pipeline import handle_chat
from app.services.retrieval import retriever

router = APIRouter(prefix="/api")


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    docs, chunks = knowledge_store.stats()
    return HealthResponse(
        status="ok",
        app=settings.app_name,
        documents=docs,
        chunks=chunks,
        embedding_backend=settings.embedding_backend,
        llm_provider=settings.llm_provider,
        openalex_enabled=settings.enable_openalex,
    )


@router.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest) -> ChatResponse:
    try:
        return handle_chat(payload)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Chat pipeline failed: {exc}") from exc


@router.post("/analyze", response_model=ChatResponse)
def analyze(payload: ChatRequest) -> ChatResponse:
    if not payload.message:
        payload.message = "Please analyse this environmental profile and recommend an evidence-supported intervention."
    payload.debug = True
    return handle_chat(payload)


@router.get("/conversation/{session_id}")
def conversation(session_id: str) -> dict:
    return {
        "session_id": session_id,
        "context": store.load_context(session_id).model_dump(),
        "history": store.history(session_id),
    }


@router.get("/knowledge", response_model=list[DocumentInfo])
def list_knowledge() -> list[DocumentInfo]:
    return [DocumentInfo(**row) for row in knowledge_store.list_documents()]


@router.post("/knowledge/search")
def search_knowledge(payload: dict) -> dict:
    query = str(payload.get("query") or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="query is required")
    hits = retriever.search(query)
    accepted, rejected = retriever.split_relevant(hits)
    return {
        "query": query,
        "accepted": [item.model_dump() for item in accepted],
        "rejected": [item.model_dump() for item in rejected],
    }


@router.post("/knowledge/ingest", response_model=IngestResponse)
async def ingest(file: UploadFile | None = File(default=None), rebuild: bool = False) -> IngestResponse:
    settings = get_settings()
    if file is not None:
        if not file.filename:
            raise HTTPException(status_code=400, detail="Uploaded file must have a name")
        suffix = Path(file.filename).suffix.lower()
        if suffix not in {".pdf", ".md", ".txt"}:
            raise HTTPException(status_code=400, detail="Only PDF, Markdown, and text files are supported")
        target = settings.pdf_dir / file.filename if suffix == ".pdf" else settings.source_dir / file.filename
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
                skipped=[file.filename] if result.get("skipped") else [],
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
def rebuild() -> IngestResponse:
    knowledge_store.rebuild_vectors()
    docs, chunks = knowledge_store.stats()
    return IngestResponse(documents_processed=docs, chunks_added=chunks, rebuilt=True)
