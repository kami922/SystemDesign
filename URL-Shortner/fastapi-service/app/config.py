import os


class Settings:
    database_url: str = os.environ.get(
        "DATABASE_URL", "postgresql://postgres:postgres@localhost:5433/urlshortener"
    )
    redis_url: str = os.environ.get("REDIS_URL", "redis://localhost:6380/0")
    base_url: str = os.environ.get("BASE_URL", "http://localhost:8001")
    default_cache_ttl_seconds: int = int(os.environ.get("DEFAULT_CACHE_TTL_SECONDS", 24 * 3600))
    custom_alias_min_len: int = 4
    custom_alias_max_len: int = 16

    # "sync_bg" (default, Milestone 3): every redirect schedules an
    # immediate background DB write for its click.
    # "buffered" (Milestone 7 experiment): clicks accumulate in memory and
    # are flushed to Postgres on an interval - see app/analytics.py and
    # docs/04-analytics-write-path.md.
    analytics_mode: str = os.environ.get("ANALYTICS_MODE", "sync_bg")
    analytics_flush_interval_seconds: float = float(
        os.environ.get("ANALYTICS_FLUSH_INTERVAL_SECONDS", "1.0")
    )


settings = Settings()
