from __future__ import annotations

import csv
import io
import re

from ..models.schemas import AnalysisResponse

FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

ANNUAL_COLUMNS = [
    ("year", "Year"),
    ("event_count", "Heatwave events (counted in start year)"),
    ("event_days", "Heatwave days"),
    ("longest_event_days", "Longest event contribution (days)"),
    ("mean_tmax_c", "Mean daily max temperature (C)"),
    ("max_tmax_c", "Highest daily max temperature (C)"),
    ("mean_excess_c", "Mean excess over threshold on heatwave days (C)"),
    ("expected_days", "Calendar days"),
    ("received_days", "Days received from source"),
    ("valid_days", "Valid observation days"),
    ("missing_days", "Unusable days (missing + implausible)"),
    ("interpolated_days", "Interpolated days (gap fill)"),
    ("duplicate_dates", "Duplicate dates"),
    ("implausible_days", "Implausible values"),
    ("outlier_days", "Statistical outlier days (flagged, kept)"),
    ("completeness", "Completeness (fraction)"),
    ("sufficient_data", "Used in trend statistics"),
    ("event_days_rolling_mean", "Heatwave days 5-yr rolling mean"),
    ("event_count_rolling_mean", "Events 5-yr rolling mean"),
]
TEMPERATURE_FIELDS = ("mean_tmax_c", "max_tmax_c", "mean_excess_c")


def annual_columns(r: AnalysisResponse) -> list[tuple[str, str]]:
    """Heatwave keeps the original columns; precipitation hazards swap labels and value columns."""
    if r.hazard.type == "heatwave":
        return ANNUAL_COLUMNS
    labels = r.hazard.labels
    precip_cols = [
        ("total_mm", "Annual precipitation (mm)"),
        ("max_daily_mm", "Wettest day (mm)"),
        ("percent_of_normal", "Annual precipitation (% of baseline normal)"),
    ]
    if r.hazard.type == "heavy_rainfall":
        precip_cols.insert(2, ("event_total_mm", "Rain on heavy-rain event days (mm)"))
    renamed = {
        "event_count": f"{labels['events']} (counted in start year)",
        "event_days": labels["days"],
        "longest_event_days": (
            "Longest dry spell in year (CDD, days)" if r.hazard.type == "drought" else f"{labels['longest']} (days)"
        ),
        "event_days_rolling_mean": f"{labels['days']} 5-yr rolling mean",
    }
    cols: list[tuple[str, str]] = []
    for field, header in ANNUAL_COLUMNS:
        if field in TEMPERATURE_FIELDS:
            if field == TEMPERATURE_FIELDS[0]:
                cols += precip_cols
            continue
        cols.append((field, renamed.get(field, header)))
    return cols


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


def _slug(text: str, limit: int) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()[:limit]


def safe_filename(label: str, hazard: str, start: int, end: int, ext: str) -> str:
    slug = _slug(label, 50) or "region"
    hazard_slug = _slug(hazard, 20) or "hazard"
    return f"climate-lens-{slug}-{hazard_slug}-{start}-{end}.{ext}"


def build_csv(result: AnalysisResponse) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
    r = result
    dq = r.data_quality
    qa = dq.analysis
    heat = r.hazard.type == "heatwave"
    unit = "C" if heat else r.hazard.units
    if r.hazard.percentile is not None:
        threshold_row = (f"{r.hazard.percentile:g}th percentile threshold ({unit})", r.baseline.threshold_value)
    else:
        threshold_row = (f"Dry-day threshold (below, {unit})", r.baseline.threshold_value)
    qualifying_day = r.hazard.labels.get("qualifying_day", "hot day")
    meta = [
        ("Region", r.region.label),
        ("Region type", r.region.kind),
        ("Latitude", r.region.latitude),
        ("Longitude", r.region.longitude),
        ("Analysis period", f"{r.period.start_year}-{r.period.end_year}"),
        ("Hazard", r.hazard.name),
        ("Hazard definition", r.hazard.definition),
        *([("Threshold percentile", r.hazard.percentile)] if r.hazard.percentile is not None else []),
        (f"Minimum consecutive {qualifying_day}s", r.hazard.min_duration_days),
        ("Baseline mode", r.baseline.mode),
        ("Baseline period", f"{r.baseline.reference_start_year}-{r.baseline.reference_end_year}"),
        threshold_row,
        *([] if heat else [("Baseline normal annual precipitation (mm)", r.baseline.normal_annual_total_mm)]),
        ("Data source", f"{r.source.provider} - {r.source.dataset}"),
        ("Data retrieved at (UTC)", r.source.retrieved_at),
        ("Analysis completeness (fraction)", qa.completeness),
        ("Calendar days", qa.expected_days),
        ("Days received from source", qa.received_days),
        ("Valid observed days", qa.valid_days),
        ("Missing days (absent + null)", qa.missing_dates + qa.null_values),
        ("Absent dates", qa.missing_dates),
        ("Null values", qa.null_values),
        ("Implausible values", qa.implausible_values),
        ("Duplicate dates", qa.duplicate_dates),
        ("Interpolated days", qa.interpolated_days),
        ("Statistical outlier days (flagged, kept)", qa.outlier_days),
        ("Accounting check", ("OK: " if qa.accounting_ok else "MISMATCH: ") + qa.accounting),
        ("Gap fill", dq.gap_fill),
        ("Outlier method", dq.outlier_method),
        ("Algorithm version", r.algorithm_version),
        ("Generated at (UTC)", r.generated_at),
    ]
    for k, v in meta:
        writer.writerow(["#", safe_cell(k), safe_cell(v)])
    for f in dq.filled_dates:
        writer.writerow(["#", f"Filled day (date, value {unit}, original flag)", f.date, safe_cell(f.value), f.reason])
    if dq.filled_total > len(dq.filled_dates):
        writer.writerow(["#", "Filled days listed", f"{len(dq.filled_dates)} of {dq.filled_total}"])
    for o in dq.outlier_dates:
        writer.writerow(["#", f"Outlier day (date, value {unit}, robust z)", o.date, safe_cell(o.value), safe_cell(o.robust_z)])
    if dq.outlier_dates:
        writer.writerow(["#", "Outlier days listed", f"{len(dq.outlier_dates)} of {dq.outlier_total}"])
    writer.writerow([])
    columns = annual_columns(r)
    writer.writerow([header for _, header in columns])
    for row in r.annual:
        data = row.model_dump()
        writer.writerow([safe_cell(data[field]) for field, _ in columns])
    return buf.getvalue()
