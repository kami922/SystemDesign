#!/usr/bin/env bash
# Fixed comparison procedure: for each stack, reset -> Locust run, reset ->
# k6 run. Targets replica 1 only - the two replicas exist for the
# distributed-correctness proof (tests/test_distributed_correctness.py),
# not this overhead comparison. Never runs two stacks concurrently, since
# both share host CPU/RAM and would confound the results.
set -euo pipefail

USERS="${USERS:-50}"
SPAWN_RATE="${SPAWN_RATE:-10}"
RUN_TIME="${RUN_TIME:-1m}"
# Generous relative to the expected traffic rate, per docs/05-load-test-design.md -
# this run measures overhead, not throttling, so admission should almost
# never trigger.
export RATE_LIMIT_DEFAULT_LIMIT="${RATE_LIMIT_DEFAULT_LIMIT:-100000}"
export RATE_LIMIT_DEFAULT_WINDOW_SECONDS="${RATE_LIMIT_DEFAULT_WINDOW_SECONDS:-60}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/infra/docker-compose.yml"

mkdir -p "$ROOT_DIR/loadtest/results"
# Locust (image runs as root) and k6 (official image runs as a non-root
# user) write results as different container UIDs - make sure neither is
# blocked writing into a host-owned directory.
chmod 777 "$ROOT_DIR/loadtest/results"

run_for_stack() {
  local stack="$1" internal_host="$2"

  echo "=== $stack: reset + Locust ==="
  "$SCRIPT_DIR/reset_stack.sh" "$stack"
  docker compose -f "$COMPOSE_FILE" run --rm locust \
    -f locustfile.py --host "$internal_host" --headless \
    --users "$USERS" --spawn-rate "$SPAWN_RATE" --run-time "$RUN_TIME" \
    --csv "results/${stack}_locust"

  echo "=== $stack: reset + k6 ==="
  "$SCRIPT_DIR/reset_stack.sh" "$stack"
  docker compose -f "$COMPOSE_FILE" --profile tools run --rm k6 \
    run --env BASE_URL="$internal_host" \
    --vus "$USERS" --duration "$RUN_TIME" \
    --out "csv=results/${stack}_k6.csv" \
    k6_script.js
}

docker compose -f "$COMPOSE_FILE" up -d --build --force-recreate --wait \
  fastapi-app-1 fastapi-app-2 fastapi-redis go-app-1 go-app-2 go-redis

run_for_stack fastapi "http://fastapi-app-1:8000"
run_for_stack go "http://go-app-1:8080"

echo "done - results in $ROOT_DIR/loadtest/results"
