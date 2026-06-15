"""Approval gate service — S2 Unit 8b (BUILD_SPEC §13–§14)."""
from datetime import datetime, timezone

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import agent_tasks, approval_requests, workflow_runs
from app.services.event_service import get_event_service
from app.services.message_bus import (
    AgentMessageDraft,
    MessageBusService,
    WorkflowDispatchItem,
    get_message_bus,
)


class ApprovalNotFound(Exception):
    """No pending approval for the given run/task."""


class ApprovalAlreadyResolved(Exception):
    """Approval was already approved or rejected."""


async def approve_task(
    db: AsyncSession,
    run_id: str,
    task_id: str,
    bus: MessageBusService | None = None,
) -> dict:
    """Approve a paused task: persist handoff message, enqueue dispatch, resume run."""
    approval, pending_task = await _load_pending(db, run_id, task_id)
    from_task = await _latest_completed_task(db, run_id, exclude_task_id=task_id)
    if from_task is None:
        raise ApprovalNotFound(f"No completed predecessor task for run {run_id}")

    bus = bus or get_message_bus()
    now = datetime.now(timezone.utc).isoformat()

    draft = AgentMessageDraft(
        run_id=run_id,
        from_task_id=from_task["id"],
        to_task_id=task_id,
        msg_type="task_output",
        payload={
            "content": from_task.get("output") or "",
            "chat_id": None,
            "agent_id": from_task["agent_id"],
        },
    )
    dispatch = WorkflowDispatchItem(
        run_id=run_id,
        task_id=task_id,
        agent_id=pending_task["agent_id"],
        node_id=pending_task["node_id"],
        input=pending_task["input"],
    )
    await bus.deliver(db, draft, dispatch)

    await db.execute(
        update(approval_requests)
        .where(approval_requests.c.id == approval["id"])
        .values(status="approved", resolved_at=now)
    )
    await db.execute(
        update(workflow_runs)
        .where(workflow_runs.c.id == run_id)
        .values(status="running")
    )
    await get_event_service().emit(
        db,
        run_id=run_id,
        task_id=task_id,
        agent_id=pending_task["agent_id"],
        event_type="approval_resolved",
        data={"run_id": run_id, "task_id": task_id, "resolution": "approved"},
    )
    await db.commit()
    return {"run_id": run_id, "task_id": task_id, "status": "running"}


async def reject_task(db: AsyncSession, run_id: str, task_id: str) -> dict:
    """Reject a paused task: fail task + run."""
    approval, pending_task = await _load_pending(db, run_id, task_id)
    now = datetime.now(timezone.utc).isoformat()

    await db.execute(
        update(approval_requests)
        .where(approval_requests.c.id == approval["id"])
        .values(status="rejected", resolved_at=now)
    )
    await db.execute(
        update(agent_tasks)
        .where(agent_tasks.c.id == task_id)
        .values(status="failed", output="approval_rejected", completed_at=now)
    )
    await db.execute(
        update(workflow_runs)
        .where(workflow_runs.c.id == run_id)
        .values(status="failed", completed_at=now)
    )
    await get_event_service().emit(
        db,
        run_id=run_id,
        task_id=task_id,
        agent_id=pending_task["agent_id"],
        event_type="approval_resolved",
        data={"run_id": run_id, "task_id": task_id, "resolution": "rejected"},
    )
    await get_event_service().emit(
        db,
        run_id=run_id,
        event_type="workflow_failed",
        data={"run_id": run_id, "reason": "approval_rejected"},
    )
    await db.commit()
    return {"run_id": run_id, "task_id": task_id, "status": "failed"}


async def _load_pending(
    db: AsyncSession, run_id: str, task_id: str
) -> tuple[dict, dict]:
    row = await db.execute(
        select(approval_requests)
        .where(approval_requests.c.run_id == run_id)
        .where(approval_requests.c.task_id == task_id)
    )
    approval = row.mappings().first()
    if approval is None:
        raise ApprovalNotFound(f"No approval for run {run_id} task {task_id}")
    approval = dict(approval)
    if approval["status"] != "pending":
        raise ApprovalAlreadyResolved(
            f"Approval for run {run_id} task {task_id} is {approval['status']}"
        )

    task_row = await db.execute(
        select(agent_tasks).where(agent_tasks.c.id == task_id)
    )
    task = task_row.mappings().first()
    if task is None:
        raise ApprovalNotFound(f"Task {task_id} not found")
    return approval, dict(task)


async def _latest_completed_task(
    db: AsyncSession, run_id: str, exclude_task_id: str
) -> dict | None:
    rows = await db.execute(
        select(agent_tasks)
        .where(agent_tasks.c.run_id == run_id)
        .where(agent_tasks.c.status == "completed")
        .where(agent_tasks.c.id != exclude_task_id)
        .order_by(text("rowid"))
    )
    completed = [dict(r) for r in rows.mappings()]
    return completed[-1] if completed else None
