"""Deterministic correctness test for token bucket.

Run directly:
    python tests/test_token_bucket.py --base-url http://localhost:9001

Asserts exact pass/fail counts against RATE_LIMIT_DEFAULT_LIMIT /
RATE_LIMIT_DEFAULT_WINDOW_SECONDS - pass --capacity/--window explicitly if
the server under test uses non-default values.
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from harness import count_status, fire_n, unique_client_id  # noqa: E402

PATH = "/api/token-bucket/action"


async def test_burst_exact_capacity(base_url: str, capacity: int) -> None:
    client_id = unique_client_id("tb-burst")
    responses = await fire_n(base_url, PATH, capacity + 5, client_id)
    ok = count_status(responses, 200)
    denied = count_status(responses, 429)
    assert ok == capacity, f"expected exactly {capacity} allowed, got {ok}"
    assert denied == 5, f"expected exactly 5 denied, got {denied}"
    print(f"PASS test_burst_exact_capacity ({ok} allowed, {denied} denied)")


async def test_refill_after_wait(base_url: str, capacity: int, window_seconds: float) -> None:
    client_id = unique_client_id("tb-refill")
    await fire_n(base_url, PATH, capacity, client_id)  # drain the bucket
    await asyncio.sleep(window_seconds + 0.5)  # wait a full refill interval + margin
    responses = await fire_n(base_url, PATH, capacity + 5, client_id)
    ok = count_status(responses, 200)
    assert ok == capacity, f"expected exactly {capacity} allowed after refill, got {ok}"
    print(f"PASS test_refill_after_wait ({ok} allowed after refill)")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:9001")
    parser.add_argument(
        "--capacity", type=int, default=int(os.environ.get("RATE_LIMIT_DEFAULT_LIMIT", "10"))
    )
    parser.add_argument(
        "--window", type=float, default=float(os.environ.get("RATE_LIMIT_DEFAULT_WINDOW_SECONDS", "10"))
    )
    args = parser.parse_args()

    await test_burst_exact_capacity(args.base_url, args.capacity)
    await test_refill_after_wait(args.base_url, args.capacity, args.window)


if __name__ == "__main__":
    asyncio.run(main())
