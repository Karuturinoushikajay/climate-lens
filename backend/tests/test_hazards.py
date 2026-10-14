"""Heavy rainfall and drought (dry spell) hazards: unit rules and end-to-end API behaviour."""

from __future__ import annotations

import csv
import io
from datetime import date, timedelta

import pytest
from pypdf import PdfReader

from app.climate.hazards import (
    PLAUSIBLE_PRECIP_RANGE_MM,
    is_dry,
    longest_runs_by_year,
    normal_annual_total,
    wet_day_threshold,
)
from app.climate.heatwave import annual_indicators, build_daily_series, detect_events

from .conftest import POINT


def rain(start: date, values: list[float | None]):
    dates = [(start + timedelta(days=i)).isoformat() for i in range(len(values))]
    end = start + timedelta(days=len(values) - 1)
    return build_daily_series(dates, values, start, end, plausible_range=PLAUSIBLE_PRECIP_RANGE_MM)


def q(**kw):
    params = {**POINT, "start_year": 1990, "end_year": 2020}
    params.update(kw)
    return params


# ---------------------------------------------------------------- unit rules

def test_wet_day_threshold_ignores_dry_days_and_missing():
    threshold, n = wet_day_threshold([0.0, 0.2, 0.9, None, 1.0, 2.0, 3.0, 4.0, 5.0], 50)
    assert n == 5  # 1.0, 2.0, 3.0, 4.0, 5.0
    assert threshold == pytest.approx(3.0)


def test_wet_day_threshold_without_wet_days():
    assert wet_day_threshold([0.0, 0.5, None], 95) == (None, 0)


def test_heavy_rain_days_are_strictly_above_threshold():
    records, _ = rain(date(2001, 7, 1), [10.0, 30.0, 30.1, 0.0, 50.0])
    events = detect_events(records, 30.0, 1)
    assert [(e.start.day, e.duration_days) for e in events] == [(3, 1), (5, 1)]


def test_negative_precipitation_is_implausible_not_dry():
    records, quality = rain(date(2001, 1, 1), [0.0] * 5 + [-1.0] + [0.0] * 5)
    assert quality.implausible_values == 1
    spells = detect_events(records, 0.0, 5, is_dry)
    assert [e.duration_days for e in spells] == [5, 5]


def test_missing_day_is_never_counted_as_dry():
    records, _ = rain(date(2001, 1, 1), [0.0] * 10 + [None] + [0.0] * 10)
    spells = detect_events(records, 0.0, 15, is_dry)
    assert spells == []
    assert longest_runs_by_year(records) == {2001: 10}


def test_dry_day_boundary_is_below_one_mm():
    assert is_dry(0.99) and not is_dry(1.0)


def test_cdd_attributed_per_calendar_year():
    start = date(2000, 12, 22)
    records, _ = rain(start, [0.0] * 20 + [5.0] + [0.0] * 3)
    longest = longest_runs_by_year(records)
    assert longest == {2000: 10, 2001: 10}


def test_annual_totals_and_normal():
    values = [2.0] * 366 + [1.0] * 365  # 2000 is a leap year
    records, _ = rain(date(2000, 1, 1), values)
    annual = annual_indicators(records, [], None, 2000, 2001, 0.9)
    assert [a.total_value for a in annual] == [732.0, 365.0]
    assert normal_annual_total(annual) == pytest.approx((732.0 + 365.0) / 2)


def test_event_value_total_sums_heavy_days_only():
    records, _ = rain(date(2001, 1, 1), [10.0, 40.0, 50.0, 5.0] + [0.0] * 361)
    events = detect_events(records, 30.0, 1)
    annual = annual_indicators(records, events, 30.0, 2001, 2001, 0.9)
    assert annual[0].heatwave_days == 2
    assert annual[0].event_value_total == pytest.approx(90.0)
    assert annual[0].total_value == pytest.approx(105.0)


# ---------------------------------------------------------------- API

