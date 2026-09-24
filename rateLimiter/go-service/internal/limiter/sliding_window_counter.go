package limiter

import (
	"context"
	"fmt"
	"math"
	"time"
)

type SlidingWindowCounterLimiter struct {
	Store         CounterStore
	Limit         int
	WindowSeconds float64
}

func (l *SlidingWindowCounterLimiter) Allow(ctx context.Context, key string) (Result, error) {
	now := float64(time.Now().UnixNano()) / 1e9
	windowIndex := int64(math.Floor(now / l.WindowSeconds))
	windowStart := float64(windowIndex) * l.WindowSeconds
	weight := 1 - (now-windowStart)/l.WindowSeconds

	currentKey := fmt.Sprintf("%s:%d", key, windowIndex)
	previousKey := fmt.Sprintf("%s:%d", key, windowIndex-1)

	// Read-both-and-conditionally-increment as ONE atomic store call - see
	// stores.go's CounterStore doc comment for why a separate
	// get-then-increment here would reintroduce the exact race this
	// project exists to prevent.
	allowed, estimate, err := l.Store.IncrementWeighted(
		ctx, currentKey, previousKey, weight, l.Limit, l.WindowSeconds*2,
	)
	if err != nil {
		return Result{}, err
	}

	remaining := max(0, int(float64(l.Limit)-estimate))
	windowEnd := windowStart + l.WindowSeconds

	result := Result{Allowed: allowed, Limit: l.Limit, Remaining: remaining, ResetAt: windowEnd}
	if !allowed {
		retryAfter := windowEnd - now
		result.RetryAfter = &retryAfter
	}
	return result, nil
}
