# Click analytics: write amplification on a read-heavy path

Every redirect is, underneath, also a write: `click_count` goes up by one
and a row lands in `click_events`. On a service whose whole point is to be
fast on the read/redirect path, that's worth being deliberate about.

## v1 (implemented): async-to-client, synchronous-to-DB

The redirect response is returned to the client **immediately**. The two
analytics writes happen afterward, in a background task
(`BackgroundTasks` in FastAPI, a plain `go func()` in Go) that the client
never waits on:

```
UPDATE links SET click_count = click_count + 1 WHERE short_code = $1;
INSERT INTO click_events (short_code) VALUES ($1);
```

This is the simplest version that's still *correct* - the count is accurate
(barring a crash between the two statements, which is wrapped in a
transaction to avoid), it's just not on the critical path the client
experiences.

It is, deliberately, not free: a hot code redirected thousands of times a
minute means thousands of `UPDATE`s serializing on the same row (Postgres
row-level locking) plus thousands of `INSERT`s. Both implementations use
this exact same strategy, so the Go-vs-FastAPI load test comparison
([05-load-test-design.md](05-load-test-design.md)) is measuring the
language/runtime difference, not a difference in analytics strategy.

Run the Zipfian load test and watch what happens to the top 1-2 codes'
redirect latency as concurrency goes up - that's this write contention,
directly observable.

## v2 (optional, not part of the core comparison): buffered writes

Instead of writing to Postgres on every redirect, buffer clicks (in-process,
or via `Redis INCR` + a periodic flush) and batch-write on an interval - say
once a second, or every N events. This trades exact real-time `click_count`
for drastically less write volume to Postgres.

This is scoped as an explicit follow-on experiment (`ANALYTICS_MODE`
config flag), run on *one* stack after the main comparison, not mixed into
it - introducing two variables (language *and* write strategy) at once would
make the results harder to interpret. The correctness tradeoff to observe
and note: `click_count` can be momentarily stale, and a crash before a flush
loses whatever was buffered. That's the real cost of the throughput win, and
it's worth feeling deliberately rather than just being told about it.

## What wasn't done

Fully synchronous writes (client waits for both statements before getting
its redirect) were not implemented, even as a "worst case" baseline. It
would be a strictly worse version of v1 - not more instructive, just slower,
and would make the load-test numbers harder to read for no analytical
benefit.
