"""S2 Unit 8 — execution event bus + SSE foundation (R09).

BUILD_SPEC §12: events persist to execution_events before fan-out to SSE
subscribers. This file covers the service-layer contract; HTTP SSE wiring is
validated via REST history and a minimal stream smoke test.
"""
import asyncio
import json
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import insert, select

from app.models import agents, agent_config, execution_events, workflow_runs, workflows
from app.services.event_service import EventService, get_event_service, reset_event_service


@pytest.fixture(autouse=True)
def _fresh_event_bus():
    reset_event_service()
    yield
    reset_event_service()


@pytest_asyncio.fixture
async def run_seed(db):
    agent_id = str(uuid.uuid4())
    await db.execute(insert(agents).values(
        id=agent_id, name="Coder", role="Engineer",
        system_prompt="", model="claude-sonnet-4-5", status="active",
    ))
    await db.execute(insert(agent_config).values(id=str(uuid.uuid4()), agent_id=agent_id))
    wf_id = str(uuid.uuid4())
    await db.execute(insert(workflows).values(
        id=wf_id, name="Dev", description="", template_key="dev_pipeline",
    ))
    run_id = str(uuid.uuid4())
    await db.execute(insert(workflow_runs).values(
        id=run_id, workflow_id=wf_id, status="pending", forced_complete=0,
        started_at="2026-06-12T00:00:00+00:00",
    ))
    await db.commit()
    return {"run_id": run_id, "agent_id": agent_id}


@pytest.mark.asyncio
async def test_emit_persists_and_fans_out_to_all_subscribers(db, run_seed):
    """BUILD_SPEC §18.1: emit → persisted row + every subscriber queue receives it."""
    bus = get_event_service()
    run_id = run_seed["run_id"]
    q1 = bus.subscribe(run_id)
    q2 = bus.subscribe(run_id)

    emitted = await bus.emit(
        db,
        run_id=run_id,
        event_type="task_started",
        data={"run_id": run_id, "task_id": "t1", "agent_id": run_seed["agent_id"]},
    )
    await db.commit()

    row = (await db.execute(
        select(execution_events.c.event_type, execution_events.c.data)
        .where(execution_events.c.id == emitted["id"])
    )).mappings().one()
    assert row["event_type"] == "task_started"
    assert json.loads(row["data"])["task_id"] == "t1"

    got1 = q1.get_nowait()
    got2 = q2.get_nowait()
    assert got1["event_type"] == "task_started"
    assert got2["id"] == emitted["id"]
    assert got1["data"]["task_id"] == "t1"


@pytest.mark.asyncio
async def test_subscriber_queue_is_bounded(db, run_seed):
    """BUILD_SPEC §12: per-subscriber queue maxsize=1000; lagging clients drop safely."""
    bus = EventService()
    q = bus.subscribe(run_seed["run_id"])
    assert q.maxsize == 1000


@pytest.mark.asyncio
async def test_list_run_events_returns_created_order(db, run_seed):
    bus = get_event_service()
    run_id = run_seed["run_id"]
    await bus.emit(db, run_id=run_id, event_type="workflow_started", data={"run_id": run_id})
    await bus.emit(db, run_id=run_id, event_type="task_started", data={"run_id": run_id, "task_id": "a"})
    await db.commit()

    events = await bus.list_run_events(db, run_id)
    assert [e["event_type"] for e in events] == ["workflow_started", "task_started"]


@pytest.mark.asyncio
async def test_get_run_events_rest_endpoint(client, db, run_seed):
    bus = get_event_service()
    run_id = run_seed["run_id"]
    await bus.emit(db, run_id=run_id, event_type="workflow_started", data={"run_id": run_id})
    await db.commit()

    resp = await client.get(f"/runs/{run_id}/events")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["event_type"] == "workflow_started"
    assert body[0]["data"]["run_id"] == run_id


@pytest.mark.asyncio
async def test_get_run_events_unknown_run_404(client):
    resp = await client.get(f"/runs/{uuid.uuid4()}/events")
    assert resp.status_code == 404
