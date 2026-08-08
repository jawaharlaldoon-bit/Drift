"""Drift Cloud Run API: event ingestion, workflow execution, SSE, and dashboard."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Query, Response, status
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from .auth import verify_pubsub_authorization
from .config import get_settings
from .demo import build_demo_incident
from .events import bus
from .ingestion import PubSubEnvelope, decode_pubsub_envelope
from .models import IncidentSummary, WorkflowRun, WorkflowStage
from .store import get_store
from .workflow import DriftWorkflow

app = FastAPI(
    title="Drift Taskmaster API",
    version="0.1.0",
    description="Proof-carrying remediation for failed AI workflows.",
)


class DemoTrigger(BaseModel):
    event_id: str | None = Field(default=None, min_length=3, max_length=120)


class AcceptedIncident(BaseModel):
    incident_id: str
    duplicate: bool
    stage: str
    demo: bool


@app.post("/v1/events/pubsub", response_model=AcceptedIncident)
async def receive_pubsub(
    envelope: PubSubEnvelope,
    response: Response,
    authorization: str | None = Header(default=None),
) -> AcceptedIncident:
    """Receive an authenticated Pub/Sub push envelope.

    The public dashboard shares this Cloud Run service, so this handler independently
    verifies the configured Pub/Sub OIDC audience and service-account email. It
    acknowledges only after the workflow is durably terminal.
    """
    try:
        await verify_pubsub_authorization(authorization, get_settings())
        event = decode_pubsub_envelope(envelope)
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    run, duplicate = await DriftWorkflow().process(event)
    if run.stage is WorkflowStage.FAILED:
        # A non-2xx response asks Pub/Sub to redeliver and ultimately route the
        # durably recorded failure to the configured dead-letter topic.
        raise HTTPException(
            status_code=503,
            detail=f"incident {run.incident_id} stopped safely; retry requested",
        )
    response.status_code = status.HTTP_200_OK
    return AcceptedIncident(
        incident_id=run.incident_id,
        duplicate=duplicate,
        stage=run.stage.value,
        demo=run.demo,
    )


@app.post("/v1/demo/incidents", response_model=AcceptedIncident)
async def trigger_demo(
    payload: DemoTrigger,
    authorization: str | None = Header(default=None),
) -> AcceptedIncident:
    settings = get_settings()
    expected = f"Bearer {settings.demo_trigger_token}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="invalid demo trigger token")
    event = build_demo_incident(settings, event_id=payload.event_id)
    run, duplicate = await DriftWorkflow().process(event)
    return AcceptedIncident(
        incident_id=run.incident_id,
        duplicate=duplicate,
        stage=run.stage.value,
        demo=True,
    )


@app.get("/v1/incidents", response_model=list[IncidentSummary])
async def list_incidents(limit: int = Query(default=30, ge=1, le=100)):
    return [IncidentSummary.from_run(run) for run in await get_store().list_runs(limit)]


@app.get("/v1/incidents/{incident_id}", response_model=WorkflowRun)
async def get_incident(incident_id: str):
    run = await get_store().get(incident_id)
    if run is None:
        raise HTTPException(status_code=404, detail="incident not found")
    return run


@app.get("/v1/incidents/{incident_id}/events")
async def get_incident_events(incident_id: str):
    run = await get_store().get(incident_id)
    if run is None:
        raise HTTPException(status_code=404, detail="incident not found")
    return await get_store().get_events(incident_id)


@app.get("/v1/events/stream")
async def event_stream():
    async def generate():
        async for event in bus.subscribe():
            yield {
                "event": "workflow",
                "id": f"{event.incident_id}:{event.occurred_at.timestamp()}",
                "data": json.dumps(event.model_dump(mode="json")),
            }

    return EventSourceResponse(generate(), ping=15)


@app.get("/healthz")
async def healthz():
    settings = get_settings()
    return {
        "ok": True,
        "service": "drift-api",
        "environment": settings.drift_env,
        "build_revision": settings.drift_build_revision,
        "reasoning_backend": settings.drift_reasoning_backend,
        "gemini_model": settings.gemini_model,
        "state_backend": settings.state_backend,
        "action_mode": settings.action_mode,
        "live_actions_ready": settings.live_actions_ready,
        "cloud": {
            "project_configured": bool(settings.google_cloud_project),
            "region": settings.google_cloud_location,
            "pubsub_topic": settings.pubsub_topic,
        },
    }


_WEB_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"
if _WEB_DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(_WEB_DIST), html=True), name="dashboard")
else:

    @app.get("/", response_class=HTMLResponse)
    async def development_index() -> str:
        return """<!doctype html><html><body style='font-family:system-ui;background:#071019;
        color:#e7f6ff;padding:3rem'><h1>Drift API is running</h1><p>Start the Vite
        frontend in <code>web/</code> or build it before creating the container.</p>
        <p><a style='color:#52e6ff' href='/docs'>Open API documentation</a></p></body></html>"""


def run() -> None:
    import uvicorn

    uvicorn.run("drift.api:app", host="0.0.0.0", port=8080)
