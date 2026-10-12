from __future__ import annotations

from datetime import date
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

MIN_YEAR = 1940  # first year available in the Open-Meteo historical archive
MAX_ANALYSIS_SPAN_YEARS = 60
MIN_REFERENCE_SPAN_YEARS = 10
MAX_BOX_SPAN_DEGREES = 10.0
MAX_LABEL_LENGTH = 80
# Render appends three entries: the client (from Cloudflare), the Cloudflare edge, and its load balancer.
PROXY_HOPS_WHEN_TRUSTED = 3


def latest_complete_year() -> int:
    return date.today().year - 1


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = "development"
    mongodb_uri: str = ""
    mongodb_database: str = "climate_lens"
    mongodb_timeout_ms: int = 3000

    allowed_origins: str = "http://localhost:5173"
    allowed_origin_regex: str = ""

    observation_cache_ttl_hours: int = Field(720, ge=1)
    analysis_cache_ttl_hours: int = Field(168, ge=1)
    memory_cache_max_entries: int = Field(128, ge=1)

    rate_limit_analyze_per_minute: int = Field(30, ge=1)
    rate_limit_export_per_minute: int = Field(10, ge=1)
    trusted_proxy_hops: int | None = Field(None, ge=0, le=5)
    # Legacy switch: true means "behind Render", which appends PROXY_HOPS_WHEN_TRUSTED entries.
    trust_proxy_headers: bool = False

    open_meteo_archive_url: str = "https://archive-api.open-meteo.com/v1/archive"
    upstream_timeout_seconds: float = Field(30.0, gt=0, le=120)
    upstream_max_retries: int = Field(2, ge=0, le=5)
    upstream_backoff_seconds: float = Field(0.5, ge=0)

    min_year_completeness: float = Field(0.8, ge=0, le=1)

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def proxy_hops(self) -> int:
        if self.trusted_proxy_hops is not None:
            return self.trusted_proxy_hops
        return PROXY_HOPS_WHEN_TRUSTED if self.trust_proxy_headers else 0

    @property
    def cors_origin_regex(self) -> str | None:
        return self.allowed_origin_regex.strip() or None

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
