import re
from urllib.parse import urlparse

import asyncpg
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.config import settings
from app.db import get_pool
from app.schemas import LinkCreateRequest, LinkResponse, StatsResponse
from app.shortcode import encode

router = APIRouter(prefix="/api/links", tags=["links"])

_ALIAS_PATTERN = re.compile(r"^[A-Za-z0-9_-]{4,16}$")


def _is_valid_long_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def _is_valid_alias(alias: str) -> bool:
    return bool(_ALIAS_PATTERN.match(alias))


@router.post("", response_model=LinkResponse, status_code=201)
async def create_link(payload: LinkCreateRequest):
    if not _is_valid_long_url(payload.long_url):
        return JSONResponse(status_code=400, content={"error": "invalid_long_url"})

    if payload.custom_alias is not None and not _is_valid_alias(payload.custom_alias):
        return JSONResponse(status_code=400, content={"error": "invalid_custom_alias"})

    pool = get_pool()
    async with pool.acquire() as conn:
        if payload.custom_alias is not None:
            # A pre-check would still race under concurrent requests for the
            # same alias, so the unique index is the real source of truth -
            # we just catch the violation it raises.
            try:
                row = await conn.fetchrow(
                    """
                    INSERT INTO links (short_code, long_url, is_custom_alias, expires_at)
                    VALUES ($1, $2, TRUE, $3)
                    RETURNING long_url, is_custom_alias, created_at, expires_at
                    """,
                    payload.custom_alias,
                    payload.long_url,
                    payload.expires_at,
                )
            except asyncpg.UniqueViolationError:
                return JSONResponse(status_code=409, content={"error": "alias_taken"})
            short_code = payload.custom_alias
        else:
            link_id = await conn.fetchval("SELECT nextval('links_id_seq')")
            short_code = encode(link_id)
            row = await conn.fetchrow(
                """
                INSERT INTO links (id, short_code, long_url, expires_at)
                VALUES ($1, $2, $3, $4)
                RETURNING long_url, is_custom_alias, created_at, expires_at
                """,
                link_id,
                short_code,
                payload.long_url,
                payload.expires_at,
            )

    return LinkResponse(
        short_code=short_code,
        short_url=f"{settings.base_url}/{short_code}",
        long_url=row["long_url"],
        is_custom_alias=row["is_custom_alias"],
        created_at=row["created_at"],
        expires_at=row["expires_at"],
    )


@router.get("/{code}/stats", response_model=StatsResponse)
async def get_stats(code: str):
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT l.short_code, l.long_url, l.click_count, l.created_at, l.expires_at,
                   (SELECT MAX(clicked_at) FROM click_events WHERE short_code = l.short_code)
                       AS last_clicked_at
            FROM links l
            WHERE l.short_code = $1
            """,
            code,
        )

    if row is None:
        return JSONResponse(status_code=404, content={"error": "not_found"})

    return StatsResponse(**dict(row))