def test_heavy_rainfall_analysis(client, mock_api):
    r = client.get("/api/analyze", params=q(hazard="heavy_rainfall"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert mock_api.calls.last.request.url.params["daily"] == "precipitation_sum"
    assert mock_api.calls.last.request.url.params["precipitation_unit"] == "mm"
    h = body["hazard"]
    assert h["type"] == "heavy_rainfall" and h["units"] == "mm" and h["min_duration_days"] == 1
    assert h["percentile"] == 95 and "wet-day" in h["definition"]
    b = body["baseline"]
    assert b["threshold_c"] is None and b["threshold_value"] > 1.0 and b["threshold_units"] == "mm"
    assert b["normal_annual_total_mm"] > 0
    s = body["summary"]
    assert s["peak_tmax_c"] is None and s["peak_daily_mm"] >= b["threshold_value"]
    assert s["total_heatwave_days"] == sum(a["heatwave_days"] for a in body["annual"]) > 0
    for a in body["annual"]:
        assert a["mean_tmax_c"] is None and a["total_mm"] is not None
        assert 0 <= a["event_total_mm"] <= a["total_mm"]
        if a["heatwave_days"]:
            assert a["max_daily_mm"] > b["threshold_value"]
    for e in body["events"]:
        assert e["peak_tmax_c"] is None and e["peak_value"] > b["threshold_value"]
    assert body["trends"]["mean_tmax"]["indicator"] == "Annual total precipitation"
    assert body["trends"]["mean_tmax"]["units"] == "mm/year"
    assert body["trends"]["heatwave_days"]["indicator"] == "Annual heavy-rain days"
    assert "heavy-rain event(s)" in body["insights"][0]
    assert any("convective" in c for c in body["caveats"])
    assert "not applied to precipitation" in body["data_quality"]["outlier_method"]
    assert body["data_quality"]["plausible_range_units"] == "mm"
    assert body["data_quality"]["analysis"]["accounting_ok"]


def test_drought_analysis(client, mock_api):
    r = client.get("/api/analyze", params=q(hazard="drought"))
    assert r.status_code == 200, r.text
    body = r.json()
    h = body["hazard"]
    assert h["type"] == "drought" and h["percentile"] is None and h["min_duration_days"] == 15
    assert h["comparison"] == "strictly less than"
    assert body["baseline"]["threshold_value"] == 1.0
    normal = body["baseline"]["normal_annual_total_mm"]
    assert normal > 0
    assert body["events"], "the synthetic monsoon climate has long dry winters"
    assert all(e["duration_days"] >= 15 for e in body["events"])
    for a in body["annual"]:
        assert a["longest_event_days"] >= max(
            (y["days"] for e in body["events"] for y in e["year_contributions"] if y["year"] == a["year"]), default=0
        )
        assert a["percent_of_normal"] == pytest.approx(100 * a["total_mm"] / normal, abs=0.1)
    assert any("normal of" in line for line in body["insights"])
    assert any("not a declared drought" in c for c in body["caveats"])


def test_hazards_do_not_share_cached_observations(client, mock_api):
    client.get("/api/analyze", params=q())
    client.get("/api/analyze", params=q(hazard="heavy_rainfall"))
    client.get("/api/analyze", params=q(hazard="drought"))
    variables = [c.request.url.params["daily"] for c in mock_api.calls]
    assert variables == ["temperature_2m_max", "precipitation_sum"]  # drought reuses the precipitation series


def test_drought_ignores_percentile_in_cache_key(client, mock_api):
    a = client.get("/api/analyze", params=q(hazard="drought", percentile=90)).json()
    b = client.get("/api/analyze", params=q(hazard="drought", percentile=99)).json()
    assert b["cache"]["analysis"] == "hit"
    assert a["summary"] == b["summary"]


def test_custom_dry_spell_length(client, mock_api):
    short = client.get("/api/analyze", params=q(hazard="drought", min_duration_days=5)).json()
    long = client.get("/api/analyze", params=q(hazard="drought", min_duration_days=30)).json()
    assert short["summary"]["total_heatwave_days"] >= long["summary"]["total_heatwave_days"]
    assert "at least 30 consecutive" in long["hazard"]["definition"]


def test_precipitation_unit_mismatch_rejected(make_client, mock_api):
    import httpx

    payload = {
        "latitude": 17.4, "longitude": 78.5, "timezone": "Asia/Kolkata",
        "daily_units": {"precipitation_sum": "inch"},
        "daily": {"time": ["1990-01-01"], "precipitation_sum": [0.1]},
    }
    mock_api.get("https://archive-api.open-meteo.com/v1/archive").mock(return_value=httpx.Response(200, json=payload))
    r = make_client().get("/api/analyze", params=q(hazard="heavy_rainfall"))
    assert r.status_code == 502
    assert "precipitation unit" in r.json()["error"]["message"]


@pytest.mark.parametrize("hazard, column", [("heavy_rainfall", "Rain on heavy-rain event days (mm)"), ("drought", "Longest dry spell in year (CDD, days)")])
def test_precipitation_exports(client, hazard, column):
    body = client.get("/api/analyze", params=q(hazard=hazard)).json()
    text = client.get("/api/export.csv", params=q(hazard=hazard)).text
    rows = list(csv.reader(io.StringIO(text)))
    meta = {r[1]: r[2] for r in rows if r and r[0] == "#" and len(r) >= 3}
    assert "Baseline normal annual precipitation (mm)" in meta
    header = next(r for r in rows if r and r[0] == "Year")
    assert column in header and "Annual precipitation (mm)" in header
    assert not any("temperature" in h.lower() for h in header)
    data = [r for r in rows[rows.index(header) + 1:] if r]
    total_col = header.index(body["hazard"]["labels"]["days"])
    assert sum(int(r[total_col]) for r in data) == body["summary"]["total_heatwave_days"]

    pdf = client.get("/api/export.pdf", params=q(hazard=hazard)).content
    pdf_text = " ".join(" ".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages).split())
    assert f"{body['hazard']['name']} Trend Report" in pdf_text
    assert "Daily precipitation total (mm)" in pdf_text
    assert "Mean daily maximum" not in pdf_text
