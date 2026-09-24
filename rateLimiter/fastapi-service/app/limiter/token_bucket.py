import time

from app.limiter.base import RateLimitResult
from app.storage.base import BucketStore


class TokenBucketLimiter:
    def __init__(self, store: BucketStore, capacity: int, refill_rate: float) -> None:
        self._store = store
        self._capacity = capacity
        self._refill_rate = refill_rate  # tokens per second

    async def allow(self, key: str) -> RateLimitResult:
        now = time.time()
        allowed, tokens_after, retry_after = await self._store.take(
            key, capacity=self._capacity, rate=self._refill_rate, now=now
        )
        remaining = int(tokens_after)
        # "Reset" for a continuously-refilling bucket = time until it's
        # back to full, not a discrete window edge like fixed window has.
        reset_at = (
            now + (self._capacity - tokens_after) / self._refill_rate
            if self._refill_rate > 0
            else now
        )
        return RateLimitResult(
            allowed=allowed,
            limit=self._capacity,
            remaining=remaining,
            reset_at=reset_at,
            retry_after=retry_after if not allowed else None,
        )
