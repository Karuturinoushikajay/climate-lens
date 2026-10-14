from __future__ import annotations

import csv
import io
from datetime import date

import httpx
import pytest
from pypdf import PdfReader

from .conftest import ARCHIVE_URL, POINT, open_meteo_handler


def q(**kw):
    params = {**POINT, "start_year": 1990, "end_year": 2020}
    params.update(kw)
    return params


# ---------------------------------------------------------------- health / regions

def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["cache"]["mode"] == "memory"
    assert "Open-Meteo" in body["data_source"]["provider"]
    assert r.headers["x-content-type-options"] == "nosniff"


def test_regions(client):
    r = client.get("/api/regions")
    assert r.status_code == 200
    names = {x["name"] for x in r.json()["regions"]}
    for city in ("Hyderabad", "Mumbai", "Delhi", "Bengaluru", "Chennai", "Visakhapatnam"):
        assert city in names
    states = [x for x in r.json()["regions"] if x["kind"] == "state"]
    assert states and all(s["bbox"] for s in states)


# ---------------------------------------------------------------- analysis

def test_analyze_valid_point(client, mock_api):
    r = client.get("/api/analyze", params=q())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["region"]["label"] == "Hyderabad"
    assert body["region"]["kind"] == "point"
    assert body["period"]["years"] == 31
    assert len(body["annual"]) == 31
    assert body["baseline"]["threshold_c"] is not None
    assert body["hazard"]["min_duration_days"] == 3
    s = body["summary"]
    assert s["total_events"] == len(body["events"]) == sum(a["event_count"] for a in body["annual"])
    assert s["total_heatwave_days"] == sum(a["heatwave_days"] for a in body["annual"])
    assert s["total_heatwave_days"] == sum(e["duration_days"] for e in body["events"])
    assert all(e["duration_days"] >= 3 for e in body["events"])
    mk = body["trends"]["heatwave_days"]["mann_kendall"]
    assert mk["n"] == 31 and mk["alpha"] == 0.05
    assert body["cache"] == {"backend": "memory", "analysis": "miss", "observations": "miss"}
    assert body["insights"] and body["caveats"]
    assert mock_api.calls.call_count == 1
    sent = mock_api.calls.last.request.url.params
    assert sent["daily"] == "temperature_2m_max"
    assert sent["start_date"] == "1990-01-01" and sent["end_date"] == "2020-12-31"


def test_cache_hit_avoids_upstream(client, mock_api):
    first = client.get("/api/analyze", params=q()).json()
    second = client.get("/api/analyze", params=q()).json()
    assert mock_api.calls.call_count == 1
    assert second["cache"]["analysis"] == "hit"
    assert first["summary"] == second["summary"]


def test_observation_cache_reused_for_new_label(client, mock_api):
    client.get("/api/analyze", params=q())
    r = client.get("/api/analyze", params=q(label="Other name")).json()
    assert mock_api.calls.call_count == 1
    assert r["cache"] == {"backend": "memory", "analysis": "miss", "observations": "hit"}


def test_missing_values_reported_and_not_zero_filled(make_client, mock_api):
    nulls = {date(2000, 6, d) for d in range(1, 11)}
    mock_api.get(ARCHIVE_URL).mock(side_effect=open_meteo_handler(nulls))
    body = make_client().get("/api/analyze", params=q(start_year=2000, end_year=2005)).json()
    assert body["data_quality"]["analysis"]["null_values"] == 10
    y2000 = next(a for a in body["annual"] if a["year"] == 2000)
    assert y2000["missing_days"] == 10 and y2000["valid_days"] == 356
    assert body["data_quality"]["analysis"]["interpolated_days"] == 0
    assert body["data_quality"]["gap_fill"] == "off"


