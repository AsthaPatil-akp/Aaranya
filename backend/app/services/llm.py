from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Protocol

import httpx

from app.core.config import get_settings
from app.models.schemas import (
    ClaimEvidenceLink,
    EnvironmentalContext,
    EvidenceItem,
    ImpactedMetric,
    RecommendationBlock,
    RecommendationItem,
    TimeHorizon,
)
from app.services.prompting import (
    ANSWER_EXPAND_SYSTEM,
    SYSTEM_PROMPT,
    answer_length_band,
    build_expansion_prompt,
    build_user_prompt,
    complete_recommendation,
    compose_user_facing_answer,
    dedupe_recommendations,
    ensure_grounded_sources,
    ensure_material_variables,
    is_conceptual_question,
    filter_evidence_for_answer,
    mechanism_allowed,
    needs_answer_expansion,
    predict_budget,
    sanitize_time_horizon,
    soften_metrics,
    split_recommendation_text,
    word_count,
)

LOGGER = logging.getLogger("darukaa.llm")
_UNSET = object()
_override: object = _UNSET
_probe_cache: tuple[float, bool, str] = (0.0, False, "")
_ollama_http: httpx.Client | None = None
_ollama_provider: "OllamaProvider | None" = None


def get_ollama_http() -> httpx.Client:
    global _ollama_http
    if _ollama_http is None:
        settings = get_settings()
        _ollama_http = httpx.Client(
            base_url=settings.ollama_base_url.rstrip("/"),
            timeout=settings.ollama_timeout_seconds,
            headers={"Content-Type": "application/json"},
        )
    return _ollama_http


class LLMUnavailable(Exception):
    def __init__(self, message: str, status_code: int = 503) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class LLMProvider(Protocol):
    provider: str
    model: str

    def complete(self, system: str, user: str, **kwargs: Any) -> str: ...


LLMClient = LLMProvider


