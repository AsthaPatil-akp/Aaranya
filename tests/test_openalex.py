from app.services.fallback import sanitize_openalex_query, wants_recent_literature
from app.services.evidence import should_search_external
from app.models.schemas import EvidenceItem


def test_question_mark_removed_for_openalex():
    query = "What is the band gap of gallium nitride used in blue LED semiconductors?"
    cleaned = sanitize_openalex_query(query)
    assert "?" not in cleaned
    assert "gallium" in cleaned.lower()


def test_recent_intent_detected():
    assert wants_recent_literature("What is the latest research on cover crops?")
    assert not wants_recent_literature("My soil carbon is 0.3% and rainfall is low.")


def test_external_not_triggered_when_kb_strong():
    strong = [
        EvidenceItem(
            evidence_id="kb-1",
            source="a.md",
            document_name="a.md",
            passage="cover crops",
            relevance_score=0.9,
            origin="knowledge_base",
        )
    ]
    needed, reason = should_search_external("What should I do about low rainfall?", strong, [])
    assert needed is False
    assert reason == "kb_sufficient"


def test_research_questions_skip_clarification():
    from app.services.reasoning import is_research_lookup, needs_clarification
    from app.models.schemas import EnvironmentalContext

    message = "What does recent research say about microplastics affecting soil microbial diversity?"
    assert is_research_lookup(message)
    assert needs_clarification(EnvironmentalContext(), "soil", message) is False


def test_external_triggered_for_research_request():
    strong = [
        EvidenceItem(
            evidence_id="kb-1",
            source="a.md",
            document_name="a.md",
            passage="cover crops",
            relevance_score=0.9,
            origin="knowledge_base",
        )
    ]
    needed, reason = should_search_external("Please find recent studies on cover crops", strong, [])
    assert needed is True
    assert "research" in reason or "recency" in reason


def test_conceptual_followup_skips_openalex_when_kb_accepted():
    strong = [
        EvidenceItem(
            evidence_id="kb-1",
            source="a.md",
            document_name="a.md",
            passage="agroforestry trees crops",
            relevance_score=0.9,
            origin="knowledge_base",
        )
    ]
    needed, reason = should_search_external("What is agroforestry?", strong, [])
    assert needed is False
    assert "conceptual" in reason
