package handlers

import (
	"encoding/json"
	"errors"
	"net/http"
	"net/url"
	"regexp"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jackc/pgx/v5/pgxpool"

	"urlshortener/internal/config"
	"urlshortener/internal/shortcode"
)

var aliasPattern = regexp.MustCompile(`^[A-Za-z0-9_-]{4,16}$`)

const uniqueViolationCode = "23505"

type LinksHandler struct {
	Pool     *pgxpool.Pool
	Settings config.Settings
}

type createLinkRequest struct {
	LongURL     string     `json:"long_url"`
	CustomAlias *string    `json:"custom_alias"`
	ExpiresAt   *time.Time `json:"expires_at"`
}

type linkResponse struct {
	ShortCode     string     `json:"short_code"`
	ShortURL      string     `json:"short_url"`
	LongURL       string     `json:"long_url"`
	IsCustomAlias bool       `json:"is_custom_alias"`
	CreatedAt     time.Time  `json:"created_at"`
	ExpiresAt     *time.Time `json:"expires_at"`
}

type statsResponse struct {
	ShortCode     string     `json:"short_code"`
	LongURL       string     `json:"long_url"`
	ClickCount    int64      `json:"click_count"`
	CreatedAt     time.Time  `json:"created_at"`
	ExpiresAt     *time.Time `json:"expires_at"`
	LastClickedAt *time.Time `json:"last_clicked_at"`
}

func writeError(w http.ResponseWriter, status int, code string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(map[string]string{"error": code})
}

func writeJSON(w http.ResponseWriter, status int, v interface{}) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(v)
}

// Postgres timestamptz round-trips through pgx/JSON with the process's
// local offset rather than "Z"; normalize everything we emit to UTC so
// responses always match the contract's RFC3339-UTC convention.
func toUTC(t *time.Time) *time.Time {
	if t == nil {
		return nil
	}
	u := t.UTC()
	return &u
}

func isValidLongURL(raw string) bool {
	u, err := url.Parse(raw)
	if err != nil {
		return false
	}
	return (u.Scheme == "http" || u.Scheme == "https") && u.Host != ""
}

func (h *LinksHandler) CreateLink(w http.ResponseWriter, r *http.Request) {
	var req createLinkRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusUnprocessableEntity, "malformed_request")
		return
	}
	if req.LongURL == "" {
		writeError(w, http.StatusUnprocessableEntity, "missing_long_url")
		return
	}
	if !isValidLongURL(req.LongURL) {
		writeError(w, http.StatusBadRequest, "invalid_long_url")
		return
	}
	if req.CustomAlias != nil && !aliasPattern.MatchString(*req.CustomAlias) {
		writeError(w, http.StatusBadRequest, "invalid_custom_alias")
		return
	}

	ctx := r.Context()

	var shortCode string
	var isCustomAlias bool
	var createdAt time.Time

	if req.CustomAlias != nil {
		shortCode = *req.CustomAlias
		isCustomAlias = true

		// A pre-check would still race under concurrent requests for the
		// same alias, so the unique index is the real source of truth -
		// we just catch the violation it raises.
		err := h.Pool.QueryRow(ctx, `
			INSERT INTO links (short_code, long_url, is_custom_alias, expires_at)
			VALUES ($1, $2, TRUE, $3)
			RETURNING created_at
		`, shortCode, req.LongURL, req.ExpiresAt).Scan(&createdAt)
		if err != nil {
			var pgErr *pgconn.PgError
			if errors.As(err, &pgErr) && pgErr.Code == uniqueViolationCode {
				writeError(w, http.StatusConflict, "alias_taken")
				return
			}
			writeError(w, http.StatusInternalServerError, "internal_error")
			return
		}
	} else {
		var linkID int64
		if err := h.Pool.QueryRow(ctx, `SELECT nextval('links_id_seq')`).Scan(&linkID); err != nil {
			writeError(w, http.StatusInternalServerError, "internal_error")
			return
		}
		shortCode = shortcode.Encode(linkID)

		err := h.Pool.QueryRow(ctx, `
			INSERT INTO links (id, short_code, long_url, expires_at)
			VALUES ($1, $2, $3, $4)
			RETURNING created_at
		`, linkID, shortCode, req.LongURL, req.ExpiresAt).Scan(&createdAt)
		if err != nil {
			writeError(w, http.StatusInternalServerError, "internal_error")
			return
		}
	}

	writeJSON(w, http.StatusCreated, linkResponse{
		ShortCode:     shortCode,
		ShortURL:      h.Settings.BaseURL + "/" + shortCode,
		LongURL:       req.LongURL,
		IsCustomAlias: isCustomAlias,
		CreatedAt:     createdAt.UTC(),
		ExpiresAt:     toUTC(req.ExpiresAt),
	})
}

func (h *LinksHandler) GetStats(w http.ResponseWriter, r *http.Request) {
	code := chi.URLParam(r, "code")

	resp := statsResponse{ShortCode: code}

	err := h.Pool.QueryRow(r.Context(), `
		SELECT l.long_url, l.click_count, l.created_at, l.expires_at,
		       (SELECT MAX(clicked_at) FROM click_events WHERE short_code = l.short_code)
		FROM links l WHERE l.short_code = $1
	`, code).Scan(&resp.LongURL, &resp.ClickCount, &resp.CreatedAt, &resp.ExpiresAt, &resp.LastClickedAt)

	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			writeError(w, http.StatusNotFound, "not_found")
			return
		}
		writeError(w, http.StatusInternalServerError, "internal_error")
		return
	}

	resp.CreatedAt = resp.CreatedAt.UTC()
	resp.ExpiresAt = toUTC(resp.ExpiresAt)
	resp.LastClickedAt = toUTC(resp.LastClickedAt)

	writeJSON(w, http.StatusOK, resp)
}
