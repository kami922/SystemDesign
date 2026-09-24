package redisstore

import (
	"context"
	_ "embed"
	"fmt"
	"strconv"

	"github.com/redis/go-redis/v9"
)

//go:embed lua/token_bucket.lua
var tokenBucketScript string

// BucketStore is the Redis-backed counterpart to memory.BucketStore - same
// Take() shape, same semantics, atomicity from a Lua script (EVAL) instead
// of a mutex, so it's correct across multiple app replicas sharing one
// Redis (see docs/03-distributed-correctness.md).
type BucketStore struct {
	client    *redis.Client
	keyPrefix string
	script    *redis.Script
}

func NewBucketStore(client *redis.Client, keyPrefix string) *BucketStore {
	return &BucketStore{client: client, keyPrefix: keyPrefix, script: redis.NewScript(tokenBucketScript)}
}

func (s *BucketStore) Take(
	ctx context.Context, key string, capacity, rate, now, cost float64,
) (bool, float64, float64, error) {
	redisKey := fmt.Sprintf("%s:%s", s.keyPrefix, key)
	res, err := s.script.Run(ctx, s.client, []string{redisKey}, capacity, rate, now, cost).Slice()
	if err != nil {
		return false, 0, 0, err
	}
	allowed := res[0].(int64) == 1
	level, _ := strconv.ParseFloat(res[1].(string), 64)
	retryAfter, _ := strconv.ParseFloat(res[2].(string), 64)
	return allowed, level, retryAfter, nil
}
