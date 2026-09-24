from fastapi import FastAPI

from app.routers import action

app = FastAPI(title="Rate Limiter (FastAPI)")

app.include_router(action.router)


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}
