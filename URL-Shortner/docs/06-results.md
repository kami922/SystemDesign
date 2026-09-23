# Results

A real comparison run, scaled down from the full procedure for a quick pass:
50 users/VUs, 1-minute runs, 500 seeded links, `ZIPF_S=1.2`. Run via
`./scripts/run_comparison.sh` on a 12-core host with both stacks fully
isolated per [03-caching.md](03-caching.md) / the compose network design.

```
USERS=50 SPAWN_RATE=10 RUN_TIME=1m SEED_COUNT=500 ZIPF_S=1.2 ./scripts/run_comparison.sh
```

**Correctness held up under load in all four runs: zero failed requests,
zero failed checks**, across ~40k-220k requests per run. No race conditions
surfaced in the custom-alias unique-violation handling or the click-count
increments under concurrency.

## Locust (50 users, 1 min, throttled - `wait_time = between(0.01, 0.1)` per task)

| | FastAPI | Go |
|---|---|---|
| Total requests | 40,567 | 44,462 |
| Throughput | 685 req/s | 752 req/s |
| Redirect p50 / p95 / p99 | 11ms / 27ms / 40ms | 6ms / 17ms / 27ms |
| Redirect max | 87ms | 61ms |

Locust's numbers are close - Go is consistently faster but not dramatically
so, and both look healthy. This is the load level where you'd walk away
thinking "sure, Go's a bit quicker, no big deal."

## k6 (50 VUs, 1 min, unthrottled - no wait between iterations)

| | FastAPI | Go |
|---|---|---|
| Total requests | 53,622 | 219,821 |
| Throughput | 891 req/s | 3,662 req/s |
| Redirect p50 / p95 / p99 | 3.9ms / 8.0ms / 41ms | 0.8ms / 1.8ms / 3.0ms |

**This is a completely different picture.** k6 has no artificial per-VU
delay, so 50 VUs actually hammer as fast as each backend can respond - and
at that load, Go pulled ahead by more than 4x in throughput, not the ~10%
Locust suggested.

### Where FastAPI's time actually went

The redirect path (cache-aside hot path) stayed fast for both backends even
under k6 - the difference shows up entirely in the endpoints that touch
Postgres directly:

| Endpoint | FastAPI p50 | FastAPI p95 | Go p50 | Go p95 |
|---|---|---|---|---|
| redirect (cached) | 3.9ms | 8.0ms | 0.8ms | 1.8ms |
| create link (2 DB round trips) | 337ms | 1,049ms | 97ms | 134ms |
| custom alias (1 DB round trip) | 334ms | 1,036ms | 50ms | 73ms |
| stats (1 DB round trip) | 335ms | 1,050ms | 49ms | 71ms |

Two things stand out:

1. **FastAPI's three DB-touching endpoints are all ~330ms at p50 regardless
   of how much work each actually does** (create link does two round trips
   - reserve an id, then insert; the other two do one). If the work itself
   were the bottleneck, create link should look worse than the others, the
   way it does on the Go side (97ms vs ~50ms - roughly double, matching the
   extra round trip). Instead all three cluster at nearly the same number.
   That's the signature of **queueing for a shared, saturated resource**,
   not query cost.
2. That resource is almost certainly the **asyncpg connection pool**
   (`max_size=10`, set in `fastapi-service/app/config.py`). At 891 req/s
   with 85% of traffic being redirects that each spawn a background click-analytics
   task doing *two more* writes ([04-analytics-write-path.md](04-analytics-write-path.md)),
   the pool has to serve far more concurrent DB operations than its 10 connections
   allow. Every request that needs a real connection - not just the cache-served
   redirects - queues behind that backlog.

The Go service's `pgxpool` was left at its library default (no override in
`go-service/internal/db/db.go`), which is `max(4, number of CPUs)` - on this
12-core host, effectively a larger pool than FastAPI's hardcoded 10. That's
a real contributor, but not the whole story - the base per-endpoint numbers
without the pool difference would still favor Go, since Go's redirect path
alone is ~4x faster than FastAPI's even with no pool contention at all
(0.8ms vs 3.9ms median).

**This wasn't a planned experiment - it emerged from the numbers.** It's a
better result than a clean "Go wins" headline: it shows *specifically*
where and why, and it's directly actionable (bump `max_size` on the asyncpg
pool, or run uvicorn with multiple workers, and rerun to see how much of
the gap closes).

## Locust vs k6 as tools - the real lesson from this run