class OllamaProvider:
    provider = "ollama"

    def __init__(self) -> None:
        settings = get_settings()
        self.model = settings.ollama_model
        self.base_url = settings.ollama_base_url.rstrip("/")
        self.timeout = settings.ollama_timeout_seconds
        self._client = get_ollama_http()

    def _payload(
        self,
        system: str,
        user: str,
        *,
        json_mode: bool,
        temperature: float,
        num_predict: int,
        stream: bool,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "stream": stream,
            "keep_alive": "30m",
            "options": {
                "temperature": temperature,
                "num_ctx": 4096,
                "num_predict": num_predict,
            },
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if json_mode:
            payload["format"] = "json"
        return payload

    def complete(
        self,
        system: str,
        user: str,
        *,
        json_mode: bool = True,
        temperature: float = 0.2,
        num_predict: int = 980,
        **_kwargs: Any,
    ) -> str:
        payload = self._payload(
            system,
            user,
            json_mode=json_mode,
            temperature=temperature,
            num_predict=num_predict,
            stream=False,
        )
        try:
            response = self._client.post("/api/chat", json=payload, timeout=self.timeout)
        except httpx.ConnectError as exc:
            raise LLMUnavailable(
                "The local AI model is not running. Please start Ollama and make sure the configured model is installed."
            ) from exc
        except httpx.TimeoutException as exc:
            raise LLMUnavailable(
                "The local AI model took too long to respond. Try again, or use a smaller model such as llama3.2:3b.",
                status_code=504,
            ) from exc
        except httpx.HTTPError as exc:
            raise LLMUnavailable("The local AI model could not be reached.") from exc

        if response.status_code == 404:
            raise LLMUnavailable(
                f"The configured model '{self.model}' is not installed. Run: ollama pull {self.model}"
            )
        if response.status_code >= 400:
            detail = _safe_ollama_error(response)
            if "not found" in detail.lower():
                raise LLMUnavailable(
                    f"The configured model '{self.model}' is not installed. Run: ollama pull {self.model}"
                )
            LOGGER.warning("Ollama HTTP %s: %s", response.status_code, detail[:300])
            raise LLMUnavailable("The local AI model could not complete this request.")

        data = response.json()
        content = ((data.get("message") or {}).get("content")) or data.get("response") or ""
        if not str(content).strip():
            raise LLMUnavailable("The local AI model returned an empty response.")
        return str(content)

    def stream(
        self,
        system: str,
        user: str,
        *,
        json_mode: bool = False,
        temperature: float = 0.3,
        num_predict: int = 980,
        **_kwargs: Any,
    ):
        payload = self._payload(
            system,
            user,
            json_mode=json_mode,
            temperature=temperature,
            num_predict=num_predict,
            stream=True,
        )
        try:
            with self._client.stream("POST", "/api/chat", json=payload, timeout=self.timeout) as response:
                if response.status_code == 404:
                    raise LLMUnavailable(
                        f"The configured model '{self.model}' is not installed. Run: ollama pull {self.model}"
                    )
                if response.status_code >= 400:
                    detail = response.read().decode("utf-8", errors="ignore")[:300]
                    LOGGER.warning("Ollama HTTP %s: %s", response.status_code, detail)
                    raise LLMUnavailable("The local AI model could not complete this request.")
                for line in response.iter_lines():
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    piece = ((data.get("message") or {}).get("content")) or data.get("response") or ""
                    if piece:
                        yield str(piece)
                    if data.get("done"):
                        break
        except LLMUnavailable:
            raise
        except httpx.ConnectError as exc:
            raise LLMUnavailable(
                "The local AI model is not running. Please start Ollama and make sure the configured model is installed."
            ) from exc
        except httpx.TimeoutException as exc:
            raise LLMUnavailable(
                "The local AI model took too long to respond. Try again, or use a smaller model such as llama3.2:3b.",
                status_code=504,
            ) from exc
        except httpx.HTTPError as exc:
            raise LLMUnavailable("The local AI model could not be reached.") from exc


OllamaClient = OllamaProvider


class OpenAICompatibleProvider:
    """OpenAI Chat Completions API, including Groq's compatible endpoint."""

    provider = "openai"

    def __init__(
        self,
        *,
        model: str,
        api_key: str,
        base_url: str,
        label: str,
        provider: str,
    ) -> None:
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.label = label
        self.provider = provider
        if not self.api_key:
            raise LLMUnavailable(f"{self.label} is selected but the API key is not set.")

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def _http(self) -> httpx.Client:
        client = getattr(self, "_client", None)
        if client is None:
            self._client = httpx.Client(timeout=90.0)
        return self._client

    def _payload(
        self,
        system: str,
        user: str,
        *,
        json_mode: bool,
        temperature: float,
        stream: bool,
        num_predict: int | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "temperature": temperature,
            "stream": stream,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        if num_predict:
            payload["max_tokens"] = int(num_predict)
        return payload

    def complete(
        self,
        system: str,
        user: str,
        *,
        json_mode: bool = True,
        temperature: float = 0.2,
        **kwargs: Any,
    ) -> str:
        try:
            response = self._http().post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=self._payload(
                    system,
                    user,
                    json_mode=json_mode,
                    temperature=temperature,
                    stream=False,
                    num_predict=kwargs.get("num_predict"),
                ),
            )
        except httpx.HTTPError as exc:
            raise LLMUnavailable(f"The {self.label} provider could not be reached.") from exc
        if response.status_code >= 400:
            raise LLMUnavailable(f"The {self.label} provider rejected the request.")
        return response.json()["choices"][0]["message"]["content"]

    def stream(
        self,
        system: str,
        user: str,
        *,
        json_mode: bool = False,
        temperature: float = 0.3,
        **kwargs: Any,
    ):
        try:
            with self._http().stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=self._payload(
                    system,
                    user,
                    json_mode=json_mode,
                    temperature=temperature,
                    stream=True,
                    num_predict=kwargs.get("num_predict"),
                ),
            ) as response:
                if response.status_code >= 400:
                    response.read()
                    raise LLMUnavailable(f"The {self.label} provider rejected the request.")
                for line in response.iter_lines():
                    if not line:
                        continue
                    if line.startswith("data: "):
                        line = line[6:]
                    if line.strip() == "[DONE]":
                        break
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    delta = ((data.get("choices") or [{}])[0].get("delta") or {}).get("content") or ""
                    if delta:
                        yield str(delta)
        except LLMUnavailable:
            raise
        except httpx.HTTPError as exc:
            raise LLMUnavailable(f"The {self.label} provider could not be reached.") from exc


