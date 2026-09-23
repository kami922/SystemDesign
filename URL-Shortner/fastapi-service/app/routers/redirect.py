from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import JSONResponse, RedirectResponse

from app import analytics, cache
from app.config import settings
from app.db import get_pool

router = APIRouter()


def _is_expired(expires_at: datetime | None) -> bool:
    return expires_at is not None and expires_at < datetime.now(timezone.utc)


async def _record_click_sync_bg(short_code: str) -> None:
    # Runs after the redirect response has already been sent to the client
    # (Starlette flushes the response before executing background tasks) -
    # this is what keeps analytics off the redirect's critical path.
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "UPDATE links SET click_count = click_count + 1 WHERE short_code = $1",
                short_code,
            )
            await conn.execute(
                "INSERT INTO click_events (short_code) VALUES ($1)", short_code
            )


def _schedule_click(background_tasks: BackgroundTasks, short_code: str) -> None:
    if settings.analytics_mode == "buffered":
        analytics.record_click(short_code)  # pure in-memory, no I/O at all
    else:
        background_tasks.add_task(_record_click_sync_bg, short_code)


@router.get("/{code}")
async def redirect_to_long_url(code: str, background_tasks: BackgroundTasks):
    cached = await cache.get_link(code)
    if cached is not None:
        if _is_expired(cached["expires_at"]):
            return JSONResponse(status_code=410, content={"error": "expired"})
        _schedule_click(background_tasks, code)
        return RedirectResponse(url=cached["long_url"], status_code=302)

    # Cache miss: fall back to Postgres.
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT long_url, expires_at FROM links WHERE short_code = $1", code
        )

    if row is None:
        return JSONResponse(status_code=404, content={"error": "not_found"})

    if _is_expired(row["expires_at"]):
        # Don't cache dead entries - nothing gained from remembering a 410.
        return JSONResponse(status_code=410, content={"error": "expired"})

    await cache.set_link(code, row["long_url"], row["expires_at"])
    _schedule_click(background_tasks, code)
    return RedirectResponse(url=row["long_url"], status_code=302)
