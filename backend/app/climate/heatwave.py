"""Percentile-threshold heatwave detection.

Definition (case-study example): a heatwave event is a run of at least ``min_duration``
(default 3) consecutive *valid* days whose daily maximum temperature is strictly greater
than the 95th-percentile threshold.

Conventions:
* The daily series is rebuilt on a complete calendar index. Dates missing from the provider,
  null values and physically implausible values are all treated as missing.
* A missing day always breaks a run; missing values are never interpolated or zero-filled.
* An event is counted once, in the calendar year in which it starts.
* Its hot days are attributed to the calendar year in which each day falls.
* A year's "longest event" is the longest contribution any single event makes to that year.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Iterable, Sequence

import numpy as np

PLAUSIBLE_TMAX_RANGE_C = (-60.0, 60.0)
PERCENTILE_METHOD = "linear"  # numpy default, Hyndman & Fan type 7


@dataclass(frozen=True)
class DailyRecord:
    day: date
    tmax: float | None
    flag: str  # "ok" | "missing_date" | "null" | "implausible"


@dataclass
class DataQuality:
    expected_days: int
    provided_days: int
    valid_days: int
    missing_dates: int
    null_values: int
    implausible_values: int
    duplicate_dates: int
    out_of_range_dates: int

    @property
    def missing_days(self) -> int:
        return self.expected_days - self.valid_days

    @property
    def completeness(self) -> float:
        return self.valid_days / self.expected_days if self.expected_days else 0.0


@dataclass
class HeatwaveEvent:
    start: date
    end: date
    duration_days: int
    peak_tmax: float
    mean_tmax: float
    mean_excess_c: float
    year_contributions: dict[int, int] = field(default_factory=dict)

    @property
    def start_year(self) -> int:
        return self.start.year


@dataclass
class AnnualIndicator:
    year: int
    event_count: int
    heatwave_days: int
    longest_event_days: int
    mean_tmax: float | None
    max_tmax: float | None
    mean_excess_c: float | None
    valid_days: int
    expected_days: int
    missing_days: int
    completeness: float
    sufficient_data: bool


def _is_finite_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def build_daily_series(
    dates: Sequence[str | date],
    values: Sequence[float | None],
    start: date,
    end: date,
    plausible_range: tuple[float, float] = PLAUSIBLE_TMAX_RANGE_C,
) -> tuple[list[DailyRecord], DataQuality]:
    """Align provider output to a complete calendar from ``start`` to ``end`` inclusive."""
    if len(dates) != len(values):
        raise ValueError("dates and values must have equal length")
    if end < start:
        raise ValueError("end must not be before start")

    parsed: dict[date, float | None | str] = {}
    counts: Counter[date] = Counter()
    out_of_range = 0
    for raw_day, raw_value in zip(dates, values):
        day = raw_day if isinstance(raw_day, date) else date.fromisoformat(str(raw_day)[:10])
        if day < start or day > end:
            out_of_range += 1
            continue
        counts[day] += 1
        if counts[day] > 1:
            # Keep the first value deterministically; duplicates are reported.
            continue
        parsed[day] = raw_value

    lo, hi = plausible_range
    records: list[DailyRecord] = []
    missing_dates = null_values = implausible = 0
    current = start
    while current <= end:
        if current not in parsed:
            records.append(DailyRecord(current, None, "missing_date"))
            missing_dates += 1
        else:
            raw = parsed[current]
            if raw is None or not _is_finite_number(raw):
                records.append(DailyRecord(current, None, "null"))
                null_values += 1
            elif not lo <= float(raw) <= hi:
                records.append(DailyRecord(current, None, "implausible"))
                implausible += 1
            else:
                records.append(DailyRecord(current, float(raw), "ok"))
        current += timedelta(days=1)

    quality = DataQuality(
        expected_days=len(records),
        provided_days=sum(counts.values()),
        valid_days=sum(1 for r in records if r.tmax is not None),
        missing_dates=missing_dates,
        null_values=null_values,
        implausible_values=implausible,
        duplicate_dates=sum(c - 1 for c in counts.values() if c > 1),
        out_of_range_dates=out_of_range,
    )
    return records, quality


def percentile_threshold(values: Iterable[float | None], percentile: float = 95.0) -> float | None:
    """Percentile of valid values using linear interpolation (Hyndman & Fan type 7).

    Returns ``None`` when there are no valid values.
    """
    if not 0 <= percentile <= 100:
        raise ValueError("percentile must be within [0, 100]")
    clean = [float(v) for v in values if v is not None and _is_finite_number(v)]
    if not clean:
        return None
    return float(np.percentile(np.asarray(clean, dtype=float), percentile, method=PERCENTILE_METHOD))


def detect_events(
    records: Sequence[DailyRecord], threshold: float, min_duration: int = 3
) -> list[HeatwaveEvent]:
    """Find runs of >= ``min_duration`` consecutive calendar days with tmax > threshold.

    ``records`` must be sorted and contiguous (as produced by :func:`build_daily_series`);
    a gap in dates is nevertheless treated as a break for safety.
    """
    if min_duration < 1:
        raise ValueError("min_duration must be >= 1")

    events: list[HeatwaveEvent] = []
    run: list[DailyRecord] = []

    def flush() -> None:
        if len(run) >= min_duration:
            temps = [r.tmax for r in run if r.tmax is not None]
            contributions: Counter[int] = Counter(r.day.year for r in run)
            events.append(
                HeatwaveEvent(
                    start=run[0].day,
                    end=run[-1].day,
                    duration_days=len(run),
                    peak_tmax=max(temps),
                    mean_tmax=sum(temps) / len(temps),
                    mean_excess_c=sum(t - threshold for t in temps) / len(temps),
                    year_contributions=dict(sorted(contributions.items())),
                )
            )
        run.clear()

    previous_day: date | None = None
    for record in records:
        contiguous = previous_day is not None and record.day - previous_day == timedelta(days=1)
        if run and not contiguous:
            flush()
        if record.tmax is not None and record.tmax > threshold:
            run.append(record)
        else:
            flush()
        previous_day = record.day
    flush()
    return events


def annual_indicators(
    records: Sequence[DailyRecord],
    events: Sequence[HeatwaveEvent],
    threshold: float | None,
    start_year: int,
    end_year: int,
    min_completeness: float = 0.8,
) -> list[AnnualIndicator]:
    """Aggregate daily records and events into per-calendar-year indicators."""
    by_year: dict[int, list[DailyRecord]] = {y: [] for y in range(start_year, end_year + 1)}
    for r in records:
        if r.day.year in by_year:
            by_year[r.day.year].append(r)

    event_counts: Counter[int] = Counter()
    hw_days: Counter[int] = Counter()
    longest: dict[int, int] = {}
    excess_sums: Counter[int] = Counter()
    for ev in events:
        event_counts[ev.start_year] += 1
        for year, n_days in ev.year_contributions.items():
            hw_days[year] += n_days
            longest[year] = max(longest.get(year, 0), n_days)

    if threshold is not None:
        hot_days = {d for ev in events for d in _daterange(ev.start, ev.end)}
        for r in records:
            if r.day in hot_days and r.tmax is not None:
                excess_sums[r.day.year] += r.tmax - threshold

    result: list[AnnualIndicator] = []
    for year in range(start_year, end_year + 1):
        rows = by_year[year]
        expected = (date(year, 12, 31) - date(year, 1, 1)).days + 1
        valid = [r.tmax for r in rows if r.tmax is not None]
        completeness = len(valid) / expected
        days = hw_days.get(year, 0)
        result.append(
            AnnualIndicator(
                year=year,
                event_count=event_counts.get(year, 0),
                heatwave_days=days,
                longest_event_days=longest.get(year, 0),
                mean_tmax=(sum(valid) / len(valid)) if valid else None,
                max_tmax=max(valid) if valid else None,
                mean_excess_c=(excess_sums[year] / days) if days else None,
                valid_days=len(valid),
                expected_days=expected,
                missing_days=expected - len(valid),
                completeness=completeness,
                sufficient_data=completeness >= min_completeness,
            )
        )
    return result


def _daterange(start: date, end: date) -> Iterable[date]:
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)
