import time
from typing import Optional

from app.limiter.base import RateLimitResult
from app.storage.base import CounterStore


class FixedWindowLimiter:
    def __init__(self, store: CounterStore, limit: int, window_seconds: float) -> None:
        self._store = store
        self._limit = limit
        self._window_seconds = window_seconds

    async def allow(self, key: str) -> RateLimitResult:
        now = time.time()
        window_index = int(now // self._window_seconds)
        window_key = f"{key}:{window_index}"

        # Every request within the window increments the counter,
        # regardless of allow/deny - that's the actual definition of fixed
        # window, not an approximation of it.
        count = await self._store.increment_with_expiry(window_key, self._window_seconds)

        window_end = (window_index + 1) * self._window_seconds
        allowed = count <= self._limit
        remaining = max(0, self._limit - count)
        retry_after: Optional[float] = (window_end - now) if not allowed else None

        return RateLimitResult(
            allowed=allowed,
            limit=self._limit,
            remaining=remaining,
            reset_at=window_end,
            retry_after=retry_after,
        )