def test_fill_gaps_is_opt_in_flagged_and_keyed(make_client, mock_api):
    nulls = {date(2000, 6, 5), date(2001, 7, 1), date(2001, 7, 2)}
    mock_api.get(ARCHIVE_URL).mock(side_effect=open_meteo_handler(nulls))
    client = make_client()
    off = client.get("/api/analyze", params=q(start_year=2000, end_year=2005)).json()
    on = client.get("/api/analyze", params=q(start_year=2000, end_year=2005, fill_gaps="true")).json()
    assert on["cache"]["analysis"] == "miss" and on["cache"]["observations"] == "hit"
    assert off["data_quality"]["analysis"]["interpolated_days"] == 0
    dq = on["data_quality"]
    assert dq["analysis"]["interpolated_days"] == 1  # the two-day gap stays missing
    assert dq["gap_fill"] == "single-day linear"
    assert dq["analysis"]["valid_days"] == off["data_quality"]["analysis"]["valid_days"]
    y2000 = next(a for a in on["annual"] if a["year"] == 2000)
    assert y2000["interpolated_days"] == 1 and y2000["missing_days"] == 1
    assert on["request"]["fill_gaps"] is True
    assert on["baseline"]["threshold_c"] == off["baseline"]["threshold_c"]
    assert any("gap fill is on" in c for c in on["caveats"])


def test_filled_days_are_visible_in_events_and_lists(make_client, mock_api):
    nulls = {date(2000, 6, 5), date(2001, 7, 1), date(2001, 7, 2)}
    mock_api.get(ARCHIVE_URL).mock(side_effect=open_meteo_handler(nulls))
    client = make_client()
    on = client.get("/api/analyze", params=q(start_year=2000, end_year=2005, fill_gaps="true")).json()
    dq = on["data_quality"]
    assert dq["filled_total"] == 1
    assert dq["filled_dates"][0]["date"] == "2000-06-05" and dq["filled_dates"][0]["reason"] == "null"
    assert all("filled_days" in e for e in on["events"])
    assert sum(e["filled_days"] for e in on["events"]) <= 1
    rows, meta = _parse_csv(client.get("/api/export.csv", params=q(start_year=2000, end_year=2005, fill_gaps="true")).text)
    assert any(m.startswith("#,\"Filled day (date, value C, original flag)\",2000-06-05,") for m in meta)


@pytest.mark.parametrize("start, end, expected", [(2020, 2020, 366), (2000, 2024, 9132), (1966, 1970, 1826)])
def test_received_days_never_negative_or_below_valid(client, mock_api, start, end, expected):
    a = client.get("/api/analyze", params=q(start_year=start, end_year=end)).json()["data_quality"]["analysis"]
    assert a["received_days"] == a["provided_days"] == expected
    assert a["valid_days"] <= a["received_days"] <= a["expected_days"]
    assert a["received_days"] == a["valid_days"] + a["null_values"] + a["implausible_values"]
    assert a["expected_days"] == a["received_days"] + a["missing_dates"]
    assert a["accounting_ok"] is True and f"{expected} received from the source" in a["accounting"]


def test_quality_reports_outliers_and_method(client, mock_api):
    dq = client.get("/api/analyze", params=q(start_year=2000, end_year=2005)).json()["data_quality"]
    assert "MAD" in dq["outlier_method"]
    assert dq["outlier_total"] == dq["analysis"]["outlier_days"]
    assert len(dq["outlier_dates"]) == min(dq["outlier_total"], 20)
    assert all(abs(o["robust_z"]) > 4 for o in dq["outlier_dates"])


def test_configurable_percentile_and_duration(client, mock_api):
    base = q(start_year=2000, end_year=2010)
    p90 = client.get("/api/analyze", params={**base, "percentile": 90, "min_duration_days": 2}).json()
    p99 = client.get("/api/analyze", params={**base, "percentile": 99, "min_duration_days": 5}).json()
    assert p90["hazard"]["percentile"] == 90 and p90["hazard"]["min_duration_days"] == 2
    assert p99["hazard"]["percentile"] == 99 and p99["hazard"]["min_duration_days"] == 5
    assert p90["baseline"]["threshold_c"] < p99["baseline"]["threshold_c"]
    assert all(e["duration_days"] >= 2 for e in p90["events"])
    assert all(e["duration_days"] >= 5 for e in p99["events"])
    assert p90["summary"]["total_heatwave_days"] > p99["summary"]["total_heatwave_days"]
    assert "90th-percentile" in p90["hazard"]["definition"] and "At least 2" in p90["hazard"]["definition"]
    assert p99["cache"]["analysis"] == "miss"


