package limiter

import (
	"context"
	"fmt"
	"math"
	"time"
)

type FixedWindowLimiter struct {
	Store         CounterStore
	Limit         int
	WindowSeconds float64
}

func (l *FixedWindowLimiter) Allow(ctx context.Context, key string) (Result, error) {
	now := float64(time.Now().UnixNano()) / 1e9
	windowIndex := int64(math.Floor(now / l.WindowSeconds))
	windowKey := fmt.Sprintf("%s:%d", key, windowIndex)

	// Every request within the window increments the counter, regardless
	// of allow/deny - that's the actual definition of fixed window, not an
	// approximation of it.
	count, err := l.Store.IncrementWithExpiry(ctx, windowKey, l.WindowSeconds)
	if err != nil {
		return Result{}, err
	}

	windowEnd := float64(windowIndex+1) * l.WindowSeconds
	allowed := count <= l.Limit
	remaining := max(0, l.Limit-count)

	result := Result{Allowed: allowed, Limit: l.Limit, Remaining: remaining, ResetAt: windowEnd}
	if !allowed {
		retryAfter := windowEnd - now
		result.RetryAfter = &retryAfter
	}
	return result, nil
}
