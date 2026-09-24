package limiter

import "context"

// BucketStore: shared shape for token bucket and leaky-bucket-as-meter -
// see the Python fastapi-service/app/storage/base.py for the full
// rationale, mirrored here field-for-field.
type BucketStore interface {
	// Take returns (allowed, levelAfter, retryAfterSeconds).
	Take(ctx context.Context, key string, capacity, rate, now, cost float64) (bool, float64, float64, error)
}

// CounterStore: shared shape for fixed window and sliding window counter.
// IncrementWeighted must be one atomic operation (not a separate
// get-both-then-increment) - see storage/memory's CounterStore doc comment.
type CounterStore interface {
	IncrementWithExpiry(ctx context.Context, key string, ttlSeconds float64) (int, error)
	// IncrementWeighted returns (allowed, estimateAfter).
	IncrementWeighted(
		ctx context.Context, currentKey, previousKey string, weight float64, limit int, ttlSeconds float64,
	) (bool, float64, error)
	Get(ctx context.Context, key string) (int, error)
}

// SlidingLogStore: shape needed by sliding window log alone - an ordered
// timestamp collection, not a KV blob.
type SlidingLogStore interface {
	// TryAdd returns (allowed, countAfter).
	TryAdd(ctx context.Context, key string, now, windowSeconds float64, limit int) (bool, int, error)
}
