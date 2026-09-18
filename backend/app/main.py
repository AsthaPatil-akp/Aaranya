from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.core.config import get_settings
from app.services.ingest import knowledge_store
from app.services.llm import warm_ollama
from app.services.memory import init_db
from app.services.retrieval import retriever

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    docs, chunks = knowledge_store.stats()
    if settings.uses_vector_index:
        from app.services.embeddings import get_embedder
        from app.services.vectorstore import get_chroma

        get_embedder()
        try:
            vectors = get_chroma().count()
        except Exception:
            vectors = 0
        if chunks == 0 or vectors == 0:
            knowledge_store.ingest_directory()
    elif chunks == 0:
        knowledge_store.ingest_directory()
    try:
        retriever.warmup()
    except Exception:
        pass
    if settings.app_env != "test":
        warm_ollama()
    yield


app = FastAPI(
    title="Darukaa.Earth Biodiversity Intelligence",
    description="Evidence-grounded environmental reasoning API with RAG, conversation memory, and multi-metric analysis.",
    version="1.0.0",
    lifespan=lifespan,
)

origins = settings.cors_origin_list or ["http://localhost:5173"]
if settings.app_env == "development" and "*" not in origins:
    for extra in ("http://127.0.0.1:5173", "http://localhost:8000"):
        if extra not in origins:
            origins.append(extra)
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=settings.cors_origin_regex or None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


@app.get("/health")
def liveness() -> dict[str, str]:
    return {"status": "ok"}


frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if not frontend_dist.exists():
    frontend_dist = Path(__file__).resolve().parents[3] / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")


def run() -> None:
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.listen_port,
        reload=settings.app_env == "development",
        proxy_headers=True,
        forwarded_allow_ips="*",
    )


if __name__ == "__main__":
    run()
