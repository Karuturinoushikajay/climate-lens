"""Descriptive trend statistics and data-driven insight text for annual indicators.

Regression describes the observed change over the analysis window; it is not a forecast and
its slope alone says nothing about statistical significance.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence

from .mann_kendall import MannKendallResult

MIN_REGRESSION_POINTS = 3


@dataclass
class RegressionResult:
    n: int
    slope: float | None = None
    intercept: float | None = None
    r_squared: float | None = None
    status: str = "insufficient_data"  # ok | insufficient_data | constant_series
    notes: list[str] = field(default_factory=list)


@dataclass
class PercentChange:
    window_years: int
    first_period: str | None = None
    last_period: str | None = None
    first_mean: float | None = None
    last_mean: float | None = None
    percent_change: float | None = None
    absolute_change: float | None = None
    note: str | None = None


def _finite(v: object) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def linear_regression(xs: Sequence[float], ys: Sequence[float | None]) -> RegressionResult:
    """Ordinary least squares of ys on xs, ignoring non-finite pairs."""
    if len(xs) != len(ys):
        raise ValueError("xs and ys must have equal length")
    pairs = [(float(x), float(y)) for x, y in zip(xs, ys) if _finite(x) and _finite(y)]
    n = len(pairs)
    result = RegressionResult(n=n)
    if n < MIN_REGRESSION_POINTS:
        result.notes.append(f"At least {MIN_REGRESSION_POINTS} annual values are required; {n} available.")
        return result

    mean_x = sum(p[0] for p in pairs) / n
    mean_y = sum(p[1] for p in pairs) / n
    sxx = sum((p[0] - mean_x) ** 2 for p in pairs)
    syy = sum((p[1] - mean_y) ** 2 for p in pairs)
    sxy = sum((p[0] - mean_x) * (p[1] - mean_y) for p in pairs)

    if sxx == 0:
        result.notes.append("All x values are identical; slope is undefined.")
        return result

    slope = sxy / sxx
    result.slope = slope
    result.intercept = mean_y - slope * mean_x
    if syy == 0:
        result.status = "constant_series"
        result.notes.append("The series is constant; R-squared is undefined.")
        return result
    result.r_squared = (sxy * sxy) / (sxx * syy)
    result.status = "ok"
    return result


def rolling_mean(values: Sequence[float | None], window: int = 5) -> list[float | None]:
    """Trailing rolling mean; ``None`` until the window is full or if it contains a gap."""
    if window < 1:
        raise ValueError("window must be >= 1")
    out: list[float | None] = []
    for i in range(len(values)):
        if i + 1 < window:
            out.append(None)
            continue
        chunk = values[i + 1 - window : i + 1]
        if all(_finite(v) for v in chunk):
            out.append(sum(chunk) / window)  # type: ignore[arg-type]
        else:
            out.append(None)
    return out


def period_change(years: Sequence[int], values: Sequence[float | None], window: int = 5) -> PercentChange:
    """Compare the mean of the first and last ``window`` valid years.

    The window shrinks to half the record when fewer than ``2 * window`` valid years exist.
    Percentage change is omitted when the first-period mean is zero.
    """
    pairs = [(y, float(v)) for y, v in zip(years, values) if _finite(v)]
    w = min(window, len(pairs) // 2)
    result = PercentChange(window_years=w)
    if w < 2:
        result.note = "Too few valid years to compare early and late periods."
        return result
    first, last = pairs[:w], pairs[-w:]
    result.first_period = f"{first[0][0]}-{first[-1][0]}"
    result.last_period = f"{last[0][0]}-{last[-1][0]}"
    result.first_mean = sum(v for _, v in first) / w
    result.last_mean = sum(v for _, v in last) / w
    result.absolute_change = result.last_mean - result.first_mean
    if result.first_mean == 0:
        result.note = "Percentage change is omitted because the early-period mean is zero."
    else:
        result.percent_change = 100.0 * result.absolute_change / result.first_mean
    return result


def mk_statement(mk: MannKendallResult) -> str:
    """The required interpretation, qualified with the evidence behind it."""
    if mk.p_value is None:
        return mk.interpretation
    detail = f"p = {mk.p_value:.3f} after serial-correlation adjustment, α = {mk.alpha:g}, {mk.n} years"
    if mk.significant:
        return (
            f"{mk.interpretation} ({detail}). This is a statistical association in this reanalysis record, "
            "not proof of a long-term climate trend."
        )
    return f"{mk.interpretation} ({detail})."


def build_insights(
    label: str,
    start_year: int,
    end_year: int,
    total_events: int,
    total_days: int,
    days_change: PercentChange,
    days_regression: RegressionResult,
    days_mk: MannKendallResult,
    events_mk: MannKendallResult,
    excluded_years: Sequence[int],
) -> list[str]:
    """Plain-language statements derived only from computed values."""
    insights: list[str] = [
        f"{label}: {total_events} heatwave event(s) totalling {total_days} heatwave day(s) "
        f"were detected between {start_year} and {end_year}."
    ]

    c = days_change
    if c.first_mean is not None and c.last_mean is not None:
        if c.percent_change is not None and c.percent_change != 0:
            verb = "higher" if c.percent_change > 0 else "lower"
            insights.append(
                f"Average annual heatwave days in {c.last_period} ({c.last_mean:.1f}) were "
                f"{abs(c.percent_change):.0f}% {verb} than in {c.first_period} ({c.first_mean:.1f})."
            )
        elif c.percent_change == 0:
            insights.append(
                f"Average annual heatwave days were unchanged between {c.first_period} and "
                f"{c.last_period} ({c.first_mean:.1f})."
            )
        else:
            insights.append(
                f"Average annual heatwave days moved from {c.first_mean:.1f} ({c.first_period}) to "
                f"{c.last_mean:.1f} ({c.last_period}). {c.note}"
            )
    elif c.note:
        insights.append(c.note)

    r = days_regression
    if r.slope is not None:
        insights.append(
            f"The fitted linear slope of annual heatwave days is {r.slope * 10:+.2f} days per decade"
            + (f" (R² = {r.r_squared:.2f})." if r.r_squared is not None else " (constant series).")
            + " This describes the observed record and is not a forecast."
        )

    insights.append(f"Mann-Kendall (heatwave days): {mk_statement(days_mk)}")
    insights.append(f"Mann-Kendall (event counts): {mk_statement(events_mk)}")
    if days_mk.significant or events_mk.significant:
        insights.append(
            "Three indicators are tested at α = 0.05 without a multiple-testing correction, so one significant "
            "result among them is weaker evidence than its p-value alone suggests."
        )

    if excluded_years:
        insights.append(
            f"{len(excluded_years)} year(s) with insufficient data coverage were excluded from trend statistics."
        )
    return insights
