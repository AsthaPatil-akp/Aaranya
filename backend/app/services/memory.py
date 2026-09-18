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

DOCUMENT_COLUMNS = {
    "title": "TEXT",
    "authors": "TEXT",
    "institution": "TEXT",
    "year": "INTEGER",
    "doi": "TEXT",
    "url": "TEXT",
    "origin": "TEXT",
    "source_type": "TEXT",
}

CHUNK_COLUMNS = {
    "page_is_real": "INTEGER NOT NULL DEFAULT 0",
}


class _SqliteSession:
    """Commit on success without closing the process-wide connection."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def __enter__(self) -> sqlite3.Connection:
        return self._conn

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc_type is None:
            self._conn.commit()
        else:
            self._conn.rollback()
        return False


_CONN: sqlite3.Connection | None = None
_SCHEMA_READY = False


def connect() -> _SqliteSession:
    global _CONN, _SCHEMA_READY
    settings = get_settings()
    settings.ensure_dirs()
    if _CONN is None:
        _CONN = sqlite3.connect(str(settings.sqlite_path), check_same_thread=False, timeout=30)
        _CONN.row_factory = sqlite3.Row
        _CONN.execute("PRAGMA foreign_keys = ON")
        try:
            _CONN.execute("PRAGMA journal_mode = WAL")
        except sqlite3.Error:
            pass
    if not _SCHEMA_READY:
        _CONN.executescript(SCHEMA)
        for column, ddl in DOCUMENT_COLUMNS.items():
            _add_column(_CONN, "documents", column, ddl)
        for column, ddl in CHUNK_COLUMNS.items():
            _add_column(_CONN, "chunks", column, ddl)
        _CONN.commit()
        _SCHEMA_READY = True
    return _SqliteSession(_CONN)


def _add_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
        for column, ddl in DOCUMENT_COLUMNS.items():
            _add_column(conn, "documents", column, ddl)
        for column, ddl in CHUNK_COLUMNS.items():
            _add_column(conn, "chunks", column, ddl)


class ConversationStore:
    def __init__(self) -> None:
        init_db()

    def get_or_create(self, session_id: str | None) -> str:
        sid, _context = self.ensure_session(session_id)
        return sid

    def ensure_session(self, session_id: str | None) -> tuple[str, EnvironmentalContext]:
        sid = session_id or str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        with connect() as conn:
            row = conn.execute(
                "SELECT id, context_json FROM conversations WHERE id = ?", (sid,)
            ).fetchone()
            if not row:
                ctx = EnvironmentalContext()
                conn.execute(
                    "INSERT INTO conversations (id, created_at, updated_at, context_json) VALUES (?, ?, ?, ?)",
                    (sid, now, now, ctx.model_dump_json()),
                )
                return sid, ctx
            return sid, EnvironmentalContext.model_validate_json(row["context_json"])

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

    def merge_updates(
        self,
        session_id: str,
        updates: dict[str, Any],
        message: str,
        context: EnvironmentalContext | None = None,
    ) -> EnvironmentalContext:
        if context is None:
            context = self.load_context(session_id)
        context = apply_updates(context, updates, overwrite=looks_like_update(message))
        if message and message not in context.notes:
            snippet = message.strip()[:280]
            if snippet:
                context.notes = (context.notes + [snippet])[-12:]
        self.save_context(session_id, context)
        return context


store = ConversationStore()
