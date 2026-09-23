# URL Shortener — System Design Learning Project

A URL shortener built twice (FastAPI and Go) against the exact same API
contract, backed by Postgres + Redis (cache-aside), and load-tested locally
with both Locust and k6 to compare the two implementations under realistic,
Zipf-skewed traffic.

See [docs/](docs/) for the reasoning behind each design decision:

- [01-schema.md](docs/01-schema.md) — table design
- [02-short-code-strategy.md](docs/02-short-code-strategy.md) — base62 generation, custom aliases
- [03-caching.md](docs/03-caching.md) — cache-aside pattern
- [04-analytics-write-path.md](docs/04-analytics-write-path.md) — write amplification on the hot path
- [05-load-test-design.md](docs/05-load-test-design.md) — Locust + k6, Zipfian traffic
- [06-results.md](docs/06-results.md) — actual comparison numbers

The API contract both services implement is in
[shared/api-contract.md](shared/api-contract.md).

## Running it

```bash
cd infra
docker compose up -d --build
```

This brings up two fully isolated stacks:

| Stack | App | Postgres | Redis |
|---|---|---|---|
| FastAPI | http://localhost:8001 | localhost:5433 | localhost:6380 |
| Go | http://localhost:8002 | localhost:5434 | localhost:6381 |

Try it:

```bash
curl -X POST http://localhost:8001/api/links \
  -H "Content-Type: application/json" \
  -d '{"long_url": "https://example.com"}'

curl -v http://localhost:8001/<short_code>
```

## Load testing

**Locust web UI:**

```bash
cd infra
docker compose up locust
# open http://localhost:8089, point it at http://fastapi-app:8000 or http://go-app:8080
```

**Headless Locust:**

```bash
docker compose run --rm locust -f locustfile.py --host http://fastapi-app:8000 \
  --headless --users 200 --spawn-rate 20 --run-time 5m --csv results/fastapi_locust
```

**k6:**

```bash
docker compose --profile tools run --rm k6 run --env BASE_URL=http://fastapi-app:8000 k6_script.js
```

**Full fixed comparison (both tools, both backends, reset between each run):**

```bash
./scripts/run_comparison.sh
```

Seed the working set first (both tools read the same weighted pool):

```bash
docker compose run --rm --entrypoint python3 locust seed_data.py \
  --base-url http://fastapi-app:8000 --count 1000 --zipf-s 1.2 --output seeded_codes.json
```

## Build order

This was built in layers, each independently verified before the next:

1. FastAPI core (Postgres only, no cache)
2. + Redis cache-aside
3. + custom aliases, TTL/expiration, click analytics
4. Go port (same contract, own DB/Redis)
5. Docker Compose + Locust + k6 wiring
6. Real comparison run
7. (optional) buffered/async analytics experiment
