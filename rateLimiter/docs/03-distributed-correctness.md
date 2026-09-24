# Distributed correctness

This is the project's centerpiece proof — the equivalent of URL-Shortner's
"kill Postgres, cached redirect still works." It demonstrates a failure
mode and its fix side by side, measured, not asserted.

## The motivating problem

A rate limiter almost never runs as a single instance in production — it's
one of several replicas behind a load balancer. **In-memory state cannot be
shared across replicas.** Each replica's dict, deque, or counter is
independent. If a limit of `N` is meant to apply per client, and requests
from that client get spread across `R` replicas, each replica independently
allows up to `N` — the *aggregate* limit that actually reaches the client
can be as high as `N × R`.

This isn't a bug to patch in the in-memory implementation. It's the actual
reason the Redis-backed storage layer exists at all — a distributed limiter
needs a single, shared source of truth that every replica reads from and
writes to atomically.

## The test

Two replicas per algorithm, same Redis, fixed ports (`:9001`, `:9002` in
local testing; `fastapi-app-1:8101` / `fastapi-app-2:8102` in Compose,
Milestone 8). `tests/test_distributed_correctness.py`:

1. Pick one shared `client_id` and fire `capacity` concurrent requests at
   **each** replica at the same instant (`asyncio.gather` across both base
   URLs).
2. Sum the total `200`s admitted across both replicas.
3. Run this once against `STORAGE_BACKEND=memory`, once against
   `STORAGE_BACKEND=redis`, same client, same burst size, same everything
   except the storage backend.

## Measured results (capacity = 10, 2 replicas)

| Algorithm | Memory mode (independent state) | Redis mode (shared state) |
|---|---|---|
| Token bucket | 20 | 10 |
| Leaky bucket | 20 | 10 |
| Fixed window | 20 | 10 |
| Sliding window log | 20 | 10 |
| Sliding window counter | 20 | 10 (well within tolerance) |

Every algorithm hits **exactly** the theoretical worst case in memory
mode — `2 × capacity`, because each replica independently has no idea the
other exists. Every algorithm holds the aggregate at (or within a small,
documented tolerance of) the true limit once Redis makes the state shared.
Sliding window counter gets a ±2 tolerance in the test because it's an
*approximation* even on a single instance (see
[01-algorithms.md](01-algorithms.md)) — the distributed test isn't
introducing new error, it's just not hiding the error the algorithm already
has.

## Why this needed a dedicated test, not Locust/k6

This assertion is exact ("aggregate allowed == capacity, not
`2 × capacity`"). Locust and k6's task scheduling is probabilistic by
design — great for realistic sustained load, useless for "fire exactly 10
requests at each of 2 replicas at the same instant and count exactly how
many succeed." `tests/harness.py`'s `fire_n` (pure `asyncio.gather`, no
random delays) is what makes this test deterministic and repeatable.

## What Redis-backed storage actually buys, precisely

Not "correctness" in the abstract — specifically: every one of the five
Lua scripts (`storage/lua/*.lua`) performs its algorithm's entire
check-and-update as a single atomic operation on Redis's single-threaded
command executor. Two replicas calling `EVAL` on the same key can never
interleave mid-script — one script runs to completion before the next
begins, regardless of which replica issued it or how many app processes
exist. That's the entire mechanism. No distributed lock, no consensus
protocol, no coordination between the replicas themselves — just one
shared, atomically-updated source of truth that every replica defers to.
