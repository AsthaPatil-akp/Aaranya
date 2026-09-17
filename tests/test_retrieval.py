from app.services.ingest import clean_text, chunk_page, infer_topic
from app.services.retrieval import retriever


def test_clean_and_chunk():
    text = clean_text("Soil   organic\n\n\ncarbon  ")
    assert "  " not in text
    chunks = chunk_page("word " * 400, 2, 80, 20)
    assert len(chunks) > 1
    assert chunks[0][0] == 2


def test_topic_inference():
    assert infer_topic("pollinator diversity in monoculture landscapes") == "biodiversity" or infer_topic(
        "pollinator diversity in monoculture landscapes"
    ) in {"biodiversity", "land_use"}


def test_retrieval_returns_scores_and_sources():
    hits = retriever.search("agroforestry cover crops soil organic carbon rainfall monoculture")
    assert hits
    assert hits[0].document_name
    assert hits[0].relevance_score is not None
    assert hits[0].passage
