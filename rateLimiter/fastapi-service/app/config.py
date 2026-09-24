import os


class Settings:
    default_limit: int = int(os.environ.get("RATE_LIMIT_DEFAULT_LIMIT", "10"))
    default_window_seconds: float = float(os.environ.get("RATE_LIMIT_DEFAULT_WINDOW_SECONDS", "10"))
    storage_backend: str = os.environ.get("STORAGE_BACKEND", "memory")
    redis_url: str = os.environ.get("REDIS_URL", "redis://localhost:6380/0")


settings = Settings()
