from __future__ import annotations

import os
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="darukaa-test-"))
os.environ["DATA_DIR"] = str(TMP)
os.environ["EMBEDDING_BACKEND"] = "hashing"
os.environ["ENABLE_OPENALEX"] = "false"
os.environ["LLM_PROVIDER"] = "none"
os.environ["APP_ENV"] = "test"

import pytest

from app.core.config import get_settings

get_settings.cache_clear()

from app.services.ingest import knowledge_store
from app.services.memory import init_db

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session", autouse=True)
def seed_knowledge() -> None:
    init_db()
    knowledge_store.ingest_directory(ROOT / "knowledge" / "sources")
    docs, chunks = knowledge_store.stats()
    assert docs >= 8
    assert chunks >= 8
