package limiter

import "context"

type Result struct {
	Allowed    bool
	Limit      int
	Remaining  int
	ResetAt    float64
	RetryAfter *float64
}

type Limiter interface {
	Allow(ctx context.Context, key string) (Result, error)
}