class OpenAIProvider(OpenAICompatibleProvider):
    provider = "openai"

    def __init__(self) -> None:
        settings = get_settings()
        super().__init__(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            base_url="https://api.openai.com/v1",
            label="OpenAI",
            provider="openai",
        )


class GroqProvider(OpenAICompatibleProvider):
    provider = "groq"

    def __init__(self) -> None:
        settings = get_settings()
        super().__init__(
            model=settings.groq_model,
            api_key=settings.groq_api_key,
            base_url="https://api.groq.com/openai/v1",
            label="Groq",
            provider="groq",
        )


OpenAIClient = OpenAIProvider


class RecordingLLM:
    """Test double that records the prompt and returns grounded JSON."""

    provider = "test"
    model = "recorder"

    def __init__(self, responder=None) -> None:
        self.prompts: list[str] = []
        self.systems: list[str] = []
        self.responder = responder

    def complete(self, system: str, user: str, **kwargs: Any) -> str:
        self.systems.append(system)
        self.prompts.append(user)
        if kwargs.get("json_mode") is False:
            if self.responder:
                return self.responder(system, user)
            return (
                "Based on the conditions you described, several factors may be interacting. "
                "Low soil carbon and low rainfall can interact, and simplified wheat land use may reduce floral resources for pollinators. "
                "Drought-tolerant cover crops and residue can help rebuild soil function where rainfall is low. "
                "Widely spaced native shrubs can add habitat without a dense plantation. "
                "Impacted metrics these changes could affect: soil organic carbon; soil moisture; habitat diversity; pollinators. "
                "These metrics are potentially affected rather than guaranteed to improve. "
                "No specific timeframe is supported by the retrieved evidence beyond a gradual, multi-year soil response. "
                "Sources / Evidence\n"
                "- Soil Organic Carbon, Soil pH, Moisture and Below-Ground Biodiversity\n"
                "- Cover Crops, Residue Retention and Water-Holding Capacity in Semi-Arid Farming\n"
                "- Monoculture, Agroforestry and Habitat Complexity"
            )
        if self.responder:
            return self.responder(system, user)
        kb_ids = list(dict.fromkeys(re.findall(r"kb-[0-9]+", user)))[:3]
        oa_ids = list(dict.fromkeys(re.findall(r"oa-[A-Za-z0-9]+", user)))[:2]
        ids = kb_ids + oa_ids
        if kb_ids and oa_ids:
            status = "grounded_in_kb_and_external"
        elif kb_ids:
            status = "grounded_in_knowledge_base"
        elif oa_ids:
            status = "grounded_in_external_evidence"
        else:
            status = "insufficient_evidence"
        payload = {
            "answer": "Given the conditions you described, I would focus on rebuilding soil cover and habitat diversity without adding heavy water demand.",
            "recommendation": "Use drought-tolerant cover crops in the fallow window and native shrubs on field edges where water allows.",
            "why_it_works": "Low soil carbon and low rainfall interact: soils hold less water and living roots are scarce, which also reduces habitat for insects.",
            "environmental_relationships": "Organic carbon, rainfall and land use act together rather than as separate problems.",
            "recommendations": [
                {
                    "action": "Use drought-tolerant cover crops in the fallow window.",
                    "why": "Low soil carbon and low rainfall interact: soils hold less water and living roots are scarce.",
                    "metrics": ["Soil organic carbon", "Soil moisture"],
                    "evidence_ids": ids,
                },
                {
                    "action": "Plant native shrubs on field edges where water allows.",
                    "why": "Simplified land use may reduce floral resources for pollinators.",
                    "metrics": ["Pollinator diversity", "Habitat diversity"],
                    "evidence_ids": ids,
                },
            ],
            "impacted_metrics": [
                {"name": "Soil organic carbon", "direction": "up", "note": "gradual if residue is kept"},
                {"name": "Soil moisture", "direction": "up", "note": None},
                {"name": "Pollinator diversity", "direction": "up", "note": "if flowering cover is present"},
            ],
            "time_horizon": {
                "narrative": "Cover can appear in a season; soil carbon usually takes years.",
                "short_term": "Within a growing season for ground cover",
                "medium_term": "Multiple years for soil carbon",
                "long_term": None,
                "evidence_supported": bool(ids),
            },
            "uncertainty": "These are evidence-informed suggestions, not guaranteed field outcomes.",
            "claims": [
                {
                    "id": "c1",
                    "text": "Cover crops can add living roots and residue that support soil function.",
                    "evidence_ids": ids,
                    "support": "direct",
                }
            ],
            "evidence_used": ids,
            "confidence": "medium" if ids else "low",
            "confidence_rationale": "Some relevant retrieved passages were available." if ids else "Limited retrieved evidence.",
            "knowledge_status": status,
        }
        return json.dumps(payload)

    def stream(self, system: str, user: str, **kwargs: Any):
        yield self.complete(system, user, **kwargs)


