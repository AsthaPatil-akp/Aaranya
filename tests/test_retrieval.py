from pathlib import Path

from app.core.security import sanitize_filename
from app.services.ingest import chunk_page, clean_text, infer_topic, knowledge_store
from app.services.retrieval import retriever
from app.services.vectorstore import get_chroma


def test_clean_and_chunk():
    text = clean_text("Soil   organic\n\n\ncarbon  ")
    assert "  " not in text
    chunks = chunk_page("word " * 400, 2, 80, 20)
    assert len(chunks) > 1
    assert chunks[0][0] == 2


def test_markdown_pages_are_not_faked():
    chunks = knowledge_store.load_chunks()
    md_chunks = [row for row in chunks if str(row["document_name"]).endswith(".md")]
    assert md_chunks
    assert all(row["page"] in (None, 0) or not row["page_is_real"] for row in md_chunks)


def test_topic_inference():
    topic = infer_topic("pollinator diversity in monoculture landscapes")
    assert topic in {"biodiversity", "land_use"}


def test_chromadb_has_vectors_and_metadata():
    count = get_chroma().count()
    assert count >= 8
    hits = get_chroma().query("ground beetles cover-crop flowers", top_k=4)
    assert hits
    assert hits[0]["document_name"]
    assert hits[0]["text"]


def test_semantic_retrieval_returns_scores_and_sources():
    hits = retriever.search("agroforestry cover crops soil organic carbon rainfall")
    assert hits
    assert hits[0].document_name
    assert hits[0].relevance_score is not None
    assert hits[0].passage
    assert hits[0].evidence_id.startswith("kb-")


def test_filename_sanitization():
    assert ".." not in sanitize_filename("../../secret.pdf")
    assert sanitize_filename("ok_file.pdf") == "ok_file.pdf"
