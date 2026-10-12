"""Place-name search through the Open-Meteo Geocoding API (GeoNames data)."""

from __future__ import annotations

import logging
import math
from typing import Any

from ..cache import CacheStore, make_key
from ..errors import WeatherProviderError
from ..models.schemas import GeocodeResponse, Place, sanitize_label
from .weather import OpenMeteoClient

logger = logging.getLogger(__name__)

GEOCODING_PROVIDER = "Open-Meteo Geocoding API"
GEOCODING_ATTRIBUTION = "Place search by Open-Meteo.com, based on GeoNames (CC BY 4.0)"
GEOCODING_SCHEMA = 1


def _coord(v: Any, limit: float) -> float | None:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or abs(v) > limit:
        return None
    return float(v)


def _text(v: Any) -> str | None:
    return (sanitize_label(v) or None) if isinstance(v, str) else None


def parse_places(payload: Any) -> list[Place]:
    if not isinstance(payload, dict):
        raise WeatherProviderError(502, "upstream_malformed", "Geocoding service returned an unexpected response.")
    if payload.get("error"):
        reason = str(payload.get("reason", ""))[:200]
        raise WeatherProviderError(502, "upstream_rejected", f"Geocoding service rejected the search{': ' + reason if reason else '.'}")
    results = payload.get("results", [])
    if not isinstance(results, list):
        raise WeatherProviderError(502, "upstream_malformed", "Geocoding service returned an unexpected response.")

    places: list[Place] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        lat, lon, name = _coord(item.get("latitude"), 90), _coord(item.get("longitude"), 180), _text(item.get("name"))
        if lat is None or lon is None or name is None:
            logger.info("Skipping geocoding result without a usable name or coordinates")
            continue
        population = item.get("population")
        places.append(
            Place(
                id=item["id"] if isinstance(item.get("id"), int) else None,
                name=name,
                latitude=lat,
                longitude=lon,
                admin1=_text(item.get("admin1")),
                country=_text(item.get("country")),
                country_code=_text(item.get("country_code")),
                timezone=_text(item.get("timezone")),
                population=population if isinstance(population, int) and population >= 0 else None,
            )
        )
    return places


class GeocodingService:
    def __init__(self, client: OpenMeteoClient, cache: CacheStore, url: str, ttl_hours: int):
        self.client = client
        self.cache = cache
        self.url = url
        self.ttl_seconds = ttl_hours * 3600

    def search(self, name: str, count: int) -> GeocodeResponse:
        key = make_key("geo", {"schema": GEOCODING_SCHEMA, "name": name.casefold(), "count": count})
        cached = self.cache.get("places", key)
        if cached is not None:
            try:
                return GeocodeResponse.model_validate({**cached, "query": name, "cache": "hit"})
            except ValueError:
                logger.warning("Discarding malformed cached places %s", key)

        payload = self.client.get_json(self.url, {"name": name, "count": count, "language": "en", "format": "json"})
        response = GeocodeResponse(
            query=name, results=parse_places(payload), provider=GEOCODING_PROVIDER, attribution=GEOCODING_ATTRIBUTION, cache="miss"
        )
        self.cache.set("places", key, response.model_dump(mode="json", exclude={"query", "cache"}), self.ttl_seconds)
        return response
