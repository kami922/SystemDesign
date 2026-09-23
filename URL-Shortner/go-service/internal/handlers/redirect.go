package handlers

import (
	"context"
	"errors"
	"log"
	"net/http"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"urlshortener/internal/cache"
)

type RedirectHandler struct {
	Pool  *pgxpool.Pool
	Cache *cache.Client
}

func isExpired(expiresAt *time.Time) bool {
	return expiresAt != nil && expiresAt.Before(time.Now().UTC())
}

// recordClick runs in its own goroutine after the redirect response has
// already been written - this is what keeps analytics off the redirect's
// critical path (mirrors FastAPI's BackgroundTasks on the other stack).
func (h *RedirectHandler) recordClick(shortCode string) {
	ctx := context.Background()
	tx, err := h.Pool.Begin(ctx)
	if err != nil {
		log.Printf("record click: begin: %v", err)
		return
	}
	defer tx.Rollback(ctx)

	if _, err := tx.Exec(ctx, `UPDATE links SET click_count = click_count + 1 WHERE short_code = $1`, shortCode); err != nil {
		log.Printf("record click: update: %v", err)
		return
	}
	if _, err := tx.Exec(ctx, `INSERT INTO click_events (short_code) VALUES ($1)`, shortCode); err != nil {
		log.Printf("record click: insert: %v", err)
		return
	}
	if err := tx.Commit(ctx); err != nil {
		log.Printf("record click: commit: %v", err)
	}
}

func (h *RedirectHandler) Redirect(w http.ResponseWriter, r *http.Request) {
	code := chi.URLParam(r, "code")

	cached, err := h.Cache.GetLink(r.Context(), code)
	if err == nil && cached != nil {
		if isExpired(cached.ExpiresAt) {
			writeError(w, http.StatusGone, "expired")
			return
		}
		http.Redirect(w, r, cached.LongURL, http.StatusFound)
		go h.recordClick(code)
		return
	}

	// Cache miss (or cache error - fail open to Postgres): fall back to the DB.
	var longURL string
	var expiresAt *time.Time
	dbErr := h.Pool.QueryRow(r.Context(), `SELECT long_url, expires_at FROM links WHERE short_code = $1`, code).
		Scan(&longURL, &expiresAt)
	if dbErr != nil {
		if errors.Is(dbErr, pgx.ErrNoRows) {
			writeError(w, http.StatusNotFound, "not_found")
			return
		}
		writeError(w, http.StatusInternalServerError, "internal_error")
		return
	}

	if isExpired(expiresAt) {
		// Don't cache dead entries - nothing gained from remembering a 410.
		writeError(w, http.StatusGone, "expired")
		return
	}

	if err := h.Cache.SetLink(r.Context(), code, longURL, expiresAt); err != nil {
		log.Printf("cache set: %v", err)
	}

	http.Redirect(w, r, longURL, http.StatusFound)
	go h.recordClick(code)
}
