import asyncpg

from app.config import settings

pool: asyncpg.Pool | None = None


async def connect() -> None:
    global pool
    pool = await asyncpg.create_pool(settings.database_url, min_size=2, max_size=10)


async def disconnect() -> None:
    if pool is not None:
        await pool.close()


def get_pool() -> asyncpg.Pool:
    assert pool is not None, "DB pool not initialized"
    return pool
