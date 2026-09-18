from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pypdf import PdfReader

from app.core.config import get_settings
from app.services.embeddings import content_checksum
from app.services.memory import connect, init_db
from app.services.vectorstore import get_chroma, reset_chroma_singleton

TOPIC_HINTS = {
    "soil": "soil_health",
    "organic carbon": "soil_health",
    "ph": "soil_health",
    "rainfall": "climate",
    "drought": "climate",
    "temperature": "climate",
    "biodiversity": "biodiversity",
    "pollinator": "biodiversity",
    "species": "biodiversity",
    "habitat": "biodiversity",
    "forest": "land_use",
    "monoculture": "land_use",
    "intercrop": "land_use",
    "agroforest": "land_use",
    "pollution": "human_impact",
    "deforestation": "human_impact",
    "urban": "human_impact",
    "fragmentation": "land_use",
}

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)


def clean_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def infer_topic(text: str, fallback: str = "environmental_science") -> str:
    lowered = text.lower()
    scores: dict[str, int] = {}
    for needle, topic in TOPIC_HINTS.items():
        if needle in lowered:
            scores[topic] = scores.get(topic, 0) + 1
    if not scores:
        return fallback
    return max(scores, key=scores.get)


def chunk_page(text: str, page: int | None, chunk_size: int, overlap: int) -> list[tuple[int | None, str]]:
    text = clean_text(text)
    if not text:
        return []
    if len(text) <= chunk_size:
        return [(page, text)]
    chunks: list[tuple[int | None, str]] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + chunk_size)
        piece = text[start:end].strip()
        if piece:
            chunks.append((page, piece))
        if end == len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    raw = match.group(1)
    meta: dict[str, Any] = {}
    for line in raw.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key == "year" and value.isdigit():
            meta[key] = int(value)
        elif value:
            meta[key] = value
    return meta, text[match.end() :]


def load_manifest() -> dict[str, dict[str, Any]]:
    settings = get_settings()
    path = settings.manifest_path
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if isinstance(payload, list):
        return {item.get("file") or item.get("name"): item for item in payload if isinstance(item, dict)}
    if isinstance(payload, dict):
        return payload
    return {}


def extract_pdf(path: Path) -> tuple[list[tuple[int, str]], int]:
    reader = PdfReader(str(path))
    pages: list[tuple[int, str]] = []
    for index, page in enumerate(reader.pages, start=1):
        try:
            extracted = page.extract_text() or ""
        except Exception:
            extracted = ""
        cleaned = clean_text(extracted)
        if cleaned:
            pages.append((index, cleaned))
    return pages, len(reader.pages)


def extract_markdown(path: Path) -> tuple[list[tuple[int | None, str]], int, dict[str, Any]]:
    raw = path.read_text(encoding="utf-8")
    meta, body = parse_frontmatter(raw)
    text = clean_text(body)
    if not text:
        return [], 0, meta
    return [(None, text)], 0, meta


