#!/usr/bin/env bash
# Runs every deterministic correctness test against one or more running
# instances. This is the primary verification tool for every milestone in
# this project - see docs/04-demo-api-and-testing.md for why Locust/k6
# can't do this job.
#
# Requires httpx: pip install httpx (already in fastapi-service/.venv if
# you set that up per the README).
#
# Usage:
#   ./run_all.sh --base-url http://localhost:8101 [--base-url http://localhost:8102]
#
# With two --base-url values, also runs the distributed-correctness proof
# (redis mode) across them.
set -uo pipefail

BASE_URLS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --base-url)
      BASE_URLS+=("$2")
      shift 2
      ;;
    *)
      echo "unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [[ ${#BASE_URLS[@]} -eq 0 ]]; then
  echo "usage: run_all.sh --base-url <url> [--base-url <url2>]" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PRIMARY_URL="${BASE_URLS[0]}"
FAILED=0

run_test() {
  local name="$1"
  shift
  echo "--- $name ---"
  if python3 "$@"; then
    echo "OK: $name"
  else
    echo "FAILED: $name"
    FAILED=1
  fi
  echo
}

for f in test_token_bucket.py test_leaky_bucket.py test_fixed_window.py \
         test_sliding_window_log.py test_sliding_window_counter.py; do
  run_test "$f" "$SCRIPT_DIR/$f" --base-url "$PRIMARY_URL"
done

if [[ ${#BASE_URLS[@]} -ge 2 ]]; then
  run_test "test_distributed_correctness.py (redis)" \
    "$SCRIPT_DIR/test_distributed_correctness.py" \
    --base-url "${BASE_URLS[0]}" --base-url "${BASE_URLS[1]}" --mode redis
else
  echo "skipping test_distributed_correctness.py - needs a second --base-url"
fi

if [[ $FAILED -eq 0 ]]; then
  echo "ALL TESTS PASSED"
else
  echo "SOME TESTS FAILED"
fi
exit $FAILED
