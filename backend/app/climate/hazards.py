"""Hazard definitions: data variable, units, plausible range, labels and wording per hazard.

Heavy rainfall and drought follow ETCCDI-style indices computed from daily precipitation:
heavy-rain days above a wet-day percentile (R95p-style) and consecutive dry days (CDD).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from .heatwave import PLAUSIBLE_TMAX_RANGE_C, AnnualIndicator, DailyRecord, detect_events, percentile_threshold

WET_DAY_MM = 1.0
DRY_DAY_MM = 1.0
PLAUSIBLE_PRECIP_RANGE_MM = (0.0, 2000.0)


@dataclass(frozen=True)
class InsightWords:
    event_noun: str  # "heatwave event(s)"
    day_noun: str  # "heatwave day(s)"
    days_phrase: str  # "annual heatwave days"
    third_phrase: str  # "Annual mean daily maximum temperature"
    third_units: str
    third_decimals: int


@dataclass(frozen=True)
class HazardSpec:
    key: str
    name: str
    variable: str
    units: str
    plausible_range: tuple[float, float]
    duration_bounds: tuple[int, int, int]  # min, max, default
    uses_percentile: bool
    supports_gap_fill: bool
    flags_outliers: bool
    labels: dict[str, str]
    words: InsightWords


HAZARDS: dict[str, HazardSpec] = {
    "heatwave": HazardSpec(
        key="heatwave",
        name="Heatwave",
        variable="temperature_2m_max",
        units="°C",
        plausible_range=PLAUSIBLE_TMAX_RANGE_C,
        duration_bounds=(2, 10, 3),
        uses_percentile=True,
        supports_gap_fill=True,
        flags_outliers=True,
        labels={
            "days": "Heatwave days",
            "events": "Heatwave events",
            "longest": "Longest event",
            "threshold": "pct threshold",
            "qualifying_day": "hot day",
            "third": "Mean Tmax",
            "third_long": "Annual mean daily maximum temperature",
        },
        words=InsightWords(
            "heatwave event(s)", "heatwave day(s)", "annual heatwave days",
            "Annual mean daily maximum temperature", "°C", 2,
        ),
    ),
    "heavy_rainfall": HazardSpec(
        key="heavy_rainfall",
        name="Heavy rainfall",
        variable="precipitation_sum",
        units="mm",
        plausible_range=PLAUSIBLE_PRECIP_RANGE_MM,
        duration_bounds=(1, 10, 1),
        uses_percentile=True,
        supports_gap_fill=False,
        flags_outliers=False,
        labels={
            "days": "Heavy-rain days",
            "events": "Heavy-rain events",
            "longest": "Longest heavy-rain run",
            "threshold": "pct wet-day threshold",
            "qualifying_day": "heavy-rain day",
            "third": "Annual total",
            "third_long": "Annual total precipitation",
        },
        words=InsightWords(
            "heavy-rain event(s)", "heavy-rain day(s)", "annual heavy-rain days",
            "Annual total precipitation", "mm", 0,
        ),
    ),
    "drought": HazardSpec(
        key="drought",
        name="Drought (dry spells)",
        variable="precipitation_sum",
        units="mm",
        plausible_range=PLAUSIBLE_PRECIP_RANGE_MM,
        duration_bounds=(5, 60, 15),
        uses_percentile=False,
        supports_gap_fill=False,
        flags_outliers=False,
        labels={
            "days": "Dry-spell days",
            "events": "Dry spells",
            "longest": "Longest dry spell (CDD)",
            "threshold": "Dry-day threshold",
            "qualifying_day": "dry day",
            "third": "Annual total",
            "third_long": "Annual total precipitation",
        },
        words=InsightWords(
            "dry spell(s)", "dry-spell day(s)", "annual dry-spell days",
            "Annual total precipitation", "mm", 0,
        ),
    ),
}

SUPPORTED_HAZARDS = tuple(HAZARDS)
PRECIP_OUTLIER_NOTE = "not applied to precipitation (a skewed distribution with many zero days)"


def is_dry(value: float) -> bool:
    return value < DRY_DAY_MM


def wet_day_threshold(values: Iterable[float | None], percentile: float) -> tuple[float | None, int]:
    """Percentile of wet-day (>= 1 mm) values, and the number of wet days it is based on."""
    wet = [v for v in values if v is not None and v >= WET_DAY_MM]
    return percentile_threshold(wet, percentile), len(wet)


def longest_runs_by_year(records: Sequence[DailyRecord], qualifying=is_dry) -> dict[int, int]:
    """Longest run of qualifying days attributed to each calendar year (CDD for dry days)."""
    longest: dict[int, int] = {}
    for spell in detect_events(records, 0.0, 1, qualifying):
        for year, days in spell.year_contributions.items():
            longest[year] = max(longest.get(year, 0), days)
    return longest


def normal_annual_total(annual: Sequence[AnnualIndicator]) -> float | None:
    """Mean annual total over the years with sufficient data."""
    totals = [a.total_value for a in annual if a.sufficient_data and a.total_value is not None]
    return sum(totals) / len(totals) if totals else None
