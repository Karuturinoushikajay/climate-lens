from __future__ import annotations

import csv
import io
import re

from ..models.schemas import AnalysisResponse

FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

ANNUAL_COLUMNS = [
    ("year", "Year"),
    ("event_count", "Heatwave events (counted in start year)"),
    ("heatwave_days", "Heatwave days"),
    ("longest_event_days", "Longest event contribution (days)"),
    ("mean_tmax_c", "Mean daily max temperature (C)"),
    ("max_tmax_c", "Highest daily max temperature (C)"),
    ("mean_excess_c", "Mean excess over threshold on heatwave days (C)"),
    ("valid_days", "Valid observation days"),
    ("expected_days", "Calendar days"),
    ("missing_days", "Missing days"),
    ("interpolated_days", "Interpolated days (gap fill)"),
    ("duplicate_dates", "Duplicate dates"),
    ("implausible_days", "Implausible values"),
    ("outlier_days", "Statistical outlier days (flagged, kept)"),
    ("completeness", "Completeness (fraction)"),
    ("sufficient_data", "Used in trend statistics"),
    ("heatwave_days_rolling_mean", "Heatwave days 5-yr rolling mean"),
    ("event_count_rolling_mean", "Events 5-yr rolling mean"),
]


def safe_cell(value: object) -> str:
    """Render a value for CSV, neutralising spreadsheet formula injection in text cells."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (int, float)):
        return repr(value) if isinstance(value, float) else str(value)
    text = str(value)
    if text.startswith(FORMULA_PREFIXES):
        return "'" + text
    return text


def safe_filename(label: str, start: int, end: int, ext: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", label).strip("-").lower()[:50] or "region"
    return f"climate-lens-{slug}-{start}-{end}.{ext}"


def build_csv(result: AnalysisResponse) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
    r = result
    dq = r.data_quality
    qa = dq.analysis
    meta = [
        ("Region", r.region.label),
        ("Region type", r.region.kind),
        ("Latitude", r.region.latitude),
        ("Longitude", r.region.longitude),
        ("Analysis period", f"{r.period.start_year}-{r.period.end_year}"),
        ("Hazard definition", r.hazard.definition),
        ("Threshold percentile", r.hazard.percentile),
        ("Minimum consecutive hot days", r.hazard.min_duration_days),
        ("Baseline mode", r.baseline.mode),
        ("Baseline period", f"{r.baseline.reference_start_year}-{r.baseline.reference_end_year}"),
        (f"{r.hazard.percentile:g}th percentile threshold (C)", r.baseline.threshold_c),
        ("Data source", f"{r.source.provider} - {r.source.dataset}"),
        ("Data retrieved at (UTC)", r.source.retrieved_at),
        ("Analysis completeness (fraction)", qa.completeness),
        ("Calendar days", qa.expected_days),
        ("Valid observed days", qa.valid_days),
        ("Missing days", qa.missing_days),
        ("Interpolated days", qa.interpolated_days),
        ("Duplicate dates", qa.duplicate_dates),
        ("Implausible values", qa.implausible_values),
        ("Statistical outlier days (flagged, kept)", qa.outlier_days),
        ("Gap fill", dq.gap_fill),
        ("Outlier method", dq.outlier_method),
        ("Algorithm version", r.algorithm_version),
        ("Generated at (UTC)", r.generated_at),
    ]
    for k, v in meta:
        writer.writerow(["#", safe_cell(k), safe_cell(v)])
    writer.writerow([])
    writer.writerow([header for _, header in ANNUAL_COLUMNS])
    for row in r.annual:
        data = row.model_dump()
        writer.writerow([safe_cell(data[field]) for field, _ in ANNUAL_COLUMNS])
    return buf.getvalue()