@pytest.mark.parametrize(
    "params, fragment",
    [
        (q(latitude=95), "latitude"),
        (q(longitude=-181), "longitude"),
        (q(start_year=2010, end_year=2000), "start_year must not be after end_year"),
        (q(start_year=1940, end_year=2010), "may not exceed 60 years"),
        (q(start_year=1900), "between 1940"),
        (q(hazard="drought"), "Unsupported hazard type 'drought'"),
        ({"start_year": 2000, "end_year": 2010}, "latitude and longitude are required"),
        (q(south=10, west=70, north=12, east=72), "not both"),
        (q(baseline="fixed_reference", reference_start_year=2000, reference_end_year=2003), "at least 10 years"),
        (q(label="x" * 300), "label"),
        (q(percentile=96), "percentile must be one of 90, 92.5, 95, 97.5, 99"),
        (q(percentile="abc"), "percentile"),
        (q(min_duration_days=1), "min_duration_days"),
        (q(min_duration_days=11), "min_duration_days"),
        (
            q(baseline="fixed_reference", reference_start_year=2020, reference_end_year=1991),
            "reference_start_year must not be after reference_end_year",
        ),
    ],
)
def test_validation_errors(client, mock_api, params, fragment):
    r = client.get("/api/analyze", params=params)
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "validation_error"
    assert fragment.lower() in (err["message"] + str(err.get("details"))).lower()
    assert mock_api.calls.call_count == 0


def test_box_validation(client):
    bad = {"south": 10, "west": 70, "north": 25, "east": 72, "start_year": 2000, "end_year": 2010}
    r = client.get("/api/analyze", params=bad)
    assert r.status_code == 422 and "10 degrees" in r.json()["error"]["message"]
    inverted = {"south": 12, "west": 70, "north": 10, "east": 72, "start_year": 2000, "end_year": 2010}
    assert client.get("/api/analyze", params=inverted).status_code == 422


def test_box_query_samples_grid(client, mock_api):
    params = {"south": 16, "west": 77, "north": 19, "east": 80, "start_year": 2000, "end_year": 2010}
    body = client.get("/api/analyze", params=params).json()
    assert body["region"]["kind"] == "box"
    assert len(body["region"]["sampled_points"]) == 4
    assert len(mock_api.calls.last.request.url.params["latitude"].split(",")) == 4
    assert "4 grid points" in body["source"]["aggregation"]


def test_fixed_reference_baseline(client, mock_api):
    a = client.get("/api/analyze", params=q(start_year=1990, end_year=2020)).json()
    b = client.get(
        "/api/analyze",
        params=q(start_year=1990, end_year=2020, baseline="fixed_reference", reference_start_year=1991, reference_end_year=2000),
    ).json()
    assert b["baseline"]["mode"] == "fixed_reference"
    assert b["baseline"]["reference_start_year"] == 1991
    assert b["baseline"]["threshold_c"] != a["baseline"]["threshold_c"]
    assert b["data_quality"]["reference"] is not None
    # reference inside the analysis window -> union equals the cached range, no extra request
    assert mock_api.calls.call_count == 1


def test_defaults_to_fixed_reference_and_era5(client, mock_api):
    body = client.get("/api/analyze", params=q()).json()
    assert body["baseline"]["mode"] == "fixed_reference"
    assert (body["baseline"]["reference_start_year"], body["baseline"]["reference_end_year"]) == (1991, 2020)
    assert mock_api.calls.last.request.url.params["models"] == "era5"
    assert "ERA5" in body["source"]["dataset"]


def test_fixed_reference_disjoint_fetches_two_ranges(client, mock_api):
    client.get(
        "/api/analyze",
        params=q(start_year=2010, end_year=2020, baseline="fixed_reference", reference_start_year=1961, reference_end_year=1990),
    )
    assert mock_api.calls.call_count == 2
    ranges = sorted((c.request.url.params["start_date"], c.request.url.params["end_date"]) for c in mock_api.calls)
    assert ranges == [("1961-01-01", "1990-12-31"), ("2010-01-01", "2020-12-31")]


