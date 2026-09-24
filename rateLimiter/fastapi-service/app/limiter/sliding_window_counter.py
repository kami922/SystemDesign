import time
from typing import Optional

from app.limiter.base import RateLimitResult
from app.storage.base import CounterStore


class SlidingWindowCounterLimiter:
    def __init__(self, store: CounterStore, limit: int, window_seconds: float) -> None:
        self._store = store
        self._limit = limit
        self._window_seconds = window_seconds

    async def allow(self, key: str) -> RateLimitResult:
        now = time.time()
        window_index = int(now // self._window_seconds)
        window_start = window_index * self._window_seconds
        weight = 1 - ((now - window_start) / self._window_seconds)

        current_key = f"{key}:{window_index}"
        previous_key = f"{key}:{window_index - 1}"

        # Read-both-and-conditionally-increment as ONE atomic store call -
        # see storage/base.py's CounterStore docstring for why a separate
        # get-then-increment here would reintroduce the exact race this
        # project exists to prevent.
        allowed, estimate = await self._store.increment_weighted(
            current_key, previous_key, weight, self._limit, self._window_seconds * 2
        )

        remaining = max(0, int(self._limit - estimate))
        window_end = window_start + self._window_seconds
        retry_after: Optional[float] = (window_end - now) if not allowed else None

        return RateLimitResult(
            allowed=allowed,
            limit=self._limit,
            remaining=remaining,
            reset_at=window_end,
            retry_after=retry_after,
        )
