"""Lightweight in-process TTL cache for Vercel serverless functions.

Each serverless invocation may have its own isolated process, so this cache
only helps within the warm lifetime of a single function instance. That is still
very valuable because Vercel reuses warm instances for concurrent and successive
requests within the same invocation window.

No external dependencies. No Redis. No paid services.
"""

import time
import threading
from typing import Any, Optional


class TTLCache:
    """Thread-safe in-memory TTL cache backed by a plain dict."""

    def __init__(self) -> None:
        self._store: dict[str, tuple[Any, float]] = {}  # key -> (value, expires_at)
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            value, expires_at = entry
            if time.monotonic() > expires_at:
                del self._store[key]
                return None
            return value

    def set(self, key: str, value: Any, ttl_seconds: float) -> None:
        with self._lock:
            self._store[key] = (value, time.monotonic() + ttl_seconds)

    def delete(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    def clear_prefix(self, prefix: str) -> None:
        with self._lock:
            keys = [k for k in self._store if k.startswith(prefix)]
            for k in keys:
                del self._store[k]


# Module-level singleton — shared across all requests in the same warm process
cache = TTLCache()

# TTL constants (seconds)
TTL_CREATORS_LIST = 300     # 5 minutes
TTL_CREATOR_DETAIL = 300    # 5 minutes
TTL_COMMUNITY_POSTS = 60    # 60 seconds
TTL_LEADERBOARD = 300       # 5 minutes
