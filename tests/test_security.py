from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_no_api_keys_in_frontend_source():
    forbidden = ("sk-", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GROQ_API_KEY")
    for path in (ROOT / "frontend" / "src").rglob("*"):
        if path.suffix not in {".ts", ".tsx", ".js", ".jsx"}:
            continue
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in text, f"{token} found in {path}"
