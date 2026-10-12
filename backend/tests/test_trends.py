import pytest

from app.climate.mann_kendall import mann_kendall
from app.climate.trends import build_insights, linear_regression, period_change, rolling_mean


def test_regression_perfect_line():
    r = linear_regression([2000, 2001, 2002, 2003], [1, 3, 5, 7])
    assert r.status == "ok"
    assert r.slope == pytest.approx(2.0)
    assert r.intercept == pytest.approx(1 - 2 * 2000)
    assert r.r_squared == pytest.approx(1.0)
    assert r.n == 4


def test_regression_insufficient_points():
    r = linear_regression([2000, 2001], [1, 2])
    assert r.status == "insufficient_data" and r.slope is None


def test_regression_constant_series():
    r = linear_regression([2000, 2001, 2002], [5, 5, 5])
    assert r.status == "constant_series"
    assert r.slope == 0 and r.r_squared is None


def test_regression_skips_missing():
    r = linear_regression([1, 2, 3, 4], [1, None, 3, 4])
    assert r.n == 3


def test_regression_identical_x():
    r = linear_regression([1, 1, 1], [1, 2, 3])
    assert r.slope is None


def test_rolling_mean():
    assert rolling_mean([1, 2, 3, 4, 5], 3) == [None, None, 2.0, 3.0, 4.0]
    assert rolling_mean([1, None, 3, 4, 5], 3) == [None, None, None, None, 4.0]


def test_period_change_percentage():
    years = list(range(2000, 2010))
    values = [2] * 5 + [3] * 5
    c = period_change(years, values, 5)
    assert c.first_mean == 2 and c.last_mean == 3
    assert c.percent_change == pytest.approx(50.0)
    assert c.first_period == "2000-2004" and c.last_period == "2005-2009"


def test_period_change_zero_baseline_omits_percentage():
    c = period_change(list(range(2000, 2010)), [0] * 5 + [4] * 5, 5)
    assert c.percent_change is None
    assert c.absolute_change == 4
    assert "zero" in c.note


def test_period_change_short_record_shrinks_window():
    c = period_change([2000, 2001, 2002, 2003], [1, 1, 2, 2], 5)
    assert c.window_years == 2
    assert c.percent_change == pytest.approx(100.0)


def test_period_change_too_short():
    assert period_change([2000, 2001, 2002], [1, 2, 3]).percent_change is None


def test_insights_are_derived_from_values():
    years = list(range(2000, 2010))
    days = [0] * 5 + [4] * 5
    insights = build_insights(
        "Test",
        2000,
        2009,
        total_events=5,
        total_days=20,
        days_change=period_change(years, days),
        days_regression=linear_regression(years, days),
        days_mk=mann_kendall(days),
        events_mk=mann_kendall([0] * 10),
        excluded_years=[2003],
    )
    text = " ".join(insights)
    assert "5 heatwave event(s)" in text and "20 heatwave day(s)" in text
    assert "%" not in insights[1]  # zero baseline -> no percentage
    assert "not a forecast" in text
    assert "1 year(s)" in text
