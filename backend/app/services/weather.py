"""Open-Meteo Historical Weather API client for daily maximum temperature."""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Sequence

import httpx

from ..errors import WeatherProviderError

logger = logging.getLogger(__name__)

VARIABLE = "temperature_2m_max"
EXPECTED_UNITS = {"°C", "C", "degC"}
PROVIDER = "Open-Meteo Historical Weather API"
# Pinned so the series is one consistent dataset from 1940 onward; Open-Meteo's default
# "best_match" blends ERA5-Land (0.1°, from 1950) and other models.
MODEL = "era5"
DATASET = "ECMWF ERA5 reanalysis (Copernicus), 0.25° grid, via Open-Meteo"
ATTRIBUTION = "Weather data by Open-Meteo.com (CC BY 4.0), based on Copernicus ERA5 reanalysis"


@dataclass
class GridPoint:
    latitude: float
    longitude: float
    elevation: float | None = None


@dataclass
class WeatherSeries:
    dates: list[str]
    tmax: list[float | None]
    start: date
    end: date
    units: str
    timezone: str
    retrieved_at: str
    endpoint: str
    requested_points: list[tuple[float, float]]
    grid_points: list[GridPoint] = field(default_factory=list)
    aggregation: str = "single point"

    def to_document(self) -> dict[str, Any]:
        return {
            "dates": self.dates,
            "tmax": self.tmax,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "units": self.units,
            "timezone": self.timezone,
            "retrieved_at": self.retrieved_at,
            "endpoint": self.endpoint,
            "requested_points": [list(p) for p in self.requested_points],
            "grid_points": [vars(g) for g in self.grid_points],
            "aggregation": self.aggregation,
        }

    @classmethod
    def from_document(cls, doc: dict[str, Any]) -> "WeatherSeries":
        return cls(
            dates=list(doc["dates"]),
            tmax=list(doc["tmax"]),
            start=date.fromisoformat(doc["start"]),
            end=date.fromisoformat(doc["end"]),
            units=doc["units"],
            timezone=doc["timezone"],
            retrieved_at=doc["retrieved_at"],
            endpoint=doc["endpoint"],
            requested_points=[tuple(p) for p in doc["requested_points"]],
            grid_points=[GridPoint(**g) for g in doc.get("grid_points", [])],
            aggregation=doc.get("aggregation", "single point"),
        )


def _finite(v: object) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