The two tools disagreed sharply on the same nominal load ("50 concurrent
users") because they don't mean the same thing by it:

- `locustfile.py` gives each simulated user `wait_time = between(0.01, 0.1)`
  between tasks - a deliberate pacing choice, but one that caps the maximum
  possible throughput regardless of how fast the backend actually responds.
- `k6_script.js` has no equivalent delay - each VU fires the next iteration
  immediately after the last one completes, so k6's actual request rate is
  bounded only by the backend's response time.

At 50 users/VUs, this means Locust was measuring "fast enough not to matter"
while k6 was measuring "as fast as it can go" - and only the second one
surfaced the connection-pool saturation above. **Neither number is wrong,
but they answer different questions.** This is exactly the caveat flagged
in [05-load-test-design.md](05-load-test-design.md): the load generator's
own execution model is part of what you're measuring. A fairer head-to-head
would give both tools an equivalent think-time (or none), rather than
comparing "Locust with pacing" to "k6 without."

## Interpretation

- **Correctness**: both implementations are solid under concurrent load -
  no data corruption, no failed requests, no lost click counts.
- **Cache-aside works as designed** in both: redirect latency stayed low
  and stable even as the write-heavy endpoints degraded under FastAPI,
  because the redirect path doesn't compete for the same bottleneck (it's
  Redis-served, not Postgres-served, on a cache hit).
- **The Go-vs-FastAPI gap is real but not fixed** - it's at minimum
  "Go's redirect path is ~4x faster than FastAPI's at baseline," and at
  most (under sustained unthrottled load) "FastAPI's connection pool
  becomes a hard bottleneck that Go's doesn't hit at the same load,"
  which compounds into a >4x throughput gap. Distinguishing exactly how
  much is pool-size vs runtime/language is a good follow-up experiment
  (Milestone 7 territory): bump `asyncpg`'s `max_size` to match pgx's
  effective default and rerun k6 to see how much of the gap closes.
- **Resist "Go is just faster" as the takeaway.** The actual finding is
  more specific and more useful: a fixed, small connection pool combined
  with background-task writes riding on every redirect can silently starve
  unrelated endpoints once load crosses a threshold - a lesson about
  resource pool sizing under write-amplified read traffic, not a verdict
  on either language.

## Milestone 7: does buffered analytics fix it?

Same k6 run (50 VUs, 1 min, same seeded pool) against FastAPI with
`ANALYTICS_MODE=buffered` (`docs/04-analytics-write-path.md`'s v2 - clicks
land in an in-process dict with zero I/O, flushed to Postgres once a
second) instead of the default `sync_bg`:

| | sync_bg (baseline) | buffered |
|---|---|---|
| Throughput | 891 req/s | 1,490 req/s (+67%) |
| create link p50 / p95 | 337ms / 1,049ms | 92ms / 174ms |
| custom alias p50 / p95 | 334ms / 1,036ms | 85ms / 163ms |
| stats p50 / p95 | 335ms / 1,050ms | 80ms / 164ms |
| **redirect p50 / p95** | **3.9ms / 8.0ms** | **19.8ms / 35.7ms** |

Buffering clearly worked on the hypothesis from the section above: the
three DB-touching endpoints all dropped by roughly 3-6x once background
analytics writes stopped competing for the connection pool, and overall
throughput jumped 67%.

**But redirect latency itself got worse - almost 5x, from 8ms to 36ms at
p95 - even though redirect no longer does any per-request I/O for
analytics at all.** That's not a bug; it's the next bottleneck surfacing.
Removing the pool contention let ~67% more total traffic through the same
single uvicorn worker process every second. FastAPI/uvicorn was run with
no `--workers` flag here (one Python process, one event loop) - so once the
DB pool stopped being the limit, the event loop's own per-second request
capacity became the limit instead, and *every* endpoint sharing that loop,
redirect included, pays a bit more scheduling latency at the new, higher
request rate.

**Correctness held**: `SUM(click_count)` across all links matched
`COUNT(*)` from `click_events` exactly after the run (80,970 = 80,970) -
the batched flush didn't lose or double-count a single click during this
run. (It still would on an actual process crash mid-buffer - that's the
tradeoff, not eliminated, just not triggered here.)

**The real lesson**: fixing one bottleneck (connection pool exhaustion)
didn't produce a free win - it traded a write-contention problem for a
single-process-throughput problem, and the "cost" showed up on an endpoint
(redirect) that the fix didn't even touch. This is a fully general systems
lesson, not specific to Python or FastAPI: removing a bottleneck reveals
the next one, and improving aggregate throughput can still make individual
requests on an unrelated path slower if they share a serialization point
(here, one event loop) with the traffic that got unblocked. The obvious
next experiment - not run here, to keep this one isolated per
[05-load-test-design.md](05-load-test-design.md)'s "change one variable at
a time" principle - is adding `--workers` to uvicorn and rerunning both
modes to see whether that closes the redirect regression while keeping
buffering's throughput win.
