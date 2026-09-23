import json
from datetime import datetime, timezone

import redis.asyncio as redis

from app.config import settings

client: redis.Redis | None = None


async def connect() -> None:
    global client
    client = redis.from_url(settings.redis_url, decode_responses=True)


async def disconnect() -> None:
    if client is not None:
        await client.aclose()


def _key(short_code: str) -> str:
    return f"link:{short_code}"


async def get_link(short_code: str) -> dict | None:
    raw = await client.get(_key(short_code))
    if raw is None:
        return None
    data = json.loads(raw)
    if data["expires_at"] is not None:
        data["expires_at"] = datetime.fromisoformat(data["expires_at"])
    return data


async def set_link(short_code: str, long_url: str, expires_at: datetime | None) -> None:
    # Cache only what the redirect hot path needs, not the whole row.
    value = json.dumps(
        {
            "long_url": long_url,
            "expires_at": expires_at.isoformat() if expires_at else None,
        }
    )

    ttl_seconds = settings.default_cache_ttl_seconds
    if expires_at is not None:
        seconds_until_expiry = int((expires_at - datetime.now(timezone.utc)).total_seconds())
        ttl_seconds = max(1, min(ttl_seconds, seconds_until_expiry))

    await client.set(_key(short_code), value, ex=ttl_seconds)
