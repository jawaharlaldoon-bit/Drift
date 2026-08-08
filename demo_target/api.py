"""Cloud Run sandbox used for reliable before/after replay."""

from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel, Field

from .engine import respond

app = FastAPI(title="Drift Demo Target", version="0.1.0")


class ReplayRequest(BaseModel):
    message: str = Field(min_length=1, max_length=10_000)
    policy: str = Field(min_length=1, max_length=50_000)


@app.post("/v1/replay")
async def replay(request: ReplayRequest):
    return respond(message=request.message, policy=request.policy)


@app.get("/healthz")
async def healthz():
    return {"ok": True, "service": "drift-demo-target", "deterministic": True}


def run() -> None:
    import uvicorn

    uvicorn.run("demo_target.api:app", host="0.0.0.0", port=8082)
