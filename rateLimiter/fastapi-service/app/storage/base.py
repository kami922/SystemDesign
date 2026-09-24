from typing import Protocol, Tuple


class BucketStore(Protocol):
    """Shared shape for token bucket and leaky-bucket-as-meter: a single
    numeric level that refills/drains linearly toward a capacity ceiling,
    with an atomic "take" that combines refill + compare + write into one
    logical step (see storage/memory.py and storage/redis_backend.py for
    why that atomicity matters).
    """

    async def take(
        self, key: str, capacity: float, rate: float, now: float, cost: float = 1.0
    ) -> Tuple[bool, float, float]:
        """Returns (allowed, level_after, retry_after_seconds)."""
        ...


class CounterStore(Protocol):
    """Shared shape for fixed window and sliding window counter.

    `increment_with_expiry` alone is enough for fixed window (one counter,
    one atomic increment). Sliding window counter needs more: it must
    read TWO counters (current + previous window), compute a weighted
    estimate, and conditionally increment - all as ONE atomic step.
    A separate get-then-increment from the algorithm side would
    reintroduce the exact race this project exists to prevent (two
    concurrent requests both read estimate < limit, both increment, both
    admit). So that whole operation is its own store method.
    """

    async def increment_with_expiry(self, key: str, ttl_seconds: float) -> int: ...

    async def increment_weighted(
        self, current_key: str, previous_key: str, weight: float, limit: int, ttl_seconds: float
    ) -> Tuple[bool, float]:
        """Atomically computes estimate = previous*weight + current; if
        estimate < limit, increments current and returns (True, new_estimate);
        otherwise returns (False, estimate) without incrementing."""
        ...

    async def get(self, key: str) -> int: ...


class SlidingLogStore(Protocol):
    """Shape needed by sliding window log alone: an ordered timestamp
    collection (deque in memory, Redis ZSET), not a KV blob - the one
    place the abstraction has to bend to the algorithm's actual data
    shape rather than the other way around. Added in Milestone 5.
    """

    async def try_add(self, key: str, now: float, window_seconds: float, limit: int) -> Tuple[bool, int]:
        """Atomically evicts entries older than window_seconds, and if the
        remaining count is under limit, adds `now` as a new entry. Returns
        (allowed, count_after)."""
        ...
