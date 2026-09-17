from __future__ import annotations

import json

import httpx

from app.core.config import get_settings
from app.models.schemas import EnvironmentalContext, EvidenceItem, RecommendationBlock


SYSTEM = """You are an AI environmental scientist for Darukaa.Earth.
You may polish the explanation of a recommendation that has ALREADY been selected.
You MUST NOT invent research papers, authors, organizations, statistics, percentages, page numbers, or citations.
You MUST NOT add sources that are not in the provided evidence list.
If evidence is weak, say so. Keep the scientific reasoning tied to the user's environmental variables.
Return JSON with keys: action, why_it_works, environmental_relationships.
Do not change the intervention into a vague slogan like 'use sustainable practices'.
"""


def polish_recommendation(
    block: RecommendationBlock,
    context: EnvironmentalContext,
    evidence: list[EvidenceItem],
) -> RecommendationBlock:
    settings = get_settings()
    provider = settings.llm_provider.lower()
    if provider in {"none", "", "off"}:
        return block
    evidence_blob = [
        {
            "document": item.document_name,
            "page": item.page,
            "origin": item.origin,
            "passage": item.passage[:500],
        }
        for item in evidence
        if item.origin == "knowledge_base"
    ]
    user = {
        "existing_recommendation": block.model_dump(),
        "environmental_context": context.known_variables(),
        "allowed_evidence": evidence_blob,
    }
    try:
        text = _complete(provider, json.dumps(user))
        data = json.loads(_extract_json(text))
        block.action = data.get("action") or block.action
        block.why_it_works = data.get("why_it_works") or block.why_it_works
        block.environmental_relationships = (
            data.get("environmental_relationships") or block.environmental_relationships
        )
    except Exception:
        return block
    return block


def _extract_json(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start : end + 1]
    raise ValueError("No JSON in LLM output")


def _complete(provider: str, user: str) -> str:
    settings = get_settings()
    if provider == "openai" and settings.openai_api_key:
        response = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            json={
                "model": settings.openai_model,
                "temperature": 0.2,
                "messages": [
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": user},
                ],
            },
            timeout=40.0,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
    if provider == "groq" and settings.groq_api_key:
        response = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.groq_api_key}"},
            json={
                "model": settings.groq_model,
                "temperature": 0.2,
                "messages": [
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": user},
                ],
            },
            timeout=40.0,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
    if provider == "anthropic" and settings.anthropic_api_key:
        response = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": settings.anthropic_api_key,
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": settings.anthropic_model,
                "max_tokens": 800,
                "system": SYSTEM,
                "messages": [{"role": "user", "content": user}],
            },
            timeout=40.0,
        )
        response.raise_for_status()
        return response.json()["content"][0]["text"]
    raise RuntimeError("LLM provider not configured")
