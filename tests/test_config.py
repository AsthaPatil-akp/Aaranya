from pathlib import Path

from app.core.config import Settings


def test_listen_port_prefers_cloud_port(monkeypatch) -> None:
    monkeypatch.setenv("PORT", "10000")
    settings = Settings(_env_file=None, api_port=8000)
    assert settings.listen_port == 10000


def test_listen_port_falls_back_to_api_port(monkeypatch) -> None:
    monkeypatch.delenv("PORT", raising=False)
    settings = Settings(_env_file=None, api_port=8000)
    assert settings.listen_port == 8000


def test_sqlite_and_chroma_paths_are_configurable(tmp_path: Path) -> None:
    sqlite = tmp_path / "db" / "custom.sqlite"
    chroma = tmp_path / "vectors"
    settings = Settings(
        _env_file=None,
        data_dir=tmp_path / "data",
        sqlite_file=sqlite,
        chroma_path=chroma,
    )
    assert settings.sqlite_path == sqlite
    assert settings.resolved_chroma_path == chroma


def test_frontend_origin_is_merged_into_cors(monkeypatch) -> None:
    monkeypatch.delenv("PORT", raising=False)
    settings = Settings(
        _env_file=None,
        cors_origins="http://localhost:5173",
        frontend_origin="https://example.netlify.app/",
    )
    assert settings.cors_origin_list == [
        "http://localhost:5173",
        "https://example.netlify.app",
    ]


def test_production_cors_regex_is_opt_in() -> None:
    settings = Settings(_env_file=None, cors_origin_regex="")
    assert settings.cors_origin_regex == ""
