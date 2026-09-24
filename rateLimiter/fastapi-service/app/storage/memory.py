import asyncio
from collections import defaultdict, deque
from typing import Deque, Dict, Tuple


class MemoryBucketStore:
    """Generic "available units, linear refill toward a ceiling" bucket.

    Used identically by token bucket and by leaky-bucket-as-meter once
    leaky bucket is framed as "space available" rather than "backlog
    used" - space refills exactly like tokens do, so the same primitive
    serves both (see docs/01-algorithms.md once leaky bucket lands in
    Milestone 5).

    A per-key asyncio.Lock guards each read-refill-compare-write as one
    atomic unit - without it, two concurrent requests could both read the
    same pre-refill level and both succeed past capacity. This is the same
    atomicity lesson the Redis Lua script teaches at a different scale
    (storage/redis_backend.py, Milestone 2).
    """

    def __init__(self) -> None:
        self._state: Dict[str, Tuple[float, float]] = {}
        self._locks: Dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def take(
        self, key: str, capacity: float, rate: float, now: float, cost: float = 1.0
    ) -> Tuple[bool, float, float]:
        """Returns (allowed, level_after, retry_after_seconds)."""
        async with self._locks[key]:
            level, ts = self._state.get(key, (capacity, now))
            level = min(capacity, level + max(0.0, now - ts) * rate)

            if level >= cost:
                level -= cost
                allowed, retry_after = True, 0.0
            else:
                allowed = False
                retry_after = (cost - level) / rate if rate > 0 else float("inf")

            self._state[key] = (level, now)
            return allowed, level, retry_after


class MemoryCounterStore:
    """CounterStore backing fixed window and sliding window counter.

    Callers key each window with its own window_index (see
    limiter/fixed_window.py, limiter/sliding_window_counter.py), so a
    given key is only ever written within its own window - there's no
    stale-value-reuse to guard against, only concurrent-within-the-same-
    window access, which the per-key lock handles. `ttl_seconds` is
    accepted for interface parity with the Redis-backed store (where it's
    load-bearing - Redis is shared/persistent and must expire old window
    keys) but unused here; this in-memory store never garbage-collects old
    window counters, which is a real, documented limitation for a
    long-running process (out of scope for this demo).
    """

    def __init__(self) -> None:
        self._counts: Dict[str, int] = defaultdict(int)
        self._locks: Dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def increment_with_expiry(self, key: str, ttl_seconds: float) -> int:
        async with self._locks[key]:
            self._counts[key] += 1
            return self._counts[key]

    async def increment_weighted(
        self, current_key: str, previous_key: str, weight: float, limit: int, ttl_seconds: float
    ) -> Tuple[bool, float]:
        # Locking current_key alone is sufficient for the common case:
        # previous_key belongs to an already-closed window that nothing
        # else increments concurrently. (A request landing exactly on a
        # window boundary could in principle disagree with a neighbor on
        # which window is "current" - an accepted edge case, not solved
        # here.)
        async with self._locks[current_key]:
            current = self._counts.get(current_key, 0)
            previous = self._counts.get(previous_key, 0)
            estimate = previous * weight + current
            if estimate < limit:
                current += 1
                self._counts[current_key] = current
                return True, previous * weight + current
            return False, estimate

    async def get(self, key: str) -> int:
        return self._counts.get(key, 0)


class MemorySlidingLogStore:
    """SlidingLogStore backing sliding window log: an ordered deque of
    request timestamps per key. O(n) memory per key (n = requests within
    the trailing window) - the direct, tangible cost of this algorithm's
    precision, versus the O(1) counters the other four algorithms use.
    """

    def __init__(self) -> None:
        self._logs: Dict[str, Deque[float]] = defaultdict(deque)
        self._locks: Dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def try_add(self, key: str, now: float, window_seconds: float, limit: int) -> Tuple[bool, int]:
        async with self._locks[key]:
            log = self._logs[key]
            cutoff = now - window_seconds
            while log and log[0] <= cutoff:
                log.popleft()
            if len(log) < limit:
                log.append(now)
                return True, len(log)
            return False, len(log)
