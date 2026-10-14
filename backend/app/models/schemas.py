from __future__ import annotations

import re
import unicodedata
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..climate.hazards import HAZARDS, SUPPORTED_HAZARDS
from ..config import (
    MAX_ANALYSIS_SPAN_YEARS,
    MAX_BOX_SPAN_DEGREES,
    MAX_LABEL_LENGTH,
    MIN_REFERENCE_SPAN_YEARS,
    MIN_YEAR,
    latest_complete_year,
)

ALLOWED_PERCENTILES = (90.0, 92.5, 95.0, 97.5, 99.0)
DURATION_HELP = "; ".join(
    f"{k} {lo}-{hi} (default {d})" for k, (lo, hi, d) in ((k, s.duration_bounds) for k, s in HAZARDS.items())
)
BaselineMode = Literal["analysis_period", "fixed_reference"]


def sanitize_label(value: str) -> str:
    cleaned = "".join(ch for ch in unicodedata.normalize("NFKC", value) if unicodedata.category(ch)[0] != "C")
    return re.sub(r"\s+", " ", cleaned).strip()[:MAX_LABEL_LENGTH]


# ---------------------------------------------------------------- request


class AnalysisQuery(BaseModel):
    """Query parameters shared by /api/analyze, /api/export.csv and /api/export.pdf."""

    model_config = ConfigDict(extra="forbid")

    latitude: float | None = Field(None, ge=-90, le=90, description="Point latitude (WGS84)")
    longitude: float | None = Field(None, ge=-180, le=180, description="Point longitude (WGS84)")
    south: float | None = Field(None, ge=-90, le=90, description="Box southern latitude")
    west: float | None = Field(None, ge=-180, le=180, description="Box western longitude")
    north: float | None = Field(None, ge=-90, le=90, description="Box northern latitude")
    east: float | None = Field(None, ge=-180, le=180, description="Box eastern longitude")
    start_year: int = Field(1990, description="First calendar year of the analysis window")
    end_year: int = Field(2020, description="Last calendar year of the analysis window")
    label: str | None = Field(None, max_length=200, description=f"Display name (truncated to {MAX_LABEL_LENGTH} chars)")
    hazard: str = Field("heatwave", max_length=40, description=f"Hazard type: {', '.join(SUPPORTED_HAZARDS)}")
    baseline: BaselineMode = Field(
        "fixed_reference", description="Baseline mode for the threshold / normal; defaults to the fixed 1991-2020 reference period"
    )
    reference_start_year: int = Field(1991, description="Reference period start (fixed_reference only)")
    reference_end_year: int = Field(2020, description="Reference period end (fixed_reference only)")
    percentile: float = Field(
        95.0,
        description=f"Threshold percentile for heatwave (Tmax) and heavy_rainfall (wet days); ignored for drought. "
        f"One of {', '.join(f'{p:g}' for p in ALLOWED_PERCENTILES)}",
    )
    min_duration_days: int | None = Field(
        None, description=f"Minimum run length in days; per hazard: {DURATION_HELP}"
    )
    fill_gaps: bool = Field(
        False,
        description="Fill isolated one-day gaps with the mean of the neighbouring days (flagged and counted; heatwave only)",
    )

    @field_validator("percentile")
    @classmethod
    def _percentile_allowed(cls, v: float) -> float:
        if v not in ALLOWED_PERCENTILES:
            raise ValueError(f"percentile must be one of {', '.join(f'{p:g}' for p in ALLOWED_PERCENTILES)}.")
        return float(v)

    @field_validator("hazard")
    @classmethod
    def _hazard_supported(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in SUPPORTED_HAZARDS:
            raise ValueError(f"Unsupported hazard type '{v[:40]}'. Supported: {', '.join(SUPPORTED_HAZARDS)}.")
        return v

    @field_validator("label")
    @classmethod
    def _clean_label(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return sanitize_label(v) or None

    @model_validator(mode="after")
    def _check(self) -> "AnalysisQuery":
        point = (self.latitude, self.longitude)
        box = (self.south, self.west, self.north, self.east)
        has_point = any(v is not None for v in point)
        has_box = any(v is not None for v in box)
        if has_point and has_box:
            raise ValueError("Provide either latitude/longitude or a south/west/north/east box, not both.")
        if has_box:
            if any(v is None for v in box):
                raise ValueError("A box requires south, west, north and east.")
            if not self.south < self.north:  # type: ignore[operator]
                raise ValueError("Box south must be less than north.")
            if not self.west < self.east:  # type: ignore[operator]
                raise ValueError("Box west must be less than east (boxes crossing the antimeridian are not supported).")
            if self.north - self.south > MAX_BOX_SPAN_DEGREES or self.east - self.west > MAX_BOX_SPAN_DEGREES:  # type: ignore[operator]
                raise ValueError(f"Box sides must not exceed {MAX_BOX_SPAN_DEGREES:g} degrees.")
        elif not has_point or any(v is None for v in point):
            raise ValueError("Both latitude and longitude are required.")

        spec = HAZARDS[self.hazard]
        lo, hi, default = spec.duration_bounds
        if self.min_duration_days is None:
            self.min_duration_days = default
        elif not lo <= self.min_duration_days <= hi:
            raise ValueError(f"min_duration_days must be between {lo} and {hi} for {self.hazard}.")
        if self.fill_gaps and not spec.supports_gap_fill:
            raise ValueError("fill_gaps is only available for the heatwave hazard (precipitation gaps are not interpolated).")

        max_year = latest_complete_year()
        for name, year in (("start_year", self.start_year), ("end_year", self.end_year)):
            if not MIN_YEAR <= year <= max_year:
                raise ValueError(f"{name} must be between {MIN_YEAR} and {max_year}.")
        if self.start_year > self.end_year:
            raise ValueError("start_year must not be after end_year.")
        if self.end_year - self.start_year + 1 > MAX_ANALYSIS_SPAN_YEARS:
            raise ValueError(f"The analysis window may not exceed {MAX_ANALYSIS_SPAN_YEARS} years.")

        if self.baseline == "fixed_reference":
            for name, year in (("reference_start_year", self.reference_start_year), ("reference_end_year", self.reference_end_year)):
                if not MIN_YEAR <= year <= max_year:
                    raise ValueError(f"{name} must be between {MIN_YEAR} and {max_year}.")
            if self.reference_start_year > self.reference_end_year:
                raise ValueError("reference_start_year must not be after reference_end_year.")
            if self.reference_end_year - self.reference_start_year + 1 < MIN_REFERENCE_SPAN_YEARS:
                raise ValueError(f"The reference period must span at least {MIN_REFERENCE_SPAN_YEARS} years.")
            if self.reference_end_year - self.reference_start_year + 1 > MAX_ANALYSIS_SPAN_YEARS:
                raise ValueError(f"The reference period may not exceed {MAX_ANALYSIS_SPAN_YEARS} years.")
        return self

    @property
    def is_box(self) -> bool:
        return self.south is not None


# ---------------------------------------------------------------- response


class GridPointOut(BaseModel):
    latitude: float
    longitude: float
    elevation: float | None = None


class BBox(BaseModel):
    south: float
    west: float
    north: float
    east: float


class RegionOut(BaseModel):
    label: str
    kind: Literal["point", "box"]
    latitude: float
    longitude: float
    bbox: BBox | None = None
    sampled_points: list[list[float]]
    note: str


class PeriodOut(BaseModel):
    start_year: int
    end_year: int
    start_date: str
    end_date: str
    years: int


class HazardOut(BaseModel):
    type: str
    name: str = ""
    definition: str
    percentile: float | None = Field(description="Threshold percentile; null for drought")
    min_duration_days: int
    comparison: str
    variable: str = "temperature_2m_max"
    units: str = "°C"
    labels: dict[str, str] = Field(default_factory=dict, description="Display labels for the hazard's indicators")


class BaselineOut(BaseModel):
    mode: str
    reference_start_year: int
    reference_end_year: int
    threshold_c: float | None = Field(description="Heatwave threshold in °C; null for precipitation hazards")
    threshold_value: float | None = Field(None, description="Threshold in the hazard's units")
    threshold_units: str = "°C"
    normal_annual_total_mm: float | None = Field(
        None, description="Mean annual precipitation over the baseline years (precipitation hazards)"
    )
    percentile_method: str
    valid_days_used: int
    note: str


class SourceOut(BaseModel):
    provider: str
    dataset: str
    endpoint: str
    variable: str
    units: str
    timezone: str
    retrieved_at: str
    aggregation: str
    grid_points: list[GridPointOut]
    attribution: str


class CacheOut(BaseModel):
    backend: str
    analysis: Literal["hit", "miss"]
    observations: Literal["hit", "miss", "partial"]


class SummaryOut(BaseModel):
    total_events: int
    total_heatwave_days: int
    mean_events_per_year: float
    mean_heatwave_days_per_year: float
    longest_event_days: int
    longest_event_start: str | None
    longest_event_end: str | None
    peak_tmax_c: float | None
    mean_tmax_c: float | None
    peak_daily_mm: float | None = None
    mean_annual_total_mm: float | None = None
    years_analyzed: int
    years_used_for_trends: int
    excluded_years: list[int]


class AnnualOut(BaseModel):
    year: int
    event_count: int
    heatwave_days: int
    longest_event_days: int
    mean_tmax_c: float | None
    max_tmax_c: float | None
    mean_excess_c: float | None
    total_mm: float | None = None
    max_daily_mm: float | None = Field(None, description="Wettest day of the year (Rx1day)")
    event_total_mm: float | None = Field(None, description="Rain on heavy-rain days (R95pTOT-style)")
    percent_of_normal: float | None = Field(None, description="Annual total as % of the baseline normal")
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
    heatwave_days_rolling_mean: float | None
    event_count_rolling_mean: float | None


class YearDays(BaseModel):
    year: int
    days: int


class EventOut(BaseModel):
    start: str
    end: str
    duration_days: int
    peak_tmax_c: float | None
    mean_tmax_c: float | None
    mean_excess_c: float | None
    peak_value: float | None = Field(None, description="Peak daily value in the hazard's units")
    total_value: float | None = Field(None, description="Sum over the event (precipitation hazards, mm)")
    start_year: int
    year_contributions: list[YearDays]
    filled_days: int = Field(0, description="Interpolated days inside the event (gap fill only)")


class RegressionOut(BaseModel):
    n: int
    slope_per_year: float | None
    slope_per_decade: float | None
    intercept: float | None
    r_squared: float | None
    status: str
    notes: list[str]


class MannKendallOut(BaseModel):
    n: int
    alpha: float
    s: int | None
    var_s_no_ties: float | None
    var_s: float | None
    z: float | None
    p_value: float | None = Field(description="Two-sided p-value after the Hamed-Rao serial-correlation correction")
    z_uncorrected: float | None = None
    p_value_uncorrected: float | None = None
    variance_correction: float | None = Field(None, description="Hamed-Rao variance inflation n/n*, floored at 1")
    autocorrelation_lags: list[int] = []
    sen_slope_per_year: float | None
    sen_slope_ci_low: float | None = None
    sen_slope_ci_high: float | None = None
    direction: str
    significant: bool
    interpretation_code: str
    interpretation: str
    dropped_values: int
    notes: list[str]


class PeriodChangeOut(BaseModel):
    window_years: int
    first_period: str | None
    last_period: str | None
    first_mean: float | None
    last_mean: float | None
    absolute_change: float | None
    percent_change: float | None
    note: str | None


class IndicatorTrendOut(BaseModel):
    indicator: str
    units: str
    regression: RegressionOut
    mann_kendall: MannKendallOut
    period_change: PeriodChangeOut


class TrendsOut(BaseModel):
    heatwave_days: IndicatorTrendOut
    event_count: IndicatorTrendOut
    mean_tmax: IndicatorTrendOut


class QualityBlock(BaseModel):
    expected_days: int = Field(description="Calendar days in the window")
    received_days: int = Field(description="Distinct dates the provider returned inside the window")
    provided_days: int = Field(description="Same as received_days (kept for compatibility)")
    valid_days: int
    missing_days: int = Field(description="Days without a usable value: absent + null + implausible")
    missing_dates: int = Field(description="Calendar dates the provider did not return")
    null_values: int
    implausible_values: int
    duplicate_dates: int = Field(description="Extra rows for already-returned dates (first value kept)")
    interpolated_days: int = Field(0, description="Subset of the missing days filled by single-day gap fill")
    outlier_days: int = 0
    completeness: float
    accounting_ok: bool = Field(
        description="received = valid + null + implausible and calendar = valid + absent + null + implausible"
    )
    accounting: str


class OutlierDay(BaseModel):
    date: str
    tmax_c: float
    robust_z: float


class FilledDay(BaseModel):
    date: str
    tmax_c: float
    reason: str = Field(description="Original flag of the filled day: missing_date, null or implausible")


class DataQualityOut(BaseModel):
    analysis: QualityBlock
    reference: QualityBlock | None
    min_year_completeness: float
    insufficient_years: list[int]
    plausible_range_c: list[float] = Field(description="Plausible value range (in plausible_range_units)")
    plausible_range_units: str = "°C"
    gap_fill: str = Field("off", description="'off' or 'single-day linear'")
    outlier_method: str = ""
    outlier_dates: list[OutlierDay] = Field(default_factory=list, description="Up to 20 most extreme flagged days")
    outlier_total: int = Field(0, description="All flagged outlier days; outlier_dates may be a truncated list")
    filled_dates: list[FilledDay] = Field(default_factory=list, description="Up to 50 interpolated days")
    filled_total: int = 0


class AnalysisResponse(BaseModel):
    request: dict
    region: RegionOut
    period: PeriodOut
    hazard: HazardOut
    baseline: BaselineOut
    source: SourceOut
    cache: CacheOut
    summary: SummaryOut
    annual: list[AnnualOut]
    events: list[EventOut]
    trends: TrendsOut
    data_quality: DataQualityOut
    insights: list[str]
    caveats: list[str]
    algorithm_version: str
    generated_at: str


class PresetRegion(BaseModel):
    id: str
    name: str
    kind: Literal["city", "state"]
    latitude: float
    longitude: float
    bbox: BBox | None = None


class RegionsResponse(BaseModel):
    regions: list[PresetRegion]
    note: str


class GeocodeQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., description="Place name to search for, e.g. 'Phoenix'")
    count: int = Field(5, ge=1, le=10, description="Maximum number of matches")

    @field_validator("name")
    @classmethod
    def _clean_name(cls, v: str) -> str:
        cleaned = sanitize_label(v)
        if len(cleaned) < 2:
            raise ValueError("Enter at least 2 characters to search.")
        return cleaned


class Place(BaseModel):
    id: int | None = None
    name: str
    latitude: float
    longitude: float
    admin1: str | None = None
    country: str | None = None
    country_code: str | None = None
    timezone: str | None = None
    population: int | None = None


class GeocodeResponse(BaseModel):
    query: str
    results: list[Place]
    provider: str
    attribution: str
    cache: Literal["hit", "miss"]


class HealthResponse(BaseModel):
    status: str
    version: str
    algorithm_version: str
    environment: str
    cache: dict
    data_source: dict
    limits: dict


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[dict] | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody
