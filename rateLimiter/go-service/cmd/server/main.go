package main

import (
	"encoding/json"
	"log"
	"net/http"
	"time"

	"github.com/go-chi/chi/v5"
	goredis "github.com/redis/go-redis/v9"

	"ratelimiter/internal/config"
	"ratelimiter/internal/handlers"
	"ratelimiter/internal/limiter"
	"ratelimiter/internal/storage/memory"
	"ratelimiter/internal/storage/redisstore"
)

func buildLimiters(cfg config.Settings) map[string]limiter.Limiter {
	limitF := float64(cfg.DefaultLimit)
	window := cfg.DefaultWindowSeconds
	rate := limitF / window
	useRedis := cfg.StorageBackend == "redis"

	var redisClient *goredis.Client
	if useRedis {
		opt, err := goredis.ParseURL(cfg.RedisURL)
		if err != nil {
			log.Fatalf("parse redis url: %v", err)
		}
		redisClient = goredis.NewClient(opt)
	}

	bucketStore := func(prefix string) limiter.BucketStore {
		if useRedis {
			return redisstore.NewBucketStore(redisClient, prefix)
		}
		return memory.NewBucketStore()
	}
	// A separate store instance per algorithm (not shared): both
	// fixed_window and sliding_window_counter key their counters as
	// "{client_id}:{window_index}", so sharing one store between them
	// would let one client's traffic on one algorithm collide with the
	// same client's traffic on the other.
	counterStore := func(prefix string) limiter.CounterStore {
		if useRedis {
			return redisstore.NewCounterStore(redisClient, prefix)
		}
		return memory.NewCounterStore()
	}
	slidingLogStore := func(prefix string) limiter.SlidingLogStore {
		if useRedis {
			return redisstore.NewSlidingLogStore(redisClient, prefix)
		}
		return memory.NewSlidingLogStore()
	}

	return map[string]limiter.Limiter{
		"token_bucket": &limiter.TokenBucketLimiter{
			Store: bucketStore("rl:token_bucket"), Capacity: limitF, RefillRate: rate,
		},
		"leaky_bucket": &limiter.LeakyBucketLimiter{
			Store: bucketStore("rl:leaky_bucket"), Capacity: limitF, RefillRate: rate,
		},
		"fixed_window": &limiter.FixedWindowLimiter{
			Store: counterStore("rl:fixed_window"), Limit: cfg.DefaultLimit, WindowSeconds: window,
		},
		"sliding_window_log": &limiter.SlidingWindowLogLimiter{
			Store: slidingLogStore("rl:sliding_window_log"), Limit: cfg.DefaultLimit, WindowSeconds: window,
		},
		"sliding_window_counter": &limiter.SlidingWindowCounterLimiter{
			Store: counterStore("rl:sliding_window_counter"), Limit: cfg.DefaultLimit, WindowSeconds: window,
		},
	}
}

func main() {
	cfg := config.Load()
	actionHandler := &handlers.ActionHandler{Limiters: buildLimiters(cfg)}

	r := chi.NewRouter()
	r.Post("/api/token-bucket/action", actionHandler.Handle("token_bucket"))
	r.Post("/api/leaky-bucket/action", actionHandler.Handle("leaky_bucket"))
	r.Post("/api/fixed-window/action", actionHandler.Handle("fixed_window"))
	r.Post("/api/sliding-window-log/action", actionHandler.Handle("sliding_window_log"))
	r.Post("/api/sliding-window-counter/action", actionHandler.Handle("sliding_window_counter"))

	r.Get("/healthz", func(w http.ResponseWriter, req *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]string{"status": "ok"})
	})

	srv := &http.Server{
		Addr:         ":" + cfg.Port,
		Handler:      r,
		ReadTimeout:  10 * time.Second,
		WriteTimeout: 10 * time.Second,
	}

	log.Printf("listening on %s", srv.Addr)
	log.Fatal(srv.ListenAndServe())
}
