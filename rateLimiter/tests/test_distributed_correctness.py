"""Distributed correctness proof: does the aggregate limit hold across
replicas? Looped across all five algorithms (Milestone 6).

In-memory mode CANNOT share state across replicas - each replica's dict is
independent, so N replicas each independently allow up to `limit`, and
aggregate allowed can reach N x limit. That's not a bug to fix in memory;
it's the whole reason the Redis-backed layer exists. This test proves the
failure mode AND the fix, side by side.

Run:
    python tests/test_distributed_correctness.py \\
        --base-url http://localhost:9001 --base-url http://localhost:9002 \\
        --capacity 10 --mode redis     # expect ~= capacity allowed (the fix)
        --mode memory                   # expect > capacity allowed (the problem)
        --algorithm token_bucket        # or omit for all five
"""
import argparse
import asyncio
import os
import sys

import httpx

sys.path.insert(0, os.path.dirname(__file__))
from harness import count_status, unique_client_id  # noqa: E402

ALGORITHM_PATHS = {
    "token_bucket": "/api/token-bucket/action",
    "leaky_bucket": "/api/leaky-bucket/action",
    "fixed_window": "/api/fixed-window/action",
    "sliding_window_log": "/api/sliding-window-log/action",
    "sliding_window_counter": "/api/sliding-window-counter/action",
}

# sliding_window_counter is an approximation even on a single instance
# (see docs/01-algorithms.md) - give it a little slack the four exact
# algorithms don't need.
TOLERANCE = {
    "sliding_window_counter": 2,
}


async def _fire_n_at(base_url: str, path: str, n: int, client_id: str):
    async with httpx.AsyncClient(base_url=base_url, timeout=10.0) as client:
        tasks = [client.post(path, headers={"X-Client-Id": client_id}) for _ in range(n)]
        return await asyncio.gather(*tasks)


async def test_aggregate_limit(base_urls, algorithm: str, capacity: int, mode: str) -> None:
    path = ALGORITHM_PATHS[algorithm]
    client_id = unique_client_id("dist")
    # Fire `capacity` concurrent requests at EACH replica, at the same
    # time, using the SAME client_id - if the limit is truly shared,
    # total allowed across all replicas should be ~= capacity, not
    # capacity * len(base_urls).
    results_per_replica = await asyncio.gather(
        *[_fire_n_at(url, path, capacity, client_id) for url in base_urls]
    )
    total_allowed = sum(count_status(r, 200) for r in results_per_replica)

    if mode == "redis":
        tolerance = TOLERANCE.get(algorithm, 0)
        assert abs(total_allowed - capacity) <= tolerance, (
            f"[{algorithm}, redis mode] expected aggregate allowed ~= {capacity} "
            f"(tolerance {tolerance}) across {len(base_urls)} replicas, got "
            f"{total_allowed} - distributed correctness broken"
        )
        print(
            f"PASS test_aggregate_limit[{algorithm}, redis] (aggregate allowed = "
            f"{total_allowed}, target {capacity} +/-{tolerance})"
        )
    else:
        upper_bound = capacity * len(base_urls)
        assert total_allowed > capacity, (
            f"[{algorithm}, memory mode] expected aggregate allowed > {capacity} "
            f"(over-admission across independent replicas), got {total_allowed} - "
            f"if this now passes exactly {capacity}, are replicas actually independent?"
        )
        print(
            f"PASS test_aggregate_limit[{algorithm}, memory] (aggregate allowed = "
            f"{total_allowed}, demonstrating over-admission above the single-instance "
            f"limit of {capacity}, up to {upper_bound})"
        )


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", action="append", required=True, dest="base_urls")
    parser.add_argument(
        "--capacity", type=int, default=int(os.environ.get("RATE_LIMIT_DEFAULT_LIMIT", "10"))
    )
    parser.add_argument("--mode", choices=["memory", "redis"], required=True)
    parser.add_argument("--algorithm", choices=list(ALGORITHM_PATHS) + ["all"], default="all")
    args = parser.parse_args()

    algorithms = list(ALGORITHM_PATHS) if args.algorithm == "all" else [args.algorithm]
    for algo in algorithms:
        await test_aggregate_limit(args.base_urls, algo, args.capacity, args.mode)


if __name__ == "__main__":
    asyncio.run(main())
