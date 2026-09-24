"""Deterministic correctness test for sliding window log - and the direct
contrast with fixed window's boundary flaw.

Run directly:
    python tests/test_sliding_window_log.py --base-url http://localhost:9001
"""
import argparse
import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from harness import count_status, fire_n, unique_client_id  # noqa: E402

PATH = "/api/sliding-window-log/action"


async def test_burst_exact_limit(base_url: str, limit: int) -> None:
    client_id = unique_client_id("swl-burst")
    responses = await fire_n(base_url, PATH, limit + 5, client_id)
    ok = count_status(responses, 200)
    denied = count_status(responses, 429)
    assert ok == limit, f"expected exactly {limit} allowed, got {ok}"
    assert denied == 5, f"expected exactly 5 denied, got {denied}"
    print(f"PASS test_burst_exact_limit ({ok} allowed, {denied} denied)")


async def test_no_boundary_double_burst(base_url: str, limit: int, window_seconds: float) -> None:
    """Same timing pattern as fixed window's boundary test - but here it
    should NOT double-admit, because the sliding window looks back exactly
    `window_seconds` from `now`, with no calendar-aligned edges to exploit.
    """
    client_id = unique_client_id("swl-boundary")
    now = time.time()
    window_index = int(now // window_seconds)
    window_end = (window_index + 1) * window_seconds
    lead = 0.5
    await asyncio.sleep(max(0.0, window_end - now - lead))

    first_burst = await fire_n(base_url, PATH, limit, client_id)
    first_ok = count_status(first_burst, 200)

    await asyncio.sleep(lead + 0.2)  # crosses the calendar boundary, but well
    # within window_seconds of the first burst's timestamps

    second_burst = await fire_n(base_url, PATH, limit, client_id)
    second_ok = count_status(second_burst, 200)

    total_ok = first_ok + second_ok
    assert total_ok <= limit, (
        f"expected the sliding log to cap total admitted at {limit} across "
        f"this short span (no double-burst), got {total_ok}"
    )
    print(
        f"PASS test_no_boundary_double_burst ({first_ok} + {second_ok} = {total_ok} "
        f"admitted, correctly capped at {limit} - unlike fixed window's ~2x)"
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

    await test_burst_exact_limit(args.base_url, args.limit)
    await test_no_boundary_double_burst(args.base_url, args.limit, args.window)


if __name__ == "__main__":
    asyncio.run(main())