def _safe_ollama_error(response: httpx.Response) -> str:
    try:
        data = response.json()
        return str(data.get("error") or data)
    except Exception:
        return response.text[:300]


def set_llm_client_override(client: LLMClient | None | object) -> None:
    global _override
    _override = client


def clear_llm_client_override() -> None:
    global _override
    _override = _UNSET


def configured_llm_model() -> str:
    settings = get_settings()
    provider = settings.llm_provider.lower()
    if provider == "openai":
        return settings.openai_model
    if provider == "groq":
        return settings.groq_model
    return settings.ollama_model


def llm_is_configured() -> bool:
    if _override is not _UNSET:
        return _override is not None
    settings = get_settings()
    provider = settings.llm_provider.lower()
    if provider in {"none", "", "off"}:
        return False
    if provider == "openai":
        return bool(settings.openai_api_key)
    if provider == "groq":
        return bool(settings.groq_api_key)
    if provider == "ollama":
        return bool(settings.ollama_base_url and settings.ollama_model)
    return False


def probe_ollama(force: bool = False) -> tuple[bool, str]:
    global _probe_cache
    settings = get_settings()
    now = time.monotonic()
    cached_at, cached_ok, cached_detail = _probe_cache
    if not force and now - cached_at < 60:
        return cached_ok, cached_detail
    base = settings.ollama_base_url.rstrip("/")
    model = settings.ollama_model
    try:
        response = get_ollama_http().get("/api/tags", timeout=2.5)
        response.raise_for_status()
        names = [item.get("name") or "" for item in (response.json().get("models") or [])]
        installed = _model_is_installed(names, model)
        if not names:
            ok, detail = False, "Ollama is running but no models are installed."
        elif not installed:
            ok, detail = False, f"Ollama is running but '{model}' is not installed."
        else:
            ok, detail = True, "ok"
    except Exception:
        ok, detail = False, "Ollama is not reachable."
    _probe_cache = (now, ok, detail)
    return ok, detail


def reset_ollama_probe_cache() -> None:
    global _probe_cache, _ollama_provider, _ollama_http
    _probe_cache = (0.0, False, "")
    _ollama_provider = None
    _ollama_http = None


def _model_is_installed(names: list[str], model: str) -> bool:
    wanted = (model or "").strip()
    if not wanted:
        return False
    for name in names:
        if not name:
            continue
        if name == wanted:
            return True
        if name.startswith(f"{wanted}-") or name.startswith(f"{wanted}:"):
            return True
    return False


