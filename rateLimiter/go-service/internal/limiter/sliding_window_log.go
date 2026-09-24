package limiter

import (
	"context"
	"time"
)

type SlidingWindowLogLimiter struct {
	Store         SlidingLogStore
	Limit         int
	WindowSeconds float64
}

func (l *SlidingWindowLogLimiter) Allow(ctx context.Context, key string) (Result, error) {
	now := float64(time.Now().UnixNano()) / 1e9
	allowed, count, err := l.Store.TryAdd(ctx, key, now, l.WindowSeconds, l.Limit)
	if err != nil {
		return Result{}, err
	}

	remaining := max(0, l.Limit-count)
	// The store doesn't expose the oldest surviving timestamp, so
	// reset/retry are approximated as "a full window from now" - a
	// conservative upper bound, fine for headers, not used for the admit
	// decision.
	resetAt := now + l.WindowSeconds

	result := Result{Allowed: allowed, Limit: l.Limit, Remaining: remaining, ResetAt: resetAt}
	if !allowed {
		retryAfter := l.WindowSeconds
		result.RetryAfter = &retryAfter
	}
	return result, nil
}
