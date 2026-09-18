from app.models.schemas import ChatRequest, EvidenceItem
from app.services import pipeline
from app.services.fallback import sanitize_openalex_query


def test_retrieval_failure_falls_back(monkeypatch):
    monkeypatch.setattr(pipeline.retriever, "search", lambda query: [])
    monkeypatch.setattr(pipeline, "search_openalex", lambda *args, **kwargs: [])
    result = pipeline.handle_chat(
        ChatRequest(message="Low rainfall, 0.3% soil organic carbon, wheat monoculture in a semi-arid region.")
    )
    assert result.mode == "fallback"
    assert result.knowledge_status == "insufficient_evidence"


def test_low_relevance_chunks_are_not_treated_as_evidence(monkeypatch):
    weak = [
        EvidenceItem(
            evidence_id="kb-weak",
            source="unrelated.pdf",
            document_name="unrelated.pdf",
            page=1,
            topic="other",
            document_type="pdf_report",
            passage="This passage is about accounting software.",
            relevance_score=0.05,
            origin="knowledge_base",
        )
    ]
    monkeypatch.setattr(pipeline.retriever, "search", lambda query: weak)
    monkeypatch.setattr(pipeline.retriever, "split_relevant", lambda items: ([], items))
    monkeypatch.setattr(pipeline, "search_openalex", lambda *args, **kwargs: [])
    result = pipeline.handle_chat(
        ChatRequest(message="Low rainfall, 0.3% soil carbon, monoculture wheat, pH 8.1.")
    )
    assert result.mode == "fallback"
    assert all(item.origin != "knowledge_base" or (item.relevance_score or 0) < 0.2 for item in result.evidence)


def test_openalex_sanitizes_question_marks():
    cleaned = sanitize_openalex_query("How does Kepler-442b affect genomes?")
    assert "?" not in cleaned
    assert "*" not in cleaned
    assert "Kepler" in cleaned
