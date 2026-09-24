"""Deterministic correctness test for fixed window counter - including its
headline weakness, the boundary double-burst.

Run directly:
    python tests/test_fixed_window.py --base-url http://localhost:9001

Timing note: the boundary test computes window edges from the TEST's own
wall clock rather than probing the server, assuming client and server run
on the same host (true for local dev/Docker-on-localhost testing) so
clocks are effectively shared.
"""
import argparse
import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from harness import count_status, fire_n, unique_client_id  # noqa: E402

PATH = "/api/fixed-window/action"


async def test_burst_exact_limit(base_url: str, limit: int, window_seconds: float) -> None:
    client_id = unique_client_id("fw-burst")
    # Start clear of a boundary so the whole burst lands in one window.
    now = time.time()
    window_index = int(now // window_seconds)
    window_start = window_index * window_seconds
    if now - window_start > window_seconds * 0.7:
        await asyncio.sleep((window_index + 1) * window_seconds - now + 0.05)

    responses = await fire_n(base_url, PATH, limit + 5, client_id)
    ok = count_status(responses, 200)
    denied = count_status(responses, 429)
    assert ok == limit, f"expected exactly {limit} allowed, got {ok}"
    assert denied == 5, f"expected exactly 5 denied, got {denied}"
    print(f"PASS test_burst_exact_limit ({ok} allowed, {denied} denied)")


async def test_boundary_double_burst(base_url: str, limit: int, window_seconds: float) -> None:
    """The headline weakness: `limit` requests just before a window edge
    plus `limit` more just after both succeed - up to 2x the intended
    rate in a short span. This DEMONSTRATES the known flaw; it is not
    asserting a bug that needs fixing.
    """
    client_id = unique_client_id("fw-boundary")
    now = time.time()
    window_index = int(now // window_seconds)
    window_end = (window_index + 1) * window_seconds
    lead = 0.5
    await asyncio.sleep(max(0.0, window_end - now - lead))

    first_burst = await fire_n(base_url, PATH, limit, client_id)
    first_ok = count_status(first_burst, 200)

    await asyncio.sleep(lead + 0.2)  # cross the boundary

    second_burst = await fire_n(base_url, PATH, limit, client_id)
    second_ok = count_status(second_burst, 200)

    total_ok = first_ok + second_ok
    assert total_ok > limit, (
        f"expected the boundary double-burst to admit MORE than {limit} total "
        f"(that's the known flaw), got {total_ok} - if this is now exactly "
        f"{limit}, the timing likely didn't straddle a boundary"
    )
    print(
        f"PASS test_boundary_double_burst ({first_ok} + {second_ok} = {total_ok} "
        f"admitted across the boundary, vs a nominal limit of {limit})"
    )


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:9001")
    parser.add_argument(
        "--limit", type=int, default=int(os.environ.get("RATE_LIMIT_DEFAULT_LIMIT", "10"))
    )
    parser.add_argument(
        "--window", type=float, default=float(os.environ.get("RATE_LIMIT_DEFAULT_WINDOW_SECONDS", "10"))
    )
    args = parser.parse_args()

    await test_burst_exact_limit(args.base_url, args.limit, args.window)
    await test_boundary_double_burst(args.base_url, args.limit, args.window)


if __name__ == "__main__":
    asyncio.run(main())
