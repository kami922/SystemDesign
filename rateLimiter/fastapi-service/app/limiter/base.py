from dataclasses import dataclass
from typing import Optional, Protocol


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    reset_at: float
    retry_after: Optional[float] = None


class RateLimiter(Protocol):
    async def allow(self, key: str) -> RateLimitResult: ...
