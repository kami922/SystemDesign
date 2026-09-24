"""Maps algorithm name -> configured RateLimiter instance.

All five algorithms, both storage backends, as of Milestone 6.
"""
from app.config import settings
from app.limiter.fixed_window import FixedWindowLimiter
from app.limiter.leaky_bucket import LeakyBucketLimiter
from app.limiter.sliding_window_counter import SlidingWindowCounterLimiter
from app.limiter.sliding_window_log import SlidingWindowLogLimiter
from app.limiter.token_bucket import TokenBucketLimiter
from app.redis_client import client as redis_client
from app.storage.memory import MemoryBucketStore, MemoryCounterStore, MemorySlidingLogStore
from app.storage.redis_backend import RedisBucketStore, RedisCounterStore, RedisSlidingLogStore

_limit = settings.default_limit
_window = settings.default_window_seconds
_rate = _limit / _window
_USE_REDIS = settings.storage_backend == "redis"


def _bucket_store(key_prefix: str):
    if _USE_REDIS:
        return RedisBucketStore(redis_client, key_prefix=key_prefix)
    return MemoryBucketStore()


def _counter_store(key_prefix: str):
    # A separate store instance per algorithm (not shared): both
    # fixed_window and sliding_window_counter key their counters as
    # "{client_id}:{window_index}", so sharing one store between them
    # would let one client's traffic on one algorithm collide with the
    # same client's traffic on the other. key_prefix keeps them apart in
    # Redis; separate instances keep them apart in memory.
    if _USE_REDIS:
        return RedisCounterStore(redis_client, key_prefix=key_prefix)
    return MemoryCounterStore()


def _sliding_log_store(key_prefix: str):
    if _USE_REDIS:
        return RedisSlidingLogStore(redis_client, key_prefix=key_prefix)
    return MemorySlidingLogStore()


LIMITERS = {
    "token_bucket": TokenBucketLimiter(
        store=_bucket_store("rl:token_bucket"), capacity=_limit, refill_rate=_rate
    ),
    "leaky_bucket": LeakyBucketLimiter(
        store=_bucket_store("rl:leaky_bucket"), capacity=_limit, refill_rate=_rate
    ),
    "fixed_window": FixedWindowLimiter(
        store=_counter_store("rl:fixed_window"), limit=_limit, window_seconds=_window
    ),
    "sliding_window_log": SlidingWindowLogLimiter(
        store=_sliding_log_store("rl:sliding_window_log"), limit=_limit, window_seconds=_window
    ),
    "sliding_window_counter": SlidingWindowCounterLimiter(
        store=_counter_store("rl:sliding_window_counter"), limit=_limit, window_seconds=_window
    ),
}
