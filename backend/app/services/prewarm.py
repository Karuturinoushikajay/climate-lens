"""Background pre-warming of the default analyses for the preset cities.

Runs once per process start, only with the shared MongoDB cache, so the first visitor to a preset city
gets a cached answer instead of waiting for Open-Meteo. Series that are already cached are skipped, provider
fetches are spaced out to respect the free quota, and the run stops at the first quota or rate-limit error.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Callable

from ..climate.hazards import SUPPORTED_HAZARDS
from ..config import latest_complete_year
from ..errors import AppError
from ..models.schemas import AnalysisQuery
from .analysis import AnalysisService
from .regions import preset_regions

logger = logging.getLogger(__name__)

DEFAULT_START_YEAR = 1990
QUOTA_ERROR_CODES = {"upstream_rate_limited"}


def default_queries() -> list[AnalysisQuery]:
    """The analyses the dashboard requests by default for each preset city, for every hazard."""
    end = latest_complete_year()
    return [
        AnalysisQuery(
            latitude=r.latitude, longitude=r.longitude, label=r.name, start_year=DEFAULT_START_YEAR, end_year=end, hazard=h
        )
        for r in preset_regions()
        if r.kind == "city"
        for h in SUPPORTED_HAZARDS
    ]


@dataclass
class Prewarmer:
    service: AnalysisService
    delay_seconds: float = 120.0
    start_delay_seconds: float = 0.0
    queries: list[AnalysisQuery] = field(default_factory=default_queries)
    status: str = "pending"
    done: int = 0
    fetched: int = 0
    failed: int = 0
    detail: str = ""
    _stop: threading.Event = field(default_factory=threading.Event)
    _thread: threading.Thread | None = None
    wait: Callable[[float], bool] | None = None

    @property
    def total(self) -> int:
        return len(self.queries)

    def snapshot(self) -> dict:
        out = {"status": self.status, "done": self.done, "total": self.total}
        if self.detail:
            out["detail"] = self.detail
        return out

    def _wait(self, seconds: float) -> bool:
        """Sleep unless asked to stop; returns True if the run should stop."""
        if seconds <= 0:
            return self._stop.is_set()
        return (self.wait or self._stop.wait)(seconds)

    def run(self) -> None:
        self.status = "running"
        if self._wait(self.start_delay_seconds):
            self.status = "stopped"
            self.detail = "shutdown"
            return
        for q in self.queries:
            if self._stop.is_set():
                self.status, self.detail = "stopped", "shutdown"
                return
            try:
                if self.service.analysis_cached(q):
                    self.done += 1
                    continue
                needs_fetch = not self.service.observations_cached(q)
                if needs_fetch and self.fetched and self._wait(self.delay_seconds):
                    self.status, self.detail = "stopped", "shutdown"
                    return
                self.service.analyze(q)
                self.fetched += int(needs_fetch)
                self.done += 1
            except AppError as exc:
                if exc.code in QUOTA_ERROR_CODES or exc.status_code == 429:
                    self.status = "stopped"
                    self.detail = f"provider quota or rate limit reached after {self.done} of {self.total}"
                    logger.warning("Pre-warm stopped: %s", self.detail)
                    return
                self.failed += 1
                self.done += 1
                logger.warning("Pre-warm skipped %s %s: %s", q.label, q.hazard, exc.code)
            except Exception:  # noqa: BLE001 - pre-warming must never take the API down
                self.failed += 1
                self.done += 1
                logger.exception("Pre-warm failed for %s %s", q.label, q.hazard)
        self.status = "done"
        self.detail = f"{self.fetched} series fetched, {self.failed} failed" if self.fetched or self.failed else "all cached"
        logger.info("Pre-warm finished: %s", self.detail)

    def start(self) -> None:
        self._thread = threading.Thread(target=self.run, name="prewarm", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout)
