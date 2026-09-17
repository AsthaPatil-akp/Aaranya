from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from app.core.config import get_settings
from app.models.schemas import EnvironmentalContext
from app.services.extraction import apply_updates, looks_like_update

SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    context_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(session_id) REFERENCES conversations(id)
);
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    source TEXT NOT NULL,
    document_type TEXT NOT NULL,
    topic TEXT NOT NULL,
    pages INTEGER NOT NULL DEFAULT 0,
    checksum TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    page INTEGER,
    chunk_index INTEGER NOT NULL,
    text TEXT NOT NULL,
    topic TEXT,
    FOREIGN KEY(document_id) REFERENCES documents(id)
);
"""


def connect() -> sqlite3.Connection:
    settings = get_settings()
    settings.ensure_dirs()
    conn = sqlite3.connect(settings.sqlite_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


class ConversationStore:
    def __init__(self) -> None:
        init_db()

    def get_or_create(self, session_id: str | None) -> str:
        sid = session_id or str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        with connect() as conn:
            row = conn.execute("SELECT id FROM conversations WHERE id = ?", (sid,)).fetchone()
            if not row:
                ctx = EnvironmentalContext().model_dump_json()
                conn.execute(
                    "INSERT INTO conversations (id, created_at, updated_at, context_json) VALUES (?, ?, ?, ?)",
                    (sid, now, now, ctx),
                )
        return sid

    def load_context(self, session_id: str) -> EnvironmentalContext:
        with connect() as conn:
            row = conn.execute(
                "SELECT context_json FROM conversations WHERE id = ?", (session_id,)
            ).fetchone()
        if not row:
            return EnvironmentalContext()
        return EnvironmentalContext.model_validate_json(row["context_json"])

    def save_context(self, session_id: str, context: EnvironmentalContext) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with connect() as conn:
            conn.execute(
                "UPDATE conversations SET context_json = ?, updated_at = ? WHERE id = ?",
                (context.model_dump_json(), now, session_id),
            )

    def add_message(self, session_id: str, role: str, content: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with connect() as conn:
            conn.execute(
                "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                (session_id, role, content, now),
            )

    def history(self, session_id: str, limit: int = 20) -> list[dict[str, Any]]:
        with connect() as conn:
            rows = conn.execute(
                "SELECT role, content, created_at FROM messages WHERE session_id = ? ORDER BY id DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def merge_updates(self, session_id: str, updates: dict[str, Any], message: str) -> EnvironmentalContext:
        context = self.load_context(session_id)
        context = apply_updates(context, updates, overwrite=looks_like_update(message))
        if message and message not in context.notes:
            snippet = message.strip()[:280]
            if snippet:
                context.notes = (context.notes + [snippet])[-12:]
        self.save_context(session_id, context)
        return context


store = ConversationStore()
