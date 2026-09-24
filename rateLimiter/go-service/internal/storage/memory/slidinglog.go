package memory

import (
	"container/list"
	"context"
	"sync"
)

// SlidingLogStore backs sliding window log: an ordered list of request
// timestamps per key (container/list gives O(1) push-back and O(1)
// pop-front, matching Python's deque for this access pattern). O(n)
// memory per key (n = requests within the trailing window) - the direct,
// tangible cost of this algorithm's precision.
type SlidingLogStore struct {
	mu   sync.Mutex
	logs map[string]*list.List
}

func NewSlidingLogStore() *SlidingLogStore {
	return &SlidingLogStore{logs: make(map[string]*list.List)}
}

func (s *SlidingLogStore) TryAdd(
	ctx context.Context, key string, now, windowSeconds float64, limit int,
) (bool, int, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	log, ok := s.logs[key]
	if !ok {
		log = list.New()
		s.logs[key] = log
	}

	cutoff := now - windowSeconds
	for log.Len() > 0 {
		front := log.Front()
		if front.Value.(float64) > cutoff {
			break
		}
		log.Remove(front)
	}

	if log.Len() < limit {
		log.PushBack(now)
		return true, log.Len(), nil
	}
	return false, log.Len(), nil
}
