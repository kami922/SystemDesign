package redisstore

import (
	"context"
	_ "embed"
	"fmt"
	"strconv"

	"github.com/redis/go-redis/v9"
)

//go:embed lua/fixed_window.lua
var fixedWindowScript string

//go:embed lua/sliding_window_counter.lua
var slidingWindowCounterScript string

// CounterStore is the Redis-backed counterpart to memory.CounterStore.
type CounterStore struct {
	client         *redis.Client
	keyPrefix      string
	incrScript     *redis.Script
	weightedScript *redis.Script
}

func NewCounterStore(client *redis.Client, keyPrefix string) *CounterStore {
	return &CounterStore{
		client:         client,
		keyPrefix:      keyPrefix,
		incrScript:     redis.NewScript(fixedWindowScript),
		weightedScript: redis.NewScript(slidingWindowCounterScript),
	}
}

func (s *CounterStore) key(k string) string {
	return fmt.Sprintf("%s:%s", s.keyPrefix, k)
}

func (s *CounterStore) IncrementWithExpiry(ctx context.Context, key string, ttlSeconds float64) (int, error) {
	res, err := s.incrScript.Run(ctx, s.client, []string{s.key(key)}, ttlSeconds).Result()
	if err != nil {
		return 0, err
	}
	return int(res.(int64)), nil
}

func (s *CounterStore) IncrementWeighted(
	ctx context.Context, currentKey, previousKey string, weight float64, limit int, ttlSeconds float64,
) (bool, float64, error) {
	res, err := s.weightedScript.Run(
		ctx, s.client, []string{s.key(currentKey), s.key(previousKey)}, weight, limit, ttlSeconds,
	).Slice()
	if err != nil {
		return false, 0, err
	}
	allowed := res[0].(int64) == 1
	estimate, _ := strconv.ParseFloat(res[1].(string), 64)
	return allowed, estimate, nil
}

func (s *CounterStore) Get(ctx context.Context, key string) (int, error) {
	val, err := s.client.Get(ctx, s.key(key)).Result()
	if err == redis.Nil {
		return 0, nil
	}
	if err != nil {
		return 0, err
	}
	n, _ := strconv.Atoi(val)
	return n, nil
}
