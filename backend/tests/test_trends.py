import pytest

from app.climate.mann_kendall import mann_kendall
from app.climate.trends import build_insights, hedge, linear_regression, period_change, rolling_mean


def test_regression_perfect_line():
    r = linear_regression([2000, 2001, 2002, 2003], [1, 3, 5, 7])
    assert r.status == "ok"
    assert r.slope == pytest.approx(2.0)
    assert r.intercept == pytest.approx(1 - 2 * 2000)
    assert r.r_squared == pytest.approx(1.0)
    assert r.n == 4


def test_regression_slope_standard_error_and_p_value():
    # Hand-checked: slope 27/35, SSE 0.6/0.7, SE = sqrt(SSE / 4 / 17.5), t = sqrt(R^2 * 4 / (1 - R^2)).
    r = linear_regression([1, 2, 3, 4, 5, 6], [2, 4, 5, 4, 5, 7])
    assert r.slope == pytest.approx(27 / 35)
    assert r.r_squared == pytest.approx(27 / 35)
    assert r.slope_se == pytest.approx(0.2099562637, rel=1e-8)
    assert r.t_statistic == pytest.approx(13.5**0.5, rel=1e-9)
    assert r.p_value == pytest.approx(0.0213116411, rel=1e-6)


@pytest.mark.parametrize(
    "t, df, p",
    [
        (2.228138852, 10, 0.05),  # tabulated 97.5% quantiles
        (12.70620474, 1, 0.05),
        (2.042272456, 30, 0.05),
        (1.0, 1, 0.5),  # Cauchy: 1 - 2 atan(t) / pi
        (1.0, 2, 1 - 1 / 3**0.5),  # df = 2: 1 - t / sqrt(2 + t^2)
        (0.0, 5, 1.0),
    ],
)
def test_t_two_sided_p_matches_closed_forms(t, df, p):
    from app.climate.trends import t_two_sided_p

    assert t_two_sided_p(t, df) == pytest.approx(p, abs=1e-8)
    assert t_two_sided_p(-t, df) == pytest.approx(p, abs=1e-8)


def test_regression_no_slope_p_value_for_constant_series():
    r = linear_regression([2000, 2001, 2002], [5, 5, 5])
    assert r.slope_se == 0 and r.p_value is None and r.t_statistic is None


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
    assert "5 heatwave events totalling 20 heatwave days were detected" in text
    assert "%" not in insights[1]  # zero baseline -> no percentage
    assert "not a forecast" in text
    assert "1 year with insufficient data coverage was excluded" in text
    assert "(s)" not in text


def test_insights_use_singular_for_one():
    years = list(range(2000, 2010))
    insights = build_insights(
        "Test", 2000, 2009, total_events=1, total_days=1,
        days_change=period_change(years, [0] * 10), days_regression=linear_regression(years, [0] * 10),
        days_mk=mann_kendall([0] * 10), events_mk=mann_kendall([0] * 10), excluded_years=[],
    )
    assert insights[0].startswith("Test: 1 heatwave event totalling 1 heatwave day was detected")


def _insights(days: list[float], tmax: list[float] | None = None) -> list[str]:
    years = list(range(2000, 2000 + len(days)))
    return build_insights(
        "Test",
        years[0],
        years[-1],
        total_events=1,
        total_days=int(sum(days)),
        days_change=period_change(years, days),
        days_regression=linear_regression(years, days),
        days_mk=mann_kendall(days),
        events_mk=mann_kendall(days),
        excluded_years=[],
        tmax_change=period_change(years, tmax) if tmax else None,
        tmax_mk=mann_kendall(tmax) if tmax else None,
    )


def test_hedge_wording():
    ns = mann_kendall([3, 1, 4, 1, 5, 9, 2, 6, 5, 3, 5, 8])
    assert not ns.significant
    assert hedge(ns).startswith("(not statistically significant, p = ")
    assert hedge(ns).endswith("after serial-correlation adjustment)")
    sig = mann_kendall(list(range(30)))
    assert sig.significant
    assert hedge(sig) == (
        "(statistically significant, p < 0.001; an association in this record, not proof of a long-term trend)"
    )
    assert "not testable" in hedge(mann_kendall([1, 2]))


def test_every_headline_change_is_hedged():
    days = [2, 5, 3, 6, 4, 3, 7, 5, 4, 6, 8, 5]
    tmax = [33.0, 33.4, 33.1, 33.6, 33.2, 33.5, 33.3, 33.8, 33.4, 33.7, 33.9, 33.6]
    insights = _insights(days, tmax)
    pct = next(i for i in insights if "%" in i)
    slope = next(i for i in insights if "days per decade" in i)
    temp = next(i for i in insights if "°C between" in i)
    for line in (pct, slope, temp):
        assert "statistically significant, p" in line, line
    p_days = mann_kendall(days).p_value
    assert f"p = {p_days:.2f}" in pct or "p < 0.001" in pct or f"p = {p_days:.3f}" in pct
