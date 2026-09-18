from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TMP = Path(tempfile.mkdtemp(prefix="darukaa-test-"))
os.environ["DATA_DIR"] = str(TMP)
os.environ["CHROMA_PATH"] = str(TMP / "chroma")
os.environ["KNOWLEDGE_DIR"] = str(ROOT / "knowledge")
os.environ["SOURCE_DIR"] = str(ROOT / "knowledge" / "sources")
os.environ["PDF_DIR"] = str(ROOT / "knowledge" / "pdfs")
os.environ["EMBEDDING_BACKEND"] = "sentence-transformers"
os.environ["EMBEDDING_MODEL"] = "all-MiniLM-L6-v2"
os.environ["ENABLE_OPENALEX"] = "false"
os.environ["FETCH_OPEN_ACCESS_TEXT"] = "false"
os.environ["LLM_PROVIDER"] = "ollama"
os.environ["OLLAMA_BASE_URL"] = "http://localhost:11434"
os.environ["OLLAMA_MODEL"] = "llama3.2:3b"
os.environ["ADMIN_API_TOKEN"] = "test-admin"
os.environ["APP_ENV"] = "test"

from app.core.config import get_settings

get_settings.cache_clear()

from app.services.embeddings import get_embedder
from app.services.ingest import knowledge_store
from app.services.llm import RecordingLLM, set_llm_client_override
from app.services.memory import init_db
from app.services.vectorstore import reset_chroma_singleton

recorder = RecordingLLM()
set_llm_client_override(recorder)


def _seed() -> None:
    init_db()
    knowledge_store.ingest_directory(ROOT / "knowledge" / "sources")
    docs, chunks = knowledge_store.stats()
    assert docs >= 8
    assert chunks >= 8


@pytest.fixture(scope="session", autouse=True)
def seed_knowledge() -> None:
    get_embedder.cache_clear()
    reset_chroma_singleton()
    _seed()


@pytest.fixture(autouse=True)
def ensure_knowledge() -> None:
    _docs, chunks = knowledge_store.stats()
    if chunks < 8:
        reset_chroma_singleton()
        _seed()


@pytest.fixture
def llm_recorder() -> RecordingLLM:
    set_llm_client_override(recorder)
    recorder.prompts.clear()
    return recorder
