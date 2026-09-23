"""Buffered click analytics (Milestone 7 / ANALYTICS_MODE=buffered).

Clicks accumulate in a plain in-process dict - no I/O at all on the
redirect's critical path, not even a background task - and a single
asyncio loop flushes the whole buffer to Postgres on an interval. This
trades exact real-time click_count for far fewer, far larger writes to
Postgres under load.

The real cost, worth feeling rather than just reading about: whatever is
sitting in `_pending` when the process crashes is gone. Milestone 3's
sync_bg mode never loses a click; this one can.
"""
import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timezone

from app.config import settings
from app.db import get_pool

logger = logging.getLogger(__name__)

_pending: dict[str, list[datetime]] = defaultdict(list)
_flush_task: asyncio.Task | None = None


def record_click(short_code: str) -> None:
    _pending[short_code].append(datetime.now(timezone.utc))


async def _flush_once() -> None:
    global _pending
    if not _pending:
        return
    batch, _pending = _pending, defaultdict(list)

    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.executemany(
                "UPDATE links SET click_count = click_count + $1 WHERE short_code = $2",
                [(len(clicks), code) for code, clicks in batch.items()],
            )
            await conn.executemany(
                "INSERT INTO click_events (short_code, clicked_at) VALUES ($1, $2)",
                [(code, ts) for code, clicks in batch.items() for ts in clicks],
            )


async def _flush_loop() -> None:
    while True:
        await asyncio.sleep(settings.analytics_flush_interval_seconds)
        try:
            await _flush_once()
        except Exception:
            logger.exception("analytics flush failed")


def start() -> None:
    global _flush_task
    _flush_task = asyncio.create_task(_flush_loop())


async def stop() -> None:
    if _flush_task is None:
        return
    _flush_task.cancel()
    try:
        await _flush_task
    except asyncio.CancelledError:
        pass
    # Best-effort flush on clean shutdown - a crash still loses the buffer,
    # which is the documented tradeoff, not a bug.
    await _flush_once()
