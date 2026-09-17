from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from pypdf import PdfReader

from app.core.config import get_settings
from app.services.embeddings import content_checksum, get_embedder
from app.services.memory import connect, init_db

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


def extract_markdown(path: Path) -> tuple[list[tuple[int, str]], int]:
    text = clean_text(path.read_text(encoding="utf-8"))
    if not text:
        return [], 0
    # Approximate pages at ~1800 characters so metadata has page numbers.
    page_size = 1800
    pages: list[tuple[int, str]] = []
    for i in range(0, len(text), page_size):
        pages.append((i // page_size + 1, text[i : i + page_size]))
    return pages, len(pages)


class KnowledgeStore:
    def __init__(self) -> None:
        init_db()
        self.settings = get_settings()
        self.embedder = get_embedder()

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
                       (SELECT COUNT(*) FROM chunks c WHERE c.document_id = d.id) AS chunks
                FROM documents d ORDER BY d.name
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def ingest_path(self, path: Path, document_type: str | None = None, topic: str | None = None) -> dict:
        if not path.exists():
            raise FileNotFoundError(str(path))
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            pages, page_count = extract_pdf(path)
            doc_type = document_type or "pdf_report"
        elif suffix in {".md", ".txt"}:
            pages, page_count = extract_markdown(path)
            doc_type = document_type or "markdown_report"
        else:
            raise ValueError(f"Unsupported file type: {suffix}")

        if not pages:
            raise ValueError(f"Empty document or failed text extraction: {path.name}")

        full_text = "\n\n".join(text for _, text in pages)
        checksum = content_checksum(full_text)
        inferred_topic = topic or infer_topic(full_text)
        chunks: list[tuple[int | None, str]] = []
        for page_num, page_text in pages:
            chunks.extend(
                chunk_page(page_text, page_num, self.settings.chunk_size, self.settings.chunk_overlap)
            )
        if not chunks:
            raise ValueError(f"No chunks produced from {path.name}")

        now = datetime.now(timezone.utc).isoformat()
        with connect() as conn:
            existing = conn.execute("SELECT id, checksum FROM documents WHERE name = ?", (path.name,)).fetchone()
            if existing and existing["checksum"] == checksum:
                return {"name": path.name, "chunks": 0, "skipped": True}
            if existing:
                conn.execute("DELETE FROM chunks WHERE document_id = ?", (existing["id"],))
                conn.execute("DELETE FROM documents WHERE id = ?", (existing["id"],))
            cur = conn.execute(
                """
                INSERT INTO documents (name, source, document_type, topic, pages, checksum, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (path.name, path.name, doc_type, inferred_topic, page_count, checksum, now),
            )
            doc_id = cur.lastrowid
            for index, (page, text) in enumerate(chunks):
                conn.execute(
                    "INSERT INTO chunks (document_id, page, chunk_index, text, topic) VALUES (?, ?, ?, ?, ?)",
                    (doc_id, page, index, text, infer_topic(text, inferred_topic)),
                )
        self.rebuild_vectors()
        return {"name": path.name, "chunks": len(chunks), "skipped": False, "pages": page_count}

    def ingest_directory(self, directory: Path | None = None) -> dict:
        settings = get_settings()
        directory = directory or settings.knowledge_dir
        files: list[Path] = []
        for folder in [settings.pdf_dir, settings.source_dir, directory]:
            if folder.exists():
                files.extend(sorted(folder.glob("*.pdf")))
                files.extend(sorted(folder.glob("*.md")))
                files.extend(sorted(folder.glob("*.txt")))
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
        with connect() as conn:
            rows = conn.execute(
                """
                SELECT c.id, c.page, c.chunk_index, c.text, c.topic,
                       d.name AS document_name, d.source, d.document_type, d.topic AS doc_topic
                FROM chunks c
                JOIN documents d ON d.id = c.document_id
                ORDER BY c.id
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def rebuild_vectors(self) -> None:
        chunks = self.load_chunks()
        settings = get_settings()
        settings.ensure_dirs()
        if not chunks:
            if settings.vector_path.exists():
                settings.vector_path.unlink()
            return
        vectors = self.embedder.encode([row["text"] for row in chunks])
        ids = np.array([row["id"] for row in chunks], dtype=np.int64)
        np.savez_compressed(settings.vector_path, vectors=vectors, ids=ids, backend=np.array(self.embedder.backend))

    def load_vectors(self) -> tuple[np.ndarray, np.ndarray]:
        settings = get_settings()
        if not settings.vector_path.exists():
            self.rebuild_vectors()
        if not settings.vector_path.exists():
            return np.zeros((0, self.embedder.dim), dtype=np.float32), np.zeros((0,), dtype=np.int64)
        payload = np.load(settings.vector_path, allow_pickle=False)
        return payload["vectors"], payload["ids"]


knowledge_store = KnowledgeStore()
