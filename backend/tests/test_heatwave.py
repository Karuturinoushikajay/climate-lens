from datetime import date, timedelta

import pytest

from app.climate.heatwave import (
    annual_indicators,
    build_daily_series,
    detect_events,
    flag_outliers,
    percentile_threshold,
)

T = 30.0  # threshold used in detection tests
HOT, COOL = 35.0, 25.0


def series(start: date, temps: list[float | None]):
    dates = [(start + timedelta(days=i)).isoformat() for i in range(len(temps))]
    end = start + timedelta(days=len(temps) - 1)
    records, _ = build_daily_series(dates, temps, start, end)
    return records


# ---------- percentile ----------

def test_percentile_linear_interpolation():
    assert percentile_threshold([1, 2, 3, 4, 5]) == pytest.approx(4.8)


def test_percentile_ignores_missing_values():
    assert percentile_threshold([1, None, 2, 3, None, 4, 5]) == pytest.approx(4.8)


def test_percentile_repeated_values():
    assert percentile_threshold([7.0] * 20) == pytest.approx(7.0)


def test_percentile_empty_and_single():
    assert percentile_threshold([]) is None
    assert percentile_threshold([None, None]) is None
    assert percentile_threshold([12.5]) == pytest.approx(12.5)


def test_percentile_rejects_invalid_percentile():
    with pytest.raises(ValueError):
        percentile_threshold([1, 2], 101)


# ---------- event detection ----------

def test_two_hot_days_is_not_an_event():
    assert detect_events(series(date(2000, 6, 1), [COOL, HOT, HOT, COOL]), T) == []


def test_exactly_three_hot_days_is_an_event():
    events = detect_events(series(date(2000, 6, 1), [COOL, HOT, HOT, HOT, COOL]), T)
    assert len(events) == 1
    ev = events[0]
    assert ev.start == date(2000, 6, 2) and ev.end == date(2000, 6, 4)
    assert ev.duration_days == 3


def test_long_event():
    events = detect_events(series(date(2000, 5, 1), [HOT] * 12), T)
    assert len(events) == 1 and events[0].duration_days == 12


def test_multiple_events_and_cool_interruption():
    temps = [HOT, HOT, HOT, COOL, HOT, HOT, HOT, HOT, COOL, HOT, HOT]
    events = detect_events(series(date(2000, 7, 1), temps), T)
    assert [e.duration_days for e in events] == [3, 4]


def test_threshold_equality_is_not_hot():
    assert detect_events(series(date(2000, 7, 1), [T, T, T, T]), T) == []
    assert len(detect_events(series(date(2000, 7, 1), [T + 0.01] * 3), T)) == 1


def test_missing_temperature_breaks_sequence():
    events = detect_events(series(date(2000, 7, 1), [HOT, HOT, None, HOT, HOT]), T)
    assert events == []


def test_missing_calendar_date_breaks_sequence():
    start = date(2000, 7, 1)
    dates = [start + timedelta(days=i) for i in (0, 1, 3, 4)]  # July 3 absent
    records, quality = build_daily_series(dates, [HOT] * 4, start, start + timedelta(days=4))
    assert quality.missing_dates == 1
    assert records[2].flag == "missing_date" and records[2].tmax is None
    assert detect_events(records, T) == []


def test_implausible_value_is_flagged_and_breaks_sequence():
    records = series(date(2000, 7, 1), [HOT, HOT, 99.0, HOT, HOT, HOT])
    assert records[2].flag == "implausible"
    events = detect_events(records, T)
    assert len(events) == 1 and events[0].start == date(2000, 7, 4)


def test_leap_day_is_part_of_event():
    events = detect_events(series(date(2004, 2, 27), [HOT, HOT, HOT, HOT]), T)
    assert events[0].end == date(2004, 3, 1)
    assert events[0].duration_days == 4  # includes Feb 29


def test_event_spanning_year_boundary():
    events = detect_events(series(date(2000, 12, 30), [HOT, HOT, HOT, HOT, HOT]), T)
    assert len(events) == 1
    assert events[0].year_contributions == {2000: 2, 2001: 3}


