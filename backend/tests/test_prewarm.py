from __future__ import annotations

import time

import httpx
from fastapi.testclient import TestClient

from app.cache import MemoryCache
from app.config import latest_complete_year
from app.services.analysis import AnalysisService
from app.services.prewarm import Prewarmer, default_queries
from app.services.weather import OpenMeteoClient

from .conftest import ARCHIVE_URL, make_settings, open_meteo_handler


def _service() -> AnalysisService:
    weather = OpenMeteoClient(ARCHIVE_URL, max_retries=0, backoff_seconds=0)
    return AnalysisService(make_settings(), MemoryCache(), weather)


def _prewarmer(service: AnalysisService, cities: int, waits: list[float]) -> Prewarmer:
    queries = default_queries()[: cities * 3]
    return Prewarmer(service, delay_seconds=120, queries=queries, wait=lambda s: waits.append(s) or False)


def test_default_queries_cover_every_preset_city_and_hazard():
    queries = default_queries()
    assert len(queries) == 12 * 3
    assert {q.hazard for q in queries} == {"heatwave", "heavy_rainfall", "drought"}
    assert all(q.start_year == 1990 and q.end_year == latest_complete_year() for q in queries)
    assert all((q.reference_start_year, q.reference_end_year) == (1991, 2020) for q in queries)
    assert queries[0].label == "Hyderabad" and queries[0].percentile == 95
    assert next(q for q in queries if q.hazard == "drought").percentile is None


def test_prewarm_fetches_each_series_once_with_delays_then_skips_cached(mock_api):
    mock_api.get(ARCHIVE_URL).mock(side_effect=open_meteo_handler())
    service, waits = _service(), []
    first = _prewarmer(service, cities=2, waits=waits)
    first.run()
    # Two cities x two variables; dry spells reuse the rainfall series fetched for heavy rainfall.
    assert mock_api.calls.call_count == 4
    assert waits == [120, 120, 120]
    assert first.snapshot() == {"status": "done", "done": 6, "total": 6, "detail": "4 series fetched, 0 failed"}
    assert all(service.analysis_cached(q) for q in first.queries)

    second = _prewarmer(service, cities=2, waits=waits)
    second.run()
    assert mock_api.calls.call_count == 4 and len(waits) == 3
    assert second.snapshot()["detail"] == "all cached"


def test_prewarm_stops_on_provider_quota(mock_api):
    mock_api.get(ARCHIVE_URL).mock(return_value=httpx.Response(429, json={"reason": "quota"}))
    p = _prewarmer(_service(), cities=2, waits=[])
    p.run()
    assert mock_api.calls.call_count == 1
    assert p.status == "stopped" and p.done == 0 and "quota" in p.detail


def test_health_reports_prewarm_disabled_without_mongodb(client):
    body = client.get("/api/health").json()
    assert body["prewarm"]["status"] == "disabled" and body["prewarm"]["total"] == 0
    assert "MongoDB" in body["prewarm"]["detail"]


def test_prewarm_enabled_only_with_mongodb_and_switchable(make_settings_mongo):
    on = make_settings_mongo().get("/api/health").json()["prewarm"]
    assert on == {"status": "pending", "done": 0, "total": 36}
    off = make_settings_mongo(prewarm_enabled=False).get("/api/health").json()["prewarm"]
    assert off["status"] == "disabled" and "PREWARM_ENABLED" in off["detail"]


def test_prewarm_runs_in_background_and_stops_on_shutdown(make_settings_mongo):
    client: TestClient = make_settings_mongo(prewarm_start_delay_seconds=60)
    with client:
        deadline = time.monotonic() + 5
        while client.get("/api/health").json()["prewarm"]["status"] != "running" and time.monotonic() < deadline:
            time.sleep(0.05)
        assert client.get("/api/health").json()["prewarm"]["status"] == "running"
    assert client.app.state.prewarmer.status == "stopped"
    assert client.app.state.prewarmer.done == 0
