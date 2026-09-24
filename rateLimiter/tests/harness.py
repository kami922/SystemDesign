"""Shared helpers for the deterministic correctness test suite.

This is NOT a load-testing tool (that's loadtest/) - it exists because
Locust/k6's probabilistic task scheduling can't make exact-count
assertions like "fire N+K requests, get exactly N successes." Every
scenario here asserts an exact number.
"""
import asyncio
import time
import uuid
from typing import List

import httpx


def unique_client_id(prefix: str = "test") -> str:
    # uuid4-based so every scenario gets an isolated key - tests never
    # need a reset step between runs and can run in any order.
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


async def fire_n(base_url: str, path: str, n: int, client_id: str) -> List[httpx.Response]:
    """Max-concurrency burst: all n requests in flight at once."""
    async with httpx.AsyncClient(base_url=base_url, timeout=10.0) as client:
        tasks = [client.post(path, headers={"X-Client-Id": client_id}) for _ in range(n)]
        return await asyncio.gather(*tasks)


async def fire_sequential(
    base_url: str, path: str, n: int, client_id: str, delay_s: float
) -> List[httpx.Response]:
    """Paced firing, one request every delay_s - for refill/leak-rate tests."""
    results = []
    async with httpx.AsyncClient(base_url=base_url, timeout=10.0) as client:
        for _ in range(n):
            results.append(await client.post(path, headers={"X-Client-Id": client_id}))
            await asyncio.sleep(delay_s)
    return results


def count_status(responses: List[httpx.Response], status: int) -> int:
    return sum(1 for r in responses if r.status_code == status)


async def wait_past_reset(base_url: str, path: str, client_id: str, margin_s: float = 0.05) -> None:
    """Probe X-RateLimit-Reset and sleep past it, plus a small margin.

    Boundary-sensitive scenarios (fixed window, sliding window counter)
    are flaky if the test happens to start right at a window edge -
    call this first so the scenario starts from a known, fresh window.
    """
    async with httpx.AsyncClient(base_url=base_url, timeout=10.0) as client:
        resp = await client.post(path, headers={"X-Client-Id": client_id})
        reset_at = float(resp.headers["X-RateLimit-Reset"])
    sleep_for = max(0.0, reset_at - time.time()) + margin_s
    await asyncio.sleep(sleep_for)
