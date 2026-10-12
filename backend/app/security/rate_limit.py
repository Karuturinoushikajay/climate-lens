"""Process-local sliding-window rate limiter keyed by client IP and bucket.

Limits are not coordinated across multiple backend instances; use a shared store such as Redis
for horizontally scaled deployments.
"""

from __future__ import annotations

import math
import threading
import time
from collections import defaultdict, deque

from fastapi import Request

from ..errors import AppError

MAX_TRACKED_CLIENTS = 10_000


class RateLimiter:
    def __init__(self, window_seconds: float = 60.0, trust_proxy_headers: bool = False):
        self.window = window_seconds
        self.trust_proxy_headers = trust_proxy_headers
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def client_id(self, request: Request) -> str:
        if self.trust_proxy_headers:
            forwarded = request.headers.get("x-forwarded-for", "")
            if forwarded:
                return forwarded.split(",")[0].strip()[:64]
        return request.client.host if request.client else "unknown"

    def check(self, request: Request, bucket: str, limit: int) -> None:
        key = f"{bucket}:{self.client_id(request)}"
        now = time.monotonic()
        with self._lock:
            if len(self._hits) > MAX_TRACKED_CLIENTS:
                self._prune(now)
            hits = self._hits[key]
            while hits and hits[0] <= now - self.window:
                hits.popleft()
            if len(hits) >= limit:
                retry_after = max(1, math.ceil(hits[0] + self.window - now))
                raise AppError(
                    429,
                    "rate_limited",
                    f"Too many requests. Limit is {limit} per {int(self.window)} seconds.",
                    headers={"Retry-After": str(retry_after)},
                )
            hits.append(now)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()

    def _prune(self, now: float) -> None:
        for key in [k for k, v in self._hits.items() if not v or v[-1] <= now - self.window]:
            del self._hits[key]