class OpenMeteoClient:
    def __init__(
        self,
        base_url: str,
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
        backoff_seconds: float = 0.5,
        http_client: httpx.Client | None = None,
    ):
        self.base_url = base_url
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self._client = http_client or httpx.Client(
            timeout=httpx.Timeout(timeout_seconds, connect=10.0),
            headers={"User-Agent": "ClimateLens/1.0 (case-study application)"},
        )

    def close(self) -> None:
        self._client.close()

    def fetch_daily_tmax(self, points: Sequence[tuple[float, float]], start: date, end: date) -> WeatherSeries:
        """Fetch daily Tmax for one or more points; multiple points are averaged per day.

        A multi-point daily mean is only produced when every point has a valid value for that
        day; otherwise the day is left missing.
        """
        if not points:
            raise ValueError("at least one point is required")
        if end < start:
            raise ValueError("end must not be before start")

        params = {
            "latitude": ",".join(f"{p[0]:.4f}" for p in points),
            "longitude": ",".join(f"{p[1]:.4f}" for p in points),
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "daily": VARIABLE,
            "temperature_unit": "celsius",
            "timezone": "auto",
            "models": MODEL,
        }
        payload = self._request(params)
        locations = payload if isinstance(payload, list) else [payload]
        if len(locations) != len(points):
            raise WeatherProviderError(502, "upstream_malformed", "Weather provider returned an unexpected number of locations.")

        parsed = [self._parse_location(loc) for loc in locations]
        dates = parsed[0]["dates"]
        for other in parsed[1:]:
            if other["dates"] != dates:
                raise WeatherProviderError(502, "upstream_malformed", "Weather provider returned inconsistent dates across locations.")

        if len(parsed) == 1:
            tmax = parsed[0]["tmax"]
            aggregation = "single point"
        else:
            tmax = []
            for i in range(len(dates)):
                vals = [p["tmax"][i] for p in parsed]
                tmax.append(sum(vals) / len(vals) if all(v is not None for v in vals) else None)
            aggregation = f"daily mean of {len(parsed)} grid points (day missing unless all points valid)"

        return WeatherSeries(
            dates=dates,
            tmax=tmax,
            start=start,
            end=end,
            units="°C",
            timezone=parsed[0]["timezone"],
            retrieved_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            endpoint=self.base_url,
            requested_points=[(float(p[0]), float(p[1])) for p in points],
            grid_points=[p["grid"] for p in parsed],
            aggregation=aggregation,
        )

    def get_json(self, url: str, params: dict[str, Any]) -> Any:
        """GET another Open-Meteo endpoint with the same retry and error mapping."""
        return self._request(params, url)

    def _request(self, params: dict[str, Any], url: str | None = None) -> Any:
        last_error = "unknown error"
        for attempt in range(self.max_retries + 1):
            if attempt:
                time.sleep(self.backoff_seconds * (2 ** (attempt - 1)))
            try:
                response = self._client.get(url or self.base_url, params=params)
            except httpx.TimeoutException:
                last_error = "timeout"
                logger.warning("Open-Meteo timeout (attempt %s)", attempt + 1)
                continue
            except httpx.TransportError as exc:
                last_error = type(exc).__name__
                logger.warning("Open-Meteo transport error %s (attempt %s)", last_error, attempt + 1)
                continue

            if response.status_code == 200:
                try:
                    return response.json()
                except ValueError:
                    raise WeatherProviderError(502, "upstream_malformed", "Weather provider returned invalid JSON.")
            if response.status_code == 429:
                raise WeatherProviderError(
                    503,
                    "upstream_rate_limited",
                    "The weather data provider's request quota is currently exhausted. Please try again later.",
                    headers={"Retry-After": "60"},
                )
            if 400 <= response.status_code < 500:
                reason = ""
                try:
                    reason = str(response.json().get("reason", ""))[:200]
                except (ValueError, AttributeError):
                    pass
                raise WeatherProviderError(
                    502, "upstream_rejected", f"Weather provider rejected the request{': ' + reason if reason else '.'}"
                )
            last_error = f"HTTP {response.status_code}"
            logger.warning("Open-Meteo %s (attempt %s)", last_error, attempt + 1)

        if last_error == "timeout":
            raise WeatherProviderError(504, "upstream_timeout", "The weather data provider did not respond in time.")
        raise WeatherProviderError(503, "upstream_unavailable", "The weather data provider is currently unavailable.")

    @staticmethod
    def _parse_location(loc: Any) -> dict[str, Any]:
        if not isinstance(loc, dict):
            raise WeatherProviderError(502, "upstream_malformed", "Weather provider response is not an object.")
        if loc.get("error"):
            raise WeatherProviderError(502, "upstream_rejected", "Weather provider reported an error for this location.")
        daily = loc.get("daily")
        if not isinstance(daily, dict):
            raise WeatherProviderError(502, "upstream_malformed", "Weather provider response has no daily data.")
        times, values = daily.get("time"), daily.get(VARIABLE)
        if not isinstance(times, list) or not isinstance(values, list) or len(times) != len(values):
            raise WeatherProviderError(502, "upstream_malformed", "Weather provider daily arrays are missing or misaligned.")
        units = (loc.get("daily_units") or {}).get(VARIABLE)
        if units is not None and units not in EXPECTED_UNITS:
            raise WeatherProviderError(502, "upstream_malformed", f"Unexpected temperature unit '{units}' from provider.")

        dates: list[str] = []
        for t in times:
            try:
                dates.append(date.fromisoformat(str(t)[:10]).isoformat())
            except ValueError:
                raise WeatherProviderError(502, "upstream_malformed", "Weather provider returned an invalid date.")
        tmax = [float(v) if _finite(v) else None for v in values]
        grid = GridPoint(
            latitude=float(loc.get("latitude", math.nan)),
            longitude=float(loc.get("longitude", math.nan)),
            elevation=float(loc["elevation"]) if _finite(loc.get("elevation")) else None,
        )
        return {"dates": dates, "tmax": tmax, "timezone": str(loc.get("timezone", "GMT")), "grid": grid}
