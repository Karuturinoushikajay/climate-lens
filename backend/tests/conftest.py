from __future__ import annotations

import math
import random
from datetime import date, timedelta
from typing import Callable

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.cache import MemoryCache
from app.config import Settings
from app.main import create_app
from app.services.weather import OpenMeteoClient

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"


def synthetic_tmax(day: date, lat: float = 17.4) -> float:
    """Deterministic seasonal cycle + warming drift + noise (stand-in for provider data)."""
    rnd = random.Random(day.toordinal() * 31 + int(lat * 100))
    seasonal = 7.0 * math.sin(2 * math.pi * (day.timetuple().tm_yday - 30) / 365.25)
    drift = 0.04 * (day.year - 1990)
    return round(33.0 + seasonal + drift + rnd.gauss(0, 1.8), 1)


def location_payload(lat: float, lon: float, start: date, end: date, null_dates: set[date] | None = None) -> dict:
    null_dates = null_dates or set()
    times, values = [], []
    d = start
    while d <= end:
        times.append(d.isoformat())
        values.append(None if d in null_dates else synthetic_tmax(d, lat))
        d += timedelta(days=1)
    return {
        "latitude": round(lat, 2),
        "longitude": round(lon, 2),
        "elevation": 505.0,
        "timezone": "Asia/Kolkata",
        "utc_offset_seconds": 19800,
        "daily_units": {"time": "iso8601", "temperature_2m_max": "°C"},
        "daily": {"time": times, "temperature_2m_max": values},
    }


def open_meteo_handler(null_dates: set[date] | None = None) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        p = request.url.params
        lats = [float(v) for v in p["latitude"].split(",")]
        lons = [float(v) for v in p["longitude"].split(",")]
        start, end = date.fromisoformat(p["start_date"]), date.fromisoformat(p["end_date"])
        locs = [location_payload(la, lo, start, end, null_dates) for la, lo in zip(lats, lons)]
        return httpx.Response(200, json=locs if len(locs) > 1 else locs[0])

    return handler


@pytest.fixture
def mock_api():
    with respx.mock(assert_all_called=False) as router:
        yield router


def make_settings(**overrides) -> Settings:
    base = dict(
        mongodb_uri="",
        allowed_origins="http://localhost:5173",
        rate_limit_analyze_per_minute=1000,
        rate_limit_export_per_minute=1000,
        upstream_max_retries=2,
        upstream_backoff_seconds=0,
        open_meteo_archive_url=ARCHIVE_URL,
    )
    base.update(overrides)
    return Settings(**base)


@pytest.fixture
def make_client(mock_api):
    def factory(**overrides) -> TestClient:
        settings = make_settings(**overrides)
        weather = OpenMeteoClient(ARCHIVE_URL, max_retries=settings.upstream_max_retries, backoff_seconds=0)
        app = create_app(settings=settings, cache=MemoryCache(), weather=weather)
        return TestClient(app)

    return factory


@pytest.fixture
def make_settings_mongo(mock_api, monkeypatch):
    """Apps that share one (mock) MongoDB, standing in for several backend instances."""
    import mongomock

    from app.cache import MongoCache

    server = mongomock.MongoClient()
    monkeypatch.setattr("pymongo.MongoClient", lambda *a, **k: server)

    def factory(**overrides) -> TestClient:
        settings = make_settings(rate_limit_analyze_per_minute=3, **overrides)
        weather = OpenMeteoClient(ARCHIVE_URL, max_retries=0, backoff_seconds=0)
        return TestClient(create_app(settings=settings, cache=MongoCache("mongodb://mock", "test_db"), weather=weather))

    return factory


@pytest.fixture
def client(make_client, mock_api):
    mock_api.get(ARCHIVE_URL).mock(side_effect=open_meteo_handler())
    return make_client()


POINT = {"latitude": 17.385, "longitude": 78.4867, "label": "Hyderabad"}
