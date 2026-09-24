# Demo API and testing strategy

## Why one endpoint per algorithm

`POST /api/{algorithm}/action` — five separate endpoints, not one endpoint
with an `?algorithm=` query param. This lets a single running instance
demonstrate all five side by side (useful for manually poking at the
service), and lets both test suites target one algorithm cleanly without
threading a parameter through every request. The cost is some route
boilerplate (`routers/action.py` / `handlers/action.go`) — worth it for
the clarity.

## Why `X-Client-Id`, not IP

Every action endpoint requires an explicit `X-Client-Id` header rather
than falling back to the caller's IP address. Two reasons: Docker/NAT
makes IP-based identity ambiguous between replicas (see
[03-distributed-correctness.md](03-distributed-correctness.md) — two
replicas behind the same reverse proxy often see the same source IP for
every caller), and the test suites need a fully controllable, unique key
per scenario (`tests/harness.py`'s `unique_client_id()`) so tests never
interfere with each other and never need a reset step between runs. A
production deployment would default to IP or an authenticated user id;
this demo needs something a test can dial precisely.

## Two test tools, two different questions

This project uses two genuinely different testing tools, and conflating
them would produce meaningless results:

**`tests/` — deterministic correctness.** "Does token bucket allow exactly
`capacity` requests and reject the rest?" "Does the fixed-window boundary
admit ~2x the limit?" These are exact-count assertions requiring precise,
controlled timing (`tests/harness.py`'s `fire_n` — pure `asyncio.gather`,
no randomness). Locust and k6's task schedulers are *probabilistic* by
design — excellent for realistic sustained load, useless for "fire exactly
15 requests and assert exactly 10 succeed." Every milestone in this
project was verified with `tests/`, not the load-test tools.

**`loadtest/` — overhead and throughput.** "How much latency does each
algorithm/storage combination add on top of a normal request?" "How does
FastAPI compare to Go under sustained concurrent load?" Here, throttling
is explicitly *not* what's being measured — each virtual user gets its own
`X-Client-Id` specifically so most traffic stays under its own limit, and
an unexpected `429` is flagged as a load-test *misconfiguration*, not a
finding. This is the same category of question URL-Shortner's
`docs/05-load-test-design.md` asked about redirect latency, applied here
to the rate-limiting check itself.

Running `tests/` against the load-test traffic pattern (or vice versa)
would answer neither question well — the exact-count harness would see
noisy, non-deterministic timing; the load tools would never generate the
precise bursts correctness testing needs.

## Running both

```bash
# Deterministic correctness (from the rateLimiter/ root):
python tests/test_token_bucket.py --base-url http://localhost:8101
python tests/test_distributed_correctness.py \
  --base-url http://localhost:8101 --base-url http://localhost:8102 \
  --capacity 10 --mode redis

# Load test (from infra/, via Compose):
docker compose up locust   # web UI at :9089
docker compose run --rm locust -f locustfile.py --host http://fastapi-app-1:8000 \
  --headless --users 50 --spawn-rate 10 --run-time 1m
docker compose --profile tools run --rm k6 run --env BASE_URL=http://fastapi-app-1:8000 k6_script.js

# Full fixed comparison, both tools, both stacks:
./scripts/run_comparison.sh
```
