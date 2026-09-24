import uuid
from pathlib import Path
from typing import Tuple

import redis.asyncio as redis

_LUA_DIR = Path(__file__).parent / "lua"


class RedisBucketStore:
    """Redis-backed counterpart to MemoryBucketStore - same take() shape,
    same semantics, atomicity provided by a Lua script (EVAL) instead of
    an in-process lock, so it's correct across multiple app replicas
    sharing one Redis (see docs/03-distributed-correctness.md, Milestone 3).
    """

    def __init__(self, client: redis.Redis, key_prefix: str) -> None:
        self._client = client
        self._key_prefix = key_prefix
        self._script = client.register_script((_LUA_DIR / "token_bucket.lua").read_text())

    async def take(
        self, key: str, capacity: float, rate: float, now: float, cost: float = 1.0
    ) -> Tuple[bool, float, float]:
        redis_key = f"{self._key_prefix}:{key}"
        allowed, level, retry_after = await self._script(
            keys=[redis_key], args=[capacity, rate, now, cost]
        )
        return bool(int(allowed)), float(level), float(retry_after)


class RedisCounterStore:
    """Redis-backed counterpart to MemoryCounterStore. Backs fixed window
    (via increment_with_expiry) and sliding window counter (via
    increment_weighted) - see storage/base.py's CounterStore docstring for
    why the latter must be one atomic script rather than get-then-increment.
    """

    def __init__(self, client: redis.Redis, key_prefix: str) -> None:
        self._client = client
        self._key_prefix = key_prefix
        self._incr_script = client.register_script((_LUA_DIR / "fixed_window.lua").read_text())
        self._weighted_script = client.register_script(
            (_LUA_DIR / "sliding_window_counter.lua").read_text()
        )

    def _key(self, key: str) -> str:
        return f"{self._key_prefix}:{key}"

    async def increment_with_expiry(self, key: str, ttl_seconds: float) -> int:
        return int(await self._incr_script(keys=[self._key(key)], args=[ttl_seconds]))

    async def increment_weighted(
        self, current_key: str, previous_key: str, weight: float, limit: int, ttl_seconds: float
    ) -> Tuple[bool, float]:
        allowed, estimate = await self._weighted_script(
            keys=[self._key(current_key), self._key(previous_key)],
            args=[weight, limit, ttl_seconds],
        )
        return bool(int(allowed)), float(estimate)

    async def get(self, key: str) -> int:
        value = await self._client.get(self._key(key))
        return int(value) if value is not None else 0


class RedisSlidingLogStore:
    """Redis-backed counterpart to MemorySlidingLogStore, using a ZSET
    (score = timestamp ms) instead of a deque - see
    storage/lua/sliding_window_log.lua for why members must be unique
    per-request, not just the timestamp.
    """

    def __init__(self, client: redis.Redis, key_prefix: str) -> None:
        self._client = client
        self._key_prefix = key_prefix
        self._script = client.register_script((_LUA_DIR / "sliding_window_log.lua").read_text())

    async def try_add(
        self, key: str, now: float, window_seconds: float, limit: int
    ) -> Tuple[bool, int]:
        redis_key = f"{self._key_prefix}:{key}"
        now_ms = int(now * 1000)
        window_ms = int(window_seconds * 1000)
        member = f"{now_ms}-{uuid.uuid4().hex[:8]}"
        allowed, count = await self._script(
            keys=[redis_key], args=[now_ms, window_ms, limit, member]
        )
        return bool(int(allowed)), int(count)
