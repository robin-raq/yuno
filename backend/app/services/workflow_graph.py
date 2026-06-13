"""Workflow graph traversal — S2 Unit 6.

Evaluates outgoing edges from a completed node, creates the next pending task,
persists a task_output handoff message, and enqueues the next WorkflowDispatchItem.

Scope (this unit):
- Linear single-next-node traversal with simple condition matching.
- 'always' condition always matches; all other conditions use case-insensitive
  substring matching against the completed task's output.
- Fan-out (multiple matched edges), loop cap (max_iterations), conditional edge
  logic beyond substring matching, and stale dispatch protection are deferred.

Transaction contract:
- advance_after_task_completion returns only after the next task and handoff
  message are committed to the DB. The dispatch item is enqueued only on success.
  If this function raises, neither the DB writes nor the enqueue have occurred
  (apart from whatever was committed externally before this call).
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import agent_tasks, workflow_edges, workflow_nodes
from app.services.message_bus import (
    AgentMessageDraft,
    MessageBusService,
    WorkflowDispatchItem,
)


def edge_matches(condition: str, output: str | None) -> bool:
    """Return True if condition matches output.

    'always' (case-insensitive) always matches regardless of output. All other
    conditions are substring-matched case-insensitively against output; a None
    output does not match any non-always condition.
    """
    if condition.lower() == "always":
        return True
    if output is None:
        return False
    return condition.lower() in output.lower()


async def find_next_edges(
    db: AsyncSession, from_node_id: str, task_output: str | None
) -> list[dict]:
    """Return outgoing edges from from_node_id whose condition matches task_output."""
    rows = await db.execute(
        select(workflow_edges).where(workflow_edges.c.from_node_id == from_node_id)
    )
    edges = [dict(e) for e in rows.mappings()]
    return [e for e in edges if edge_matches(e["condition"], task_output)]


async def advance_after_task_completion(
    db: AsyncSession,
    item: WorkflowDispatchItem,
    task_output: str | None,
    bus: MessageBusService,
) -> dict | None:
    """Evaluate graph and dispatch the next task if one exists.

    Returns a dict with the next task's ids if a matched edge was found, or None
    if this is a terminal node (no outgoing edges match). On None, the caller is
    responsible for marking the run completed.

    Raises if the next node referenced by a matched edge no longer exists in the
    DB. The caller must handle that as a run-level failure (task stays completed).

    Commit boundary: the next agent_task INSERT and the agent_messages INSERT are
    committed together inside bus.persist_message. The enqueue happens only after
    that commit returns successfully.
    """
    matched_edges = await find_next_edges(db, item.node_id, task_output)
    if not matched_edges:
        return None  # terminal node — caller marks run completed

    # Linear: take the first matched edge. Fan-out deferred.
    edge = matched_edges[0]
    next_node_id = edge["to_node_id"]

    next_node_row = await db.execute(
        select(workflow_nodes).where(workflow_nodes.c.id == next_node_id)
    )
    next_node = next_node_row.mappings().first()
    if next_node is None:
        raise ValueError(f"Next node {next_node_id!r} not found in workflow_nodes")
    next_node = dict(next_node)

    # Create next task before persisting the message so the message's to_task_id
    # reference validates within the same (uncommitted) session.
    next_task_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        insert(agent_tasks).values(
            id=next_task_id,
            run_id=item.run_id,
            node_id=next_node_id,
            agent_id=next_node["agent_id"],
            source="workflow",
            status="pending",
            input=next_node["task_prompt"],
        )
    )

    # Persist handoff message. bus.persist_message commits internally, which
    # also commits the next task INSERT above (same session, same transaction).
    # Enqueue happens only after the commit.
    draft = AgentMessageDraft(
        run_id=item.run_id,
        from_task_id=item.task_id,
        to_task_id=next_task_id,
        msg_type="task_output",
        payload={
            "content": task_output or "",
            "chat_id": None,
            "agent_id": item.agent_id,
        },
    )
    await bus.persist_message(db, draft)

    # Enqueue after commit — at-most-once delivery, same as Unit 5.
    next_item = WorkflowDispatchItem(
        run_id=item.run_id,
        task_id=next_task_id,
        agent_id=next_node["agent_id"],
        node_id=next_node_id,
        input=next_node["task_prompt"],
    )
    await bus.enqueue_task(next_item)

    return {
        "task_id": next_task_id,
        "node_id": next_node_id,
        "agent_id": next_node["agent_id"],
    }
