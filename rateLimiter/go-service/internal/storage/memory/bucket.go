package memory

import (
	"context"
	"math"
	"sync"
)

type bucketState struct {
	level float64
	ts    float64
}

// BucketStore uses a single mutex guarding the whole map rather than a
// per-key lock (contrast with Python's asyncio.Lock-per-key in
// storage/memory.py): Go's built-in map isn't safe for concurrent access
// even to different keys without a lock covering the map itself, so a
// per-key lock alone wouldn't actually be safe here without extra
// machinery (e.g. sync.Map plus per-entry mutexes). Simpler and still
// fully correct; costs some parallelism across distinct keys - worth
// remembering when interpreting Go vs FastAPI load-test numbers later
// (Milestone 9).
type BucketStore struct {
	mu    sync.Mutex
	state map[string]bucketState
}

func NewBucketStore() *BucketStore {
	return &BucketStore{state: make(map[string]bucketState)}
}

func (s *BucketStore) Take(
	ctx context.Context, key string, capacity, rate, now, cost float64,
) (bool, float64, float64, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	st, ok := s.state[key]
	if !ok {
		st = bucketState{level: capacity, ts: now}
	}

	level := math.Min(capacity, st.level+math.Max(0, now-st.ts)*rate)

	var allowed bool
	var retryAfter float64
	if level >= cost {
		level -= cost
		allowed = true
	} else {
		retryAfter = (cost - level) / rate
	}

	s.state[key] = bucketState{level: level, ts: now}
	return allowed, level, retryAfter, nil
}
