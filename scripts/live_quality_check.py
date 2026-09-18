from __future__ import annotations

import json
import re
from pathlib import Path

import httpx

API = "http://127.0.0.1:8000/api/chat"
OUT = Path("data/live_quality_report.json")

FARM = (
    "I have a 5-acre farm in a semi-arid region. I grow wheat as a monoculture. "
    "My soil pH is 8.1, organic carbon is 0.3%, and soil moisture is low. "
    "Rainfall is low and irregular, with temperatures around 30°C. "
    "I have noticed fewer bees and butterflies over the last few years. "
    "What could be causing the decline in biodiversity, and what should I do?"
)

client = httpx.Client(timeout=180.0)


def post(message: str, session_id: str | None = None) -> dict:
    payload = {"message": message, "debug": True}
    if session_id:
        payload["session_id"] = session_id
    response = client.post(API, json=payload)
    if response.status_code >= 400:
        return {
            "mode": "error",
            "assistant_message": response.text[:1000],
            "knowledge_status": "error",
            "debug": {"http_status": response.status_code},
            "kb_evidence": [],
            "external_evidence": [],
            "claims": [],
            "warnings": [f"HTTP {response.status_code}"],
        }
    return response.json()


def words(text: str) -> int:
    return len(re.findall(r"\S+", text or ""))


def evidence_titles(items: list[dict]) -> list[str]:
    titles = []
    for item in items or []:
        titles.append(item.get("title") or item.get("document_name") or item.get("evidence_id"))
    return titles


farm = post(FARM)
farm_answer = farm.get("assistant_message") or ""
farm_prompt = ((farm.get("debug") or {}).get("llm_prompt") or "")
farm_kb = farm.get("kb_evidence") or []
farm_ext = farm.get("external_evidence") or []
prompt_passages = re.findall(r"passage: (.+)", farm_prompt)
kb_blob = " ".join((item.get("passage") or "") for item in farm_kb).lower()
answer_l = farm_answer.lower()
claims = farm.get("claims") or []
direct_claims = [c for c in claims if c.get("support") == "direct"]
unsupported = [c for c in claims if c.get("support") == "unsupported"]

farm_checks = {
    "mode": farm.get("mode"),
    "knowledge_status": farm.get("knowledge_status"),
    "word_count": words(farm_answer),
    "length_ok": 180 <= words(farm_answer) <= 650,
    "mentions_interaction": any(
        phrase in answer_l
        for phrase in ["interact", "combination", "together", "may contribute", "could be", "consistent with"]
    ),
    "does_not_blame_one_factor_only": "solely due" not in answer_l and "only cause" not in answer_l,
    "has_recommendation": any(
        word in answer_l
        for word in ["cover", "residue", "intercrop", "diversif", "agroforest", "margin", "tillage", "shrub", "flower"]
    ),
    "has_metrics": any(
        word in answer_l
        for word in ["organic carbon", "soil moisture", "pollinator", "habitat", "plant diversity", "species"]
    ),
    "has_time_horizon": any(
        word in answer_l for word in ["season", "year", "immediate", "gradual", "time"]
    ),
    "has_sources_section": "internal knowledge base" in answer_l or "sources / evidence" in answer_l,
    "does_not_pretend_external": (bool(farm_ext) or "external scientific" not in answer_l)
    or "no external" in answer_l,
    "prompt_contains_kb": "INTERNAL KNOWLEDGE BASE" in farm_prompt and "passage:" in farm_prompt,
    "answer_uses_retrieved_idea": any(
        token in answer_l
        for token in ["cover crop", "residue", "living root", "agroforest", "floral", "monoculture", "organic carbon"]
    )
    and any(
        token in kb_blob
        for token in ["cover", "residue", "monoculture", "organic carbon", "pollinator"]
    ),
    "no_invented_doi": not (
        set(re.findall(r"10\.\d{4,}/[^\s]+", farm_answer))
        - {item.get("doi") for item in (farm.get("evidence") or []) if item.get("doi")}
    ),
    "direct_claims": len(direct_claims),
    "unsupported_claims": len(unsupported),
    "external_used": bool(farm_ext),
    "external_search_triggered": (farm.get("debug") or {}).get("external_search_triggered"),
    "new_prompt_loaded": "biodiversity intelligence assistant" in farm_prompt.lower(),
}

# Test A — recent research / OpenAlex
a = post(
    "What does recent research say about microplastics affecting soil microbial diversity in agricultural soils?"
)
a_debug = a.get("debug") or {}
test_a = {
    "mode": a.get("mode"),
    "knowledge_status": a.get("knowledge_status"),
    "external_search_triggered": a_debug.get("external_search_triggered"),
    "external_search_reason": a_debug.get("external_search_reason"),
    "external_count": len(a.get("external_evidence") or []),
    "kb_count": len(a.get("kb_evidence") or []),
    "passed": bool(a_debug.get("external_search_triggered"))
    and (
        bool(a.get("external_evidence"))
        or a.get("knowledge_status") in {"grounded_in_external_evidence", "grounded_in_kb_and_external", "insufficient_evidence"}
    ),
}

