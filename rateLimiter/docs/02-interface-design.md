# Interface design

## The top-level contract

Every algorithm, regardless of storage backend, implements the same shape:

```python
class RateLimiter(Protocol):
    async def allow(self, key: str) -> RateLimitResult: ...
```

```python
@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    reset_at: float
    retry_after: float | None
```

This is what `routers/action.py` depends on — it never knows or cares which
algorithm or storage backend is behind a given `LIMITERS[algorithm]` entry.
Go's `Limiter` interface (`internal/limiter/result.go`) mirrors this
exactly, field for field.

## Why storage isn't one generic interface

The obvious "clean" design is a single `Store` protocol with `get`/`set`.
It's also wrong for this project: a generic get-then-compute-then-set from
the *application* side reintroduces, in the storage layer, the exact race
condition the whole distributed-correctness story is about — two concurrent
callers could both `get` the same pre-update state, both compute "allowed,"
and both `set`, together admitting more than the limit. That's not a
storage-implementation detail, it's the core problem.

So storage is split into **three protocols, each matched to the atomic
unit of work its family of algorithms actually needs** (`app/storage/base.py`):

- **`BucketStore`** — token bucket, leaky bucket. `take(key, capacity,
  rate, now, cost) -> (allowed, level_after, retry_after)`. The refill,
  the comparison, and the write happen as one atomic operation *inside*
  the store — an in-process lock for the in-memory version
  (`storage/memory.py`), a Lua script for Redis (`storage/redis_backend.py`).
  The caller never sees an intermediate state.
- **`CounterStore`** — fixed window, sliding window counter (Milestone 5).
  `increment_with_expiry(key, ttl) -> count`.
- **`SlidingLogStore`** — sliding window log only (Milestone 5). Needs an
  *ordered timestamp collection*, not a KV blob — a `deque` in memory, a
  Redis `ZSET`. This is the one place the abstraction has to bend to the
  algorithm's actual data shape rather than the reverse; forcing it into
  `CounterStore`'s shape would mean either losing ordering information or
  reimplementing a sorted structure on top of a counter, which is backwards.

**Even the in-memory stores need per-key locking**, not just Redis
(`MemoryBucketStore` uses a `defaultdict(asyncio.Lock)`). It would be easy
to skip this — a single Python process feels safe — but `asyncio.Lock`
guards against interleaving *between coroutines*, not just between OS
threads: two concurrent requests for the same key, both `await`ing inside
the read-refill-write sequence, can genuinely interleave at an `await`
point without a lock. Leaving this out wouldn't just be sloppy, it would
hide the actual lesson (atomic check-and-update) at exactly the scale
where it's cheapest to see clearly, before Redis and Lua scripts add their
own complexity on top.

## Token bucket and leaky bucket are the same store

`BucketStore` is used *identically*, byte-for-byte, by both token bucket
and leaky-bucket-as-meter (Milestone 5) — this isn't a coincidence to
paper over, it's worth stating plainly: leaky-bucket-as-meter, reframed as
"space available" instead of "backlog used," refills exactly like a token
bucket's tokens do. `space_available = capacity - backlog`, and space
regenerates at the leak rate the same way tokens regenerate at the refill
rate. The two algorithms are mathematically dual; only the terminology
(and which quantity you report to the caller) differs. One store, two thin
limiter classes on top.

## What's deliberately NOT abstracted

- **Algorithm math lives in the limiter classes** (`limiter/token_bucket.py`
  etc.), not the stores. A store answers "was this atomic operation
  allowed, and what's the state now" — it doesn't know about `reset_at`
  semantics, header formatting, or anything HTTP-shaped.
- **No shared base class across limiters.** Five algorithms, five small
  classes, all satisfying the same `RateLimiter` Protocol. A shared abstract
  base would save a few lines and cost real clarity — each algorithm's
  `allow()` method should read as a direct translation of its math, not a
  set of template-method hooks.

## Regression gate

Before adding the remaining four algorithms (Milestone 5) or Redis for
them (Milestone 6), everything built so far — `tests/test_token_bucket.py`
against both storage backends, `tests/test_distributed_correctness.py`
against both modes — must still pass unchanged. This is the checkpoint
that proves the storage-protocol split holds up under exactly the load
it's about to carry four more times.
