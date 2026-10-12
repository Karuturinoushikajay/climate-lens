"""Document cache with a MongoDB backend and a process-local in-memory fallback.

Two logical collections are used:
* ``observations`` - raw provider series (long TTL)
* ``analyses``     - derived analysis results (shorter TTL, keyed with the algorithm version)
* ``places``       - place-name search results from the geocoding API

The in-memory cache is per process; with several backend instances each keeps its own copy.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

logger = logging.getLogger(__name__)

COLLECTIONS = ("observations", "analyses", "places")


def make_key(namespace: str, params: dict[str, Any]) -> str:
    canonical = json.dumps(params, sort_keys=True, separators=(",", ":"), default=str)
    return f"{namespace}:{hashlib.sha256(canonical.encode()).hexdigest()}"


class CacheStore(Protocol):
    mode: str

    def get(self, collection: str, key: str) -> dict[str, Any] | None: ...

    def set(self, collection: str, key: str, value: dict[str, Any], ttl_seconds: int) -> None: ...

    def status(self) -> dict[str, Any]: ...


class MemoryCache:
    mode = "memory"

    def __init__(self, max_entries: int = 128, reason: str | None = None):
        self.max_entries = max_entries
        self.reason = reason
        self._data: dict[str, OrderedDict[str, tuple[float, dict[str, Any]]]] = {c: OrderedDict() for c in COLLECTIONS}
        self._lock = threading.Lock()

    def get(self, collection: str, key: str) -> dict[str, Any] | None:
        with self._lock:
            bucket = self._data.setdefault(collection, OrderedDict())
            item = bucket.get(key)
            if item is None:
                return None
            expires_at, value = item
            if expires_at <= time.monotonic():
                bucket.pop(key, None)
                return None
            bucket.move_to_end(key)
            return value

    def set(self, collection: str, key: str, value: dict[str, Any], ttl_seconds: int) -> None:
        with self._lock:
            bucket = self._data.setdefault(collection, OrderedDict())
            bucket[key] = (time.monotonic() + ttl_seconds, value)
            bucket.move_to_end(key)
            while len(bucket) > self.max_entries:
                bucket.popitem(last=False)

    def status(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "healthy": True,
            "detail": self.reason or "Process-local in-memory cache (not shared between instances).",
        }


class MongoCache:
    mode = "mongodb"

    def __init__(self, uri: str, database: str, timeout_ms: int = 3000):
        from pymongo import MongoClient

        self._client = MongoClient(uri, serverSelectionTimeoutMS=timeout_ms, connectTimeoutMS=timeout_ms, appname="climate-lens")
        self._client.admin.command("ping")
        self._db = self._client[database]
        for name in COLLECTIONS:
            self._db[name].create_index("expires_at", expireAfterSeconds=0, name="ttl_expires_at")
        self._healthy = True
        self._last_error: str | None = None

    def get(self, collection: str, key: str) -> dict[str, Any] | None:
        from pymongo.errors import PyMongoError

        try:
            doc = self._db[collection].find_one({"_id": key})
            self._healthy = True
        except PyMongoError as exc:
            self._mark_error(exc)
            return None
        if not doc:
            return None
        expires_at = doc.get("expires_at")
        if expires_at is not None:
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at <= datetime.now(timezone.utc):
                return None  # TTL monitor runs about once a minute; never serve expired data
        return doc.get("payload")

    def set(self, collection: str, key: str, value: dict[str, Any], ttl_seconds: int) -> None:
        from pymongo.errors import PyMongoError

        now = datetime.now(timezone.utc)
        try:
            self._db[collection].replace_one(
                {"_id": key},
                {"_id": key, "payload": value, "created_at": now, "expires_at": now + timedelta(seconds=ttl_seconds)},
                upsert=True,
            )
            self._healthy = True
        except PyMongoError as exc:
            self._mark_error(exc)

    def collection(self, name: str) -> Any:
        return self._db[name]

    def _mark_error(self, exc: Exception) -> None:
        self._healthy = False
        self._last_error = type(exc).__name__
        logger.warning("MongoDB cache operation failed: %s", self._last_error)

    def status(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "healthy": self._healthy,
            "detail": "MongoDB with TTL indexes" if self._healthy else f"MongoDB degraded ({self._last_error}); requests bypass the cache",
        }


def create_cache(uri: str, database: str, timeout_ms: int, max_memory_entries: int) -> CacheStore:
    if not uri:
        return MemoryCache(max_memory_entries, "MONGODB_URI not set; using process-local in-memory cache.")
    try:
        cache = MongoCache(uri, database, timeout_ms)
        logger.info("Connected to MongoDB cache")
        return cache
    except Exception as exc:  # noqa: BLE001 - any connection failure falls back
        logger.warning("MongoDB unavailable (%s); falling back to in-memory cache", type(exc).__name__)
        return MemoryCache(max_memory_entries, f"MongoDB unavailable at startup ({type(exc).__name__}); using in-memory fallback.")
