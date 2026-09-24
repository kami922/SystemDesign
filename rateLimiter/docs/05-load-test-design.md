# Load test design: overhead, not correctness

See [04-demo-api-and-testing.md](04-demo-api-and-testing.md) for why this
is a different question from `tests/`, answered with different tools.
This doc is about *how* that question is answered.

## Traffic shape

`loadtest/locustfile.py` and `loadtest/k6_script.js` mirror each other: an
even mix across all five `/api/{algorithm}/action` endpoints (no weighting
- unlike URL-Shortner's Zipfian traffic, the point here isn't modeling
realistic request *distribution*, it's comparing five algorithms under the
*same* load fairly).

Each virtual user/VU gets its own `X-Client-Id`, generated once (Locust's
`on_start`, k6's `__VU`). Two reasons: it keeps most traffic under its own
limit rather than measuring throttling behavior (an unexpected `429` here
is flagged as a **misconfiguration**, not a finding — see the locustfile's
own docstring), and it gives Redis realistic key cardinality, many distinct
keys rather than one hot key, which matters because every Lua script here
operates per-key.

**The rate limit itself must be configured generously for this test** -
high enough relative to the actual traffic rate that admission almost
never triggers. `RATE_LIMIT_DEFAULT_LIMIT`/`_WINDOW_SECONDS` are Compose
env overrides for exactly this: the demo defaults (`limit=10`,
`window=10s`) are tuned for *manually* trying the API, not for hundreds of
requests/second from a load generator. Smoke-testing this
(`docs/04-demo-api-and-testing.md`) surfaced this directly: k6's unthrottled
firing rate against the low default limit produced ~56% expected 429s -
correct behavior for the *limiter*, useless for measuring the limiter's
*overhead*. The real comparison run raises the limit specifically to avoid
this.

## Comparison axes

Scoped deliberately to two questions, not a wall of 20 algorithm × storage
× language numbers:

1. **Memory vs Redis overhead**, using token bucket as the representative
   algorithm (per language) — what does adding a network round-trip to
   Redis (plus Lua script execution) cost, versus an in-process lock?
2. **Algorithm-to-algorithm overhead within Redis mode** (per language) —
   does sliding window log's `ZADD`/`ZREMRANGEBYSCORE` on a `ZSET` cost
   measurably more than fixed window's plain `INCR`? This is the load-test
   counterpart to [01-algorithms.md](01-algorithms.md)'s memory-cost
   comparison — there it was bytes per key, here it's request latency.

## Procedure

`scripts/reset_stack.sh <fastapi|go>` flushes that stack's Redis (no
Postgres in this project — only cache state exists). `scripts/run_comparison.sh`
runs, per stack, sequentially (never both stacks concurrently — they share
host CPU/RAM, and concurrent runs would confound the results, same
rationale as URL-Shortner):

```
reset -> Locust run (paced, wait_time between tasks)
reset -> k6 run (unthrottled, fires as fast as it can)
```

against replica 1 only (`fastapi-app-1`, `go-app-1`) — the second replica
of each stack exists for the distributed-correctness proof
(`tests/test_distributed_correctness.py`), not this overhead comparison,
so introducing it here would just add unrelated network fan-out to the
numbers.

## Reading the results

Same interpretive cautions as URL-Shortner's load-test design, since the
underlying tools and host are the same:

- **Locust vs k6 disagreement** on the same backend/params usually traces
  to the load generator's own overhead (paced Python client vs k6's
  unthrottled Go-runtime client), not the backend.
- **Resist "Go is just faster."** If Go shows lower overhead, look for a
  mechanism (goroutine-per-request vs a Python event loop; a single
  process without a `--workers` flag; the specific Redis command pattern
  each algorithm uses) rather than treating it as a verdict on the
  language.

Actual numbers and interpretation go in [06-results.md](06-results.md).