def llm_is_available() -> bool:
    if _override is not _UNSET:
        return _override is not None
    settings = get_settings()
    provider = settings.llm_provider.lower()
    if provider == "openai":
        return bool(settings.openai_api_key)
    if provider == "groq":
        return bool(settings.groq_api_key)
    if provider == "ollama":
        ok, _detail = probe_ollama()
        return ok
    return False


def get_llm_client() -> LLMClient | None:
    global _ollama_provider
    if _override is not _UNSET:
        return _override  # type: ignore[return-value]
    settings = get_settings()
    provider = settings.llm_provider.lower()
    if provider in {"none", "", "off"}:
        return None
    if provider == "ollama":
        if _ollama_provider is None:
            _ollama_provider = OllamaProvider()
        return _ollama_provider
    if provider == "openai":
        if not settings.openai_api_key:
            return None
        return OpenAIProvider()
    if provider == "groq":
        if not settings.groq_api_key:
            return None
        return GroqProvider()
    return None


def _unconfigured_message() -> str:
    settings = get_settings()
    provider = settings.llm_provider.lower()
    if provider == "openai":
        return "OpenAI is selected but OPENAI_API_KEY is not set."
    if provider == "groq":
        return "Groq is selected but GROQ_API_KEY is not set."
    return "The local AI model is not configured. Set LLM_PROVIDER=ollama and start Ollama."


def generate_answer(system: str, user: str, **kwargs: Any) -> str:
    client = get_llm_client()
    if client is None:
        raise LLMUnavailable(_unconfigured_message())
    return client.complete(system, user, **kwargs)


def stream_answer(system: str, user: str, **kwargs: Any):
    client = get_llm_client()
    if client is None:
        raise LLMUnavailable(_unconfigured_message())
    stream_fn = getattr(client, "stream", None)
    if stream_fn is None:
        yield client.complete(system, user, **kwargs)
        return
    yield from stream_fn(system, user, **kwargs)


def warm_ollama() -> None:
    if _override is not _UNSET:
        return
    settings = get_settings()
    if settings.llm_provider.lower() != "ollama":
        return
    try:
        client = get_llm_client()
        if client is None:
            return
        client.complete(
            "You are a warmup probe.",
            "Reply with ok.",
            json_mode=False,
            temperature=0.0,
            num_predict=4,
        )
    except Exception:
        LOGGER.info("Ollama warmup skipped.")


def _extract_json(text: str) -> dict[str, Any]:
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        blob = cleaned[start : end + 1]
        try:
            data = json.loads(blob)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            try:
                data, _offset = json.JSONDecoder().raw_decode(cleaned[start:])
                if isinstance(data, dict):
                    return data
            except json.JSONDecodeError:
                pass
    answer = cleaned[:4000].strip() or "The model replied, but the response was not structured."
    return {
        "answer": answer,
        "recommendation": "",
        "why_it_works": "",
        "environmental_relationships": "",
        "impacted_metrics": [],
        "time_horizon": {"narrative": None, "evidence_supported": False},
        "uncertainty": "The local model did not return valid structured JSON.",
        "claims": [],
        "evidence_used": [],
        "confidence": "low",
        "confidence_rationale": "Response parsing fell back to the raw model text.",
        "knowledge_status": "insufficient_evidence",
    }


def _coerce_direction(value: Any) -> str:
    text = str(value or "unknown").strip().lower()
    if text in {"up", "increase", "increasing", "higher", "improve", "improved", "positive"}:
        return "up"
    if text in {"down", "decrease", "decreasing", "lower", "decline", "declining", "negative"}:
        return "down"
    if text in {"neutral", "stable", "unchanged", "same"}:
        return "neutral"
    return "unknown"


def _coerce_confidence(value: Any) -> str:
    text = str(value or "low").strip().lower()
    if text in {"high", "medium", "low"}:
        return text
    return "low"