# ---------------------------------------------------------------- provider failures

def test_provider_server_error_retries_then_503(make_client, mock_api):
    route = mock_api.get(ARCHIVE_URL).mock(return_value=httpx.Response(500))
    r = make_client(upstream_max_retries=2).get("/api/analyze", params=q())
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "upstream_unavailable"
    assert route.call_count == 3
    assert "Traceback" not in r.text


def test_provider_timeout(make_client, mock_api):
    mock_api.get(ARCHIVE_URL).mock(side_effect=httpx.ReadTimeout("slow"))
    r = make_client().get("/api/analyze", params=q())
    assert r.status_code == 504
    assert r.json()["error"]["code"] == "upstream_timeout"


def test_provider_rate_limit_not_retried(make_client, mock_api):
    route = mock_api.get(ARCHIVE_URL).mock(return_value=httpx.Response(429, json={"reason": "limit"}))
    r = make_client().get("/api/analyze", params=q())
    assert r.status_code == 503 and r.json()["error"]["code"] == "upstream_rate_limited"
    assert route.call_count == 1


def test_provider_bad_request_reason(make_client, mock_api):
    mock_api.get(ARCHIVE_URL).mock(return_value=httpx.Response(400, json={"error": True, "reason": "Bad dates"}))
    r = make_client().get("/api/analyze", params=q())
    assert r.status_code == 502 and "Bad dates" in r.json()["error"]["message"]


def test_provider_malformed(make_client, mock_api):
    mock_api.get(ARCHIVE_URL).mock(return_value=httpx.Response(200, json={"daily": {"time": ["2000-01-01"]}}))
    r = make_client().get("/api/analyze", params=q())
    assert r.status_code == 502 and r.json()["error"]["code"] == "upstream_malformed"


def test_failed_fetch_is_not_cached(make_client, mock_api):
    route = mock_api.get(ARCHIVE_URL)
    route.side_effect = [httpx.Response(500), httpx.Response(500), httpx.Response(500), open_meteo_handler()]
    c = make_client()
    assert c.get("/api/analyze", params=q()).status_code == 503
    route.side_effect = open_meteo_handler()
    assert c.get("/api/analyze", params=q()).status_code == 200


# ---------------------------------------------------------------- rate limiting

def test_rate_limit(make_client, mock_api):
    mock_api.get(ARCHIVE_URL).mock(side_effect=open_meteo_handler())
    c = make_client(rate_limit_analyze_per_minute=2, rate_limit_export_per_minute=1)
    assert c.get("/api/analyze", params=q()).status_code == 200
    assert c.get("/api/analyze", params=q()).status_code == 200
    r = c.get("/api/analyze", params=q())
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "rate_limited"
    assert int(r.headers["retry-after"]) >= 1
    # export bucket is independent
    assert c.get("/api/export.csv", params=q()).status_code == 200
    assert c.get("/api/export.csv", params=q()).status_code == 429


def test_rate_limit_ignores_spoofed_forwarded_for(make_client, mock_api):
    mock_api.get(ARCHIVE_URL).mock(side_effect=open_meteo_handler())
    c = make_client(rate_limit_analyze_per_minute=30, trusted_proxy_hops=1)
    statuses = [
        c.get("/api/analyze", params=q(), headers={"X-Forwarded-For": f"10.0.0.{i}, 203.0.113.7"}).status_code
        for i in range(31)
    ]
    assert statuses[:30] == [200] * 30
    assert statuses[30] == 429


def test_rate_limit_separates_real_clients_behind_proxy(make_client, mock_api):
    mock_api.get(ARCHIVE_URL).mock(side_effect=open_meteo_handler())
    c = make_client(rate_limit_analyze_per_minute=1, trusted_proxy_hops=1)
    assert c.get("/api/analyze", params=q(), headers={"X-Forwarded-For": "203.0.113.7"}).status_code == 200
    assert c.get("/api/analyze", params=q(), headers={"X-Forwarded-For": "203.0.113.8"}).status_code == 200
    assert c.get("/api/analyze", params=q(), headers={"X-Forwarded-For": "9.9.9.9, 203.0.113.8"}).status_code == 429


