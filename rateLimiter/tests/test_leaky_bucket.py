"""Deterministic correctness test for leaky bucket (meter variant).

Run directly:
    python tests/test_leaky_bucket.py --base-url http://localhost:9001
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from harness import count_status, fire_n, fire_sequential, unique_client_id  # noqa: E402

PATH = "/api/leaky-bucket/action"


async def test_burst_exact_capacity(base_url: str, capacity: int) -> None:
    client_id = unique_client_id("lb-burst")
    responses = await fire_n(base_url, PATH, capacity + 5, client_id)
    ok = count_status(responses, 200)
    denied = count_status(responses, 429)
    assert ok == capacity, f"expected exactly {capacity} allowed, got {ok}"
    assert denied == 5, f"expected exactly 5 denied, got {denied}"
    print(f"PASS test_burst_exact_capacity ({ok} allowed, {denied} denied)")


async def test_trickle_all_allowed(base_url: str, capacity: int, window_seconds: float) -> None:
    # Trickling at the leak rate should never exceed the backlog - every
    # request should be allowed, since the bucket drains as fast as it fills.
    client_id = unique_client_id("lb-trickle")
    leak_rate = capacity / window_seconds
    delay = 1.0 / leak_rate
    responses = await fire_sequential(base_url, PATH, capacity, client_id, delay)
    ok = count_status(responses, 200)
    assert ok == capacity, f"expected all {capacity} trickled requests allowed, got {ok}"
    print(f"PASS test_trickle_all_allowed ({ok}/{capacity} allowed at leak rate)")


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
    await test_trickle_all_allowed(args.base_url, args.capacity, args.window)


if __name__ == "__main__":
    asyncio.run(main())
