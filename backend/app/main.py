from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import __version__
from .api.routes import router
from .cache import CacheStore, create_cache
from .config import Settings, get_settings
from .errors import AppError
from .security.rate_limit import RateLimiter
from .services.analysis import AnalysisService
from .services.geocoding import GeocodingService
from .services.weather import OpenMeteoClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("climate_lens")


def _error(status: int, code: str, message: str, details: list | None = None, headers: dict | None = None) -> JSONResponse:
    body: dict = {"error": {"code": code, "message": message}}
    if details:
        body["error"]["details"] = details
    return JSONResponse(status_code=status, content=body, headers=headers)


def create_app(
    settings: Settings | None = None,
    cache: CacheStore | None = None,
    weather: OpenMeteoClient | None = None,
) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        app.state.weather.close()

    app = FastAPI(
        title="Climate Lens API",
        version=__version__,
        description="Heatwave detection and trend analysis from Open-Meteo historical daily maximum temperature.",
        lifespan=lifespan,
    )

    app.state.settings = settings
    app.state.cache = cache or create_cache(
        settings.mongodb_uri, settings.mongodb_database, settings.mongodb_timeout_ms, settings.memory_cache_max_entries
    )
    app.state.weather = weather or OpenMeteoClient(
        settings.open_meteo_archive_url,
        settings.upstream_timeout_seconds,
        settings.upstream_max_retries,
        settings.upstream_backoff_seconds,
    )
    app.state.service = AnalysisService(settings, app.state.cache, app.state.weather)
    app.state.geocoder = GeocodingService(
        app.state.weather, app.state.cache, settings.open_meteo_geocoding_url, settings.geocode_cache_ttl_hours
    )
    app.state.limiter = RateLimiter(60.0, settings.proxy_hops)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_origin_regex=settings.cors_origin_regex,
        allow_methods=["GET"],
        allow_headers=["*"],
        expose_headers=["Content-Disposition", "Retry-After"],
        max_age=600,
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Frame-Options", "DENY")
        return response

    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError):
        return _error(exc.status_code, exc.code, exc.message, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_: Request, exc: RequestValidationError):
        details = []
        for err in exc.errors():
            msg = str(err.get("msg", "Invalid value")).removeprefix("Value error, ")
            loc = [str(p) for p in err.get("loc", []) if p not in ("query", "body")]
            details.append({"field": ".".join(loc) or None, "message": msg})
        message = details[0]["message"] if details else "Invalid request parameters."
        return _error(422, "validation_error", message, details)

    @app.exception_handler(StarletteHTTPException)
    async def http_handler(_: Request, exc: StarletteHTTPException):
        return _error(exc.status_code, "http_error", str(exc.detail))

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception):
        logger.exception("Unhandled error")
        return _error(500, "internal_error", "An unexpected error occurred. Please try again later.")

    app.include_router(router)

    @app.get("/", include_in_schema=False)
    def root():
        return {"name": "Climate Lens API", "docs": "/docs", "health": "/api/health"}

    return app


app = create_app()
