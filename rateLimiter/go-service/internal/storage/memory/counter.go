package memory

import (
	"context"
	"sync"
)

// CounterStore backs fixed window (IncrementWithExpiry) and sliding
// window counter (IncrementWeighted). ttlSeconds is accepted for
// interface parity with the Redis-backed store (load-bearing there) but
// unused here - this in-memory store never garbage-collects old window
// counters, a documented limitation for a long-running process.
type CounterStore struct {
	mu     sync.Mutex
	counts map[string]int
}

func NewCounterStore() *CounterStore {
	return &CounterStore{counts: make(map[string]int)}
}

func (s *CounterStore) IncrementWithExpiry(ctx context.Context, key string, ttlSeconds float64) (int, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.counts[key]++
	return s.counts[key], nil
}

func (s *CounterStore) IncrementWeighted(
	ctx context.Context, currentKey, previousKey string, weight float64, limit int, ttlSeconds float64,
) (bool, float64, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	current := s.counts[currentKey]
	previous := s.counts[previousKey]
	estimate := float64(previous)*weight + float64(current)

	if estimate < float64(limit) {
		current++
		s.counts[currentKey] = current
		return true, float64(previous)*weight + float64(current), nil
	}
	return false, estimate, nil
}

func (s *CounterStore) Get(ctx context.Context, key string) (int, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.counts[key], nil
}
