from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx

LOGGER = logging.getLogger("darukaa.geocode")

USER_AGENT = "DarukaaEarth/1.0 (biodiversity intelligence lab; local research prototype)"
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json",
    "Accept-Language": "en",
}
PROVIDER_TIMEOUT = 3.5
CACHE_TTL_SECONDS = 600.0
_CACHE: dict[str, tuple[float, list[dict]]] = {}


def search_places(query: str, limit: int = 5) -> list[dict]:
    text = (query or "").strip()
    if len(text) < 2:
        return []
    cache_key = f"{text.lower()}|{limit}"
    cached = _CACHE.get(cache_key)
    if cached and time.monotonic() - cached[0] < CACHE_TTL_SECONDS:
        return cached[1]
    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(_nominatim, text, limit),
            pool.submit(_photon, text, limit),
        ]
        try:
            for future in as_completed(futures, timeout=PROVIDER_TIMEOUT + 0.5):
                try:
                    found = future.result() or []
                except Exception:
                    found = []
                if found:
                    rows = found
                    break
        except Exception:
            LOGGER.info("Geocode lookup timed out.", exc_info=True)
    _CACHE[cache_key] = (time.monotonic(), rows)
    return rows


def _nominatim(query: str, limit: int) -> list[dict]:
    try:
        response = httpx.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": query, "format": "json", "limit": limit, "addressdetails": 1},
            headers=HEADERS,
            timeout=PROVIDER_TIMEOUT,
        )
        if response.status_code >= 400:
            LOGGER.info("Nominatim returned %s; trying Photon.", response.status_code)
            return []
        rows = []
        for item in response.json() or []:
            try:
                rows.append(
                    {
                        "label": item.get("display_name") or query,
                        "latitude": float(item["lat"]),
                        "longitude": float(item["lon"]),
                    }
                )
            except (KeyError, TypeError, ValueError):
                continue
        return rows
    except Exception:
        LOGGER.info("Nominatim lookup failed; trying Photon.", exc_info=True)
        return []


def _photon(query: str, limit: int) -> list[dict]:
    try:
        response = httpx.get(
            "https://photon.komoot.io/api/",
            params={"q": query, "limit": limit},
            headers=HEADERS,
            timeout=PROVIDER_TIMEOUT,
        )
        if response.status_code >= 400:
            return []
        rows = []
        for feature in (response.json() or {}).get("features") or []:
            props = feature.get("properties") or {}
            coords = (feature.get("geometry") or {}).get("coordinates") or []
            if len(coords) < 2:
                continue
            try:
                longitude = float(coords[0])
                latitude = float(coords[1])
            except (TypeError, ValueError):
                continue
            rows.append(
                {
                    "label": _photon_label(props, query),
                    "latitude": latitude,
                    "longitude": longitude,
                }
            )
        return rows
    except Exception:
        LOGGER.info("Photon lookup failed.", exc_info=True)
        return []


def _photon_label(props: dict, fallback: str) -> str:
    parts: list[str] = []
    for key in ("name", "city", "county", "state", "country"):
        value = str(props.get(key) or "").strip()
        if value and value not in parts:
            parts.append(value)
    return ", ".join(parts) or fallback
