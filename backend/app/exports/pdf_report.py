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
        ["Z statistic", _fmt(mk.z, 4)],
        ["Two-sided p-value", _p_value(mk.p_value)],
        ["Significance level (alpha)", _fmt(mk.alpha, 2)],
        ["Trend direction", mk.direction],
        ["Significant at alpha", "yes" if mk.significant else "no"],
        ["Sen's slope (per year)", _fmt(mk.sen_slope_per_year, 4)],
        ["Observations used (n)", mk.n],
        ["Interpretation", mk.interpretation],
    ]
    return reg_rows, mk_rows


def build_pdf(r: AnalysisResponse) -> bytes:
    s = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=18 * mm,
        title=f"Climate Lens heatwave report - {r.region.label}",
        author="Climate Lens",
        subject="Heatwave trend analysis",
    )
    P = lambda text, style="body": Paragraph(escape(str(text)), s[style])  # noqa: E731
    wrap = lambda text: Paragraph(escape(str(text)), s["cell"])  # noqa: E731
    story: list = []

    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    story.append(Paragraph("Heatwave Trend Report", s["title"]))
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

    story.append(Paragraph("Heatwave definition and baseline", s["h2"]))
    story.append(P(r.hazard.definition))
    story.append(
        _table(
            [
                ["Baseline mode", r.baseline.mode.replace("_", " ")],
                ["Baseline period", f"{r.baseline.reference_start_year}-{r.baseline.reference_end_year}"],
                ["95th-percentile threshold", _fmt(r.baseline.threshold_c, 2, " °C")],
                ["Percentile method", r.baseline.percentile_method],
                ["Valid days used for threshold", r.baseline.valid_days_used],
            ],
            [45 * mm, 129 * mm],
            header=False,
        )
    )
    story.append(Spacer(1, 3))
    story.append(P(r.baseline.note, "small"))

    sm = r.summary
    story.append(Paragraph("Summary metrics", s["h2"]))
    story.append(
        _table(
            [
                ["Total heatwave events", sm.total_events],
                ["Total heatwave days", sm.total_heatwave_days],
                ["Mean events per year", _fmt(sm.mean_events_per_year, 2)],
                ["Mean heatwave days per year", _fmt(sm.mean_heatwave_days_per_year, 2)],
                ["Longest event", f"{sm.longest_event_days} days" + (f" ({sm.longest_event_start} to {sm.longest_event_end})" if sm.longest_event_start else "")],
                ["Peak daily maximum", _fmt(sm.peak_tmax_c, 2, " °C")],
                ["Mean daily maximum", _fmt(sm.mean_tmax_c, 2, " °C")],
                ["Years analysed / used for trends", f"{sm.years_analyzed} / {sm.years_used_for_trends}"],
            ],
            [60 * mm, 114 * mm],
            header=False,
        )
    )

    story.append(Paragraph("Key insights", s["h2"]))
    for line in r.insights:
        story.append(P(f"- {line}"))

    years = [a.year for a in r.annual]
    story.append(Spacer(1, 6))
    story.append(KeepTogether([_bar_chart("Annual heatwave days", years, [a.heatwave_days for a in r.annual], AMBER)]))
    story.append(KeepTogether([_bar_chart("Annual heatwave events (counted in start year)", years, [a.event_count for a in r.annual], MINT)]))

    story.append(Paragraph("Annual heatwave days", s["h2"]))
    rows: list[list[object]] = [["Year", "Heatwave days", "Longest event (days)", "Mean excess (°C)", "Mean Tmax (°C)", "Completeness", "Used in trends"]]
    for a in r.annual:
        rows.append([a.year, a.heatwave_days, a.longest_event_days, _fmt(a.mean_excess_c), _fmt(a.mean_tmax_c), f"{a.completeness * 100:.1f}%", _fmt(a.sufficient_data)])
    story.append(_table(rows))

    story.append(Paragraph("Annual event frequency", s["h2"]))
    rows = [["Year", "Events", "5-yr rolling mean (events)", "Heatwave days", "5-yr rolling mean (days)", "Max Tmax (°C)"]]
    for a in r.annual:
        rows.append([a.year, a.event_count, _fmt(a.event_count_rolling_mean), a.heatwave_days, _fmt(a.heatwave_days_rolling_mean), _fmt(a.max_tmax_c)])
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
        ["Valid daily values", qa.valid_days],
        ["Missing days (total)", qa.missing_days],
        ["Dates absent from provider", qa.missing_dates],
        ["Null values from provider", qa.null_values],
        [f"Implausible values (outside {q.plausible_range_c[0]:g} to {q.plausible_range_c[1]:g} °C)", qa.implausible_values],
        ["Duplicate dates", qa.duplicate_dates],
        ["Completeness", f"{qa.completeness * 100:.2f}%"],
        ["Minimum completeness for a year to enter trends", f"{q.min_year_completeness * 100:.0f}%"],
        ["Years excluded from trends", ", ".join(map(str, q.insufficient_years)) or "none"],
    ]
    if q.reference:
        dq_rows.append(["Reference-period completeness", f"{q.reference.completeness * 100:.2f}%"])
    story.append(_table([[wrap(a), b] for a, b in dq_rows], [90 * mm, 84 * mm], header=False))

    story.append(Paragraph("Methodology, limitations and statistical caveats", s["h2"]))
    method = [
        "Daily maximum 2 m air temperature is retrieved from the Open-Meteo Historical Weather API and aligned to a complete calendar. Missing dates, null values and implausible values are kept as missing; nothing is interpolated or zero-filled.",
        "A hot day is a valid day whose maximum temperature is strictly greater than the threshold. A heatwave is a run of at least three consecutive hot days; any missing day breaks the run.",
        "Events are counted once, in the year they start. Heatwave days are attributed to the calendar year in which each day falls, and a year's longest event is the longest single-event contribution to that year.",
        "Percentage changes compare the mean of the first and last five qualifying years and are omitted when the early-period mean is zero.",
    ]
    for line in method + r.caveats:
        story.append(P(f"- {line}"))
    story.append(Spacer(1, 6))
    story.append(P(r.source.attribution, "small"))
    story.append(P(f"Algorithm version {r.algorithm_version}.", "small"))

    doc.build(story, canvasmaker=_NumberedCanvas)
    return buf.getvalue()
