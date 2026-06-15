"""Workflow graph traversal — S2 Units 6–7.

Evaluates outgoing edges from a completed node and decides what happens next:
create the next pending task (forward or feedback loop-back), complete the run,
force-complete a capped loop, or fail the run with `no_matching_edge`.

Unit 6 (linear): forward single-next traversal with simple condition matching.
Unit 7 (semantics): feedback-loop cap (§9.3), no_matching_edge failure (§9.5),
and correct conditional branch selection across all outgoing edges (§9.2).

Loop-edge definition (scoped heuristic):
- A loop edge is an edge that (a) has a non-"always" condition, (b) points to
  a node that has already executed in this run, and (c) points *backward* in the
  seeded layout (``to_node.position_x < from_node.position_x``). Without (c), a
  conditional forward re-entry (Compliance→Analyst after a Research loop-back)
  would be misclassified as a feedback loop.

Iteration counter:
- loops_taken for a loop edge = (number of prior tasks for its to_node in this
  run) − 1 (the original pass is iteration 0; each loop-back adds one task). The
  forward "always" edge re-creating the *other* node's tasks does not affect this
  count, so it lands exactly on the §9.3 example (cap=2 → 2 loop-backs, 3rd skipped).

Outcomes (AdvanceResult.status):
- next_task        — a next task was created, message persisted, item enqueued.
- completed        — terminal node / sink: caller marks run completed (unforced).
- completed_forced — a loop was capped and nothing else matched: caller marks the
                     run completed with forced_complete=true (NOT failed).
- failed_no_match  — a non-end node had outgoing edges but none matched and no
                     loop was capped: caller marks the run failed (task stays
                     completed). This is a deliberate control-flow outcome, not an
                     exception — the caller must NOT route it through the
                     post-completion exception handler.

Transaction contract (unchanged from Unit 6):
- The next agent_task INSERT, any feedback_sent event, and the handoff message are
  committed together inside bus.persist_message. The dispatch item is enqueued
  only after that commit. feedback_loop_capped events on the completed_forced path
  are left uncommitted for the caller to commit atomically with the run update.
"""
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    agent_config, agent_tasks, agents, approval_requests, execution_events, workflow_edges,
    workflow_nodes, workflow_runs,
)
from app.domain.remittance.analyst import compose_analyst_task_input
from app.services.event_service import get_event_service
from app.services.message_bus import (
    AgentMessageDraft,
    MessageBusService,
    WorkflowDispatchItem,
)

log = logging.getLogger(__name__)

_FEEDBACK_BLOCK_START = "--- FEEDBACK FROM PREVIOUS STEP ---"
_FEEDBACK_BLOCK_END = "--- END FEEDBACK ---"


def compose_loop_back_input(task_prompt: str, task_output: str | None) -> str:
    """Compose loop-back task input: static prompt plus delimited upstream output."""
    prompt = (task_prompt or "").strip()
    feedback = (task_output or "").strip()
    if not feedback:
        return prompt
    return (
        f"{prompt}\n\n{_FEEDBACK_BLOCK_START}\n"
        f"{feedback}\n"
        f"{_FEEDBACK_BLOCK_END}"
    )


_DEFAULT_FEEDBACK_CAP = 2  # BUILD_SPEC §9.3 default when neither edge nor agent set it


@dataclass
class AdvanceResult:
    """Outcome of advancing the graph after a task completes. The worker maps
    each status to a run-state transition (see module docstring)."""
    status: str  # next_task | completed | completed_forced | failed_no_match | awaiting_approval
    next_task_id: str | None = None
    next_node_id: str | None = None
    next_agent_id: str | None = None


def edge_matches(condition: str, output: str | None) -> bool:
    """Return True if condition matches output.

    'always' (case-insensitive) always matches regardless of output. All other
    conditions are substring-matched case-insensitively against output; a None
    output does not match any non-always condition.

    Conditions containing ``=`` (KTD6 sentinels such as ``COMPLIANCE=CLEARED``)
    match only the first line of output so a FLAGGED body cannot fail-open by
    echoing an upstream sentinel in prose.
    """
    if condition.lower() == "always":
        return True
    if output is None:
        return False
    haystack = output.splitlines()[0] if "=" in condition else output
    return condition.lower() in haystack.lower()