# Test B — conversation context
b1 = post("My farm has low soil moisture and low organic carbon.")
b2 = post("What should I do?", session_id=b1.get("session_id"))
b2_prompt = ((b2.get("debug") or {}).get("llm_prompt") or "")
b2_known = b2.get("known_variables") or {}
test_b = {
    "first_mode": b1.get("mode"),
    "second_mode": b2.get("mode"),
    "known": b2_known,
    "moisture_remembered": str(b2_known.get("soil_moisture", "")).lower() == "low"
    or "organic_carbon" in b2_known
    or b2_known.get("soil_organic_carbon_label") == "low",
    "context_in_prompt_or_questions": (
        "moisture" in b2_prompt.lower()
        or "organic carbon" in b2_prompt.lower()
        or (
            b2.get("mode") == "clarification"
            and "moisture" not in " ".join(b2.get("clarifying_questions") or []).lower()
        )
    ),
}
test_b["passed"] = bool(test_b["moisture_remembered"] and test_b["context_in_prompt_or_questions"])

# Test C — clarifying questions
c = post("My biodiversity is decreasing. What should I do?")
c_questions = " ".join(c.get("clarifying_questions") or []).lower()
test_c = {
    "mode": c.get("mode"),
    "questions": c.get("clarifying_questions") or [],
    "generic_advice": any(
        phrase in (c.get("assistant_message") or "").lower()
        for phrase in ["plant trees", "be more sustainable", "go organic"]
    )
    and c.get("mode") != "clarification",
    "passed": c.get("mode") == "clarification" and len(c.get("clarifying_questions") or []) >= 2,
}

# Test D — Kepler unrelated
d = post(
    "How does Kepler-442b orbital resonance affect silicon wafer doping yields in hadal amphipod genomes?"
)
test_d = {
    "mode": d.get("mode"),
    "knowledge_status": d.get("knowledge_status"),
    "message": d.get("assistant_message"),
    "llm_prompt_present": bool((d.get("debug") or {}).get("llm_prompt")),
    "passed": d.get("knowledge_status") == "insufficient_evidence"
    and d.get("mode") in {"fallback", "recommendation", "clarification"},
}

farm_pass = all(
    [
        farm_checks["mode"] == "recommendation",
        farm_checks["new_prompt_loaded"],
        farm_checks["length_ok"],
        farm_checks["mentions_interaction"],
        farm_checks["has_recommendation"],
        farm_checks["has_metrics"],
        farm_checks["has_sources_section"],
        farm_checks["prompt_contains_kb"],
        farm_checks["answer_uses_retrieved_idea"],
        farm_checks["no_invented_doi"],
        farm.get("knowledge_status")
        in {"grounded_in_knowledge_base", "grounded_in_kb_and_external"},
    ]
)

report = {
    "farm": {
        "passed": farm_pass,
        "checks": farm_checks,
        "assistant_message": farm_answer,
        "kb_titles": evidence_titles(farm_kb),
        "kb_passages": [
            {
                "id": item.get("evidence_id"),
                "title": item.get("title") or item.get("document_name"),
                "passage": (item.get("passage") or "")[:500],
                "score": item.get("relevance_score"),
            }
            for item in farm_kb
        ],
        "external_titles": evidence_titles(farm_ext),
        "evidence_in_prompt_preview": farm_prompt[farm_prompt.find("INTERNAL KNOWLEDGE BASE") : farm_prompt.find("INTERNAL KNOWLEDGE BASE") + 2500]
        if "INTERNAL KNOWLEDGE BASE" in farm_prompt
        else farm_prompt[:1500],
        "claims": claims,
        "warnings": farm.get("warnings") or [],
        "source_types": farm.get("source_types") or [],
    },
    "test_a": {**test_a, "assistant_message": a.get("assistant_message"), "external": evidence_titles(a.get("external_evidence") or [])},
    "test_b": {**test_b, "second_message": b2.get("assistant_message")},
    "test_c": {**test_c, "assistant_message": c.get("assistant_message")},
    "test_d": test_d,
}

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps({k: (v.get("passed") if isinstance(v, dict) and "passed" in v else v) for k, v in {
    "farm_passed": report["farm"]["passed"],
    "farm_words": farm_checks["word_count"],
    "farm_status": farm_checks["knowledge_status"],
    "farm_checks": farm_checks,
    "test_a": test_a,
    "test_b_passed": test_b["passed"],
    "test_c_passed": test_c["passed"],
    "test_d_passed": test_d["passed"],
}.items()}, indent=2))
print("WROTE", OUT)
