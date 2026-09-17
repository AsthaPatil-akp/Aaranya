from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Darukaa.Earth"
    app_env: str = "development"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8000"

    data_dir: Path = ROOT_DIR / "data"
    knowledge_dir: Path = ROOT_DIR / "knowledge"
    pdf_dir: Path = ROOT_DIR / "knowledge" / "pdfs"
    source_dir: Path = ROOT_DIR / "knowledge" / "sources"

    embedding_backend: str = "hashing"
    embedding_model: str = "all-MiniLM-L6-v2"
    relevance_threshold: float = 0.28
    retrieval_top_k: int = 6
    chunk_size: int = 900
    chunk_overlap: int = 140

    llm_provider: str = "none"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-3-5-haiku-latest"
    groq_api_key: str = ""
    groq_model: str = "llama-3.1-8b-instant"

    enable_openalex: bool = True
    openalex_mailto: str = "darukaa-prototype@example.org"

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def sqlite_path(self) -> Path:
        return self.data_dir / "darukaa.sqlite"

    @property
    def vector_path(self) -> Path:
        return self.data_dir / "vectors.npz"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.pdf_dir.mkdir(parents=True, exist_ok=True)
        self.source_dir.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings
