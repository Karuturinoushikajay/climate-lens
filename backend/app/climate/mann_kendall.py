"""Mann-Kendall test for a monotonic trend, with tie correction and Sen's slope.

    S      = sum_{i<j} sign(x_j - x_i)
    Var(S) = [n(n-1)(2n+5) - sum_g t_g(t_g-1)(2t_g+5)] / 18      (t_g = size of tie group g)
    Z      = (S-1)/sqrt(Var(S)) if S>0;  0 if S==0;  (S+1)/sqrt(Var(S)) if S<0   (continuity corr.)
    p      = 2 * (1 - Phi(|Z|)) = erfc(|Z| / sqrt(2))                               (two-sided)

Non-finite values are removed before testing (the test only uses the order of observations,
so the remaining values keep their chronological order). The normal approximation assumes
independent observations; positive serial autocorrelation inflates the false-positive rate,
and no pre-whitening / variance correction is applied here.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from statistics import median
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
    sen_slope: float | None = None
    direction: str = "undetermined"  # increasing | decreasing | none | undetermined
    significant: bool = False
    interpretation_code: str = "insufficient_data"
    interpretation: str = INTERPRETATIONS["insufficient_data"]
    dropped_values: int = 0
    notes: list[str] = field(default_factory=list)


def _finite(v: object) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


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
        result.notes.append(f"{dropped} missing or non-numeric value(s) were excluded before testing.")
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

    if s > 0:
        z = (s - 1) / math.sqrt(var_s)
    elif s < 0:
        z = (s + 1) / math.sqrt(var_s)
    else:
        z = 0.0
    p = math.erfc(abs(z) / math.sqrt(2))

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
