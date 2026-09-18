from __future__ import annotations

import logging

import httpx

LOGGER = logging.getLogger("darukaa.geocode")

USER_AGENT = "DarukaaEarth/1.0 (biodiversity intelligence lab; local research prototype)"
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json",
    "Accept-Language": "en",
}


def search_places(query: str, limit: int = 5) -> list[dict]:
    text = (query or "").strip()
    if len(text) < 2:
        return []
    return _nominatim(text, limit) or _photon(text, limit)


def _nominatim(query: str, limit: int) -> list[dict]:
    try:
        response = httpx.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": query, "format": "json", "limit": limit, "addressdetails": 1},
            headers=HEADERS,
            timeout=10.0,
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
            timeout=10.0,
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