def test_rate_limit_render_header_layout(make_client, mock_api):
    mock_api.get(ARCHIVE_URL).mock(side_effect=open_meteo_handler())
    c = make_client(rate_limit_analyze_per_minute=1, trusted_proxy_hops=3)
    tail = "198.51.100.20, 172.68.146.199, 10.29.149.43"
    assert c.get("/api/analyze", params=q(), headers={"X-Forwarded-For": f"1.2.3.4, {tail}"}).status_code == 200
    assert c.get("/api/analyze", params=q(), headers={"X-Forwarded-For": f"5.6.7.8, {tail}"}).status_code == 429


def test_rate_limit_without_proxy_ignores_forwarded_for(make_client, mock_api):
    mock_api.get(ARCHIVE_URL).mock(side_effect=open_meteo_handler())
    c = make_client(rate_limit_analyze_per_minute=1)
    assert c.get("/api/analyze", params=q(), headers={"X-Forwarded-For": "1.1.1.1"}).status_code == 200
    assert c.get("/api/analyze", params=q(), headers={"X-Forwarded-For": "2.2.2.2"}).status_code == 429


def test_rate_limit_uses_cf_connecting_ip_when_forwarded_chain_varies(make_client, mock_api):
    mock_api.get(ARCHIVE_URL).mock(side_effect=open_meteo_handler())
    c = make_client(rate_limit_analyze_per_minute=30, trust_proxy_headers=True)
    remaining, statuses = [], []
    for i in range(31):
        # The entry 3rd from the right changes on every request, as on some Render paths.
        xff = f"203.0.113.7, 172.68.{i}.1, 10.29.{i}.43, 10.0.0.{i}"
        r = c.get("/api/analyze", params=q(), headers={"CF-Connecting-IP": "203.0.113.7", "X-Forwarded-For": xff})
        statuses.append(r.status_code)
        remaining.append(int(r.headers["x-ratelimit-remaining"]))
    assert statuses[:30] == [200] * 30 and statuses[30] == 429
    assert remaining[:30] == list(range(29, -1, -1))


def test_rate_limit_groups_ipv6_by_64_network(make_client, mock_api):
    mock_api.get(ARCHIVE_URL).mock(side_effect=open_meteo_handler())
    c = make_client(rate_limit_analyze_per_minute=2, client_ip_header="cf-connecting-ip")
    ips = ["2401:4900:8f9b:3076::1", "2401:4900:8f9b:3076:4936:5a15:a0aa:de2c", "2401:4900:8f9b:3076:ffff::9"]
    assert [c.get("/api/analyze", params=q(), headers={"CF-Connecting-IP": ip}).status_code for ip in ips] == [200, 200, 429]
    other_net = c.get("/api/analyze", params=q(), headers={"CF-Connecting-IP": "2401:4900:8f9b:3077::1"})
    assert other_net.status_code == 200


def test_rate_limit_invalid_client_header_falls_back_to_forwarded_for(make_client, mock_api):
    mock_api.get(ARCHIVE_URL).mock(side_effect=open_meteo_handler())
    c = make_client(rate_limit_analyze_per_minute=1, client_ip_header="cf-connecting-ip", trusted_proxy_hops=1)
    h = {"X-Forwarded-For": "198.51.100.20"}
    assert c.get("/api/analyze", params=q(), headers={**h, "CF-Connecting-IP": "not-an-ip"}).status_code == 200
    assert c.get("/api/analyze", params=q(), headers=h).status_code == 429


@pytest.mark.parametrize(
    "overrides, header",
    [
        ({}, ""),
        ({"trust_proxy_headers": True}, "cf-connecting-ip"),
        ({"trust_proxy_headers": True, "client_ip_header": ""}, ""),
        ({"client_ip_header": " True-Client-IP "}, "true-client-ip"),
    ],
)
def test_client_ip_header_setting(overrides, header):
    from .conftest import make_settings

    assert make_settings(**overrides).client_ip_source_header == header


