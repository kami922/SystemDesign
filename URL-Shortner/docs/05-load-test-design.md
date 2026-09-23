# Load test design: Locust and k6

Two tools, driven from the same seeded data, targeting the same API
contract. The point isn't just "which backend is faster" - it's also
"what does a realistic traffic *shape* actually stress," and "how do two
different load-testing tools compare when pointed at the identical
scenario."

## Why Zipfian, not uniform random

Real short-URL traffic is never uniform - a small number of links get most
of the clicks (a viral tweet, a popular campaign link), and a long tail gets
almost none. Sampling redirects uniformly across all seeded codes would
never create real cache pressure: with enough concurrent users, a uniform
draw across 1000 codes just means every code gets cached almost immediately
and stays cached, which tells you nothing interesting about the cache-aside
design in [03-caching.md](03-caching.md).

`loadtest/traffic_profile.py` assigns each seeded code a weight
proportional to `rank^-s` (classic Zipf's law - frequency inversely
proportional to popularity rank). A small `s` (near 1) gives a long, gentle
tail; a larger `s` concentrates traffic hard on the top few codes. `ZIPF_S`
is exposed precisely so this can be tuned and the effect on cache
hit-rate/latency observed directly.

## Shared seed data, not independent sampling

`loadtest/seed_data.py` creates the links via the real API, shuffles them
(so "popular" isn't correlated with "created first"), assigns Zipf weights,
and writes both to `loadtest/seeded_codes.json`. **Both Locust and k6 read
this same file.** If each tool computed its own skew independently, a
Locust-vs-k6 comparison would be confounded by two different traffic
shapes; reading a shared artifact removes that variable.

## Traffic mix

One task set, mirrored between `locustfile.py` and `k6_script.js`:

| Task | Weight | Notes |
|---|---|---|
| Redirect (`GET /{code}`) | 85% | Zipf-weighted draw from the seeded pool - the hot path |
| Create link (`POST /api/links`) | 10% | random long_url, no alias |
| Create custom alias | 3% | random long_url + random valid alias string |
| Stats lookup | 2% | uniform draw from the seeded pool - not assumed to skew |

Redirects don't follow the `Location` header (`allow_redirects=False` /
`redirects: 0`) - we're measuring the shortener's own redirect issuance,
not fetching whatever fake `example.com` URL it points to.

## Locust vs k6 - why both

Locust is Python, code-first: the task file *is* the test, and weighting is
plain Python (`random.choices`). k6 is JS-based and adds declarative
`thresholds` - pass/fail SLO gates baked into the script itself (e.g.
`http_req_duration{name:redirect}: p(95)<200`), which Locust has no built-in
equivalent for. Running both against the same contract is as much about
learning two different load-testing tools' ergonomics as it is about the
backend comparison.

## The fixed comparison procedure

Four runs total - two tools × two backends - never two running
concurrently (see the isolation note in the compose setup: both stacks
share host CPU/RAM, so simultaneous runs would confound resource
contention with backend performance):

```
for stack in [fastapi, go]:
    reset_stack.sh <stack>          # truncate tables, flush cache
    seed_data.py --base-url ...     # regenerate seeded_codes.json
    locust --headless --csv=... --users=200 --spawn-rate=20 --run-time=5m

    reset_stack.sh <stack>          # fresh baseline again
    seed_data.py --base-url ...
    k6 run --vus=200 --duration=5m
```

`scripts/run_comparison.sh` runs exactly this. Parameters worth varying
across repeat runs: `USERS`/`SPAWN_RATE` (concurrency), `RUN_TIME`,
`ZIPF_S` (skew intensity), and later, `ANALYTICS_MODE` (see
[04-analytics-write-path.md](04-analytics-write-path.md)) as an isolated
follow-up experiment.

## Reading the results

- **p50 close, p99 diverging** between the two backends under the same
  load usually points to GC pauses (Go) or async-event-loop contention
  (Python/uvicorn) - worth specifically looking for in the tail latency.
- **Latency bimodality** (a fast cluster and a slow cluster in the same
  run) is the visible signature of cache hit vs cache miss on the redirect
  path - even without an explicit cache-hit-rate metric, the histogram
  shows it.
- **Throughput differences** reflect the I/O model (FastAPI's asyncpg +
  uvicorn event loop vs Go's goroutine-per-request model) as much as raw
  language speed - resist the naive "Go is just faster" reading.
- **Locust vs k6 disagreement** on the same backend/params usually traces
  to the load generator's own overhead (a Python-based client vs k6's
  Go-runtime-based one), not the backend - a useful reminder that the load
  tool itself is part of what you're measuring.

Actual numbers and interpretation from real runs go in
[06-results.md](06-results.md).
