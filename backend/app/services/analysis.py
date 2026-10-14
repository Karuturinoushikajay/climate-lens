"""Analysis orchestration: observations (cached) -> heatwave detection -> trends -> response.

The dashboard JSON, CSV export and PDF report are all produced from ``AnalysisService.analyze``
so they always share identical numbers.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any

from ..cache import CacheStore, make_key
from ..climate import ALGORITHM_VERSION
from ..climate.heatwave import (
    OUTLIER_METHOD,
    PERCENTILE_METHOD,
    PLAUSIBLE_TMAX_RANGE_C,
    AnnualIndicator,
    DailyRecord,
    DataQuality,
    annual_indicators,
    build_daily_series,
    detect_events,
    flag_outliers,
    percentile_threshold,
)
from ..climate.mann_kendall import MannKendallResult, mann_kendall
from ..climate.trends import (
    PercentChange,
    RegressionResult,
    build_insights,
    linear_regression,
    period_change,
    rolling_mean,
)
from ..config import Settings
from ..models.schemas import (
    AnalysisQuery,
    AnalysisResponse,
    AnnualOut,
    BaselineOut,
    BBox,
    CacheOut,
    DataQualityOut,
    EventOut,
    FilledDay,
    GridPointOut,
    HazardOut,
    IndicatorTrendOut,
    MannKendallOut,
    OutlierDay,
    PeriodChangeOut,
    PeriodOut,
    QualityBlock,
    RegionOut,
    RegressionOut,
    SourceOut,
    SummaryOut,
    TrendsOut,
    YearDays,
)
from .weather import ATTRIBUTION, DATASET, MODEL, PROVIDER, VARIABLE, OpenMeteoClient, WeatherSeries

logger = logging.getLogger(__name__)

ROLLING_WINDOW_YEARS = 5
MAX_OUTLIER_DATES = 20
MAX_FILLED_DATES = 50
OBSERVATION_SCHEMA = "obs-v1"


def sample_points(q: AnalysisQuery) -> list[tuple[float, float]]:
    """Point query -> the point. Box -> up to a 2x2 grid of cell centres (quota-bounded)."""
    if not q.is_box:
        return [(round(q.latitude, 4), round(q.longitude, 4))]  # type: ignore[arg-type]
    s, w, n, e = q.south, q.west, q.north, q.east
    n_lat = 1 if n - s < 0.25 else 2  # type: ignore[operator]
    n_lon = 1 if e - w < 0.25 else 2  # type: ignore[operator]
    points = []
    for i in range(n_lat):
        lat = s + (i + 0.5) * (n - s) / n_lat  # type: ignore[operator]
        for j in range(n_lon):
            lon = w + (j + 0.5) * (e - w) / n_lon  # type: ignore[operator]
            points.append((round(lat, 4), round(lon, 4)))
    return points


def _quality_block(q: DataQuality) -> QualityBlock:
    return QualityBlock(
        expected_days=q.expected_days,
        received_days=q.received_days,
        provided_days=q.received_days,
        valid_days=q.valid_days,
        missing_days=q.missing_days,
        missing_dates=q.missing_dates,
        null_values=q.null_values,
        implausible_values=q.implausible_values,
        duplicate_dates=q.duplicate_dates,
        interpolated_days=q.interpolated_days,
        outlier_days=q.outlier_days,
        completeness=round(q.completeness, 6),
        accounting_ok=q.accounting_ok,
        accounting=(
            f"{q.expected_days} calendar days = {q.valid_days} valid + {q.absent_or_null_days} missing "
            f"({q.missing_dates} absent, {q.null_values} null) + {q.implausible_values} implausible; "
            f"{q.received_days} received from the source = {q.valid_days} valid + {q.null_values} null + "
            f"{q.implausible_values} implausible"
            + (f" ({q.duplicate_dates} duplicate rows ignored)" if q.duplicate_dates else "")
        ),
    )


def _observed(records: list[DailyRecord]):
    return (r.tmax for r in records if r.observed)


def _regression_out(r: RegressionResult) -> RegressionOut:
    return RegressionOut(
        n=r.n,
        slope_per_year=r.slope,
        slope_per_decade=r.slope * 10 if r.slope is not None else None,
        intercept=r.intercept,
        r_squared=r.r_squared,
        status=r.status,
        notes=r.notes,
    )


def _mk_out(r: MannKendallResult) -> MannKendallOut:
    return MannKendallOut(
        n=r.n,
        alpha=r.alpha,
        s=r.s,
        var_s_no_ties=r.var_s_no_ties,
        var_s=r.var_s,
        z=r.z,
        p_value=r.p_value,
        z_uncorrected=r.z_uncorrected,
        p_value_uncorrected=r.p_value_uncorrected,
        variance_correction=r.variance_correction,
        autocorrelation_lags=r.autocorrelation_lags,
        sen_slope_per_year=r.sen_slope,
        sen_slope_ci_low=r.sen_slope_ci_low,
        sen_slope_ci_high=r.sen_slope_ci_high,
        direction=r.direction,
        significant=r.significant,
        interpretation_code=r.interpretation_code,
        interpretation=r.interpretation,
        dropped_values=r.dropped_values,
        notes=r.notes,
    )


def _change_out(c: PercentChange) -> PeriodChangeOut:
    return PeriodChangeOut(
        window_years=c.window_years,
        first_period=c.first_period,
        last_period=c.last_period,
        first_mean=c.first_mean,
        last_mean=c.last_mean,
        absolute_change=c.absolute_change,
        percent_change=c.percent_change,
        note=c.note,
    )


class AnalysisService:
    def __init__(self, settings: Settings, cache: CacheStore, weather: OpenMeteoClient):
        self.settings = settings
        self.cache = cache
        self.weather = weather

    # ------------------------------------------------------------ public

    def analyze(self, q: AnalysisQuery) -> AnalysisResponse:
        points = sample_points(q)
        key_params = self._analysis_key_params(q, points)
        key = make_key("analysis", key_params)

        cached = self.cache.get("analyses", key)
        if cached is not None and cached.get("algorithm_version") == ALGORITHM_VERSION:
            try:
                response = AnalysisResponse.model_validate(cached)
                response.cache = CacheOut(backend=self.cache.mode, analysis="hit", observations="hit")
                return response
            except ValueError:
                logger.warning("Discarding incompatible cached analysis %s", key)

        response = self._compute(q, points, key_params)
        self.cache.set(
            "analyses", key, response.model_dump(mode="json"), self.settings.analysis_cache_ttl_hours * 3600
        )
        return response

    # ------------------------------------------------------------ observations

    def _observations(self, points: list[tuple[float, float]], start: date, end: date) -> tuple[WeatherSeries, bool]:
        key = make_key(
            "obs",
            {"schema": OBSERVATION_SCHEMA, "points": points, "start": start, "end": end, "variable": VARIABLE, "model": MODEL},
        )
        doc = self.cache.get("observations", key)
        if doc is not None:
            try:
                return WeatherSeries.from_document(doc), True
            except (KeyError, TypeError, ValueError):
                logger.warning("Discarding malformed cached observations %s", key)
        series = self.weather.fetch_daily_tmax(points, start, end)
        self.cache.set("observations", key, series.to_document(), self.settings.observation_cache_ttl_hours * 3600)
        return series, False

    def _fetch_ranges(
        self, points: list[tuple[float, float]], q: AnalysisQuery
    ) -> tuple[WeatherSeries, WeatherSeries | None, str]:
        a_start, a_end = q.start_year, q.end_year
        if q.baseline != "fixed_reference":
            series, hit = self._observations(points, date(a_start, 1, 1), date(a_end, 12, 31))
            return series, None, "hit" if hit else "miss"

        r_start, r_end = q.reference_start_year, q.reference_end_year
        if r_start <= a_end + 1 and a_start <= r_end + 1:  # overlapping or adjacent -> one request
            lo, hi = min(a_start, r_start), max(a_end, r_end)
            series, hit = self._observations(points, date(lo, 1, 1), date(hi, 12, 31))
            return series, series, "hit" if hit else "miss"

        a_series, a_hit = self._observations(points, date(a_start, 1, 1), date(a_end, 12, 31))
        r_series, r_hit = self._observations(points, date(r_start, 1, 1), date(r_end, 12, 31))
        status = "hit" if a_hit and r_hit else "miss" if not (a_hit or r_hit) else "partial"
        return a_series, r_series, status

    # ------------------------------------------------------------ computation

    def _compute(self, q: AnalysisQuery, points: list[tuple[float, float]], key_params: dict[str, Any]) -> AnalysisResponse:
        a_series, r_series, obs_status = self._fetch_ranges(points, q)
        a_start, a_end = date(q.start_year, 1, 1), date(q.end_year, 12, 31)

        records, quality = build_daily_series(
            a_series.dates, a_series.tmax, a_start, a_end, fill_single_gaps=q.fill_gaps
        )
        records, quality.outlier_days = flag_outliers(records)

        ref_quality: DataQuality | None = None
        if q.baseline == "fixed_reference" and r_series is not None:
            r_start, r_end = date(q.reference_start_year, 1, 1), date(q.reference_end_year, 12, 31)
            ref_records, ref_quality = build_daily_series(r_series.dates, r_series.tmax, r_start, r_end)
            ref_records, ref_quality.outlier_days = flag_outliers(ref_records)
            threshold = percentile_threshold(_observed(ref_records), q.percentile)
            threshold_days = ref_quality.valid_days
            baseline_note = (
                f"Threshold computed from {q.reference_start_year}-{q.reference_end_year} observations and applied "
                f"to {q.start_year}-{q.end_year}. Results are not comparable with analyses using another baseline."
            )
            ref_years = (q.reference_start_year, q.reference_end_year)
        else:
            threshold = percentile_threshold(_observed(records), q.percentile)
            threshold_days = quality.valid_days
            baseline_note = (
                f"Threshold computed from the selected analysis period ({q.start_year}-{q.end_year}); "
                "changing the period changes the threshold."
            )
            ref_years = (q.start_year, q.end_year)

        events = detect_events(records, threshold, q.min_duration_days) if threshold is not None else []
        annual = annual_indicators(
            records,
            events,
            threshold,
            q.start_year,
            q.end_year,
            self.settings.min_year_completeness,
            duplicates_by_year=quality.duplicates_by_year,
        )
        outliers = sorted((r for r in records if r.outlier), key=lambda r: -abs(r.outlier_z or 0))[:MAX_OUTLIER_DATES]
        filled = [r for r in records if r.flag == "interpolated"]

        label = q.label or self._default_label(q)
        trends, raw_trends = self._trends(annual)
        summary = self._summary(records, events, annual)
        if threshold is not None:
            days_reg, days_mk, days_change = raw_trends["heatwave_days"]
            insights = build_insights(
                label,
                q.start_year,
                q.end_year,
                summary.total_events,
                summary.total_heatwave_days,
                days_change,
                days_reg,
                days_mk,
                raw_trends["event_count"][1],
                summary.excluded_years,
                tmax_change=raw_trends["mean_tmax"][2],
                tmax_mk=raw_trends["mean_tmax"][1],
            )
        else:
            insights = ["No valid temperature observations were available, so no heatwave analysis could be performed."]

        return AnalysisResponse(
            request=key_params,
            region=self._region(q, points, label),
            period=PeriodOut(
                start_year=q.start_year,
                end_year=q.end_year,
                start_date=a_start.isoformat(),
                end_date=a_end.isoformat(),
                years=q.end_year - q.start_year + 1,
            ),
            hazard=HazardOut(
                type="heatwave",
                definition=(
                    f"At least {q.min_duration_days} consecutive valid days with daily maximum temperature strictly "
                    f"greater than the {q.percentile:g}th-percentile threshold."
                ),
                percentile=q.percentile,
                min_duration_days=q.min_duration_days,
                comparison="strictly greater than",
            ),
            baseline=BaselineOut(
                mode=q.baseline,
                reference_start_year=ref_years[0],
                reference_end_year=ref_years[1],
                threshold_c=round(threshold, 4) if threshold is not None else None,
                percentile_method=f"numpy '{PERCENTILE_METHOD}' interpolation (Hyndman & Fan type 7)",
                valid_days_used=threshold_days,
                note=baseline_note,
            ),
            source=SourceOut(
                provider=PROVIDER,
                dataset=DATASET,
                endpoint=a_series.endpoint,
                variable=VARIABLE,
                units=a_series.units,
                timezone=a_series.timezone,
                retrieved_at=a_series.retrieved_at,
                aggregation=a_series.aggregation,
                grid_points=[GridPointOut(**vars(g)) for g in a_series.grid_points],
                attribution=ATTRIBUTION,
            ),
            cache=CacheOut(backend=self.cache.mode, analysis="miss", observations=obs_status),  # type: ignore[arg-type]
            summary=summary,
            annual=self._annual_out(annual),
            events=[
                EventOut(
                    start=e.start.isoformat(),
                    end=e.end.isoformat(),
                    duration_days=e.duration_days,
                    peak_tmax_c=round(e.peak_tmax, 2),
                    mean_tmax_c=round(e.mean_tmax, 2),
                    mean_excess_c=round(e.mean_excess_c, 2),
                    start_year=e.start_year,
                    year_contributions=[YearDays(year=y, days=d) for y, d in e.year_contributions.items()],
                    filled_days=e.filled_days,
                )
                for e in events
            ],
            trends=trends,
            data_quality=DataQualityOut(
                analysis=_quality_block(quality),
                reference=_quality_block(ref_quality) if ref_quality else None,
                min_year_completeness=self.settings.min_year_completeness,
                insufficient_years=[a.year for a in annual if not a.sufficient_data],
                plausible_range_c=list(PLAUSIBLE_TMAX_RANGE_C),
                gap_fill="single-day linear" if q.fill_gaps else "off",
                outlier_method=OUTLIER_METHOD,
                outlier_dates=[
                    OutlierDay(date=r.day.isoformat(), tmax_c=round(r.tmax, 2), robust_z=r.outlier_z)  # type: ignore[arg-type]
                    for r in outliers
                ],
                outlier_total=quality.outlier_days,
                filled_dates=[
                    FilledDay(date=r.day.isoformat(), tmax_c=round(r.tmax, 2), reason=r.filled_from or "")  # type: ignore[arg-type]
                    for r in filled[:MAX_FILLED_DATES]
                ],
                filled_total=len(filled),
            ),
            insights=insights,
            caveats=self._caveats(q, threshold),
            algorithm_version=ALGORITHM_VERSION,
            generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )

    # ------------------------------------------------------------ helpers

    def _analysis_key_params(self, q: AnalysisQuery, points: list[tuple[float, float]]) -> dict[str, Any]:
        params: dict[str, Any] = {
            "algorithm_version": ALGORITHM_VERSION,
            "hazard": q.hazard,
            "percentile": q.percentile,
            "min_duration_days": q.min_duration_days,
            "fill_gaps": q.fill_gaps,
            "points": [list(p) for p in points],
            "start_year": q.start_year,
            "end_year": q.end_year,
            "baseline": q.baseline,
            "min_year_completeness": self.settings.min_year_completeness,
            "label": q.label,
        }
        if q.is_box:
            params["bbox"] = [q.south, q.west, q.north, q.east]
        if q.baseline == "fixed_reference":
            params["reference_start_year"] = q.reference_start_year
            params["reference_end_year"] = q.reference_end_year
        return params

    @staticmethod
    def _default_label(q: AnalysisQuery) -> str:
        if q.is_box:
            return f"Box {q.south:.2f}..{q.north:.2f}N, {q.west:.2f}..{q.east:.2f}E"
        return f"Point {q.latitude:.4f}, {q.longitude:.4f}"

    @staticmethod
    def _region(q: AnalysisQuery, points: list[tuple[float, float]], label: str) -> RegionOut:
        if q.is_box:
            return RegionOut(
                label=label,
                kind="box",
                latitude=round((q.south + q.north) / 2, 4),  # type: ignore[operator]
                longitude=round((q.west + q.east) / 2, 4),  # type: ignore[operator]
                bbox=BBox(south=q.south, west=q.west, north=q.north, east=q.east),  # type: ignore[arg-type]
                sampled_points=[list(p) for p in points],
                note=(
                    f"Daily maximum temperature is the mean of {len(points)} sampled grid point(s) inside the box. "
                    "This is a coarse spatial sample, not an area-weighted or administrative-boundary average."
                ),
            )
        return RegionOut(
            label=label,
            kind="point",
            latitude=points[0][0],
            longitude=points[0][1],
            sampled_points=[list(p) for p in points],
            note=(
                "Results describe the reanalysis grid cell containing this point, not an entire city "
                "or administrative area."
            ),
        )

    @staticmethod
    def _summary(records, events, annual: list[AnnualIndicator]) -> SummaryOut:
        valid = list(_observed(records))
        longest = max(events, key=lambda e: e.duration_days, default=None)
        years = len(annual)
        used = [a for a in annual if a.sufficient_data]
        total_events = len(events)
        total_days = sum(e.duration_days for e in events)
        return SummaryOut(
            total_events=total_events,
            total_heatwave_days=total_days,
            mean_events_per_year=round(total_events / years, 4) if years else 0.0,
            mean_heatwave_days_per_year=round(total_days / years, 4) if years else 0.0,
            longest_event_days=longest.duration_days if longest else 0,
            longest_event_start=longest.start.isoformat() if longest else None,
            longest_event_end=longest.end.isoformat() if longest else None,
            peak_tmax_c=round(max(valid), 2) if valid else None,
            mean_tmax_c=round(sum(valid) / len(valid), 2) if valid else None,
            years_analyzed=years,
            years_used_for_trends=len(used),
            excluded_years=[a.year for a in annual if not a.sufficient_data],
        )

    @staticmethod
    def _annual_out(annual: list[AnnualIndicator]) -> list[AnnualOut]:
        days = [a.heatwave_days if a.sufficient_data else None for a in annual]
        counts = [a.event_count if a.sufficient_data else None for a in annual]
        days_rm = rolling_mean(days, ROLLING_WINDOW_YEARS)
        counts_rm = rolling_mean(counts, ROLLING_WINDOW_YEARS)
        return [
            AnnualOut(
                year=a.year,
                event_count=a.event_count,
                heatwave_days=a.heatwave_days,
                longest_event_days=a.longest_event_days,
                mean_tmax_c=round(a.mean_tmax, 2) if a.mean_tmax is not None else None,
                max_tmax_c=round(a.max_tmax, 2) if a.max_tmax is not None else None,
                mean_excess_c=round(a.mean_excess_c, 2) if a.mean_excess_c is not None else None,
                valid_days=a.valid_days,
                expected_days=a.expected_days,
                missing_days=a.missing_days,
                completeness=round(a.completeness, 4),
                sufficient_data=a.sufficient_data,
                received_days=a.received_days,
                interpolated_days=a.interpolated_days,
                duplicate_dates=a.duplicate_dates,
                implausible_days=a.implausible_days,
                outlier_days=a.outlier_days,
                heatwave_days_rolling_mean=round(dr, 3) if dr is not None else None,
                event_count_rolling_mean=round(cr, 3) if cr is not None else None,
            )
            for a, dr, cr in zip(annual, days_rm, counts_rm)
        ]

    @staticmethod
    def _trends(
        annual: list[AnnualIndicator],
    ) -> tuple[TrendsOut, dict[str, tuple[RegressionResult, MannKendallResult, PercentChange]]]:
        used = [a for a in annual if a.sufficient_data]
        years = [a.year for a in used]
        raw: dict[str, tuple[RegressionResult, MannKendallResult, PercentChange]] = {}

        def indicator(key: str, name: str, units: str, values: list[float | None]) -> IndicatorTrendOut:
            reg = linear_regression(years, values)
            mk = mann_kendall(values, x=years)
            change = period_change(years, values, ROLLING_WINDOW_YEARS)
            raw[key] = (reg, mk, change)
            return IndicatorTrendOut(
                indicator=name,
                units=units,
                regression=_regression_out(reg),
                mann_kendall=_mk_out(mk),
                period_change=_change_out(change),
            )

        trends = TrendsOut(
            heatwave_days=indicator("heatwave_days", "Annual heatwave days", "days/year", [a.heatwave_days for a in used]),
            event_count=indicator("event_count", "Annual heatwave events", "events/year", [a.event_count for a in used]),
            mean_tmax=indicator(
                "mean_tmax", "Annual mean daily maximum temperature", "°C", [a.mean_tmax for a in used]
            ),
        )
        return trends, raw

    @staticmethod
    def _caveats(q: AnalysisQuery, threshold: float | None) -> list[str]:
        caveats = [
            f"Data source: {DATASET}. Reanalysis values are model estimates, not weather-station observations.",
            "Daily maximum temperature is aggregated in the location's local time zone.",
            "Events touching the first or last day of the analysis window may be truncated by the window.",
            "Linear regression describes the observed record; it is not a forecast and its slope alone does not "
            "establish statistical significance.",
            "Mann-Kendall p-values are adjusted for serial correlation (Hamed-Rao variance correction); the "
            "uncorrected values are reported alongside. Three indicators are tested without a multiple-testing "
            "correction.",
            "A non-significant result does not prove the absence of a trend, and neither test establishes causation.",
            f"Percentile thresholds are relative to this location's own climate: the {q.percentile:g}th percentile "
            "here is a different temperature from the same percentile elsewhere.",
            "Statistical outliers are flagged for review but kept in the analysis, because genuine heat extremes "
            "are also unusual.",
        ]
        if q.fill_gaps:
            caveats.append(
                "Single-day gap fill is on: an isolated missing day between two observed days is set to their mean, "
                "flagged as interpolated, and can complete a heatwave run. Interpolated days are never used for the "
                "threshold, completeness, or annual mean and maximum."
            )
        else:
            caveats.append(
                "Missing observations are never interpolated or zero-filled; any missing day breaks a heatwave run, "
                "which can under-count events in incomplete years."
            )
        if q.baseline == "analysis_period":
            caveats.insert(
                0,
                f"The {q.percentile:g}th-percentile threshold is derived from the selected analysis period, so results "
                "for different periods use different thresholds and should not be compared directly.",
            )
        if threshold is None:
            caveats.insert(0, "No valid observations were available to compute a threshold.")
        return caveats