def test_rate_limit_headers_on_every_response(make_client, mock_api):
    mock_api.get(ARCHIVE_URL).mock(side_effect=open_meteo_handler())
    c = make_client(rate_limit_analyze_per_minute=3)
    remaining = []
    for _ in range(3):
        r = c.get("/api/analyze", params=q())
        assert r.status_code == 200 and r.headers["x-ratelimit-limit"] == "3"
        assert 1 <= int(r.headers["x-ratelimit-reset"]) <= 60
        remaining.append(r.headers["x-ratelimit-remaining"])
    assert remaining == ["2", "1", "0"]
    r = c.get("/api/analyze", params=q())
    assert r.status_code == 429 and r.headers["x-ratelimit-remaining"] == "0"
    assert "x-ratelimit-limit" not in c.get("/api/health").headers


def test_rate_limit_shared_across_instances_via_mongodb(make_settings_mongo, mock_api):
    mock_api.get(ARCHIVE_URL).mock(side_effect=open_meteo_handler())
    first, second = make_settings_mongo(), make_settings_mongo()
    statuses = [c.get("/api/analyze", params=q()).status_code for c in (first, second, first, second, first)]
    assert statuses == [200, 200, 200, 429, 429]
    assert "MongoDB" in first.get("/api/health").json()["limits"]["rate_limits_scope"]


def test_mongo_rate_limit_falls_back_when_store_fails():
    from pymongo.errors import PyMongoError

    from app.security.rate_limit import MongoHitStore

    class Broken:
        def create_index(self, *a, **k):
            pass

        def find_one_and_update(self, *a, **k):
            raise PyMongoError("down")

    store = MongoHitStore(Broken())
    assert [store.hit("k", 2, 60, 1000.0 + i)[0] for i in range(3)] == [True, True, False]


@pytest.mark.parametrize(
    "overrides, hops",
    [({}, 0), ({"trust_proxy_headers": True}, 3), ({"trust_proxy_headers": True, "trusted_proxy_hops": 2}, 2)],
)
def test_proxy_hops_setting(overrides, hops):
    from .conftest import make_settings

    assert make_settings(**overrides).proxy_hops == hops


def test_cors_restricted(client):
    ok = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    bad = client.get("/api/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in bad.headers


def test_cors_origin_regex_and_trailing_slash(make_client):
    client = make_client(
        allowed_origins="https://climate-lens.vercel.app/",
        allowed_origin_regex=r"https://climate-lens(-[a-z0-9]+)?-team\.vercel\.app",
    )
    for origin in ("https://climate-lens.vercel.app", "https://climate-lens-7c11f9you-team.vercel.app"):
        r = client.get("/api/health", headers={"Origin": origin})
        assert r.headers.get("access-control-allow-origin") == origin
    for origin in ("https://climate-lens-x-other.vercel.app", "https://climate-lens-1-team.vercel.app.evil.com"):
        r = client.get("/api/health", headers={"Origin": origin})
        assert "access-control-allow-origin" not in r.headers


# ---------------------------------------------------------------- exports

def _parse_csv(text: str):
    text = text.lstrip("\ufeff")
    lines = [l for l in text.splitlines() if l and not l.startswith("#")]
    meta = [l for l in text.splitlines() if l.startswith("#")]
    return list(csv.DictReader(io.StringIO("\n".join(lines)))), meta


def test_csv_export(client):
    r = client.get("/api/export.csv", params=q(start_year=2000, end_year=2010))
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert r.headers["content-disposition"] == 'attachment; filename="climate-lens-hyderabad-2000-2010.csv"'
    rows, meta = _parse_csv(r.text)
    assert [int(x["Year"]) for x in rows] == list(range(2000, 2011))
    assert any("Hyderabad" in m for m in meta)
    assert {"Heatwave days", "Heatwave events (counted in start year)", "Unusable days (missing + implausible)"} <= set(rows[0])
    assert "Days received from source" in rows[0]
    assert any(m.startswith('#,Accounting check,"OK: ') for m in meta)
    assert {"Interpolated days (gap fill)", "Duplicate dates", "Implausible values"} <= set(rows[0])
    assert "Statistical outlier days (flagged, kept)" in rows[0]
    assert "#,95th percentile threshold (C)," in "\n".join(meta)
    assert "#,Gap fill,off" in meta


def test_exports_follow_configured_hazard(make_client, mock_api):
    nulls = {date(2001, 7, 1)}
    mock_api.get(ARCHIVE_URL).mock(side_effect=open_meteo_handler(nulls))
    c = make_client()
    params = q(start_year=2000, end_year=2005, percentile=90, min_duration_days=2, fill_gaps="true")
    rows, meta = _parse_csv(c.get("/api/export.csv", params=params).text)
    joined = "\n".join(meta)
    assert "#,Threshold percentile,90.0" in joined
    assert "#,Minimum consecutive hot days,2" in joined
    assert "#,90th percentile threshold (C)," in joined
    assert "#,Interpolated days,1" in joined
    assert "#,Gap fill,single-day linear" in joined
    assert sum(int(r["Interpolated days (gap fill)"]) for r in rows) == 1

    pdf = c.get("/api/export.pdf", params=params).content
    text = " ".join(" ".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages).split())
    assert "90th-percentile threshold" in text
    assert "Minimum consecutive hot days 2" in text
    assert "Interpolated days (gap fill) 1" in text
    assert "Annual data quality" in text
    assert "at least 2 consecutive hot days" in text
    assert "any missing day breaks the run" not in text
    assert "single-day gap between two observed days is filled and flagged" in text
    assert "Filled days (showing 1 of 1)" in text
    assert "Accounting check OK" in text


def test_csv_formula_injection_is_neutralised(client):
    r = client.get("/api/export.csv", params=q(label="=HYPERLINK(\"http://x\")", start_year=2000, end_year=2005))
    assert r.status_code == 200
    region_line = next(l for l in r.text.lstrip("\ufeff").splitlines() if l.startswith("#,Region,"))
    assert "'=HYPERLINK" in region_line
    assert "climate-lens-hyperlink-http-x-2000-2005.csv" in r.headers["content-disposition"]


def test_pdf_export(client):
    r = client.get("/api/export.pdf", params=q(start_year=1975, end_year=2020))
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF-")
    reader = PdfReader(io.BytesIO(r.content))
    assert len(reader.pages) >= 3
    text = "\n".join(p.extract_text() for p in reader.pages)
    assert "Heatwave Trend Report" in text
    assert "Hyderabad" in text
    assert "Mann-Kendall" in text
    assert f"Page 1 of {len(reader.pages)}" in text


def test_pdf_label_markup_is_escaped(client):
    r = client.get("/api/export.pdf", params=q(label="<b>Bold & co</b>", start_year=2000, end_year=2005))
    assert r.status_code == 200
    text = "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(r.content)).pages)
    assert "<b>Bold & co</b>" in text


# ---------------------------------------------------------------- consistency

def test_dashboard_csv_pdf_agree(client, mock_api):
    params = q(start_year=1995, end_year=2020)
    data = client.get("/api/analyze", params=params).json()
    rows, _ = _parse_csv(client.get("/api/export.csv", params=params).text)
    pdf = client.get("/api/export.pdf", params=params).content
    text = " ".join(" ".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages).split())

    assert mock_api.calls.call_count == 1
    for annual, row in zip(data["annual"], rows):
        assert int(row["Year"]) == annual["year"]
        assert int(row["Heatwave days"]) == annual["heatwave_days"]
        assert int(row["Heatwave events (counted in start year)"]) == annual["event_count"]
        assert int(row["Longest event contribution (days)"]) == annual["longest_event_days"]
        assert int(row["Valid observation days"]) == annual["valid_days"]

    assert f"{data['baseline']['threshold_c']:.2f} °C" in text
    assert f"Total heatwave events {data['summary']['total_events']}" in text
    assert f"Total heatwave days {data['summary']['total_heatwave_days']}" in text
    mk = data["trends"]["heatwave_days"]["mann_kendall"]
    assert f"S statistic {mk['s']}" in text
    if mk["z"] is not None:
        assert f"{mk['z']:.4f}" in text
