"""Mann-Kendall test for a monotonic trend, with tie correction and Sen's slope.

    S      = sum_{i<j} sign(x_j - x_i)
    Var(S) = [n(n-1)(2n+5) - sum_g t_g(t_g-1)(2t_g+5)] / 18      (t_g = size of tie group g)
    Z      = (S-1)/sqrt(Var(S)) if S>0;  0 if S==0;  (S+1)/sqrt(Var(S)) if S<0   (continuity corr.)
    p      = 2 * (1 - Phi(|Z|)) = erfc(|Z| / sqrt(2))                               (two-sided)

Non-finite values are removed before testing (the test only uses the order of observations,
so the remaining values keep their chronological order).

Serial correlation (Hamed & Rao, 1998): the series is detrended with Sen's slope, ranked, and
the rank autocorrelations r_k that are significant at alpha are used to inflate the variance:

    n/n* = 1 + 2 / (n(n-1)(n-2)) * sum_k (n-k)(n-k-1)(n-k-2) r_k
    Var*(S) = Var(S) * max(1, n/n*)

The factor is floored at 1 so the correction can only make the test more conservative. The
verdict uses the corrected p-value; the uncorrected value is reported alongside.

Sen's slope confidence interval (Gilbert, 1987): with C = z_{1-alpha/2} * sqrt(Var*(S)) and N
pairwise slopes sorted ascending, the bounds are the M1-th and (M2+1)-th slopes, where
M1 = (N - C) / 2 and M2 = (N + C) / 2.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from statistics import NormalDist, median
from typing import Sequence

MIN_OBSERVATIONS = 4
SMALL_SAMPLE_WARNING = 10

INTERPRETATIONS = {
    "increasing_significant": "Increasing monotonic trend detected, with the significance criterion met.",
    "decreasing_significant": "Decreasing monotonic trend detected, with the significance criterion met.",
    "direction_not_significant": (
        "Trend direction estimated, but statistical evidence is insufficient at the selected threshold."
    ),
    "no_detectable_trend": "No statistically detectable monotonic trend under this test.",
    "insufficient_data": "Insufficient data for reliable testing.",
}


@dataclass
class MannKendallResult:
    n: int
    alpha: float
    s: int | None = None
    var_s_no_ties: float | None = None
    var_s: float | None = None
    z: float | None = None
    p_value: float | None = None
    z_uncorrected: float | None = None
    p_value_uncorrected: float | None = None
    variance_correction: float | None = None
    autocorrelation_lags: list[int] = field(default_factory=list)
    sen_slope: float | None = None
    sen_slope_ci_low: float | None = None
    sen_slope_ci_high: float | None = None
    direction: str = "undetermined"  # increasing | decreasing | none | undetermined
    significant: bool = False
    interpretation_code: str = "insufficient_data"
    interpretation: str = INTERPRETATIONS["insufficient_data"]
    dropped_values: int = 0
    notes: list[str] = field(default_factory=list)


def _finite(v: object) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _ranks(values: Sequence[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def _autocorrelation(values: Sequence[float], lag: int) -> float:
    n = len(values)
    mean = sum(values) / n
    denom = sum((v - mean) ** 2 for v in values)
    if denom == 0:
        return 0.0
    return sum((values[i] - mean) * (values[i + lag] - mean) for i in range(n - lag)) / denom


def hamed_rao_factor(xs: Sequence[float], ys: Sequence[float], slope: float, alpha: float) -> tuple[float, list[int]]:
    """Variance inflation n/n* from significant rank autocorrelations of the detrended series."""
    n = len(ys)
    if n < 3:
        return 1.0, []
    detrended = [y - slope * x for x, y in zip(xs, ys)]
    ranks = _ranks(detrended)
    bound = NormalDist().inv_cdf(1 - alpha / 2) / math.sqrt(n)
    total = 0.0
    lags: list[int] = []
    for k in range(1, n - 2):
        r = _autocorrelation(ranks, k)
        if abs(r) > bound:
            total += (n - k) * (n - k - 1) * (n - k - 2) * r
            lags.append(k)
    return 1 + 2 * total / (n * (n - 1) * (n - 2)), lags


def _z_from_s(s: int, var: float) -> float:
    if s > 0:
        return (s - 1) / math.sqrt(var)
    if s < 0:
        return (s + 1) / math.sqrt(var)
    return 0.0


def sen_slope_ci(slopes: Sequence[float], var_s: float, alpha: float) -> tuple[float | None, float | None]:
    n = len(slopes)
    if n == 0 or var_s <= 0:
        return None, None
    ordered = sorted(slopes)
    c = NormalDist().inv_cdf(1 - alpha / 2) * math.sqrt(var_s)
    lo = round((n - c) / 2)
    hi = round((n + c) / 2) + 1
    if lo < 1 or hi > n:
        return None, None
    return ordered[lo - 1], ordered[hi - 1]


def mann_kendall(
    values: Sequence[float | None],
    x: Sequence[float] | None = None,
    alpha: float = 0.05,
) -> MannKendallResult:
    if not 0 < alpha < 1:
        raise ValueError("alpha must be in (0, 1)")
    if x is not None and len(x) != len(values):
        raise ValueError("x and values must have equal length")

    xs_all = list(x) if x is not None else list(range(len(values)))
    pairs = [(float(xi), float(v)) for xi, v in zip(xs_all, values) if _finite(v) and _finite(xi)]
    dropped = len(values) - len(pairs)
    n = len(pairs)
    result = MannKendallResult(n=n, alpha=alpha, dropped_values=dropped)
    if dropped:
        result.notes.append(
            f"{dropped} missing or non-numeric {'value was' if dropped == 1 else 'values were'} excluded before testing."
        )
    if n < MIN_OBSERVATIONS:
        result.notes.append(f"At least {MIN_OBSERVATIONS} observations are required; {n} available.")
        return result

    xs = [p[0] for p in pairs]
    ys = [p[1] for p in pairs]

    s = 0
    slopes: list[float] = []
    for i in range(n - 1):
        for j in range(i + 1, n):
            diff = ys[j] - ys[i]
            s += (diff > 0) - (diff < 0)
            if xs[j] != xs[i]:
                slopes.append(diff / (xs[j] - xs[i]))

    var_no_ties = n * (n - 1) * (2 * n + 5) / 18.0
    tie_term = sum(t * (t - 1) * (2 * t + 5) for t in Counter(ys).values() if t > 1)
    var_s = (n * (n - 1) * (2 * n + 5) - tie_term) / 18.0

    result.s = s
    result.var_s_no_ties = var_no_ties
    result.var_s = var_s
    result.sen_slope = median(slopes) if slopes else None

    if n < SMALL_SAMPLE_WARNING:
        result.notes.append(
            f"Only {n} observations: the normal approximation for Z is less reliable below {SMALL_SAMPLE_WARNING}."
        )

    if var_s <= 0:
        result.direction = "none"
        result.interpretation_code = "no_detectable_trend"
        result.interpretation = INTERPRETATIONS["no_detectable_trend"]
        result.notes.append("All values are identical, so Var(S) is zero and Z/p are undefined.")
        return result

    z_raw = _z_from_s(s, var_s)
    result.z_uncorrected = z_raw
    result.p_value_uncorrected = math.erfc(abs(z_raw) / math.sqrt(2))

    factor, lags = hamed_rao_factor(xs, ys, result.sen_slope or 0.0, alpha)
    factor = max(1.0, factor)
    var_corrected = var_s * factor
    result.variance_correction = factor
    result.autocorrelation_lags = lags
    if factor > 1:
        result.notes.append(
            f"Serial correlation detected ({'lag' if len(lags) == 1 else 'lags'} {', '.join(map(str, lags))}); the variance was inflated by "
            f"{factor:.2f}x (Hamed-Rao), which makes the test more conservative."
        )

    z = _z_from_s(s, var_corrected)
    p = math.erfc(abs(z) / math.sqrt(2))
    result.sen_slope_ci_low, result.sen_slope_ci_high = sen_slope_ci(slopes, var_corrected, alpha)

    result.z = z
    result.p_value = p
    result.significant = p < alpha
    result.direction = "increasing" if s > 0 else "decreasing" if s < 0 else "none"

    if result.significant and s > 0:
        code = "increasing_significant"
    elif result.significant and s < 0:
        code = "decreasing_significant"
    elif s != 0:
        code = "direction_not_significant"
    else:
        code = "no_detectable_trend"
    result.interpretation_code = code
    result.interpretation = INTERPRETATIONS[code]
    return result
