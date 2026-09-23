# API Contract

Both `fastapi-service` and `go-service` must implement this exactly, so the same
Locust/k6 test suite can target either one interchangeably (via `--host` / `BASE_URL`).

Conventions:
- Fields are `snake_case`.
- Timestamps are RFC3339 UTC, e.g. `2026-09-23T10:00:00Z`.
- Error bodies are always `{"error": "<code>"}`.
- Management endpoints live under `/api`; redirects are at the root path since a
  real short URL has no prefix.

## POST /api/links

Create a shortened link. Omit `custom_alias` for an auto-generated base62 code.

Request:
```json
{
  "long_url": "https://example.com/some/very/long/path",
  "custom_alias": "my-link",
  "expires_at": "2026-12-31T23:59:59Z"
}
```
`custom_alias` and `expires_at` are optional.

Responses:
- `201 Created`
```json
{
  "short_code": "aZ9k1",
  "short_url": "http://localhost:8000/aZ9k1",
  "long_url": "https://example.com/some/very/long/path",
  "is_custom_alias": false,
  "created_at": "2026-09-23T10:00:00Z",
  "expires_at": null
}
```
- `400 Bad Request` — `long_url` is not a valid absolute URL, or `custom_alias`
  fails charset/length validation (`^[A-Za-z0-9_-]{4,16}$`).
- `409 Conflict` — `custom_alias` already taken.
- `422 Unprocessable Entity` — malformed JSON / missing `long_url`.

## GET /{code}

Redirect to the long URL. This is the hot path.

- `302 Found` with `Location: <long_url>` — **302, not 301**: a 301 gets cached
  permanently by browsers, which breaks expiration semantics.
- `404 Not Found` — code does not exist. Body: `{"error": "not_found"}`.
- `410 Gone` — code exists but `expires_at < now()`. Body: `{"error": "expired"}`.

## GET /api/links/{code}/stats

- `200 OK`
```json
{
  "short_code": "aZ9k1",
  "long_url": "https://example.com/some/very/long/path",
  "click_count": 4213,
  "created_at": "2026-09-23T10:00:00Z",
  "expires_at": null,
  "last_clicked_at": "2026-09-23T11:45:00Z"
}
```
`last_clicked_at` is `null` if the link has never been clicked.
- `404 Not Found` — unknown code. Body: `{"error": "not_found"}`.

## GET /healthz

- `200 OK` `{"status": "ok"}` — used by Docker Compose healthchecks and by load
  test tooling to gate startup.