async def advance_after_task_completion(
    db: AsyncSession,
    item: WorkflowDispatchItem,
    task_output: str | None,
    bus: MessageBusService,
) -> AdvanceResult:
    """Evaluate the graph after item's task completed and decide the next step.

    Returns an AdvanceResult; see the module docstring for the four outcomes and
    their commit semantics. Raises (exception path) only when a matched edge
    points to a node that no longer exists — the caller treats that as a
    run-level failure with the task left completed.
    """
    completed_node = await _get_node(db, item.node_id)
    edges = await _get_edges_from(db, item.node_id)
    matched = [e for e in edges if edge_matches(e["condition"], task_output)]

    eligible: list[tuple[dict, bool, int | None]] = []
    capped_any = False
    for edge in matched:
        to_node = await _get_node(db, edge["to_node_id"])
        is_back_edge = (
            to_node is not None
            and completed_node is not None
            and to_node["position_x"] < completed_node["position_x"]
        )
        is_loop = (
            edge["condition"].lower() != "always"
            and is_back_edge
            and await _node_executed(db, item.run_id, edge["to_node_id"])
        )
        if not is_loop:
            eligible.append((edge, False, None))
            continue
        loops_taken = await _count_node_tasks(db, item.run_id, edge["to_node_id"]) - 1
        cap = await _resolve_cap(db, edge)
        if loops_taken >= cap:
            # iteration_count = loop-backs already accepted (== cap at the boundary),
            # i.e. how many times this edge fired before being skipped, not the
            # skipped attempt.
            await _emit_event(
                db, item.run_id, "feedback_loop_capped",
                {"run_id": item.run_id, "edge_id": edge["id"], "iteration_count": loops_taken},
            )
            capped_any = True
            continue
        eligible.append((edge, True, loops_taken + 1))

    if not eligible:
        if capped_any:
            # §9.3: a capped loop with nothing else to take completes (forced),
            # never fails — the sender's last output is accepted as final.
            return AdvanceResult(status="completed_forced")
        if not edges or (completed_node and completed_node["node_type"] == "end"):
            return AdvanceResult(status="completed")
        # §9.5: a non-end node with edges but no match (and no cap) fails.
        return AdvanceResult(status="failed_no_match")

    if len(eligible) > 1:
        # Fan-out (≥2 matched non-loop edges) is deferred — dispatch the first only.
        log.warning(
            "multiple eligible edges from node %s; dispatching first only (fan-out deferred)",
            item.node_id,
        )
    edge, is_loop, iteration = eligible[0]
    return await _dispatch_next(db, item, task_output, bus, edge, is_loop, iteration)


async def _dispatch_next(
    db: AsyncSession,
    item: WorkflowDispatchItem,
    task_output: str | None,
    bus: MessageBusService,
    edge: dict,
    is_loop: bool,
    iteration: int | None,
) -> AdvanceResult:
    """Create the next task, persist the handoff message (and feedback_sent on a
    loop), and enqueue — all committed atomically by bus.persist_message."""
    next_node = await _get_node(db, edge["to_node_id"])
    if next_node is None:
        raise ValueError(f"Next node {edge['to_node_id']!r} not found in workflow_nodes")

    next_task_id = str(uuid.uuid4())
    if is_loop:
        next_input = compose_loop_back_input(next_node["task_prompt"], task_output)
    elif task_output:
        next_agent_name = await _get_agent_name(db, next_node["agent_id"])
        if next_agent_name == "Analyst":
            research_output = await _get_latest_agent_output(db, item.run_id, "Research")
            if research_output:
                next_input = compose_analyst_task_input(research_output, task_output)
            else:
                next_input = task_output
        else:
            # Forward handoff: prior agent output becomes the next task input (BUILD_SPEC §7.1).
            next_input = task_output
    else:
        next_input = next_node["task_prompt"]
    await db.execute(insert(agent_tasks).values(
        id=next_task_id,
        run_id=item.run_id,
        node_id=next_node["id"],
        agent_id=next_node["agent_id"],
        source="workflow",
        status="pending",
        input=next_input,
        feedback_iteration_count=iteration if is_loop else 0,
    ))

    if await _agent_requires_approval(db, next_node["agent_id"]):
        agent_name = await _get_agent_name(db, next_node["agent_id"]) or "Agent"
        description = f"Approve {agent_name} to proceed"
        now = datetime.now(timezone.utc).isoformat()
        await db.execute(insert(approval_requests).values(
            id=str(uuid.uuid4()),
            run_id=item.run_id,
            task_id=next_task_id,
            description=description,
            status="pending",
            created_at=now,
        ))
        await db.execute(
            update(workflow_runs)
            .where(workflow_runs.c.id == item.run_id)
            .values(status="awaiting_approval")
        )
        await get_event_service().emit(
            db,
            run_id=item.run_id,
            task_id=next_task_id,
            agent_id=next_node["agent_id"],
            event_type="approval_required",
            data={
                "run_id": item.run_id,
                "task_id": next_task_id,
                "agent_id": next_node["agent_id"],
                "description": description,
            },
        )
        await db.commit()
        return AdvanceResult(
            status="awaiting_approval",
            next_task_id=next_task_id,
            next_node_id=next_node["id"],
            next_agent_id=next_node["agent_id"],
        )

    if is_loop:
        # feedback_sent is committed atomically with the task + message below.
        await _emit_event(
            db, item.run_id, "feedback_sent",
            {
                "run_id": item.run_id,
                "from_agent": item.agent_id,
                "to_agent": next_node["agent_id"],
                "iteration": iteration,
            },
        )

    draft = AgentMessageDraft(
        run_id=item.run_id,
        from_task_id=item.task_id,
        to_task_id=next_task_id,
        msg_type="feedback" if is_loop else "task_output",
        payload={
            "content": task_output or "",
            "chat_id": None,
            "agent_id": item.agent_id,
        },
    )
    await bus.persist_message(db, draft)  # commits next_task + feedback_sent + message

    await bus.enqueue_task(WorkflowDispatchItem(
        run_id=item.run_id,
        task_id=next_task_id,
        agent_id=next_node["agent_id"],
        node_id=next_node["id"],
        input=next_input,
    ))

    return AdvanceResult(
        status="next_task",
        next_task_id=next_task_id,
        next_node_id=next_node["id"],
        next_agent_id=next_node["agent_id"],
    )


