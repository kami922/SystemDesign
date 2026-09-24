#!/usr/bin/env bash
# Flush the cache for one stack, so repeated load test runs start from an
# identical, empty baseline. No Postgres here (unlike URL-Shortner) - the
# rate limiter's only state lives in Redis.
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

docker compose -f "$COMPOSE_FILE" exec -T "${STACK}-redis" redis-cli FLUSHALL

echo "reset ${STACK} stack (flushed cache)"