class KnowledgeStore:
    def __init__(self) -> None:
        init_db()
        self.settings = get_settings()
        self._chunks_cache: list[dict] | None = None

    def invalidate_caches(self) -> None:
        self._chunks_cache = None
        try:
            get_chroma()._count_cache = None
        except Exception:
            pass

    def stats(self) -> tuple[int, int]:
        with connect() as conn:
            docs = conn.execute("SELECT COUNT(*) AS n FROM documents").fetchone()["n"]
            chunks = conn.execute("SELECT COUNT(*) AS n FROM chunks").fetchone()["n"]
        return docs, chunks

    def list_documents(self) -> list[dict]:
        with connect() as conn:
            rows = conn.execute(
                """
                SELECT d.id, d.name, d.source, d.document_type, d.topic, d.pages,
                       d.title, d.year, d.doi, d.url, d.origin,
                       (SELECT COUNT(*) FROM chunks c WHERE c.document_id = d.id) AS chunks
                FROM documents d ORDER BY d.name
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def _should_skip_generated_pdf(self, path: Path) -> bool:
        if path.suffix.lower() != ".pdf":
            return False
        twin = self.settings.source_dir / f"{path.stem}.md"
        return twin.exists()

    def ingest_path(self, path: Path, document_type: str | None = None, topic: str | None = None) -> dict:
        if not path.exists():
            raise FileNotFoundError(str(path))
        if self._should_skip_generated_pdf(path):
            return {"name": path.name, "chunks": 0, "skipped": True, "reason": "duplicate_markdown"}

        suffix = path.suffix.lower()
        meta: dict[str, Any] = {}
        page_is_real = False
        if suffix == ".pdf":
            pages, page_count = extract_pdf(path)
            doc_type = document_type or "pdf_report"
            page_is_real = True
        elif suffix in {".md", ".txt"}:
            pages, page_count, meta = extract_markdown(path)
            doc_type = document_type or "markdown_report"
        else:
            raise ValueError(f"Unsupported file type: {suffix}")

        if not pages:
            raise ValueError(f"Empty document or failed text extraction: {path.name}")

        manifest = load_manifest().get(path.name) or load_manifest().get(path.stem) or {}
        meta = {**manifest, **meta}
        full_text = "\n\n".join(text for _, text in pages)
        checksum = content_checksum(full_text)
        inferred_topic = topic or meta.get("topic") or infer_topic(full_text)
        chunks: list[tuple[int | None, str]] = []
        for page_num, page_text in pages:
            chunks.extend(
                chunk_page(page_text, page_num, self.settings.chunk_size, self.settings.chunk_overlap)
            )
        if not chunks:
            raise ValueError(f"No chunks produced from {path.name}")

        now = datetime.now(timezone.utc).isoformat()
        title = meta.get("title") or path.stem.replace("_", " ")
        origin = meta.get("origin") or "knowledge_base"
        with connect() as conn:
            existing = conn.execute(
                "SELECT id, checksum FROM documents WHERE checksum = ? OR name = ?",
                (checksum, path.name),
            ).fetchone()
            if existing and existing["checksum"] == checksum:
                return {"name": path.name, "chunks": 0, "skipped": True, "reason": "checksum"}
            if existing:
                conn.execute("DELETE FROM chunks WHERE document_id = ?", (existing["id"],))
                conn.execute("DELETE FROM documents WHERE id = ?", (existing["id"],))
            cur = conn.execute(
                """
                INSERT INTO documents (
                    name, source, document_type, topic, pages, checksum, created_at,
                    title, authors, institution, year, doi, url, origin, source_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    path.name,
                    meta.get("source") or path.name,
                    doc_type,
                    inferred_topic,
                    page_count,
                    checksum,
                    now,
                    title,
                    meta.get("authors") or meta.get("organization"),
                    meta.get("institution") or meta.get("organization"),
                    meta.get("year"),
                    meta.get("doi"),
                    meta.get("url") or meta.get("related_url"),
                    origin,
                    meta.get("source_type") or "darukaa_synthesis",
                ),
            )
            doc_id = cur.lastrowid
            for index, (page, text) in enumerate(chunks):
                conn.execute(
                    """
                    INSERT INTO chunks (document_id, page, chunk_index, text, topic, page_is_real)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (doc_id, page, index, text, infer_topic(text, inferred_topic), 1 if page_is_real else 0),
                )
        self.rebuild_vectors()
        return {"name": path.name, "chunks": len(chunks), "skipped": False, "pages": page_count}

    def ingest_directory(self, directory: Path | None = None) -> dict:
        settings = get_settings()
        directory = directory or settings.knowledge_dir
        files: list[Path] = []
        for folder in [settings.source_dir, settings.pdf_dir, directory]:
            if folder.exists():
                files.extend(sorted(folder.glob("*.md")))
                files.extend(sorted(folder.glob("*.txt")))
                files.extend(sorted(folder.glob("*.pdf")))
        unique: dict[str, Path] = {}
        for file in files:
            unique[file.name] = file
        processed = 0
        chunks_added = 0
        skipped: list[str] = []
        errors: list[str] = []
        for file in unique.values():
            try:
                result = self.ingest_path(file)
                if result.get("skipped"):
                    skipped.append(file.name)
                else:
                    processed += 1
                    chunks_added += int(result.get("chunks") or 0)
            except Exception as exc:
                errors.append(f"{file.name}: {exc}")
        return {
            "documents_processed": processed,
            "chunks_added": chunks_added,
            "skipped": skipped,
            "errors": errors,
            "rebuilt": True,
        }

    def load_chunks(self) -> list[dict]:
        if self._chunks_cache is not None:
            return self._chunks_cache
        with connect() as conn:
            rows = conn.execute(
                """
                SELECT c.id, c.page, c.chunk_index, c.text, c.topic, c.page_is_real,
                       d.name AS document_name, d.source, d.document_type, d.topic AS doc_topic,
                       d.title, d.authors, d.institution, d.year, d.doi, d.url, d.origin, d.checksum
                FROM chunks c
                JOIN documents d ON d.id = c.document_id
                ORDER BY c.id
                """
            ).fetchall()
        self._chunks_cache = [dict(row) for row in rows]
        return self._chunks_cache

    def rebuild_vectors(self) -> None:
        self.invalidate_caches()
        chunks = self.load_chunks()
        reset_chroma_singleton()
        store = get_chroma()
        store.reset()
        if chunks:
            store.upsert_chunks(chunks)

    def chroma_count(self) -> int:
        try:
            return get_chroma().count()
        except Exception:
            return 0


knowledge_store = KnowledgeStore()
