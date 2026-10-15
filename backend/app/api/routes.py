from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Request, Response

from .. import __version__
from ..climate import ALGORITHM_VERSION
from ..config import MAX_ANALYSIS_SPAN_YEARS, MAX_BOX_SPAN_DEGREES, MIN_YEAR, latest_complete_year
from ..exports.csv_export import build_csv, safe_filename
from ..exports.pdf_report import build_pdf
from ..models.schemas import (
    AnalysisQuery,
    AnalysisResponse,
    ErrorResponse,
    GeocodeQuery,
    GeocodeResponse,
    HealthResponse,
    RegionsResponse,
)
from ..services.regions import preset_regions
from ..services.weather import ATTRIBUTION, DATASET, PROVIDER

router = APIRouter(prefix="/api")

ERROR_RESPONSES = {
    422: {"model": ErrorResponse, "description": "Invalid parameters"},
    429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    502: {"model": ErrorResponse, "description": "Weather provider returned an invalid response"},
    503: {"model": ErrorResponse, "description": "Weather provider unavailable or quota exhausted"},
    504: {"model": ErrorResponse, "description": "Weather provider timed out"},
}

QueryParams = Annotated[AnalysisQuery, Query()]


def _run(request: Request, q: AnalysisQuery, bucket: str) -> AnalysisResponse:
    state = request.app.state
    limit = (
        state.settings.rate_limit_analyze_per_minute if bucket == "analyze" else state.settings.rate_limit_export_per_minute
    )
    state.limiter.check(request, bucket, limit)
    return state.service.analyze(q)


@router.get("/health", response_model=HealthResponse, summary="Service health, cache mode and data source")
def health(request: Request) -> HealthResponse:
    s = request.app.state.settings
    return HealthResponse(
        status="ok",
        version=__version__,
        algorithm_version=ALGORITHM_VERSION,
        environment=s.environment,
        cache=request.app.state.cache.status(),
        data_source={"provider": PROVIDER, "dataset": DATASET, "endpoint": s.open_meteo_archive_url, "attribution": ATTRIBUTION},
        limits={
            "min_year": MIN_YEAR,
            "max_year": latest_complete_year(),
            "max_analysis_span_years": MAX_ANALYSIS_SPAN_YEARS,
            "max_box_span_degrees": MAX_BOX_SPAN_DEGREES,
            "rate_limit_analyze_per_minute": s.rate_limit_analyze_per_minute,
            "rate_limit_export_per_minute": s.rate_limit_export_per_minute,
            "rate_limit_geocode_per_minute": s.rate_limit_geocode_per_minute,
            "rate_limits_scope": request.app.state.limiter.scope,
        },
        prewarm=_prewarm_status(request),
    )


def _prewarm_status(request: Request) -> dict:
    prewarmer = request.app.state.prewarmer
    if prewarmer is not None:
        return prewarmer.snapshot()
    return {"done": 0, "total": 0, **request.app.state.prewarm_status}


@router.get("/regions", response_model=RegionsResponse, summary="Preset regions")
def regions() -> RegionsResponse:
    return RegionsResponse(
        regions=preset_regions(),
        note="City presets are single points; state presets are approximate rectangles, not administrative boundaries.",
    )


@router.get("/geocode", response_model=GeocodeResponse, responses=ERROR_RESPONSES, summary="Search places by name")
def geocode(request: Request, q: Annotated[GeocodeQuery, Query()]) -> GeocodeResponse:
    state = request.app.state
    state.limiter.check(request, "geocode", state.settings.rate_limit_geocode_per_minute)
    return state.geocoder.search(q.name, q.count)


@router.get("/analyze", response_model=AnalysisResponse, responses=ERROR_RESPONSES, summary="Heatwave analysis")
def analyze(request: Request, q: QueryParams) -> AnalysisResponse:
    return _run(request, q, "analyze")


@router.get(
    "/export.csv",
    responses={**ERROR_RESPONSES, 200: {"content": {"text/csv": {}}, "description": "Annual indicators as CSV"}},
    summary="Annual indicators as CSV",
)
def export_csv(request: Request, q: QueryParams) -> Response:
    result = _run(request, q, "export")
    filename = safe_filename(result.region.label, result.hazard.name, result.period.start_year, result.period.end_year, "csv")
    return Response(
        content="\ufeff" + build_csv(result),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store"},
    )


@router.get(
    "/export.pdf",
    responses={**ERROR_RESPONSES, 200: {"content": {"application/pdf": {}}, "description": "PDF report"}},
    summary="PDF report",
)
def export_pdf(request: Request, q: QueryParams) -> Response:
    result = _run(request, q, "export")
    filename = safe_filename(result.region.label, result.hazard.name, result.period.start_year, result.period.end_year, "pdf")
    return Response(
        content=build_pdf(result),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store"},
    )
