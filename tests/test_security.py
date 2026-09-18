from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIR_NAMES = {".git", ".venv", "venv", "node_modules", "data", "dist", "__pycache__"}
TEXT_SUFFIXES = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".md",
    ".yml",
    ".yaml",
    ".toml",
    ".txt",
    ".sh",
    ".example",
    ".gitignore",
}


def _iter_text_files():
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if path.name == "test_security.py":
            continue
        if any(part in SKIP_DIR_NAMES for part in path.parts):
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in {"Dockerfile", "docker-compose.yml"}:
            continue
        yield path


def test_no_api_keys_in_frontend_source():
    forbidden = ("sk-", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GROQ_API_KEY")
    for path in (ROOT / "frontend" / "src").rglob("*"):
        if path.suffix not in {".ts", ".tsx", ".js", ".jsx"}:
            continue
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in text, f"{token} found in {path}"


def test_no_vite_secret_variables():
    scanned = list((ROOT / "frontend" / "src").rglob("*"))
    scanned.append(ROOT / "frontend" / ".env.example")
    for path in scanned:
        if not path.is_file():
            continue
        if path.suffix not in {".ts", ".tsx", ".js", ".jsx", ".example"}:
            continue
        text = path.read_text(encoding="utf-8")
        assert "VITE_ADMIN" not in text
        assert "VITE_OPENAI" not in text
        assert "VITE_GROQ" not in text
        assert "VITE_ANTHROPIC" not in text
        assert "VITE_OLLAMA" not in text


def test_docker_compose_interpolates_secrets():
    text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "ADMIN_API_TOKEN: ${ADMIN_API_TOKEN:-}" in text
    assert "OPENAI_API_KEY: ${OPENAI_API_KEY:-}" in text
    assert "sk-" not in text


def test_repo_text_has_no_live_looking_secrets():
    markers = ("sk-" + "live", "sk-" + "proj-", "ghp_", "github_pat_")
    begin = "-----begin " + "private key-----"
    for path in _iter_text_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        lowered = text.lower()
        for token in markers:
            assert token not in lowered, f"{token} found in {path}"
        assert begin not in lowered
