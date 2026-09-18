from __future__ import annotations

import re
from pathlib import Path

from fastapi import Header, HTTPException

from app.core.config import get_settings

SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def sanitize_filename(name: str) -> str:
    raw = Path(name or "").name
    cleaned = SAFE_NAME.sub("_", raw).strip("._")
    if not cleaned:
        raise HTTPException(status_code=400, detail="Uploaded file must have a safe file name")
    if len(cleaned) > 180:
        stem = Path(cleaned).stem[:160]
        suffix = Path(cleaned).suffix[:20]
        cleaned = f"{stem}{suffix}"
    return cleaned


def require_admin(x_admin_token: str | None = Header(default=None, alias="X-Admin-Token")) -> None:
    settings = get_settings()
    expected = (settings.admin_api_token or "").strip()
    if not expected:
        raise HTTPException(
            status_code=401,
            detail="Admin endpoints are locked. Set ADMIN_API_TOKEN on the server.",
        )
    if not x_admin_token or x_admin_token.strip() != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing admin token")
