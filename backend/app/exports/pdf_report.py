"""Server-side PDF report built with ReportLab from an ``AnalysisResponse``."""

from __future__ import annotations

import io
from datetime import datetime, timezone
from xml.sax.saxutils import escape

from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from ..models.schemas import AnalysisResponse, IndicatorTrendOut

FOREST = colors.HexColor("#1f3d33")
MINT = colors.HexColor("#7fd1b9")
AMBER = colors.HexColor("#e0a03a")
GRID = colors.HexColor("#c9d3cf")
ZEBRA = colors.HexColor("#f2f6f4")


def _fmt(value: object, digits: int = 2, suffix: str = "") -> str:
    if value is None:
        return "n/a"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return f"{value:.{digits}f}{suffix}"
    return f"{value}{suffix}"


def _p_value(p: float | None) -> str:
    if p is None:
        return "undefined"
    return "< 0.0001" if p < 1e-4 else f"{p:.4f}"


class _NumberedCanvas(rl_canvas.Canvas):
    """Canvas that writes 'Page X of Y' after all pages are laid out."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_states: list[dict] = []

    def showPage(self):  # noqa: N802 - ReportLab API
        self._saved_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved_states)
        for state in self._saved_states:
            self.__dict__.update(state)
            self.setFont("Helvetica", 8)
            self.setFillColor(colors.grey)
            self.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Page {self._pageNumber} of {total}")
            self.drawString(18 * mm, 10 * mm, "Climate Lens - Climate Hazard Trend Analyzer")
            super().showPage()
        super().save()


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("title", parent=base["Title"], textColor=FOREST, alignment=TA_LEFT, fontSize=20),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], textColor=FOREST, spaceBefore=10, spaceAfter=4),
        "body": ParagraphStyle("body", parent=base["BodyText"], fontSize=9, leading=12),
        "small": ParagraphStyle("small", parent=base["BodyText"], fontSize=8, leading=10, textColor=colors.HexColor("#444444")),
        "cell": ParagraphStyle("cell", parent=base["BodyText"], fontSize=8, leading=10),
    }


def _table(rows: list[list[object]], col_widths: list[float] | None = None, header: bool = True) -> Table:
    t = Table(rows, colWidths=col_widths, repeatRows=1 if header else 0, hAlign="LEFT")
    style = [
        ("FONT", (0, 0), (-1, -1), "Helvetica", 8),
        ("GRID", (0, 0), (-1, -1), 0.25, GRID),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]
    if header:
        style += [
            ("BACKGROUND", (0, 0), (-1, 0), FOREST),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ZEBRA]),
        ]
    else:
        style += [("FONT", (0, 0), (0, -1), "Helvetica-Bold", 8), ("BACKGROUND", (0, 0), (0, -1), ZEBRA)]
    t.setStyle(TableStyle(style))
    return t


def _bar_chart(title: str, years: list[int], values: list[float], color) -> Drawing:
    width, height = 170 * mm, 60 * mm
    d = Drawing(width, height)
    d.add(String(0, height - 10, title, fontName="Helvetica-Bold", fontSize=9, fillColor=FOREST))
    chart = VerticalBarChart()
    chart.x, chart.y = 25, 22
    chart.width, chart.height = width - 35, height - 40
    chart.data = [values or [0]]
    chart.bars[0].fillColor = color
    chart.bars[0].strokeColor = None
    chart.valueAxis.valueMin = 0
    chart.valueAxis.labels.fontSize = 7
    chart.valueAxis.labels.fontName = "Helvetica"
    chart.categoryAxis.labels.fontName = "Helvetica"
    chart.categoryAxis.categoryNames = [str(y) if (i % max(1, len(years) // 15) == 0) else "" for i, y in enumerate(years)]
    chart.categoryAxis.labels.fontSize = 6
    chart.categoryAxis.labels.angle = 45
    chart.categoryAxis.labels.dy = -8
    d.add(chart)
    return d


def _trend_rows(t: IndicatorTrendOut) -> tuple[list[list[object]], list[list[object]]]:
    reg = t.regression
    mk = t.mann_kendall
    reg_rows = [
        ["Indicator", t.indicator],
        ["Slope", f"{_fmt(reg.slope_per_year, 4)} {t.units} per year ({_fmt(reg.slope_per_decade, 3)} per decade)"],
        ["Intercept", _fmt(reg.intercept, 3)],
        ["R-squared", _fmt(reg.r_squared, 4)],
        ["Annual values used (n)", reg.n],
        ["Status", reg.status + ("; " + " ".join(reg.notes) if reg.notes else "")],
    ]
    mk_rows = [
        ["Indicator", t.indicator],
        ["S statistic", _fmt(mk.s)],
        ["Var(S) without tie correction", _fmt(mk.var_s_no_ties, 3)],
        ["Var(S) tie-corrected", _fmt(mk.var_s, 3)],
        ["Hamed-Rao variance factor", _fmt(mk.variance_correction, 3)],
        ["Z statistic (adjusted)", _fmt(mk.z, 4)],
        ["Two-sided p-value (adjusted)", _p_value(mk.p_value)],
        ["Z statistic (unadjusted)", _fmt(mk.z_uncorrected, 4)],
        ["Two-sided p-value (unadjusted)", _p_value(mk.p_value_uncorrected)],
        ["Significance level (alpha)", _fmt(mk.alpha, 2)],
        ["Trend direction", mk.direction],
        ["Significant at alpha (adjusted p)", "yes" if mk.significant else "no"],
        ["Sen's slope (per year)", _fmt(mk.sen_slope_per_year, 4)],
        ["Sen's slope CI low / high", f"{_fmt(mk.sen_slope_ci_low, 4)} / {_fmt(mk.sen_slope_ci_high, 4)}"],
        ["Observations used (n)", mk.n],
        ["Interpretation", mk.interpretation],
    ]
    return reg_rows, mk_rows


def build_pdf(r: AnalysisResponse) -> bytes:
    s = _styles()
    buf = io.BytesIO()
    h = r.hazard
    heat = h.type == "heatwave"
    labels = h.labels or {}
    name = h.name or "Heatwave"
    days_label = labels.get("days", "Heatwave days")
    events_label = labels.get("events", "Heatwave events")
    qualifying_day = labels.get("qualifying_day", "hot day")
    unit = h.units
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=18 * mm,
        title=f"Climate Lens {name.lower()} report - {r.region.label}",
        author="Climate Lens",
        subject=f"{name} trend analysis",
    )
    P = lambda text, style="body": Paragraph(escape(str(text)), s[style])  # noqa: E731
    wrap = lambda text: Paragraph(escape(str(text)), s["cell"])  # noqa: E731
    story: list = []

    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    story.append(Paragraph(f"{name} Trend Report", s["title"]))
    story.append(P(f"Climate Lens - Climate Hazard Trend Analyzer. Report generated {generated}.", "small"))
    story.append(Spacer(1, 6))

    region = r.region
    coords = f"{region.latitude:.4f}, {region.longitude:.4f}"
    if region.bbox:
        b = region.bbox
        coords += f" (box S {b.south:.3f}, W {b.west:.3f}, N {b.north:.3f}, E {b.east:.3f})"
    story.append(Paragraph("Selection", s["h2"]))
    story.append(
        _table(
            [
                ["Region", wrap(region.label)],
                ["Coordinates", wrap(coords)],
                ["Analysis period", f"{r.period.start_year}-{r.period.end_year} ({r.period.years} years)"],
                ["Weather data source", wrap(f"{r.source.provider}: {r.source.dataset}")],
                ["Variable / units", f"{r.source.variable} ({r.source.units}), time zone {r.source.timezone}"],
                ["Spatial handling", wrap(r.source.aggregation)],
                ["Data retrieved (UTC)", r.source.retrieved_at],
                ["Analysis computed (UTC)", r.generated_at],
            ],
            [45 * mm, 129 * mm],
            header=False,
        )
    )
    story.append(Spacer(1, 4))
    story.append(P(region.note, "small"))

    story.append(Paragraph(f"{name} definition and baseline", s["h2"]))
    story.append(P(h.definition))
    def_rows: list[list[object]] = [
        ["Baseline mode", r.baseline.mode.replace("_", " ")],
        ["Baseline period", f"{r.baseline.reference_start_year}-{r.baseline.reference_end_year}"],
    ]
    if h.percentile is not None:
        threshold = r.baseline.threshold_c if heat else r.baseline.threshold_value
        def_rows += [
            ["Threshold percentile", f"{h.percentile:g}th"],
            [f"Minimum consecutive {qualifying_day}s", h.min_duration_days],
            [f"{h.percentile:g}th-percentile threshold", _fmt(threshold, 2, f" {unit}")],
        ]
    else:
        def_rows += [
            [f"Minimum consecutive {qualifying_day}s", h.min_duration_days],
            ["Dry-day threshold", f"below {_fmt(r.baseline.threshold_value, 1, ' mm')}"],
        ]
    if not heat:
        def_rows.append(["Baseline normal annual precipitation", _fmt(r.baseline.normal_annual_total_mm, 0, " mm")])
    def_rows += [
        ["Percentile method", wrap(r.baseline.percentile_method)],
        ["Valid days used for threshold", r.baseline.valid_days_used],
    ]
    story.append(_table(def_rows, [45 * mm, 129 * mm], header=False))
    story.append(Spacer(1, 3))
    story.append(P(r.baseline.note, "small"))

    sm = r.summary
    story.append(Paragraph("Summary metrics", s["h2"]))
    longest = f"{sm.longest_event_days} days" + (
        f" ({sm.longest_event_start} to {sm.longest_event_end})" if sm.longest_event_start else ""
    )
    summary_rows: list[list[object]] = [
        [f"Total {events_label.lower()}", sm.total_events],
        [f"Total {days_label.lower()}", sm.total_heatwave_days],
        ["Mean events per year", _fmt(sm.mean_events_per_year, 2)],
        [f"Mean {days_label.lower()} per year", _fmt(sm.mean_heatwave_days_per_year, 2)],
        ["Longest event", longest],
    ]
    if heat:
        summary_rows += [
            ["Peak daily maximum", _fmt(sm.peak_tmax_c, 2, " °C")],
            ["Mean daily maximum", _fmt(sm.mean_tmax_c, 2, " °C")],
        ]
    else:
        summary_rows += [
            ["Wettest day in the period", _fmt(sm.peak_daily_mm, 1, " mm")],
            ["Mean annual precipitation", _fmt(sm.mean_annual_total_mm, 0, " mm")],
        ]
    summary_rows.append(["Years analysed / used for trends", f"{sm.years_analyzed} / {sm.years_used_for_trends}"])
    story.append(_table(summary_rows, [60 * mm, 114 * mm], header=False))

    story.append(Paragraph("Key insights", s["h2"]))
    for line in r.insights:
        story.append(P(f"- {line}"))

    years = [a.year for a in r.annual]
    story.append(Spacer(1, 6))
    story.append(KeepTogether([_bar_chart(f"Annual {days_label.lower()}", years, [a.heatwave_days for a in r.annual], AMBER)]))
    story.append(KeepTogether([_bar_chart(f"Annual {events_label.lower()} (counted in start year)", years, [a.event_count for a in r.annual], MINT)]))
    if not heat:
        story.append(KeepTogether([_bar_chart("Annual precipitation (mm)", years, [a.total_mm or 0 for a in r.annual], FOREST)]))

    story.append(Paragraph(f"Annual {days_label.lower()}", s["h2"]))
    rows: list[list[object]]
    if heat:
        rows = [["Year", "Heatwave days", "Longest event (days)", "Mean excess (°C)", "Mean Tmax (°C)", "Completeness", "Used in trends"]]
        for a in r.annual:
            rows.append([a.year, a.heatwave_days, a.longest_event_days, _fmt(a.mean_excess_c), _fmt(a.mean_tmax_c), f"{a.completeness * 100:.1f}%", _fmt(a.sufficient_data)])
    else:
        longest_col = "Longest dry spell (days)" if h.type == "drought" else "Longest run (days)"
        rows = [["Year", days_label, longest_col, "Total (mm)", "% of normal", "Wettest day (mm)", "Completeness", "Used in trends"]]
        for a in r.annual:
            rows.append([
                a.year, a.heatwave_days, a.longest_event_days, _fmt(a.total_mm, 0), _fmt(a.percent_of_normal, 0, "%"),
                _fmt(a.max_daily_mm, 1), f"{a.completeness * 100:.1f}%", _fmt(a.sufficient_data),
            ])
    story.append(_table(rows))

    story.append(Paragraph("Annual event frequency", s["h2"]))
    last_col = "Max Tmax (°C)" if heat else ("Rain on event days (mm)" if h.type == "heavy_rainfall" else "Total (mm)")
    rows = [["Year", "Events", "5-yr rolling mean (events)", days_label, "5-yr rolling mean (days)", last_col]]
    for a in r.annual:
        last = _fmt(a.max_tmax_c) if heat else _fmt(a.event_total_mm if h.type == "heavy_rainfall" else a.total_mm, 0)
        rows.append([a.year, a.event_count, _fmt(a.event_count_rolling_mean), a.heatwave_days, _fmt(a.heatwave_days_rolling_mean), last])
    story.append(_table(rows))

    story.append(Paragraph("Linear regression (descriptive)", s["h2"]))
    story.append(P("Ordinary least squares of each annual indicator on year, using years that meet the completeness rule. The slope describes the observed record; it is not a forecast or a significance test.", "small"))
    for t in (r.trends.heatwave_days, r.trends.event_count, r.trends.mean_tmax):
        reg_rows, _ = _trend_rows(t)
        story.append(_table([[a, wrap(b)] for a, b in reg_rows], [55 * mm, 119 * mm], header=False))
        story.append(Spacer(1, 4))

    story.append(Paragraph("Mann-Kendall trend test", s["h2"]))
    story.append(P("Non-parametric test for a monotonic trend. Var(S) uses the tie correction; Z uses a continuity correction; the p-value is two-sided from the normal approximation.", "small"))
    for t in (r.trends.heatwave_days, r.trends.event_count, r.trends.mean_tmax):
        _, mk_rows = _trend_rows(t)
        story.append(_table([[a, wrap(b)] for a, b in mk_rows], [55 * mm, 119 * mm], header=False))
        for note in t.mann_kendall.notes:
            story.append(P(f"Note: {note}", "small"))
        story.append(Spacer(1, 4))

    q = r.data_quality
    story.append(Paragraph("Data completeness and missing data", s["h2"]))
    qa = q.analysis
    dq_rows: list[list[object]] = [
        ["Calendar days in window", qa.expected_days],
        ["Days received from source", qa.received_days],
        ["Valid daily values", qa.valid_days],
        ["Missing days (absent + null)", qa.missing_dates + qa.null_values],
        ["Dates absent from provider", qa.missing_dates],
        ["Null values from provider", qa.null_values],
        [f"Implausible values (outside {q.plausible_range_c[0]:g} to {q.plausible_range_c[1]:g} {q.plausible_range_units})", qa.implausible_values],
        ["Duplicate dates", qa.duplicate_dates],
        ["Interpolated days (gap fill)", qa.interpolated_days],
        ["Statistical outlier days (flagged, kept)", qa.outlier_days],
        ["Accounting check", ("OK: " if qa.accounting_ok else "MISMATCH: ") + qa.accounting],
        ["Gap fill", q.gap_fill],
        ["Completeness", f"{qa.completeness * 100:.2f}%"],
        ["Minimum completeness for a year to enter trends", f"{q.min_year_completeness * 100:.0f}%"],
        ["Years excluded from trends", ", ".join(map(str, q.insufficient_years)) or "none"],
    ]
    if q.reference:
        dq_rows.append(["Reference-period completeness", f"{q.reference.completeness * 100:.2f}%"])
    story.append(_table([[wrap(a), wrap(b) if isinstance(b, str) else b] for a, b in dq_rows], [90 * mm, 84 * mm], header=False))
    if q.outlier_method:
        story.append(Spacer(1, 3))
        story.append(P(f"Outlier method: {q.outlier_method}.", "small"))
    if q.outlier_dates:
        listed = "; ".join(f"{o.date} ({o.tmax_c:.1f} °C, z {o.robust_z:+.1f})" for o in q.outlier_dates)
        story.append(
            P(f"Most extreme flagged days (showing {len(q.outlier_dates)} of {q.outlier_total}): {listed}.", "small")
        )
    if q.filled_dates:
        listed = "; ".join(f"{f.date} ({f.tmax_c:.1f} °C, was {f.reason.replace('_', ' ')})" for f in q.filled_dates)
        story.append(P(f"Filled days (showing {len(q.filled_dates)} of {q.filled_total}): {listed}.", "small"))

    story.append(Paragraph("Annual data quality", s["h2"]))
    rows = [["Year", "Received", "Valid", "Missing", "Implausible", "Filled", "Duplicates", "Outliers"]]
    for a in r.annual:
        rows.append([
            a.year, a.received_days, a.valid_days, a.missing_days - a.implausible_days, a.implausible_days,
            a.interpolated_days, a.duplicate_dates, a.outlier_days,
        ])
    story.append(_table(rows))
    story.append(P("Calendar days = valid + missing + implausible. Filled days are a subset of the missing and implausible days.", "small"))

    story.append(Paragraph("Methodology, limitations and statistical caveats", s["h2"]))
    filled = (
        "With the optional gap fill on, an isolated one-day gap between two observed days is set to their mean and flagged as interpolated; it never enters the threshold, completeness or annual mean."
        if q.gap_fill != "off"
        else "Nothing is interpolated or zero-filled."
    )
    variable_text = "Daily maximum 2 m air temperature" if heat else "Daily precipitation total (mm)"
    if heat:
        rule = (
            f"A hot day is a valid day whose maximum temperature is strictly greater than the threshold. A heatwave is a run of at least {h.min_duration_days} consecutive hot days; "
            + (
                "an isolated single-day gap between two observed days is filled and flagged, and any longer gap breaks the run."
                if q.gap_fill != "off"
                else "any missing day breaks the run."
            )
        )
        attribution = "Heatwave days are attributed to the calendar year in which each day falls, and a year's longest event is the longest single-event contribution to that year."
    else:
        rule = h.definition + " A missing day is never treated as dry or wet; it breaks the run."
        attribution = (
            "Dry-spell days are attributed to the calendar year in which each day falls; a year's longest dry spell is the longest run of dry days falling in that year, whatever its length."
            if h.type == "drought"
            else "Heavy-rain days are attributed to the calendar year in which each day falls."
        )
    method = [
        f"{variable_text} is retrieved from the Open-Meteo Historical Weather API and aligned to a complete calendar. Missing dates, null values and implausible values are kept as missing. " + filled,
        rule,
        "Events are counted once, in the year they start. " + attribution,
        "Percentage changes compare the mean of the first and last five qualifying years and are omitted when the early-period mean is zero.",
    ]
    for line in method + r.caveats:
        story.append(P(f"- {line}"))
    story.append(Spacer(1, 6))
    story.append(P(r.source.attribution, "small"))
    story.append(P(f"Algorithm version {r.algorithm_version}.", "small"))

    doc.build(story, canvasmaker=_NumberedCanvas)
    return buf.getvalue()
