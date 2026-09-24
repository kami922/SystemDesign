# Rate Limiter — System Design Learning Project

All five classic rate-limiting algorithms — token bucket, leaky bucket,
fixed window counter, sliding window log, sliding window counter — built
twice (FastAPI and Go) against the same API contract, each supporting both
an in-memory (single-node) and Redis-backed (distributed) storage mode,
and proven correct with a deterministic test harness rather than just
described.

See [docs/](docs/) for the reasoning behind each decision:

- [01-algorithms.md](docs/01-algorithms.md) — all five algorithms, their storage, and their measured weaknesses
- [02-interface-design.md](docs/02-interface-design.md) — why storage splits into three protocols, not one
- [03-distributed-correctness.md](docs/03-distributed-correctness.md) — the central proof: memory mode fails, Redis mode fixes it
- [04-demo-api-and-testing.md](docs/04-demo-api-and-testing.md) — the API contract and why two different test tools exist
- [05-load-test-design.md](docs/05-load-test-design.md) — Locust + k6 overhead comparison design
- [06-results.md](docs/06-results.md) — actual comparison numbers

The API contract both services implement is in
[shared/api-contract.md](shared/api-contract.md).

## Running it

```bash
cd infra
docker compose up -d --build
```

Two fully isolated stacks, two replicas each (for the distributed-correctness
proof):

| Stack | Replica 1 | Replica 2 | Redis |
|---|---|---|---|
| FastAPI | http://localhost:8101 | http://localhost:8102 | localhost:6480 |
| Go | http://localhost:8201 | http://localhost:8202 | localhost:6481 |

Try it (every client needs an `X-Client-Id` header):

```bash
curl -X POST http://localhost:8101/api/token-bucket/action -H "X-Client-Id: me"
```

## Verifying correctness

```bash
pip install httpx   # if not already available
./tests/run_all.sh --base-url http://localhost:8101 --base-url http://localhost:8102
./tests/run_all.sh --base-url http://localhost:8201 --base-url http://localhost:8202
```

This runs the deterministic correctness suite (exact-count burst tests per
algorithm, plus the distributed-correctness proof) — not a load test. See
[docs/04-demo-api-and-testing.md](docs/04-demo-api-and-testing.md) for why
Locust/k6 can't do this job.

## Load testing (overhead, not correctness)

```bash
docker compose up locust   # web UI at :9089
docker compose run --rm locust -f locustfile.py --host http://fastapi-app-1:8000 \
  --headless --users 50 --spawn-rate 10 --run-time 1m

docker compose --profile tools run --rm k6 run --env BASE_URL=http://fastapi-app-1:8000 k6_script.js
```

Full fixed comparison (both tools, both backends, reset between each run):

```bash
./scripts/run_comparison.sh
```

## Build order

1. FastAPI + token bucket, in-memory only
2. + Redis-backed token bucket
3. + second replica, distributed-correctness proof (token bucket only)
4. Refactor checkpoint: finalize the storage protocol shapes
5. Remaining four algorithms, in-memory
6. Redis-backed storage for the remaining four; distributed proof across all five
7. Go port (same contract, verified with the same test suite)
8. Docker Compose wiring (both stacks, 2 replicas each) + Locust/k6 tooling
9. Real overhead comparison, written up in docs/06-results.md
