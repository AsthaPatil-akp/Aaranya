from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
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
    manifest_path: Path = ROOT_DIR / "knowledge" / "manifest.json"

    embedding_backend: str = "sentence-transformers"
    embedding_model: str = "all-MiniLM-L6-v2"
    relevance_threshold: float = 0.42
    weak_kb_threshold: float = 0.52
    retrieval_top_k: int = 8
    llm_evidence_k: int = 5
    chunk_size: int = 900
    chunk_overlap: int = 140

    chroma_path: Path | None = None
    chroma_collection: str = "darukaa_knowledge"

    llm_provider: str = "ollama"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2:3b"
    ollama_timeout_seconds: float = 120
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-3-5-haiku-latest"
    groq_api_key: str = ""
    groq_model: str = "llama-3.1-8b-instant"

    enable_openalex: bool = True
    openalex_mailto: str = "darukaa-prototype@example.org"
    openalex_max_results: int = 8
    openalex_keep: int = 3
    fetch_open_access_text: bool = True

    admin_api_token: str = ""
    history_window: int = 6

    @field_validator(
        "data_dir",
        "knowledge_dir",
        "pdf_dir",
        "source_dir",
        "manifest_path",
        mode="after",
    )
    @classmethod
    def resolve_repo_paths(cls, value: Path) -> Path:
        path = Path(value)
        return path if path.is_absolute() else (ROOT_DIR / path).resolve()

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def sqlite_path(self) -> Path:
        return self.data_dir / "darukaa.sqlite"

    @property
    def resolved_chroma_path(self) -> Path:
        if self.chroma_path:
            path = Path(self.chroma_path)
            return path if path.is_absolute() else ROOT_DIR / path
        return Path(self.data_dir) / "chroma"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.pdf_dir.mkdir(parents=True, exist_ok=True)
        self.source_dir.mkdir(parents=True, exist_ok=True)
        self.resolved_chroma_path.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings
