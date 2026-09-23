#!/usr/bin/env bash
# Truncate tables + flush cache for one stack, so repeated load test runs
# start from an identical, empty baseline.
set -euo pipefail

STACK="${1:?usage: reset_stack.sh <fastapi|go>}"

case "$STACK" in
  fastapi | go) ;;
  *)
    echo "unknown stack: $STACK (expected 'fastapi' or 'go')" >&2
    exit 1
    ;;
esac

COMPOSE_FILE="$(cd "$(dirname "${BASH_SOURCE[0]}")/../infra" && pwd)/docker-compose.yml"

docker compose -f "$COMPOSE_FILE" exec -T "${STACK}-postgres" \
  psql -U postgres -d urlshortener -c "TRUNCATE click_events, links RESTART IDENTITY CASCADE;"

docker compose -f "$COMPOSE_FILE" exec -T "${STACK}-redis" redis-cli FLUSHALL

echo "reset ${STACK} stack (truncated tables, flushed cache)"