def test_event_metrics():
    ev = detect_events(series(date(2000, 7, 1), [31.0, 33.0, 35.0]), T)[0]
    assert ev.peak_tmax == 35.0
    assert ev.mean_tmax == pytest.approx(33.0)
    assert ev.mean_excess_c == pytest.approx(3.0)


# ---------- data quality ----------

def test_build_daily_series_quality_counts():
    start, end = date(2001, 1, 1), date(2001, 1, 5)
    dates = ["2001-01-01", "2001-01-01", "2001-01-02", "2001-01-04", "2001-01-05", "2002-01-01"]
    values = [10.0, 11.0, None, float("nan"), 12.0, 13.0]
    records, q = build_daily_series(dates, values, start, end)
    assert q.expected_days == 5
    assert q.duplicate_dates == 1
    assert q.out_of_range_dates == 1
    assert q.missing_dates == 1  # 2001-01-03
    assert q.null_values == 2  # None + NaN
    assert q.valid_days == 2
    assert records[0].tmax == 10.0  # first duplicate kept
    assert q.completeness == pytest.approx(0.4)
    assert q.received_days == 4  # distinct in-window dates; duplicate and out-of-range rows excluded
    assert q.accounting_ok


@pytest.mark.parametrize("fill", [False, True])
def test_quality_counts_always_add_up(fill):
    start, end = date(2001, 1, 1), date(2001, 1, 10)
    dates = ["2001-01-01", "2001-01-02", "2001-01-02", "2001-01-03", "2001-01-05", "2001-01-06",
             "2001-01-07", "2001-01-08", "2001-01-10", "2000-12-31"]
    values = [20.0, 21.0, 99.0, None, 22.0, 80.0, 23.0, 24.0, 25.0, 19.0]
    _, q = build_daily_series(dates, values, start, end, fill_single_gaps=fill)
    assert (q.missing_dates, q.null_values, q.implausible_values, q.duplicate_dates) == (2, 1, 1, 1)
    assert q.received_days == 8 == q.valid_days + q.null_values + q.implausible_values
    assert q.expected_days == q.valid_days + q.absent_or_null_days + q.implausible_values
    assert q.valid_days <= q.received_days
    assert q.accounting_ok


def test_missing_values_are_never_zero_filled():
    records = series(date(2001, 1, 1), [None, None])
    assert all(r.tmax is None for r in records)


# ---------- annual accounting ----------

def test_cross_year_annual_accounting():
    # 2000-12-29 .. 2001-01-02 hot (5 days: 3 in 2000, 2 in 2001)
    start = date(2000, 1, 1)
    end = date(2001, 12, 31)
    n = (end - start).days + 1
    temps = [COOL] * n
    for i in range(n):
        d = start + timedelta(days=i)
        if date(2000, 12, 29) <= d <= date(2001, 1, 2):
            temps[i] = HOT
    records = series(start, temps)
    events = detect_events(records, T)
    annual = {a.year: a for a in annual_indicators(records, events, T, 2000, 2001)}

    assert annual[2000].event_count == 1  # counted in start year only
    assert annual[2001].event_count == 0
    assert annual[2000].heatwave_days == 3
    assert annual[2001].heatwave_days == 2
    assert annual[2000].longest_event_days == 3
    assert annual[2001].longest_event_days == 2
    assert sum(a.event_count for a in annual.values()) == len(events)
    assert sum(a.heatwave_days for a in annual.values()) == sum(e.duration_days for e in events)


def test_annual_events_vs_days_are_distinct():
    start = date(2003, 1, 1)
    temps = [COOL] * 365
    for i in range(100, 103):
        temps[i] = HOT
    for i in range(200, 210):
        temps[i] = HOT
    records = series(start, temps)
    events = detect_events(records, T)
    a = annual_indicators(records, events, T, 2003, 2003)[0]
    assert a.event_count == 2
    assert a.heatwave_days == 13
    assert a.longest_event_days == 10
    assert a.mean_excess_c == pytest.approx(HOT - T)


def test_annual_completeness_and_leap_year():
    start = date(2004, 1, 1)
    temps: list[float | None] = [COOL] * 366
    for i in range(0, 100):
        temps[i] = None
    records = series(start, temps)
    a = annual_indicators(records, [], T, 2004, 2004, min_completeness=0.8)[0]
    assert a.expected_days == 366
    assert a.valid_days == 266
    assert a.missing_days == 100
    assert a.completeness == pytest.approx(266 / 366)
    assert a.sufficient_data is False
    assert a.mean_tmax == pytest.approx(COOL)


