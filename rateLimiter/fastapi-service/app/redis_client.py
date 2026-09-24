import redis.asyncio as redis

from app.config import settings

# redis-py's async client lazily connects its pool on first command, so no
# explicit connect() step is needed the way asyncpg required in the
# URL-Shortner project - constructing it eagerly here is enough.
client = redis.from_url(settings.redis_url, decode_responses=True)
