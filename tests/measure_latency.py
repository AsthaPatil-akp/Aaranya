"""Live timing probe for Darukaa chat. Run against a running API, not pytest isolation."""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

API = "http://127.0.0.1:8000"

CASES = [
    (
        "A_kb_only",
        "According to the knowledge base, how do cover crops affect soil organic carbon and soil moisture in dry farmland?",
        None,
    ),
    (
        "B_kb_plus_external",
        "What do recent scientific papers say about cover crops and soil carbon in semi-arid wheat systems?",
        None,
    ),
    (
        "C_followup",
        "What should I do?",
        "My farm is 5 acres in a semi-arid region. I grow wheat as a monoculture. Soil pH is 8.1, organic carbon is 0.3%, soil moisture is low, rainfall is low and irregular, and I've noticed fewer bees and butterflies.",
    ),
    (
        "D_complex_farm",
        (
            "I manage a 10-acre farm in a semi-arid region. The farm is mostly a wheat monoculture. "
            "Soil pH is 8.2, organic carbon is 0.25%, soil moisture is low, rainfall is irregular, "
            "and temperatures are usually around 30–32°C. There are very few flowering plants around "
            "the farm and I have observed a decline in bees, butterflies and other insects over the "
            "last three years. Pesticides are also used during the growing season. What should I do?"
        ),
        None,
    ),
]


def _post_stream(payload: dict) -> tuple[dict, float, float]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{API}/api/chat/stream",
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/x-ndjson"},
        method="POST",
    )
    started = time.perf_counter()
    first_token = None
    final = None
    with urllib.request.urlopen(request, timeout=180) as response:
        for raw in response:
            line = raw.decode("utf-8").strip()
            if not line:
                continue
            event = json.loads(line)
            if event.get("type") == "token" and first_token is None:
                first_token = time.perf_counter()
            if event.get("type") == "error":
                raise RuntimeError(event.get("detail") or "stream error")
            if event.get("type") == "final":
                final = event["response"]
    ended = time.perf_counter()
    if final is None:
        raise RuntimeError("stream ended without a final response")
    client_first_ms = round(((first_token or ended) - started) * 1000, 1)
    client_total_ms = round((ended - started) * 1000, 1)
    return final, client_first_ms, client_total_ms


def _health() -> dict:
    with urllib.request.urlopen(f"{API}/api/health", timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    try:
        health = _health()
    except Exception as exc:
        print(f"API not reachable at {API}: {exc}")
        return 2
    print(json.dumps({"health": health}, indent=2))
    rows = []
    session_id = None
    for name, message, setup in CASES:
        if setup:
            primed, _, _ = _post_stream(
                {"message": setup, "session_id": session_id, "debug": True}
            )
            session_id = primed["session_id"]
        result, client_first, client_total = _post_stream(
            {"message": message, "session_id": session_id, "debug": True}
        )
        session_id = result["session_id"]
        debug = result.get("debug") or {}
        row = {
            "case": name,
            "mode": result.get("mode"),
            "external_search_triggered": debug.get("external_search_triggered"),
            "evidence_selected": debug.get("evidence_selected_for_llm"),
            "environment_extraction_ms": debug.get("environment_extraction_ms"),
            "memory_ms": debug.get("memory_ms"),
            "chroma_retrieval_ms": debug.get("chroma_retrieval_ms"),
            "openalex_ms": debug.get("openalex_ms"),
            "evidence_selection_ms": debug.get("evidence_selection_ms"),
            "prompt_build_ms": debug.get("prompt_build_ms"),
            "llm_first_token_ms": debug.get("llm_first_token_ms"),
            "llm_total_ms": debug.get("llm_total_ms"),
            "grounding_ms": debug.get("grounding_ms"),
            "total_request_ms": debug.get("total_request_ms"),
            "client_first_token_ms": client_first,
            "client_total_ms": client_total,
            "word_count": len((result.get("assistant_message") or "").split()),
        }
        rows.append(row)
        print(json.dumps(row, indent=2))
    print("\nSUMMARY")
    for row in rows:
        print(
            f"{row['case']}: total={row['total_request_ms']}ms "
            f"first_token={row['llm_first_token_ms']}ms "
            f"chroma={row['chroma_retrieval_ms']}ms "
            f"openalex={row['openalex_ms']}ms "
            f"llm={row['llm_total_ms']}ms "
            f"grounding={row['grounding_ms']}ms "
            f"openalex_used={row['external_search_triggered']}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
