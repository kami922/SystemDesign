# API Contract

Both `fastapi-service` and `go-service` implement this exactly, so the same
deterministic test harness (`tests/`) and load-test tools can target either
one interchangeably.

Conventions: `snake_case` JSON fields, error bodies `{"error": "<code>"}`
(matches the URL-Shortner project's convention).

## Client identity

Every action endpoint requires a `X-Client-Id: <string>` request header.
This identifies the caller for rate-limiting purposes. Deliberately not
IP-based: Docker/NAT makes IP ambiguous between replicas, and tests need a
controllable, unique key per scenario.

Missing header → `400 Bad Request` `{"error": "missing_client_id"}`.

## POST /api/{algorithm}/action

One endpoint per algorithm (see docs/01-algorithms.md for semantics of
each): `/api/token-bucket/action`, `/api/leaky-bucket/action`,
`/api/fixed-window/action`, `/api/sliding-window-log/action`,
`/api/sliding-window-counter/action`.

Request: no body required.

Every response (allowed or not) carries:
- `X-RateLimit-Limit`: the configured limit (integer)
- `X-RateLimit-Remaining`: requests remaining in the current allowance (integer, >= 0)
- `X-RateLimit-Reset`: unix epoch seconds when the limit resets/replenishes (float)

Responses:
- `200 OK` `{"ok": true, "algorithm": "token_bucket"}`
- `429 Too Many Requests` `{"error": "rate_limited"}`, additionally carries
  `Retry-After: <seconds>` (float) - only present on 429s.

## GET /healthz

`200 OK` `{"status": "ok"}`.

## Configuration (env vars, both services)

- `RATE_LIMIT_DEFAULT_LIMIT` (int, default 10) - the `N` in "N requests per window."
- `RATE_LIMIT_DEFAULT_WINDOW_SECONDS` (float, default 10) - the `W`. Token
  bucket derives `capacity=N`, `refill_rate=N/W` from these same two knobs,
  so every algorithm is configured identically for fair comparison.
- `STORAGE_BACKEND` (`memory` | `redis`, default `memory` until Milestone 2).
