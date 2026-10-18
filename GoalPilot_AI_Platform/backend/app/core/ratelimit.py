"""A minimal in-process fixed-window rate limiter.

Deliberately not a distributed limiter: the brief says to avoid unnecessary
infrastructure, and this is a single-process academic deployment. It is dependency
injection friendly so a Redis-backed limiter could replace it without touching routes.
"""
from __future__ import annotations

import time
from collections import defaultdict
from threading import Lock

from app.core.errors import RateLimited


class FixedWindowLimiter:
    def __init__(self) -> None:
        self._hits: dict[tuple[str, str], list[float]] = defaultdict(list)
        self._lock = Lock()

    def check(self, bucket: str, identity: str, limit_per_minute: int) -> None:
        if limit_per_minute <= 0:
            return
        now = time.monotonic()
        key = (bucket, identity)
        with self._lock:
            window = [t for t in self._hits[key] if now - t < 60.0]
            if len(window) >= limit_per_minute:
                retry_after = max(0.0, 60.0 - (now - window[0]))
                raise RateLimited(
                    f"Too many requests. Retry in {retry_after:.0f}s.",
                    details={"retry_after_seconds": round(retry_after)},
                )
            window.append(now)
            self._hits[key] = window

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = FixedWindowLimiter()