# ---------- gap fill and outliers ----------

def _filled(temps: list[float | None], start: date = date(2001, 1, 1)):
    dates = [(start + timedelta(days=i)).isoformat() for i in range(len(temps))]
    return build_daily_series(dates, temps, start, start + timedelta(days=len(temps) - 1), fill_single_gaps=True)


def test_gap_fill_is_off_by_default():
    records = series(date(2001, 1, 1), [HOT, None, HOT])
    assert records[1].tmax is None and records[1].flag == "null"


def test_single_day_gap_is_filled_and_flagged():
    records, q = _filled([HOT, None, 37.0])
    assert records[1].tmax == pytest.approx(36.0)
    assert records[1].flag == "interpolated"
    assert q.interpolated_days == 1
    assert q.valid_days == 2  # observed only
    assert q.completeness == pytest.approx(2 / 3)


def test_two_day_gap_is_not_filled():
    records, q = _filled([HOT, None, None, HOT])
    assert [r.tmax for r in records[1:3]] == [None, None]
    assert q.interpolated_days == 0


def test_gaps_at_series_edges_are_not_filled():
    records, q = _filled([None, HOT, HOT, None])
    assert records[0].tmax is None and records[-1].tmax is None
    assert q.interpolated_days == 0


def test_implausible_day_is_filled_only_when_opted_in():
    records, q = _filled([HOT, 99.0, HOT])
    assert records[1].flag == "interpolated"
    assert q.implausible_values == 1


def test_interpolated_day_completes_a_run_but_not_the_threshold():
    records, _ = _filled([COOL, HOT, None, HOT, COOL])
    events = detect_events(records, T)
    assert len(events) == 1 and events[0].filled_days == 1
    observed = [r.tmax for r in records if r.observed]
    assert observed == [COOL, HOT, HOT, COOL]
    assert records[2].filled_from == "null"


def test_annual_counts_interpolated_duplicates_and_implausible():
    start = date(2001, 1, 1)
    temps: list[float | None] = [COOL] * 365
    temps[10] = None
    temps[20] = 99.0
    dates = [(start + timedelta(days=i)).isoformat() for i in range(365)] + ["2001-03-01"]
    records, q = build_daily_series(dates, temps + [COOL], start, date(2001, 12, 31), fill_single_gaps=True)
    a = annual_indicators(records, [], T, 2001, 2001, duplicates_by_year=q.duplicates_by_year)[0]
    assert a.interpolated_days == 2
    assert a.implausible_days == 1
    assert a.duplicate_dates == 1
    assert a.valid_days == 363
    assert a.missing_days == 2
    assert a.received_days == 365


def _seasonal_years(years: int = 5) -> list[float | None]:
    start = date(2001, 1, 1)
    end = date(2000 + years, 12, 31)
    out: list[float | None] = []
    d = start
    i = 0
    while d <= end:
        out.append(30.0 + ((i * 7) % 5) * 0.5)  # 30.0 .. 32.0, deterministic spread
        d += timedelta(days=1)
        i += 1
    return out


def test_outlier_is_flagged_but_kept():
    temps = _seasonal_years()
    temps[400] = 45.0
    start = date(2001, 1, 1)
    dates = [(start + timedelta(days=i)).isoformat() for i in range(len(temps))]
    records, _ = build_daily_series(dates, temps, start, date(2005, 12, 31))
    flagged, n = flag_outliers(records)
    assert n == 1
    assert flagged[400].outlier and flagged[400].outlier_z > 4
    assert flagged[400].tmax == 45.0
    assert sum(r.tmax is not None for r in flagged) == len(records)


def test_outlier_skips_small_windows_and_zero_mad():
    records = series(date(2001, 1, 1), [COOL] * 10 + [50.0])
    _, n = flag_outliers(records)
    assert n == 0  # fewer than 30 values in the window
    flat = series(date(2001, 1, 1), [COOL] * 365)
    _, n = flag_outliers(flat)
    assert n == 0  # MAD is zero
