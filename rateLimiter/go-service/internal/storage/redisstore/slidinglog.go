package redisstore

import (
	"context"
	"crypto/rand"
	_ "embed"
	"encoding/hex"
	"fmt"

	"github.com/redis/go-redis/v9"
)

//go:embed lua/sliding_window_log.lua
var slidingWindowLogScript string

// SlidingLogStore is the Redis-backed counterpart to memory.SlidingLogStore,
// using a ZSET (score = timestamp ms) instead of a linked list - see
// lua/sliding_window_log.lua for why members must be unique per-request,
// not just the timestamp.
type SlidingLogStore struct {
	client    *redis.Client
	keyPrefix string
	script    *redis.Script
}

func NewSlidingLogStore(client *redis.Client, keyPrefix string) *SlidingLogStore {
	return &SlidingLogStore{
		client:    client,
		keyPrefix: keyPrefix,
		script:    redis.NewScript(slidingWindowLogScript),
	}
}

func randomSuffix() string {
	b := make([]byte, 4)
	_, _ = rand.Read(b)
	return hex.EncodeToString(b)
}

func (s *SlidingLogStore) TryAdd(
	ctx context.Context, key string, now, windowSeconds float64, limit int,
) (bool, int, error) {
	redisKey := fmt.Sprintf("%s:%s", s.keyPrefix, key)
	nowMs := int64(now * 1000)
	windowMs := int64(windowSeconds * 1000)
	member := fmt.Sprintf("%d-%s", nowMs, randomSuffix())

	res, err := s.script.Run(ctx, s.client, []string{redisKey}, nowMs, windowMs, limit, member).Slice()
	if err != nil {
		return false, 0, err
	}
	allowed := res[0].(int64) == 1
	count := int(res[1].(int64))
	return allowed, count, nil
}
