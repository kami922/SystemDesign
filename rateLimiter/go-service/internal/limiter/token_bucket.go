package limiter

import (
	"context"
	"time"
)

type TokenBucketLimiter struct {
	Store      BucketStore
	Capacity   float64
	RefillRate float64
}

func (l *TokenBucketLimiter) Allow(ctx context.Context, key string) (Result, error) {
	now := float64(time.Now().UnixNano()) / 1e9
	allowed, tokensAfter, retryAfter, err := l.Store.Take(ctx, key, l.Capacity, l.RefillRate, now, 1.0)
	if err != nil {
		return Result{}, err
	}

	resetAt := now
	if l.RefillRate > 0 {
		resetAt = now + (l.Capacity-tokensAfter)/l.RefillRate
	}

	result := Result{
		Allowed:   allowed,
		Limit:     int(l.Capacity),
		Remaining: int(tokensAfter),
		ResetAt:   resetAt,
	}
	if !allowed {
		result.RetryAfter = &retryAfter
	}
	return result, nil
}
