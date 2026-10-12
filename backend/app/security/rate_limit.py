"""Sliding-window rate limiter keyed by client IP and bucket.

With MongoDB configured, hits are stored in a shared collection, so the limit holds across
backend instances, overlapping deploys and restarts. Without it (or if MongoDB fails), a
process-local store is used.
"""

from __future__ import annotations

import ipaddress
import logging
import math
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from fastapi import Request

from ..errors import AppError

logger = logging.getLogger(__name__)

MAX_TRACKED_CLIENTS = 10_000


@dataclass
class RateLimitState:
    limit: int
    remaining: int
    reset_seconds: int
    allowed: bool

    def headers(self) -> dict[str, str]:
        return {
            "X-RateLimit-Limit": str(self.limit),
            "X-RateLimit-Remaining": str(self.remaining),
            "X-RateLimit-Reset": str(self.reset_seconds),
        }


class HitStore(Protocol):
    scope: str

    def hit(self, key: str, limit: int, window: float, now: float) -> tuple[bool, int, float]:
        """Record a hit if under ``limit``. Returns (allowed, hits in window, oldest hit time)."""
        ...


class MemoryHitStore:
    scope = "per client IP, per backend process"

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int, window: float, now: float) -> tuple[bool, int, float]:
        with self._lock:
            if len(self._hits) > MAX_TRACKED_CLIENTS:
                for k in [k for k, v in self._hits.items() if not v or v[-1] <= now - window]:
                    del self._hits[k]
            hits = self._hits[key]
            while hits and hits[0] <= now - window:
                hits.popleft()
            allowed = len(hits) < limit
            if allowed:
                hits.append(now)
            return allowed, len(hits), hits[0] if hits else now

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


class MongoHitStore:
    """One document per bucket and client holding the hit times inside the window.

    The filter-check-append runs as a single atomic update, so concurrent requests on
    different instances cannot both take the last slot.
    """

    scope = "per client IP, shared across backend instances (MongoDB)"

    def __init__(self, collection: Any, fallback: MemoryHitStore | None = None):
        self._col = collection
        self._fallback = fallback or MemoryHitStore()
        self._col.create_index("expires_at", expireAfterSeconds=0, name="ttl_expires_at")

    def hit(self, key: str, limit: int, window: float, now: float) -> tuple[bool, int, float]:
        from pymongo import ReturnDocument
        from pymongo.errors import DuplicateKeyError, PyMongoError

        expires = datetime.fromtimestamp(now, timezone.utc) + timedelta(seconds=window)
        pipeline = [
            {"$set": {"hits": {"$filter": {"input": {"$ifNull": ["$hits", []]}, "cond": {"$gt": ["$$this", now - window]}}}}},
            {"$set": {"ok": {"$lt": [{"$size": "$hits"}, limit]}}},
            {
                "$set": {
                    "hits": {"$cond": ["$ok", {"$concatArrays": ["$hits", [now]]}, "$hits"]},
                    "expires_at": expires,
                }
            },
        ]
        def update() -> dict[str, Any]:
            return self._col.find_one_and_update({"_id": key}, pipeline, upsert=True, return_document=ReturnDocument.AFTER)

        try:
            try:
                doc = update()
            except DuplicateKeyError:
                doc = update()  # two first hits raced on the upsert; the document now exists
        except PyMongoError as exc:
            logger.warning("Rate-limit store unavailable (%s); using process-local limits", type(exc).__name__)
            return self._fallback.hit(key, limit, window, now)
        hits = doc.get("hits") or []
        return bool(doc.get("ok")), len(hits), min(hits) if hits else now


def normalise_ip(value: str) -> str | None:
    """Canonical client key: the IPv4 address, or the /64 network for IPv6 (clients rotate
    temporary addresses inside their /64). None if ``value`` is not an IP address."""
    try:
        addr = ipaddress.ip_address(value.strip())
    except ValueError:
        return None
    if addr.version == 6:
        if addr.ipv4_mapped:
            return str(addr.ipv4_mapped)
        return str(ipaddress.ip_network(f"{addr}/64", strict=False))
    return str(addr)


class RateLimiter:
    """Identifies the client in this order:

    1. ``client_ip_header`` (e.g. ``cf-connecting-ip``): a header set by the edge proxy itself,
       which overwrites any value the client sends. Only safe when every request passes that proxy.
    2. ``trusted_proxy_hops``: the X-Forwarded-For entry that many positions from the right;
       entries to its left were supplied by the client and are ignored.
    3. The TCP peer address.
    """

    def __init__(
        self,
        window_seconds: float = 60.0,
        trusted_proxy_hops: int = 0,
        store: HitStore | None = None,
        client_ip_header: str = "",
    ):
        self.window = window_seconds
        self.trusted_proxy_hops = max(0, trusted_proxy_hops)
        self.client_ip_header = client_ip_header.strip().lower()
        self.store: HitStore = store or MemoryHitStore()

    @property
    def scope(self) -> str:
        return self.store.scope

    def client_id(self, request: Request) -> str:
        if self.client_ip_header:
            ip = normalise_ip(request.headers.get(self.client_ip_header, ""))
            if ip:
                return ip
        if self.trusted_proxy_hops:
            hops = [h.strip() for h in request.headers.get("x-forwarded-for", "").split(",") if h.strip()]
            if len(hops) >= self.trusted_proxy_hops:
                ip = normalise_ip(hops[-self.trusted_proxy_hops])
                if ip:
                    return ip
        peer = request.client.host if request.client else "unknown"
        return normalise_ip(peer) or peer[:64]

    def check(self, request: Request, bucket: str, limit: int) -> RateLimitState:
        now = time.time()
        allowed, count, oldest = self.store.hit(f"{bucket}:{self.client_id(request)}", limit, self.window, now)
        state = RateLimitState(
            limit=limit,
            remaining=max(0, limit - count),
            reset_seconds=max(1, math.ceil(oldest + self.window - now)),
            allowed=allowed,
        )
        request.state.rate_limit = state
        if not allowed:
            raise AppError(
                429,
                "rate_limited",
                f"Too many requests. Limit is {limit} per {int(self.window)} seconds.",
                headers={"Retry-After": str(state.reset_seconds), **state.headers()},
            )
        return state
