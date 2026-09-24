# Results

Real comparison run: 50 users/VUs, Locust paced (`wait_time` between
tasks) vs k6 unthrottled, against replica 1 of each stack, `RATE_LIMIT_DEFAULT_LIMIT=100000`
over a 60s window (generous enough that admission essentially never
triggers - this measures overhead, not throttling, per
[05-load-test-design.md](05-load-test-design.md)).

```
./scripts/run_comparison.sh   # Locust + k6, redis mode, both stacks
# plus a supplementary pair of k6 runs in memory mode, for the
# memory-vs-redis axis that run_comparison.sh alone doesn't cover
```

**Zero failures across every run** - correctness held under load for both
languages, both storage backends, all five algorithms.

## Axis 1: memory vs Redis overhead (k6, 50 VUs, 30s, token bucket representative - actually averaged across all five, see Axis 2 for why that's fine)

| | FastAPI | Go |
|---|---|---|
| Memory mode throughput | 4,375 req/s | 20,847 req/s |
| Memory mode avg / p95 latency | 11.3ms / 19.6ms | 2.16ms / 6.23ms |
| Redis mode throughput | 2,980 req/s | 13,934 req/s |
| Redis mode avg / p95 latency | 16.65ms / 24.5ms | 3.4ms / 5.69ms |
| **Redis's cost** | **-32% throughput, +5.35ms avg latency** | **-33% throughput, +1.24ms avg latency** |

The proportional cost of adding Redis is nearly identical between the two
languages (~32-33% throughput reduction) despite wildly different absolute
numbers. That consistency is itself informative: it isolates the Redis
round-trip + Lua `EVAL` as a fixed tax that applies roughly equally
regardless of what's making the request, rather than something that
interacts differently with each language's runtime.

**The Go-vs-FastAPI gap is not a Redis effect.** It's already fully present
in memory mode alone - 20,847 vs 4,375 req/s is a 4.77x gap with *no*
network hop involved at all. Redis mode shows a 4.67x gap - statistically
the same ratio. Whatever separates the two languages here, it's there
before Redis ever enters the picture.

## Axis 2: algorithm-to-algorithm overhead within Redis mode

| Endpoint | FastAPI avg | FastAPI p95 | Go avg | Go p95 |
|---|---|---|---|---|
| token bucket (Lua: `HMGET`+refill+`HMSET`) | 16.65ms | 24.39ms | 3.41ms | 5.69ms |
| leaky bucket (same script as token bucket) | 16.68ms | 24.46ms | 3.41ms | 5.71ms |
| fixed window (Lua: `INCR`+`EXPIRE`) | 16.58ms | 24.58ms | 3.39ms | 5.69ms |
| sliding window counter (Lua: 2x `GET`+`INCR`) | 16.68ms | 24.60ms | 3.41ms | 5.70ms |
| sliding window log (Lua: `ZREMRANGEBYSCORE`+`ZCARD`+`ZADD`) | 16.70ms | 24.61ms | 3.42ms | 5.71ms |

**All five algorithms cost the same, per language, within noise** - despite
sliding window log doing measurably more work on Redis's side (three ZSET
operations vs fixed window's single `INCR`). This says something specific:
at this request rate, **the fixed cost of the round trip and `EVAL`
invocation dwarfs the cost of the actual commands inside the script.**
Redis executes all of these in well under a millisecond regardless of
which one; the milliseconds being measured here are network + HTTP +
connection-pool overhead, not Redis compute.

The practical implication: choosing sliding window log for its accuracy
(no boundary double-burst - see [01-algorithms.md](01-algorithms.md))
essentially costs nothing extra over fixed window once you're already
paying for a Redis-backed limiter. The algorithm choice should be driven
by correctness requirements, not by a latency budget - the latency budget
is already spent on "talking to Redis at all," not on which Redis
operations you ask for.

## Locust vs k6, again

Same pattern as URL-Shortner: Locust's `wait_time` between tasks caps
throughput well below what either backend can actually sustain (~380 req/s
aggregate for both languages, nearly identical p50/p95), while k6's
unthrottled firing surfaces the real capacity difference (2,980-20,847
req/s depending on language and storage mode). Locust alone would have
suggested "these two are basically the same"; only the unpaced tool
revealed the actual gap. Neither number is wrong - they answer different
questions, and only one of them was asking "how fast can this actually
go."

## Interpretation

- **Correctness first, and it held**: zero failed requests across every
  combination tested here, on top of the exact-count deterministic proofs
  in `tests/` from Milestones 1-7. Performance numbers are only worth
  discussing because correctness wasn't in question.
- **Storage backend, not algorithm, is the dominant cost lever.** Within a
  storage mode, algorithm choice is nearly free. Between storage modes,
  the difference is large and consistent (~32-33%) regardless of language.
- **The language gap predates Redis.** It's visible in memory mode already
  and doesn't meaningfully widen or narrow once Redis is added - two
  independent effects (language/runtime, storage backend) that happen to
  compose additively rather than interacting.
- **Resist "Go is just faster" as the takeaway** (same caution as
  URL-Shortner's results, because the same mechanism is almost certainly
  at play): FastAPI's Dockerfile runs uvicorn with no `--workers` flag -
  one Python process, one event loop, handling all traffic for that
  replica. Go's goroutine-per-request model spreads the same load across
  real OS threads by default, with no configuration required to get that.
  The fair follow-up experiment - not run here, to keep this comparison to
  one variable at a time - is adding `--workers` to uvicorn and rechecking
  whether the gap narrows.
