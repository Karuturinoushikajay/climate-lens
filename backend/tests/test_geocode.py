from __future__ import annotations

import httpx
import pytest

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"

PHOENIX = {
    "results": [
        {
            "id": 5308655,
            "name": "Phoenix",
            "latitude": 33.44838,
            "longitude": -112.07404,
            "country_code": "US",
            "timezone": "America/Phoenix",
            "population": 1650070,
            "country": "United States",
            "admin1": "Arizona",
        },
        {"id": 5745656, "name": "Phoenix", "latitude": 42.27541, "longitude": -122.81809, "country": "United States", "admin1": "Oregon"},
    ],
    "generationtime_ms": 0.6,
}


def test_geocode_returns_places(make_client, mock_api):
    route = mock_api.get(GEOCODING_URL).mock(return_value=httpx.Response(200, json=PHOENIX))
    r = make_client().get("/api/geocode", params={"name": "Phoenix"})
    assert r.status_code == 200
    body = r.json()
    assert body["cache"] == "miss"
    assert [(p["admin1"], p["latitude"], p["longitude"]) for p in body["results"]] == [
        ("Arizona", 33.44838, -112.07404),
        ("Oregon", 42.27541, -122.81809),
    ]
    assert body["results"][1]["population"] is None
    assert "GeoNames" in body["attribution"]
    params = route.calls.last.request.url.params
    assert params["name"] == "Phoenix" and params["count"] == "5"


def test_geocode_no_match_is_empty_not_error(make_client, mock_api):
    mock_api.get(GEOCODING_URL).mock(return_value=httpx.Response(200, json={"generationtime_ms": 0.5}))
    r = make_client().get("/api/geocode", params={"name": "zzqqxx"})
    assert r.status_code == 200 and r.json()["results"] == []


def test_geocode_is_cached_case_insensitively(make_client, mock_api):
    route = mock_api.get(GEOCODING_URL).mock(return_value=httpx.Response(200, json=PHOENIX))
    c = make_client()
    assert c.get("/api/geocode", params={"name": "Phoenix"}).json()["cache"] == "miss"
    second = c.get("/api/geocode", params={"name": "  phoenix "}).json()
    assert second["cache"] == "hit" and second["query"] == "phoenix"
    assert len(second["results"]) == 2
    assert route.call_count == 1


def test_geocode_skips_results_without_valid_coordinates(make_client, mock_api):
    payload = {
        "results": [
            {"name": "Nowhere", "latitude": None, "longitude": 10},
            {"name": "Off-globe", "latitude": 95, "longitude": 10},
            {"latitude": 10, "longitude": 10},
            {"name": "Pune", "latitude": 18.51957, "longitude": 73.85535, "country": "India"},
        ]
    }
    mock_api.get(GEOCODING_URL).mock(return_value=httpx.Response(200, json=payload))
    results = make_client().get("/api/geocode", params={"name": "Pune"}).json()["results"]
    assert [p["name"] for p in results] == ["Pune"]


@pytest.mark.parametrize("params", [{"name": "a"}, {"name": "   "}, {}, {"name": "Pune", "count": 0}, {"name": "Pune", "count": 11}])
def test_geocode_validation(make_client, params):
    r = make_client().get("/api/geocode", params=params)
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"


def test_geocode_provider_errors(make_client, mock_api):
    mock_api.get(GEOCODING_URL).mock(return_value=httpx.Response(200, json={"results": "oops"}))
    assert make_client().get("/api/geocode", params={"name": "Pune"}).status_code == 502

    mock_api.get(GEOCODING_URL).mock(return_value=httpx.Response(500))
    r = make_client(upstream_max_retries=0).get("/api/geocode", params={"name": "Delhi"})
    assert r.status_code == 503


def test_geocode_failures_are_not_cached(make_client, mock_api):
    route = mock_api.get(GEOCODING_URL)
    route.side_effect = [httpx.Response(500), httpx.Response(200, json=PHOENIX)]
    c = make_client(upstream_max_retries=0)
    assert c.get("/api/geocode", params={"name": "Phoenix"}).status_code == 503
    assert c.get("/api/geocode", params={"name": "Phoenix"}).json()["cache"] == "miss"


def test_geocode_rate_limited(make_client, mock_api):
    mock_api.get(GEOCODING_URL).mock(return_value=httpx.Response(200, json=PHOENIX))
    c = make_client(rate_limit_geocode_per_minute=2)
    assert [c.get("/api/geocode", params={"name": "Phoenix"}).status_code for _ in range(3)] == [200, 200, 429]
