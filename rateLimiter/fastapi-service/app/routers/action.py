from typing import Optional

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse

from app.limiter.base import RateLimitResult
from app.registry import LIMITERS

router = APIRouter(prefix="/api")


def _rate_limit_headers(result: RateLimitResult) -> dict:
    headers = {
        "X-RateLimit-Limit": str(result.limit),
        "X-RateLimit-Remaining": str(max(0, result.remaining)),
        "X-RateLimit-Reset": str(result.reset_at),
    }
    if result.retry_after is not None:
        headers["Retry-After"] = str(result.retry_after)
    return headers


async def _handle(algorithm: str, x_client_id: Optional[str]) -> JSONResponse:
    if not x_client_id:
        return JSONResponse(status_code=400, content={"error": "missing_client_id"})

    result = await LIMITERS[algorithm].allow(x_client_id)
    headers = _rate_limit_headers(result)

    if not result.allowed:
        return JSONResponse(status_code=429, content={"error": "rate_limited"}, headers=headers)

    return JSONResponse(status_code=200, content={"ok": True, "algorithm": algorithm}, headers=headers)


@router.post("/token-bucket/action")
async def token_bucket_action(x_client_id: Optional[str] = Header(default=None, alias="X-Client-Id")):
    return await _handle("token_bucket", x_client_id)


@router.post("/leaky-bucket/action")
async def leaky_bucket_action(x_client_id: Optional[str] = Header(default=None, alias="X-Client-Id")):
    return await _handle("leaky_bucket", x_client_id)


@router.post("/fixed-window/action")
async def fixed_window_action(x_client_id: Optional[str] = Header(default=None, alias="X-Client-Id")):
    return await _handle("fixed_window", x_client_id)


@router.post("/sliding-window-log/action")
async def sliding_window_log_action(x_client_id: Optional[str] = Header(default=None, alias="X-Client-Id")):
    return await _handle("sliding_window_log", x_client_id)


@router.post("/sliding-window-counter/action")
async def sliding_window_counter_action(
    x_client_id: Optional[str] = Header(default=None, alias="X-Client-Id")
):
    return await _handle("sliding_window_counter", x_client_id)
