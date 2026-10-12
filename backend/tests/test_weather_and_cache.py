from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import httpx
import mongomock
import pytest
from pymongo.errors import PyMongoError

from app.cache import MemoryCache, MongoCache, create_cache, make_key
from app.errors import WeatherProviderError
from app.services.weather import OpenMeteoClient, WeatherSeries

from .conftest import ARCHIVE_URL, location_payload


def _client():
    return OpenMeteoClient(ARCHIVE_URL, max_retries=0, backoff_seconds=0)


def test_single_point_fetch_and_metadata(mock_api):
    mock_api.get(ARCHIVE_URL).mock(
        return_value=httpx.Response(200, json=location_payload(17.4, 78.5, date(2001, 1, 1), date(2001, 1, 10)))
    )
    s = _client().fetch_daily_tmax([(17.4, 78.5)], date(2001, 1, 1), date(2001, 1, 10))
    assert len(s.dates) == 10 and s.units == "°C" and s.timezone == "Asia/Kolkata"
    assert s.grid_points[0].elevation == 505.0
    assert s.retrieved_at
    assert WeatherSeries.from_document(s.to_document()).tmax == s.tmax


def test_multi_point_mean_requires_all_valid(mock_api):
    a = location_payload(1, 1, date(2001, 1, 1), date(2001, 1, 3))
    b = location_payload(2, 2, date(2001, 1, 1), date(2001, 1, 3))
    a["daily"]["temperature_2m_max"] = [10.0, 20.0, None]
    b["daily"]["temperature_2m_max"] = [20.0, None, 30.0]
    mock_api.get(ARCHIVE_URL).mock(return_value=httpx.Response(200, json=[a, b]))
    s = _client().fetch_daily_tmax([(1, 1), (2, 2)], date(2001, 1, 1), date(2001, 1, 3))
    assert s.tmax == [15.0, None, None]


def test_unexpected_units_rejected(mock_api):
    payload = location_payload(1, 1, date(2001, 1, 1), date(2001, 1, 2))
    payload["daily_units"]["temperature_2m_max"] = "°F"
    mock_api.get(ARCHIVE_URL).mock(return_value=httpx.Response(200, json=payload))
    with pytest.raises(WeatherProviderError) as e:
        _client().fetch_daily_tmax([(1, 1)], date(2001, 1, 1), date(2001, 1, 2))
    assert e.value.code == "upstream_malformed"


def test_misaligned_arrays_rejected(mock_api):
    payload = location_payload(1, 1, date(2001, 1, 1), date(2001, 1, 3))
    payload["daily"]["temperature_2m_max"].pop()
    mock_api.get(ARCHIVE_URL).mock(return_value=httpx.Response(200, json=payload))
    with pytest.raises(WeatherProviderError):
        _client().fetch_daily_tmax([(1, 1)], date(2001, 1, 1), date(2001, 1, 3))


def test_non_numeric_values_become_missing(mock_api):
    payload = location_payload(1, 1, date(2001, 1, 1), date(2001, 1, 3))
    payload["daily"]["temperature_2m_max"] = [10.0, "bad", None]
    mock_api.get(ARCHIVE_URL).mock(return_value=httpx.Response(200, json=payload))
    s = _client().fetch_daily_tmax([(1, 1)], date(2001, 1, 1), date(2001, 1, 3))
    assert s.tmax == [10.0, None, None]


def test_connection_error_retries(mock_api):
    route = mock_api.get(ARCHIVE_URL).mock(side_effect=httpx.ConnectError("down"))
    client = OpenMeteoClient(ARCHIVE_URL, max_retries=2, backoff_seconds=0)
    with pytest.raises(WeatherProviderError) as e:
        client.fetch_daily_tmax([(1, 1)], date(2001, 1, 1), date(2001, 1, 3))
    assert e.value.status_code == 503 and route.call_count == 3


# ---------------------------------------------------------------- cache

def test_make_key_is_order_independent():
    assert make_key("a", {"x": 1, "y": 2}) == make_key("a", {"y": 2, "x": 1})
    assert make_key("a", {"x": 1}) != make_key("a", {"x": 2})


def test_memory_cache_ttl_and_eviction(monkeypatch):
    c = MemoryCache(max_entries=2)
    c.set("analyses", "k1", {"v": 1}, 60)
    c.set("analyses", "k2", {"v": 2}, 60)
    c.set("analyses", "k3", {"v": 3}, 60)
    assert c.get("analyses", "k1") is None  # evicted (LRU)
    assert c.get("analyses", "k3") == {"v": 3}
    c.set("observations", "old", {"v": 0}, -1)
    assert c.get("observations", "old") is None


@pytest.fixture
def mongo_cache(monkeypatch):
    monkeypatch.setattr("pymongo.MongoClient", mongomock.MongoClient)
    return MongoCache("mongodb://mock", "test_db")


def test_mongo_cache_roundtrip_and_ttl_index(mongo_cache):
    mongo_cache.set("analyses", "k", {"value": 42}, 3600)
    assert mongo_cache.get("analyses", "k") == {"value": 42}
    indexes = mongo_cache._db["analyses"].index_information()
    assert indexes["ttl_expires_at"]["expireAfterSeconds"] == 0
    assert mongo_cache.status()["mode"] == "mongodb"


def test_mongo_cache_never_serves_expired(mongo_cache):
    past = datetime.now(timezone.utc) - timedelta(seconds=5)
    mongo_cache._db["analyses"].insert_one({"_id": "old", "payload": {"v": 1}, "expires_at": past})
    assert mongo_cache.get("analyses", "old") is None


def test_mongo_failure_degrades_gracefully(mongo_cache, monkeypatch):
    def boom(*a, **k):
        raise PyMongoError("down")

    monkeypatch.setattr(mongo_cache._db["analyses"], "find_one", boom)
    assert mongo_cache.get("analyses", "k") is None
    assert mongo_cache.status()["healthy"] is False


def test_create_cache_falls_back_to_memory():
    cache = create_cache("mongodb://127.0.0.1:1/?directConnection=true", "x", 200, 10)
    assert cache.mode == "memory"
    assert "unavailable" in cache.status()["detail"]
    assert create_cache("", "x", 200, 10).mode == "memory"
