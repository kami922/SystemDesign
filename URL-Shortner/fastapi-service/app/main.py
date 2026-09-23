from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import analytics, cache, db
from app.config import settings
from app.routers import links, redirect


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.connect()
    await cache.connect()
    if settings.analytics_mode == "buffered":
        analytics.start()
    yield
    if settings.analytics_mode == "buffered":
        await analytics.stop()
    await cache.disconnect()
    await db.disconnect()


app = FastAPI(title="URL Shortener (FastAPI)", lifespan=lifespan)

app.include_router(links.router)


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


# Must be registered last: "/{code}" is a single-segment catch-all and would
# shadow "/healthz" (also single-segment) if registered before it.
app.include_router(redirect.router)
