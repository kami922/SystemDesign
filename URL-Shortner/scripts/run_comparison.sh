#!/usr/bin/env bash
# Fixed comparison procedure: for each stack, reset -> seed -> Locust run,
# reset -> seed -> k6 run. Never runs two of these concurrently, since both
# stacks share host CPU/RAM and would confound the results.
set -euo pipefail

USERS="${USERS:-200}"
SPAWN_RATE="${SPAWN_RATE:-20}"
RUN_TIME="${RUN_TIME:-5m}"
SEED_COUNT="${SEED_COUNT:-1000}"
ZIPF_S="${ZIPF_S:-1.2}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/infra/docker-compose.yml"

mkdir -p "$ROOT_DIR/loadtest/results"
# Locust and k6 write results as different container UIDs (locust's image
# runs as root, the official k6 image runs as a non-root user) - make sure
# neither is blocked writing into a host-owned directory.
chmod 777 "$ROOT_DIR/loadtest/results"

seed_stack() {
  local internal_host="$1"
  docker compose -f "$COMPOSE_FILE" run --rm --entrypoint python3 locust \
    seed_data.py --base-url "$internal_host" --count "$SEED_COUNT" --zipf-s "$ZIPF_S" \
    --output seeded_codes.json
}

run_for_stack() {
  local stack="$1" internal_host="$2"

  echo "=== $stack: reset + seed + Locust ==="
  "$SCRIPT_DIR/reset_stack.sh" "$stack"
  seed_stack "$internal_host"
  docker compose -f "$COMPOSE_FILE" run --rm locust \
    -f locustfile.py --host "$internal_host" --headless \
    --users "$USERS" --spawn-rate "$SPAWN_RATE" --run-time "$RUN_TIME" \
    --csv "results/${stack}_locust"

  echo "=== $stack: reset + seed + k6 ==="
  "$SCRIPT_DIR/reset_stack.sh" "$stack"
  seed_stack "$internal_host"
  docker compose -f "$COMPOSE_FILE" --profile tools run --rm k6 \
    run --env BASE_URL="$internal_host" --env SEEDED_CODES_PATH=./seeded_codes.json \
    --vus "$USERS" --duration "$RUN_TIME" \
    --out "csv=results/${stack}_k6.csv" \
    k6_script.js
}

docker compose -f "$COMPOSE_FILE" up -d --wait \
  fastapi-app fastapi-postgres fastapi-redis go-app go-postgres go-redis

run_for_stack fastapi "http://fastapi-app:8000"
run_for_stack go "http://go-app:8080"

echo "done - results in $ROOT_DIR/loadtest/results"
