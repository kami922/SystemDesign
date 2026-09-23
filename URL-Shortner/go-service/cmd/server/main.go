package main

import (
	"context"
	"encoding/json"
	"log"
	"net/http"
	"time"

	"github.com/go-chi/chi/v5"

	"urlshortener/internal/cache"
	"urlshortener/internal/config"
	"urlshortener/internal/db"
	"urlshortener/internal/handlers"
)

func main() {
	cfg := config.Load()

	ctx := context.Background()
	pool, err := db.NewPool(ctx, cfg.DatabaseURL)
	if err != nil {
		log.Fatalf("connect to postgres: %v", err)
	}
	defer pool.Close()

	cacheClient, err := cache.New(cfg.RedisURL, cfg.DefaultCacheTTLSeconds)
	if err != nil {
		log.Fatalf("connect to redis: %v", err)
	}

	linksHandler := &handlers.LinksHandler{Pool: pool, Settings: cfg}
	redirectHandler := &handlers.RedirectHandler{Pool: pool, Cache: cacheClient}

	r := chi.NewRouter()

	r.Post("/api/links", linksHandler.CreateLink)
	r.Get("/api/links/{code}/stats", linksHandler.GetStats)

	// chi matches literal routes before wildcard patterns regardless of
	// registration order (radix tree), so /healthz needs no special
	// ordering relative to "/{code}" the way Starlette's router did.
	r.Get("/healthz", func(w http.ResponseWriter, req *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]string{"status": "ok"})
	})

	r.Get("/{code}", redirectHandler.Redirect)

	srv := &http.Server{
		Addr:         ":8080",
		Handler:      r,
		ReadTimeout:  10 * time.Second,
		WriteTimeout: 10 * time.Second,
	}

	log.Printf("listening on %s", srv.Addr)
	log.Fatal(srv.ListenAndServe())
}
