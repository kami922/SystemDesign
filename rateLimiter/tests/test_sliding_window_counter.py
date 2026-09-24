"""Deterministic correctness test for sliding window counter - run the
identical boundary-straddling timing as fixed window's test for the direct
side-by-side payoff: total stays close to `limit`, not ~2x.

Run directly:
    python tests/test_sliding_window_counter.py --base-url http://localhost:9001
"""
import argparse
import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from harness import count_status, fire_n, unique_client_id  # noqa: E402

PATH = "/api/sliding-window-counter/action"


async def test_burst_near_limit(base_url: str, limit: int) -> None:
    # The weighted estimate depends on exactly when the burst lands within
    # the window, so admission can be off by one or two from `limit` -
    # assert "close to", not "exactly", unlike fixed window/sliding log's
    # crisp per-window semantics.
    client_id = unique_client_id("swc-burst")
    responses = await fire_n(base_url, PATH, limit + 5, client_id)
    ok = count_status(responses, 200)
    assert limit - 1 <= ok <= limit + 1, f"expected approximately {limit} allowed, got {ok}"
    print(f"PASS test_burst_near_limit ({ok} allowed, target ~{limit})")


async def test_boundary_stays_near_limit(base_url: str, limit: int, window_seconds: float) -> None:
    client_id = unique_client_id("swc-boundary")
    now = time.time()
    window_index = int(now // window_seconds)
    window_end = (window_index + 1) * window_seconds
    lead = 0.5
    await asyncio.sleep(max(0.0, window_end - now - lead))

    first_burst = await fire_n(base_url, PATH, limit, client_id)
    first_ok = count_status(first_burst, 200)

    await asyncio.sleep(lead + 0.2)

    second_burst = await fire_n(base_url, PATH, limit, client_id)
    second_ok = count_status(second_burst, 200)

    total_ok = first_ok + second_ok
    upper_bound = int(limit * 1.5)
    assert total_ok <= upper_bound, (
        f"expected total admitted to stay well under 2x{limit} across the "
        f"boundary (got {total_ok}) - the whole point of the weighted "
        f"estimate vs fixed window's hard reset"
    )
    print(
        f"PASS test_boundary_stays_near_limit ({first_ok} + {second_ok} = {total_ok} "
        f"admitted across the boundary, vs fixed window's ~{2 * limit})"
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

    await test_burst_near_limit(args.base_url, args.limit)
    await test_boundary_stays_near_limit(args.base_url, args.limit, args.window)


if __name__ == "__main__":
    asyncio.run(main())
