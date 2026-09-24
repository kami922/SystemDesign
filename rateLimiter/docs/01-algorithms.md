# Algorithms

All five are configured from the same two knobs — `RATE_LIMIT_DEFAULT_LIMIT`
(`N`) and `RATE_LIMIT_DEFAULT_WINDOW_SECONDS` (`W`) — so they're directly
comparable: bucket algorithms derive `capacity=N`, `rate=N/W`; the rest use
`limit=N`, `window=W` directly. Key convention: `rl:{algo}:{client_id}`.

## Token bucket

**State**: `tokens` (float, available now), `ts` (last update).
**Model**: tokens refill continuously at `rate` up to `capacity`; a request
costs 1 token, denied if insufficient.
**Storage**: `BucketStore.take()` — see [02-interface-design.md](02-interface-design.md)
for why refill+compare+write must be one atomic step.

**Weakness (by design, not a flaw)**: a full-capacity burst is allowed
immediately after any idle period — the bucket doesn't know or care how
that capacity accumulated. This is the intentional tradeoff that makes
token bucket good at absorbing legitimate bursts (a user who's been idle
for a while gets to burst).

## Leaky bucket (meter variant)

Implemented as a level/backlog dual of token bucket — reject when over
capacity — **not** a literal FIFO queue with a drain worker. A true
queueing leaky bucket is a *traffic shaper*: it delays excess requests
instead of rejecting them, which means holding the connection open and
answering late rather than answering "no" — that breaks the synchronous
`allow() -> allowed/denied` interface every other algorithm and the demo
API share. This variant is a *policer*, matching what production API rate
limiters (and the other four algorithms here) actually do.

**The non-obvious part**: reframed as "space available" (`capacity -
backlog`) instead of "backlog used," leaky-bucket-as-meter is
*mathematically identical* to token bucket — space regenerates at the leak
rate exactly like tokens regenerate at the refill rate. `LeakyBucketLimiter`
literally subclasses `TokenBucketLimiter` with no overrides
(`fastapi-service/app/limiter/leaky_bucket.py`). Measured: both hit exactly
`capacity` allowed on a burst and 100% admission when trickled at the leak
rate — identical behavior, because it's identical math.

**Weakness**: easy to implement "by flipping a comparison" without
understanding *why* it differs from token bucket, or that the textbook
"queue" version is a different algorithm entirely with different
operational characteristics (added latency vs added rejections).

## Fixed window counter

**State**: an integer count per `(client_id, window_index)`, where
`window_index = floor(now / window_seconds)`.
**Model**: every request increments the counter for the current window,
regardless of allow/deny — allowed while `count <= limit`.
**Storage**: `CounterStore.increment_with_expiry()` — one atomic INCR
(+expiry-if-first), because incrementing without a TTL would let old
window keys accumulate forever, and a naive separate INCR-then-EXPIRE
leaves a gap where a crash/preemption between the two calls loses the TTL.

**Weakness (the headline one) — measured, not just described**: `limit`
requests just before a window edge plus `limit` more just after can both
fully succeed. Measured directly (`tests/test_fixed_window.py`,
`limit=10`): **20 requests admitted** across a boundary that should only
allow ~10 in that timespan — exactly double. This isn't a bug to patch; it's
the structural cost of resetting to zero on a fixed calendar boundary,
independent of actual request history. The next two algorithms exist
specifically to fix this.

## Sliding window log

**State**: every request timestamp within the trailing `window_seconds`.
**Storage**: `SlidingLogStore.try_add()` — evict expired entries, count,
and conditionally append, all as one atomic step (a separate
evict-then-count-then-add would let two concurrent requests both see room
and both add, exceeding the limit).

**The same boundary scenario that broke fixed window, run against this
algorithm**: **10 + 0 = 10 admitted** (`tests/test_sliding_window_log.py`).
Zero double-burst — because "the trailing `window_seconds` from now" has
no calendar-aligned edge to exploit at all. This is the most accurate of
the three window-based algorithms.

**Weakness**: O(n) memory per key, where n = the request count within the
window — the most accurate algorithm is also the most expensive one, a
direct memory-vs-precision tradeoff against the next algorithm.

## Sliding window counter

**State**: two fixed-window counters, `current` (this window_index) and
`previous` (window_index - 1). Estimate = `previous * weight + current`,
where `weight = 1 - (elapsed_in_current_window / window_seconds)`.
**Storage**: `CounterStore.increment_weighted()` — reading both counters,
computing the weighted estimate, and conditionally incrementing must be
one atomic operation. A separate get-both-then-increment would reintroduce
the same race the whole project is about: two concurrent requests both
read `estimate < limit`, both increment, both admit past the limit.

**Same boundary scenario again**: **10 + 1 = 11 admitted**
(`tests/test_sliding_window_counter.py`) — not the log's perfect 10, but
nowhere near fixed window's 20. This is the direct, measured payoff of
the approximation: cheap like fixed window (two O(1) counters, no
per-request timestamp storage), but far more resistant to the boundary
exploit because the previous window's weight doesn't just vanish at the
edge.

**Weakness**: it's an *approximation* — the math assumes requests are
distributed roughly uniformly within each window, which is not always
true. Cheap and mostly-accurate, not exact.

## Side-by-side: the same attack, three outcomes

| Algorithm | Requests admitted across one boundary crossing (nominal limit = 10) |
|---|---|
| Fixed window counter | **20** (full double-burst) |
| Sliding window counter | **11** (approximation nearly eliminates it) |
| Sliding window log | **10** (exact — no double-burst at all) |

This is the real, measured shape of the classic "accuracy vs cost"
tradeoff in rate limiting: exactness (sliding log, O(n) memory) at one
end, cheapness with a known error bound (sliding counter, O(1) memory) in
the middle, and cheapness with a known structural flaw (fixed window,
O(1) memory) at the other end. None of the three is strictly better —
which one is right depends on whether the boundary exploit actually
matters for what's being protected.