def _coerce_support(value: Any) -> str:
    text = str(value or "direct").strip().lower()
    if text in {"direct", "inference", "unsupported"}:
        return text
    if text in {"supported", "evidence", "cited"}:
        return "direct"
    if text in {"guess", "speculative"}:
        return "inference"
    return "direct"


def generate_recommendation(
    *,
    message: str,
    context: EnvironmentalContext,
    history: list[dict[str, Any]],
    kb_evidence: list[EvidenceItem],
    external_evidence: list[EvidenceItem],
    candidates: list[dict[str, Any]],
) -> tuple[RecommendationBlock, dict[str, Any], str, str]:
    client = get_llm_client()
    if client is None:
        raise LLMUnavailable(
            "The local AI model is not configured. Set LLM_PROVIDER=ollama, start Ollama, and pull the configured model."
        )
    user = build_user_prompt(
        message=message,
        context=context,
        history=history,
        kb_evidence=kb_evidence,
        external_evidence=external_evidence,
        candidates=candidates,
    )
    band = answer_length_band(context, message)
    raw = generate_answer(SYSTEM_PROMPT, user, num_predict=predict_budget(band))
    data = _extract_json(raw)
    metrics = []
    for item in data.get("impacted_metrics") or []:
        if isinstance(item, dict) and item.get("name"):
            metrics.append(
                ImpactedMetric(
                    name=item["name"],
                    direction=_coerce_direction(item.get("direction")),
                    note=item.get("note"),
                )
            )
    horizon_raw = data.get("time_horizon") or {}
    if isinstance(horizon_raw, str):
        horizon = TimeHorizon(narrative=horizon_raw, evidence_supported=False)
    elif isinstance(horizon_raw, dict):
        horizon = TimeHorizon(
            short_term=horizon_raw.get("short_term"),
            medium_term=horizon_raw.get("medium_term"),
            long_term=horizon_raw.get("long_term"),
            narrative=horizon_raw.get("narrative"),
            evidence_supported=bool(horizon_raw.get("evidence_supported")),
        )
    else:
        horizon = TimeHorizon()
    claims = []
    for item in data.get("claims") or []:
        if not isinstance(item, dict):
            continue
        claims.append(
            ClaimEvidenceLink(
                claim_id=str(item.get("id") or item.get("claim_id") or f"c{len(claims)+1}"),
                text=str(item.get("text") or ""),
                evidence_ids=[str(x) for x in (item.get("evidence_ids") or [])],
                support=_coerce_support(item.get("support")),
            )
        )
    rec = data.get("recommendation") or data.get("action")
    if isinstance(rec, list) and rec:
        rec = rec[0] if isinstance(rec[0], str) else rec[0].get("text") or rec[0].get("action")
    parsed_recs: list[dict[str, Any]] = []
    for item in data.get("recommendations") or []:
        if isinstance(item, dict):
            action_text = str(item.get("action") or item.get("text") or "").strip()
            if action_text:
                parsed_recs.append(
                    {
                        "action": action_text,
                        "why": str(item.get("why") or item.get("why_it_works") or "").strip(),
                        "metrics": item.get("metrics") or [],
                        "evidence_ids": [str(x) for x in (item.get("evidence_ids") or [])],
                    }
                )
        elif isinstance(item, str) and item.strip():
            parsed_recs.append({"action": item.strip(), "why": "", "metrics": [], "evidence_ids": []})
    if rec:
        for part in split_recommendation_text(str(rec)):
            if part and not any(part.lower() in str(existing.get("action")).lower() for existing in parsed_recs):
                parsed_recs.insert(0, {"action": part, "why": str(data.get("why_it_works") or ""), "metrics": [], "evidence_ids": []})
    parsed_recs = dedupe_recommendations(parsed_recs)
    parsed_recs = [
        item
        for item in parsed_recs
        if mechanism_allowed(str(item.get("action") or ""), kb_evidence + external_evidence, context, message)
    ]
    data["recommendations"] = parsed_recs
    extra_actions = [str(item.get("action") or "").strip() for item in parsed_recs if item.get("action")]
    extra_whys = [str(item.get("why") or "").strip() for item in parsed_recs if item.get("why")]
    rec_ids: list[str] = []
    rec_items: list[RecommendationItem] = []
    for item in parsed_recs:
        rec_ids.extend(str(eid) for eid in (item.get("evidence_ids") or []))
        item_metrics: list[ImpactedMetric] = []
        for metric_name in item.get("metrics") or []:
            name = str(metric_name).strip()
            if not name:
                continue
            item_metrics.append(ImpactedMetric(name=name, direction="unknown", note="potentially affected"))
            if all(existing.name.lower() != name.lower() for existing in metrics):
                metrics.append(ImpactedMetric(name=name, direction="unknown"))
        rec_items.append(
            RecommendationItem(
                action=str(item.get("action") or "").strip(),
                why=str(item.get("why") or "").strip(),
                impacted_metrics=item_metrics,
            )
        )
    rec = "; ".join(extra_actions) if extra_actions else rec
    why = str(data.get("why_it_works") or "").strip()
    if not why and extra_whys:
        why = " ".join(dict.fromkeys(extra_whys))
    horizon = sanitize_time_horizon(horizon, kb_evidence + external_evidence)
    metrics = soften_metrics(metrics)
    block = RecommendationBlock(
        action=str(rec or "").strip(),
        why_it_works=why,
        environmental_relationships=str(data.get("environmental_relationships") or "").strip(),
        impacted_metrics=metrics,
        time_horizon=horizon,
        uncertainty=None if data.get("uncertainty") is None else str(data.get("uncertainty")),
        confidence=_coerce_confidence(data.get("confidence")),
        confidence_rationale=str(data.get("confidence_rationale") or ""),
        items=rec_items,
    )
    composed = ensure_grounded_sources(
        compose_user_facing_answer(
            data=data,
            rec=block,
            kb_evidence=kb_evidence,
            external_evidence=external_evidence,
            message=message,
        ),
        kb_evidence,
        external_evidence,
        message=message,
    )
    rag_prompt = f"SYSTEM INSTRUCTIONS:\n{SYSTEM_PROMPT}\n\n{user}"
    provider = getattr(client, "provider", "")
    if provider in {"ollama", "openai"} and needs_answer_expansion(composed, context, message):
        expansion_user = build_expansion_prompt(
            message=message,
            context=context,
            kb_evidence=kb_evidence,
            external_evidence=external_evidence,
            structured={**data, "_answer": composed},
        )
        try:
            expanded = generate_answer(
                ANSWER_EXPAND_SYSTEM,
                expansion_user,
                json_mode=False,
                temperature=0.35,
                num_predict=2200,
            ).strip()
            if expanded:
                if word_count(expanded) >= 180:
                    composed = ensure_grounded_sources(expanded, kb_evidence, external_evidence, message=message)
                    data["_expansion_raw"] = expanded[:8000]
                    rag_prompt = f"{rag_prompt}\n\n--- USER-FACING EXPANSION ---\n{expansion_user}"
        except LLMUnavailable:
            LOGGER.warning("Answer expansion skipped because the language model was unavailable.")
        except Exception:
            LOGGER.exception("Answer expansion failed; using composed JSON fields.")
    if not is_conceptual_question(message):
        composed = ensure_material_variables(composed, context)
    used_kb, used_ext = filter_evidence_for_answer(composed, claims, rec_ids, kb_evidence, external_evidence)
    composed = ensure_grounded_sources(composed, used_kb, used_ext, message=message)
    block = complete_recommendation(
        block,
        composed,
        context,
        [*used_kb, *used_ext],
        user_message=message,
    )
    data["_claims"] = [c.model_dump() for c in claims]
    data["_answer"] = composed or str(data.get("answer") or block.action)
    data["_raw"] = raw
    data["_kb_used"] = used_kb
    data["_ext_used"] = used_ext
    return block, data, rag_prompt, getattr(client, "model", "")
