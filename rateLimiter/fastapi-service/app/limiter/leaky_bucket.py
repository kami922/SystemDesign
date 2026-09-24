"""Leaky bucket, implemented as a meter (reject when over capacity), not a
literal FIFO queue with a drain worker - see docs/01-algorithms.md. A true
queueing leaky bucket delays excess requests instead of rejecting them,
which needs an async worker holding the connection open, and doesn't fit
the synchronous allow() -> bool interface every algorithm here shares.

As a meter, leaky bucket is mathematically identical to token bucket: read
"space available" (capacity - backlog) instead of "tokens available," and
it refills exactly the same way - see docs/02-interface-design.md. Same
store, same math, different name for the same underlying model.
"""
from app.limiter.token_bucket import TokenBucketLimiter


class LeakyBucketLimiter(TokenBucketLimiter):
    pass
