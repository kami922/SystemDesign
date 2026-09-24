package limiter

// LeakyBucketLimiter is a genuine type alias for TokenBucketLimiter, not
// just similar code - see docs/01-algorithms.md and
// docs/02-interface-design.md for why leaky bucket, framed as "space
// available" instead of "backlog used," is mathematically identical to
// token bucket. Same store, same math; Go's type alias makes that
// equivalence explicit rather than duplicating the struct.
type LeakyBucketLimiter = TokenBucketLimiter
