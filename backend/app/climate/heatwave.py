"""Percentile-threshold heatwave detection.

Definition (case-study example): a heatwave event is a run of at least ``min_duration``
(default 3) consecutive *valid* days whose daily maximum temperature is strictly greater
than the 95th-percentile threshold.

Conventions:
* The daily series is rebuilt on a complete calendar index. Dates missing from the provider,
  null values and physically implausible values are all treated as missing.
* A missing day breaks a run and is never zero-filled. Only when the caller opts in, an isolated
  one-day gap between two observed days is filled with their mean; such days are flagged
  "interpolated", counted, and never used for the percentile threshold.
* Statistical outliers (robust z-score against the same time of year) are flagged and counted
  but kept, because genuine heat extremes are also unusual.
* An event is counted once, in the calendar year in which it starts.
* Its hot days are attributed to the calendar year in which each day falls.
* A year's "longest event" is the longest contribution any single event makes to that year.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from typing import Callable, Iterable, Sequence

import numpy as np

PLAUSIBLE_TMAX_RANGE_C = (-60.0, 60.0)
PERCENTILE_METHOD = "linear"  # numpy default, Hyndman & Fan type 7
OUTLIER_Z = 4.0
OUTLIER_WINDOW_DAYS = 15
OUTLIER_MIN_SAMPLES = 30
OUTLIER_METHOD = (
    f"robust z-score |0.6745*(x - median)/MAD| > {OUTLIER_Z:g}, against all observed values within "
    f"±{OUTLIER_WINDOW_DAYS} calendar days of the same date in the period; flagged, not removed"
)


@dataclass(frozen=True)
class DailyRecord:
    day: date
    tmax: float | None
    flag: str  # "ok" | "missing_date" | "null" | "implausible" | "interpolated"
    outlier_z: float | None = None
    filled_from: str | None = None  # original flag of an interpolated day

    @property
    def observed(self) -> bool:
        return self.flag == "ok"

    @property
    def outlier(self) -> bool:
        return self.outlier_z is not None


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
    interpolated_days: int = 0
    outlier_days: int = 0
    duplicates_by_year: dict[int, int] = field(default_factory=dict)

    @property
    def missing_days(self) -> int:
        """Calendar days without a usable observed value (absent, null or implausible)."""
        return self.expected_days - self.valid_days

    @property
    def received_days(self) -> int:
        """Distinct calendar dates the provider returned inside the window."""
        return self.expected_days - self.missing_dates

    @property
    def absent_or_null_days(self) -> int:
        return self.missing_dates + self.null_values

    @property
    def accounting_ok(self) -> bool:
        return (
            self.received_days == self.valid_days + self.null_values + self.implausible_values
            and self.expected_days == self.valid_days + self.absent_or_null_days + self.implausible_values
        )

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
    filled_days: int = 0

    @property
    def start_year(self) -> int:
        return self.start.year


@dataclass
class AnnualIndicator:
    year: int
    event_count: int
    event_days: int
    longest_event_days: int
    mean_tmax: float | None
    max_tmax: float | None
    mean_excess_c: float | None
    valid_days: int
    expected_days: int
    missing_days: int
    completeness: float
    sufficient_data: bool
    received_days: int = 0
    interpolated_days: int = 0
    duplicate_dates: int = 0
    implausible_days: int = 0
    outlier_days: int = 0
    total_value: float | None = None
    event_value_total: float = 0.0


def _is_finite_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def build_daily_series(
    dates: Sequence[str | date],
    values: Sequence[float | None],
    start: date,
    end: date,
    plausible_range: tuple[float, float] = PLAUSIBLE_TMAX_RANGE_C,
    fill_single_gaps: bool = False,
) -> tuple[list[DailyRecord], DataQuality]:
    """Align provider output to a complete calendar from ``start`` to ``end`` inclusive.

    ``valid_days`` and completeness count observed values only; filled days are reported
    separately as ``interpolated_days``.
    """
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

    interpolated = 0
    if fill_single_gaps:
        for i in range(1, len(records) - 1):
            prev, cur, nxt = records[i - 1], records[i], records[i + 1]
            if cur.tmax is None and prev.observed and nxt.observed:
                mean = round((prev.tmax + nxt.tmax) / 2, 2)  # type: ignore[operator]
                records[i] = DailyRecord(cur.day, mean, "interpolated", filled_from=cur.flag)
                interpolated += 1

    duplicates_by_year: Counter[int] = Counter()
    for day, c in counts.items():
        if c > 1:
            duplicates_by_year[day.year] += c - 1

    quality = DataQuality(
        expected_days=len(records),
        provided_days=sum(counts.values()),
        valid_days=sum(1 for r in records if r.observed),
        missing_dates=missing_dates,
        null_values=null_values,
        implausible_values=implausible,
        duplicate_dates=sum(duplicates_by_year.values()),
        out_of_range_dates=out_of_range,
        interpolated_days=interpolated,
        duplicates_by_year=dict(duplicates_by_year),
    )
    assert quality.accounting_ok, "daily quality counts do not add up"
    return records, quality


def _day_of_year(d: date) -> int:
    """Day of year on a fixed 365-day calendar (29 February shares 28 February's slot)."""
    doy = d.timetuple().tm_yday
    leap = d.year % 4 == 0 and (d.year % 100 != 0 or d.year % 400 == 0)
    return doy - 1 if leap and doy > 59 else doy


def flag_outliers(
    records: Sequence[DailyRecord],
    z_limit: float = OUTLIER_Z,
    window: int = OUTLIER_WINDOW_DAYS,
    min_samples: int = OUTLIER_MIN_SAMPLES,
) -> tuple[list[DailyRecord], int]:
    """Flag observed days far from the typical value for that time of year.

    Each observed value is compared with the median and MAD of all observed values within
    ``window`` days of the same calendar date (wrapping over the year end). Windows with fewer
    than ``min_samples`` values or zero MAD are skipped rather than guessed.
    """
    idx = [i for i, r in enumerate(records) if r.observed]
    if not idx:
        return list(records), 0
    doy = np.array([_day_of_year(records[i].day) for i in idx])
    vals = np.array([records[i].tmax for i in idx], dtype=float)
    z = np.full(len(idx), np.nan)
    for d in np.unique(doy):
        dist = np.abs(doy - d)
        in_window = np.minimum(dist, 365 - dist) <= window
        sample = vals[in_window]
        if sample.size < min_samples:
            continue
        median = np.median(sample)
        mad = np.median(np.abs(sample - median))
        if mad == 0:
            continue
        here = doy == d
        z[here] = 0.6745 * (vals[here] - median) / mad

    out = list(records)
    flagged = 0
    for k, i in enumerate(idx):
        if np.isfinite(z[k]) and abs(z[k]) > z_limit:
            out[i] = replace(out[i], outlier_z=round(float(z[k]), 2))
            flagged += 1
    return out, flagged


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
    records: Sequence[DailyRecord],
    threshold: float,
    min_duration: int = 3,
    qualifies: Callable[[float], bool] | None = None,
) -> list[HeatwaveEvent]:
    """Find runs of >= ``min_duration`` consecutive calendar days that qualify.

    A day qualifies when its value is strictly greater than ``threshold``, unless another
    ``qualifies`` test is given (for example "below 1 mm" for dry days). Missing days never qualify.
    ``records`` must be sorted and contiguous (as produced by :func:`build_daily_series`);
    a gap in dates is nevertheless treated as a break for safety.
    """
    if min_duration < 1:
        raise ValueError("min_duration must be >= 1")
    test = qualifies or (lambda v: v > threshold)

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
                    filled_days=sum(1 for r in run if r.flag == "interpolated"),
                )
            )
        run.clear()

    previous_day: date | None = None
    for record in records:
        contiguous = previous_day is not None and record.day - previous_day == timedelta(days=1)
        if run and not contiguous:
            flush()
        if record.tmax is not None and test(record.tmax):
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
    duplicates_by_year: dict[int, int] | None = None,
) -> list[AnnualIndicator]:
    """Aggregate daily records and events into per-calendar-year indicators.

    Completeness, mean and maximum use observed values only; interpolated days can still
    complete a heatwave run and are counted per year.
    """
    by_year: dict[int, list[DailyRecord]] = {y: [] for y in range(start_year, end_year + 1)}
    for r in records:
        if r.day.year in by_year:
            by_year[r.day.year].append(r)

    event_counts: Counter[int] = Counter()
    hw_days: Counter[int] = Counter()
    longest: dict[int, int] = {}
    excess_sums: Counter[int] = Counter()
    event_sums: Counter[int] = Counter()
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
                event_sums[r.day.year] += r.tmax

    result: list[AnnualIndicator] = []
    for year in range(start_year, end_year + 1):
        rows = by_year[year]
        expected = (date(year, 12, 31) - date(year, 1, 1)).days + 1
        valid = [r.tmax for r in rows if r.observed]
        completeness = len(valid) / expected
        days = hw_days.get(year, 0)
        result.append(
            AnnualIndicator(
                year=year,
                event_count=event_counts.get(year, 0),
                event_days=days,
                longest_event_days=longest.get(year, 0),
                mean_tmax=(sum(valid) / len(valid)) if valid else None,
                max_tmax=max(valid) if valid else None,
                mean_excess_c=(excess_sums[year] / days) if days else None,
                valid_days=len(valid),
                expected_days=expected,
                missing_days=expected - len(valid),
                completeness=completeness,
                sufficient_data=completeness >= min_completeness,
                received_days=sum(1 for r in rows if "missing_date" not in (r.flag, r.filled_from)),
                interpolated_days=sum(1 for r in rows if r.flag == "interpolated"),
                duplicate_dates=(duplicates_by_year or {}).get(year, 0),
                implausible_days=sum(1 for r in rows if "implausible" in (r.flag, r.filled_from)),
                outlier_days=sum(1 for r in rows if r.outlier),
                total_value=sum(valid) if valid else None,
                event_value_total=event_sums.get(year, 0.0),
            )
        )
    return result


def _daterange(start: date, end: date) -> Iterable[date]:
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)
