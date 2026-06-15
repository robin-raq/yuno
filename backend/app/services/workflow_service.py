"""Workflow API spine (S2 Unit 3 + Unit 9 enqueue).

Lists workflows, starts a run (validate graph → create run + first pending task
→ persist workflow_started → enqueue first dispatch item), and returns a run
snapshot. The background worker (S2 Unit 9) drains the queue; Goose is never
invoked in this module.
"""
import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import insert, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    agents, workflows, workflow_nodes, workflow_runs, agent_tasks,
    agent_messages, approval_requests,
)
from app.services.event_service import get_event_service
from app.services.message_bus import WorkflowDispatchItem, get_message_bus


class WorkflowNotFound(Exception):
    """Requested workflow id does not exist."""


class GraphValidationError(Exception):
    """Workflow graph failed the minimal Unit-3 validation."""


class RunNotFound(Exception):
    """Requested run id does not exist."""


async def list_workflows(db: AsyncSession) -> list[dict]:
    rows = await db.execute(
        select(
            workflows.c.id, workflows.c.name,
            workflows.c.description, workflows.c.template_key,
        ).order_by(workflows.c.name)
    )
    return [dict(r) for r in rows.mappings()]


async def start_run(db: AsyncSession, workflow_id: str, initial_input: str) -> dict:
    """Validate the graph, then create the run, its first pending task, and the
    workflow_started event. Raises before any insert if validation fails."""
    workflow = await _get_workflow(db, workflow_id)
    if not workflow:
        raise WorkflowNotFound(workflow_id)

    start_node = await _validate_graph(db, workflow_id)

    run_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(insert(workflow_runs).values(
        id=run_id,
        workflow_id=workflow_id,
        status="pending",          # worker (later unit) owns pending -> running
        forced_complete=0,
        started_at=now,
    ))

    # First task: the start node, awaiting a worker. Input falls back to the
    # node's own prompt when the caller supplies none.
    task_id = str(uuid.uuid4())
    task_input = initial_input or start_node["task_prompt"]
    await db.execute(insert(agent_tasks).values(
        id=task_id,
        run_id=run_id,
        node_id=start_node["id"],
        agent_id=start_node["agent_id"],
        source="workflow",
        status="pending",
        input=task_input,
    ))

    await get_event_service().emit(
        db,
        run_id=run_id,
        event_type="workflow_started",
        data={"run_id": run_id, "workflow_id": workflow_id},
    )
    await db.commit()

    await get_message_bus().enqueue_task(WorkflowDispatchItem(
        run_id=run_id,
        task_id=task_id,
        agent_id=start_node["agent_id"],
        node_id=start_node["id"],
        input=task_input,
    ))

    return {
        "run_id": run_id,
        "workflow_id": workflow_id,
        "status": "pending",
        "forced_complete": False,
        "started_at": now,
    }


async def list_run_events(db: AsyncSession, run_id: str) -> list[dict]:
    """REST history of execution_events for a run (BUILD_SPEC §6)."""
    row = await db.execute(select(workflow_runs.c.id).where(workflow_runs.c.id == run_id))
    if row.first() is None:
        raise RunNotFound(run_id)
    return await get_event_service().list_run_events(db, run_id)


async def get_run(db: AsyncSession, run_id: str) -> dict:
    row = await db.execute(select(workflow_runs).where(workflow_runs.c.id == run_id))
    run = row.mappings().first()
    if not run:
        raise RunNotFound(run_id)
    run = dict(run)

    workflow = await _get_workflow(db, run["workflow_id"])

    # rowid preserves insertion ("created") order; agent_tasks has no created_at.
    task_rows = await db.execute(
        select(agent_tasks)
        .where(agent_tasks.c.run_id == run_id)
        .order_by(text("rowid"))
    )
    tasks = [dict(t) for t in task_rows.mappings()]

    # Order matches MessageBusService.list_messages: created_at + rowid tiebreak
    # so same-second messages are deterministically ordered by insertion.
    # Payload is decoded from JSON string to dict to match frontend expectations.
    msg_rows = await db.execute(
        select(agent_messages)
        .where(agent_messages.c.run_id == run_id)
        .order_by(agent_messages.c.created_at, text("rowid"))
    )
    messages = []
    for m in msg_rows.mappings():
        d = dict(m)
        d["payload"] = json.loads(d["payload"])
        messages.append(d)

    approval_rows = await db.execute(
        select(approval_requests).where(
            approval_requests.c.run_id == run_id,
            approval_requests.c.status == "pending",
        )
    )
    pending = approval_rows.mappings().first()

    return {
        "run_id": run["id"],
        "workflow_id": run["workflow_id"],
        "status": run["status"],
        "forced_complete": bool(run["forced_complete"]),
        "started_at": run["started_at"],
        "completed_at": run["completed_at"],
        "total_tokens": run["total_tokens"],
        "total_cost": run["total_cost"],
        "workflow": dict(workflow) if workflow else None,
        "tasks": tasks,
        "messages": messages,
        "pending_approval": dict(pending) if pending else None,
    }


async def _get_workflow(db: AsyncSession, workflow_id: str) -> dict | None:
    row = await db.execute(select(workflows).where(workflows.c.id == workflow_id))
    wf = row.mappings().first()
    return dict(wf) if wf else None


async def _validate_graph(db: AsyncSession, workflow_id: str) -> dict:
    """Minimal Unit-3 validation: ≥1 start node whose agent exists. Returns the
    start node. Orphan-node and full-edge validation are deferred (see AI_USAGE)."""
    rows = await db.execute(
        select(workflow_nodes).where(workflow_nodes.c.workflow_id == workflow_id)
    )
    nodes = [dict(n) for n in rows.mappings()]

    start_nodes = [n for n in nodes if n["node_type"] == "start"]
    if not start_nodes:
        raise GraphValidationError("workflow has no start node")
    start = start_nodes[0]

    agent_row = await db.execute(select(agents.c.id).where(agents.c.id == start["agent_id"]))
    if agent_row.first() is None:
        raise GraphValidationError("start node references a missing agent")

    return start
