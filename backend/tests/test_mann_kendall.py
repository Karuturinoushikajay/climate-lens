import math

import pytest

from app.climate.mann_kendall import mann_kendall


def test_strictly_increasing_series():
    r = mann_kendall(list(range(1, 11)))
    assert r.s == 45
    assert r.var_s == pytest.approx(125.0)
    assert r.z == pytest.approx(44 / math.sqrt(125))
    assert r.p_value == pytest.approx(8.30e-5, rel=1e-2)
    assert r.significant and r.direction == "increasing"
    assert r.interpretation_code == "increasing_significant"


def test_strictly_decreasing_series():
    r = mann_kendall(list(range(10, 0, -1)))
    assert r.s == -45
    assert r.z == pytest.approx(-44 / math.sqrt(125))
    assert r.interpretation_code == "decreasing_significant"


def test_hand_computed_five_values():
    r = mann_kendall([1, 2, 3, 4, 5])
    assert r.s == 10
    assert r.var_s == pytest.approx(5 * 4 * 15 / 18)
    assert r.z == pytest.approx(9 / math.sqrt(5 * 4 * 15 / 18))
    assert r.p_value == pytest.approx(0.0275, abs=5e-4)
    assert r.significant


def test_tie_corrected_variance():
    r = mann_kendall([1, 1, 2, 2, 3])
    assert r.s == 8
    assert r.var_s_no_ties == pytest.approx(300 / 18)
    assert r.var_s == pytest.approx((300 - 36) / 18)
    assert r.z == pytest.approx(7 / math.sqrt(264 / 18))
    assert r.p_value == pytest.approx(0.0676, abs=5e-4)
    assert not r.significant
    assert r.interpretation_code == "direction_not_significant"


def test_constant_series_is_undefined_not_significant():
    r = mann_kendall([4.0] * 12)
    assert r.s == 0 and r.var_s == 0
    assert r.z is None and r.p_value is None
    assert not r.significant
    assert r.interpretation_code == "no_detectable_trend"


def test_s_zero_with_variance():
    r = mann_kendall([1, 3, 2, 2, 3, 1])
    assert r.s == 0 and r.z == 0.0 and r.p_value == pytest.approx(1.0)
    assert r.interpretation_code == "no_detectable_trend"


def test_too_few_observations():
    r = mann_kendall([1, 2, 3])
    assert r.interpretation_code == "insufficient_data"
    assert r.s is None and r.p_value is None


def test_missing_and_invalid_values_are_dropped():
    r = mann_kendall([1, None, 2, float("nan"), 3, float("inf"), 4, 5])
    assert r.n == 5 and r.dropped_values == 3
    assert r.s == 10


def test_missing_years_preserve_order_and_sen_slope():
    years = [2000, 2001, 2003, 2006, 2010]
    values = [0, 2, 6, 12, 20]  # exactly 2 per year
    r = mann_kendall(values, x=years)
    assert r.s == 10
    assert r.sen_slope == pytest.approx(2.0)


def test_alpha_controls_significance():
    vals = [1, 1, 2, 2, 3]  # p ~ 0.0676
    assert not mann_kendall(vals, alpha=0.05).significant
    assert mann_kendall(vals, alpha=0.10).significant


def test_autocorrelated_series_is_adjusted():
    # Slow oscillation around a weak drift: neighbouring years are strongly correlated.
    vals = [0.05 * i + 1.5 * math.sin(i / 4.0) for i in range(40)]
    r = mann_kendall(vals)
    assert r.variance_correction is not None and r.variance_correction > 1
    assert r.p_value_uncorrected < 0.05
    assert r.p_value > 0.05
    assert not r.significant
    assert r.interpretation_code == "direction_not_significant"


def test_independent_series_not_adjusted_below_one():
    r = mann_kendall([1, 3, 2, 5, 4, 7, 6, 9, 8, 10])
    assert r.variance_correction >= 1
    assert r.p_value >= r.p_value_uncorrected


def test_sen_slope_confidence_interval_brackets_slope():
    rnd = __import__("random").Random(7)
    vals = [0.05 * i + rnd.gauss(0, 1) for i in range(50)]
    r = mann_kendall(vals)
    assert r.sen_slope_ci_low <= r.sen_slope <= r.sen_slope_ci_high


def test_invalid_alpha():
    with pytest.raises(ValueError):
        mann_kendall([1, 2, 3, 4], alpha=0)
