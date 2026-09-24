import time
from typing import Optional

from app.limiter.base import RateLimitResult
from app.storage.base import SlidingLogStore


class SlidingWindowLogLimiter:
    def __init__(self, store: SlidingLogStore, limit: int, window_seconds: float) -> None:
        self._store = store
        self._limit = limit
        self._window_seconds = window_seconds

    async def allow(self, key: str) -> RateLimitResult:
        now = time.time()
        allowed, count = await self._store.try_add(key, now, self._window_seconds, self._limit)
        remaining = max(0, self._limit - count)

        # The store doesn't expose the oldest surviving timestamp, so
        # reset/retry are approximated as "a full window from now" rather
        # than "when the oldest entry actually falls out" - a conservative
        # upper bound, fine for headers, not used for the admit decision.
        reset_at = now + self._window_seconds
        retry_after: Optional[float] = self._window_seconds if not allowed else None

        return RateLimitResult(
            allowed=allowed,
            limit=self._limit,
            remaining=remaining,
            reset_at=reset_at,
            retry_after=retry_after,
        )
