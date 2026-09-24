package handlers

import (
	"encoding/json"
	"fmt"
	"net/http"

	"ratelimiter/internal/limiter"
)

type ActionHandler struct {
	Limiters map[string]limiter.Limiter
}

func writeJSON(w http.ResponseWriter, status int, v interface{}, headers map[string]string) {
	for k, val := range headers {
		w.Header().Set(k, val)
	}
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(v)
}

func rateLimitHeaders(r limiter.Result) map[string]string {
	h := map[string]string{
		"X-RateLimit-Limit":     fmt.Sprintf("%d", r.Limit),
		"X-RateLimit-Remaining": fmt.Sprintf("%d", max(0, r.Remaining)),
		"X-RateLimit-Reset":     fmt.Sprintf("%v", r.ResetAt),
	}
	if r.RetryAfter != nil {
		h["Retry-After"] = fmt.Sprintf("%v", *r.RetryAfter)
	}
	return h
}

func (h *ActionHandler) Handle(algorithm string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		clientID := r.Header.Get("X-Client-Id")
		if clientID == "" {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": "missing_client_id"}, nil)
			return
		}

		result, err := h.Limiters[algorithm].Allow(r.Context(), clientID)
		if err != nil {
			writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "internal_error"}, nil)
			return
		}

		headers := rateLimitHeaders(result)
		if !result.Allowed {
			writeJSON(w, http.StatusTooManyRequests, map[string]string{"error": "rate_limited"}, headers)
			return
		}
		writeJSON(w, http.StatusOK, map[string]interface{}{"ok": true, "algorithm": algorithm}, headers)
	}
}