# ── DB helpers ────────────────────────────────────────────────────────────────

async def _get_node(db: AsyncSession, node_id: str) -> dict | None:
    row = await db.execute(select(workflow_nodes).where(workflow_nodes.c.id == node_id))
    node = row.mappings().first()
    return dict(node) if node else None


async def _get_agent_name(db: AsyncSession, agent_id: str) -> str | None:
    row = await db.execute(select(agents.c.name).where(agents.c.id == agent_id))
    return row.scalar_one_or_none()


async def _get_latest_agent_output(
    db: AsyncSession, run_id: str, agent_name: str
) -> str | None:
    row = await db.execute(
        select(agent_tasks.c.output)
        .join(agents, agents.c.id == agent_tasks.c.agent_id)
        .where(
            agent_tasks.c.run_id == run_id,
            agents.c.name == agent_name,
            agent_tasks.c.status == "completed",
            agent_tasks.c.output.isnot(None),
        )
        .order_by(agent_tasks.c.completed_at.desc())
        .limit(1)
    )
    return row.scalar_one_or_none()


async def _get_edges_from(db: AsyncSession, from_node_id: str) -> list[dict]:
    # Ordered by id so "take the first eligible edge" is deterministic when more
    # than one edge matches (true fan-out is deferred — see advance_after_task_completion).
    rows = await db.execute(
        select(workflow_edges)
        .where(workflow_edges.c.from_node_id == from_node_id)
        .order_by(workflow_edges.c.id)
    )
    return [dict(e) for e in rows.mappings()]


async def _node_executed(db: AsyncSession, run_id: str, node_id: str) -> bool:
    """True if node_id already has at least one task in this run."""
    row = await db.execute(
        select(agent_tasks.c.id)
        .where(agent_tasks.c.run_id == run_id, agent_tasks.c.node_id == node_id)
        .limit(1)
    )
    return row.first() is not None


async def _count_node_tasks(db: AsyncSession, run_id: str, node_id: str) -> int:
    row = await db.execute(
        select(func.count())
        .select_from(agent_tasks)
        .where(agent_tasks.c.run_id == run_id, agent_tasks.c.node_id == node_id)
    )
    return int(row.scalar_one())


async def _resolve_cap(db: AsyncSession, edge: dict) -> int:
    """Edge-level max_iterations if set, else the target agent's
    max_feedback_iterations, else the §9.3 default (2)."""
    if edge["max_iterations"] is not None:
        return int(edge["max_iterations"])
    to_node = await _get_node(db, edge["to_node_id"])
    if to_node is None:
        return _DEFAULT_FEEDBACK_CAP
    row = await db.execute(
        select(agent_config.c.max_feedback_iterations)
        .where(agent_config.c.agent_id == to_node["agent_id"])
    )
    val = row.scalar_one_or_none()
    return int(val) if val is not None else _DEFAULT_FEEDBACK_CAP


async def _agent_requires_approval(db: AsyncSession, agent_id: str) -> bool:
    row = await db.execute(
        select(agent_config.c.requires_approval).where(agent_config.c.agent_id == agent_id)
    )
    val = row.scalar_one_or_none()
    return bool(val)


async def _emit_event(
    db: AsyncSession, run_id: str, event_type: str, data: dict
) -> None:
    """Insert one execution_events row (uncommitted; committed by the caller's
    next commit). Graph events omit task_id/agent_id like other run-level events."""
    await get_event_service().emit(db, run_id=run_id, event_type=event_type, data=data)
