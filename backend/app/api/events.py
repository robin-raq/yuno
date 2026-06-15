"""SSE + REST execution events — S2 Unit 8."""
import asyncio
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.database import get_db
from app.services.event_service import get_event_service
from app.services.workflow_service import RunNotFound, list_run_events

log = logging.getLogger(__name__)
router = APIRouter(tags=["events"])

_KEEPALIVE_SECONDS = 30


@router.get("/events")
async def stream_events(
    request: Request,
    run_id: str | None = None,
    agent_id: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """SSE stream for a workflow run or run-less agent task monitor."""
    if bool(run_id) == bool(agent_id):
        raise HTTPException(
            400,
            detail={"error": "invalid_query", "message": "Provide exactly one of run_id or agent_id"},
        )
    channel = run_id or agent_id
    assert channel is not None
    bus = get_event_service()

    async def generator():
        if run_id:
            try:
                history = await list_run_events(db, run_id)
            except RunNotFound:
                yield {"event": "error", "data": json.dumps({"message": "run_not_found"})}
                return
        else:
            history = await bus.list_agent_events(db, agent_id)  # type: ignore[arg-type]

        for ev in history:
            yield _sse_payload(ev)

        queue = bus.subscribe(channel)
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    live = await asyncio.wait_for(queue.get(), timeout=_KEEPALIVE_SECONDS)
                except asyncio.TimeoutError:
                    yield {"comment": "keepalive"}
                    continue
                yield _sse_payload(live)
        finally:
            bus.unsubscribe(channel, queue)

    return EventSourceResponse(generator())


def _sse_payload(ev: dict) -> dict:
    return {
        "event": ev["event_type"],
        "data": json.dumps({
            "id": ev["id"],
            "run_id": ev.get("run_id"),
            "agent_id": ev.get("agent_id"),
            "task_id": ev.get("task_id"),
            **ev.get("data", {}),
        }),
    }
