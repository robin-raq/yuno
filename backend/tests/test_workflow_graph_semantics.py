"""S2 Unit 7 — workflow graph-execution semantics tests.

TDD red phase: these tests drive multi-step workflow runs through a three-node
branch graph (Coder -> Reviewer, with a REJECTED feedback loop back to Coder and
an APPROVED forward edge to Deployer). Unit 6's traversal has no loop cap and
treats "no matching edge" as terminal, so:
  - the loop-cap tests RED by exceeding the drain step budget (uncapped loop), and
  - the no_matching_edge test RED because the run is wrongly marked completed.

Implementation follows in workflow_graph.py (AdvanceResult, loop cap,
no_matching_edge, branch selection) and workflow_worker.py (outcome mapping).

Coverage:
  S1  Loop cap fires at the boundary (max_iterations=2 -> 2 loop-backs, 3rd capped).
  S2  Edge-level max_iterations overrides the agent default.
  S3  Null edge max_iterations falls back to the target agent's default (2).
  S4  Correct branch selection: APPROVED takes the forward edge, not the loop.
  S5  no_matching_edge on a non-end node fails the run; task stays completed.
  S6  Terminal end node completes normally (forced_complete=false).
  S7  feedback_sent event shape (run_id, from_agent, to_agent, iteration).
  S8  feedback_loop_capped event shape (run_id, edge_id, iteration_count).
  S9  forced_complete column is persisted, not only carried in the event.
"""
import json
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import insert, select, text, update

from app.adapters.base import TaskInput, TaskResult
from app.models import (
    agent_config, agent_tasks, agents, execution_events,
    workflow_edges, workflow_nodes, workflow_runs, workflows,
)
from app.services.message_bus import (
    InMemoryWorkflowQueue, MessageBusService, WorkflowDispatchItem,
)
from app.services.workflow_worker import WorkflowWorker


# ── Scripted adapter ──────────────────────────────────────────────────────────

def make_scripted_adapter(script: dict[str, str]):
    """Return an adapter class whose invoke() output is chosen by substring match
    on the task content. No shared mutable state across tests (closure per call)."""

    class _Scripted:
        def __init__(self, host="127.0.0.1", port=3284):
            pass

        async def invoke(self, task: TaskInput, on_event) -> TaskResult:
            content = (task.task_content or "").lower()
            output = "DEFAULT"
            for key, value in script.items():
                if key in content:
                    output = value
                    break
            return TaskResult(
                output=output, tokens_input=1, tokens_output=1,
                tokens_total=2, estimated_cost=0.0, session_id="s",
            )

        async def health_check(self) -> bool:
            return True

    return _Scripted


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_bus():
    return MessageBusService(InMemoryWorkflowQueue())


async def _drain(worker: WorkflowWorker, db, max_steps: int = 20) -> int:
    """Process queued items until the queue drains. Bounded to catch a runaway
    (uncapped) loop instead of hanging the suite."""
    steps = 0
    while await worker.process_next(db):
        steps += 1
        if steps > max_steps:
            raise AssertionError(
                f"drain exceeded {max_steps} steps — likely an uncapped loop"
            )
    return steps


async def _events(db, run_id: str, event_type: str) -> list[dict]:
    rows = (await db.execute(
        select(execution_events)
        .where(execution_events.c.run_id == run_id)
        .where(execution_events.c.event_type == event_type)
        .order_by(text("rowid"))
    )).mappings().all()
    return [{**dict(r), "data": json.loads(r["data"])} for r in rows]


async def _tasks_for_node(db, run_id: str, node_id: str) -> list[dict]:
    rows = (await db.execute(
        select(agent_tasks)
        .where(agent_tasks.c.run_id == run_id)
        .where(agent_tasks.c.node_id == node_id)
        .order_by(text("rowid"))
    )).mappings().all()
    return [dict(r) for r in rows]


async def _run_status(db, run_id: str) -> str:
    return (await db.execute(
        select(workflow_runs.c.status).where(workflow_runs.c.id == run_id)
    )).scalar_one()


# ── Branch fixture: Coder -> Reviewer -(REJECTED loop)-> Coder / -(APPROVED)-> Deployer ──

@pytest_asyncio.fixture
async def branch(db):
    """Three-node branch graph mirroring dev_pipeline.

    Coder(start) --always--> Reviewer(middle)
    Reviewer --REJECTED(max_iterations=2)--> Coder   (feedback loop)
    Reviewer --APPROVED--> Deployer(end)

    One pending task for the Coder. Returns the ids tests need.
    """
    ids = {k: str(uuid.uuid4()) for k in (
        "coder", "reviewer", "deployer",  # agent ids
        "workflow", "n_coder", "n_reviewer", "n_deployer",
        "e_fwd", "e_loop", "e_approve",
        "run", "task_coder",
    )}

    for aid, name in [
        (ids["coder"], "Coder"), (ids["reviewer"], "Reviewer"),
        (ids["deployer"], "Deployer"),
    ]:
        await db.execute(insert(agents).values(
            id=aid, name=name, role="tester",
            system_prompt="You are a test agent.", model="claude-haiku-4-5-20251001",
            status="active",
        ))
        await db.execute(insert(agent_config).values(
            id=str(uuid.uuid4()), agent_id=aid,
            extensions='["developer"]', requires_approval=0,
            max_tokens_per_run=50000, max_runs_per_minute=6,
            blocked_extensions="[]", max_feedback_iterations=2,
            max_turns=5, timeout_seconds=60,
        ))

    await db.execute(insert(workflows).values(
        id=ids["workflow"], name="Branch Workflow", description="",
    ))
    await db.execute(insert(workflow_nodes).values(
        id=ids["n_coder"], workflow_id=ids["workflow"], agent_id=ids["coder"],
        node_type="start", task_prompt="Write code.", position_x=0, position_y=0,
    ))
    await db.execute(insert(workflow_nodes).values(
        id=ids["n_reviewer"], workflow_id=ids["workflow"], agent_id=ids["reviewer"],
        node_type="middle", task_prompt="Review code.", position_x=100, position_y=0,
    ))
    await db.execute(insert(workflow_nodes).values(
        id=ids["n_deployer"], workflow_id=ids["workflow"], agent_id=ids["deployer"],
        node_type="end", task_prompt="Deploy code.", position_x=200, position_y=0,
    ))
    await db.execute(insert(workflow_edges).values(
        id=ids["e_fwd"], from_node_id=ids["n_coder"], to_node_id=ids["n_reviewer"],
        condition="always",
    ))
    await db.execute(insert(workflow_edges).values(
        id=ids["e_loop"], from_node_id=ids["n_reviewer"], to_node_id=ids["n_coder"],
        condition="REJECTED", max_iterations=2,
    ))
    await db.execute(insert(workflow_edges).values(
        id=ids["e_approve"], from_node_id=ids["n_reviewer"], to_node_id=ids["n_deployer"],
        condition="APPROVED",
    ))
    await db.execute(insert(workflow_runs).values(
        id=ids["run"], workflow_id=ids["workflow"], status="running",
        forced_complete=0, started_at="2026-01-01T00:00:00+00:00",
    ))
    await db.execute(insert(agent_tasks).values(
        id=ids["task_coder"], run_id=ids["run"], node_id=ids["n_coder"],
        agent_id=ids["coder"], source="workflow", status="pending", input="Write code.",
    ))
    await db.commit()
    return ids


async def _start(worker: WorkflowWorker, ids: dict) -> None:
    """Enqueue the first (Coder) dispatch item so a drain can run the whole graph."""
    await worker.bus.enqueue_task(WorkflowDispatchItem(
        run_id=ids["run"], task_id=ids["task_coder"], agent_id=ids["coder"],
        node_id=ids["n_coder"], input="Write code.",
    ))


# ── S1: loop cap fires at the boundary ────────────────────────────────────────

@pytest.mark.asyncio
async def test_loop_cap_fires_at_boundary(db, branch):
    """REJECTED forever: the loop edge is taken exactly twice (Coder runs 3x),
    the 3rd REJECTED is capped, run completes forced (not failed)."""
    adapter = make_scripted_adapter({"write": "looks ok", "review": "REJECTED"})
    worker = WorkflowWorker(_make_bus(), adapter_cls=adapter)
    await _start(worker, branch)
    await _drain(worker, db)

    coder_tasks = await _tasks_for_node(db, branch["run"], branch["n_coder"])
    reviewer_tasks = await _tasks_for_node(db, branch["run"], branch["n_reviewer"])
    assert len(coder_tasks) == 3, "original Coder + 2 feedback loop-backs"
    assert len(reviewer_tasks) == 3, "Reviewer ran after each Coder pass"

    assert await _run_status(db, branch["run"]) == "completed"
    forced = (await db.execute(
        select(workflow_runs.c.forced_complete).where(workflow_runs.c.id == branch["run"])
    )).scalar_one()
    assert forced == 1, "capped loop completes with forced_complete=true"

    capped = await _events(db, branch["run"], "feedback_loop_capped")
    assert len(capped) == 1
    completed = await _events(db, branch["run"], "workflow_completed")
    assert len(completed) == 1
    assert completed[0]["data"].get("forced_complete") is True
    assert len(await _events(db, branch["run"], "workflow_failed")) == 0


@pytest.mark.asyncio
async def test_loop_cap_emits_two_feedback_sent(db, branch):
    """Exactly two feedback_sent events (the two accepted loop-backs)."""
    adapter = make_scripted_adapter({"write": "looks ok", "review": "REJECTED"})
    worker = WorkflowWorker(_make_bus(), adapter_cls=adapter)
    await _start(worker, branch)
    await _drain(worker, db)

    sent = await _events(db, branch["run"], "feedback_sent")
    assert len(sent) == 2
    assert [s["data"]["iteration"] for s in sent] == [1, 2]


# ── S2 / S3: max_iterations resolution ────────────────────────────────────────

@pytest.mark.asyncio
async def test_edge_max_iterations_override(db, branch):
    """Edge max_iterations=1 caps after a single loop-back (Coder runs 2x)."""
    await db.execute(update(workflow_edges)
                     .where(workflow_edges.c.id == branch["e_loop"])
                     .values(max_iterations=1))
    await db.commit()

    adapter = make_scripted_adapter({"write": "looks ok", "review": "REJECTED"})
    worker = WorkflowWorker(_make_bus(), adapter_cls=adapter)
    await _start(worker, branch)
    await _drain(worker, db)

    assert len(await _tasks_for_node(db, branch["run"], branch["n_coder"])) == 2
    capped = await _events(db, branch["run"], "feedback_loop_capped")
    assert len(capped) == 1
    assert capped[0]["data"]["iteration_count"] == 1
    assert await _run_status(db, branch["run"]) == "completed"


@pytest.mark.asyncio
async def test_null_edge_falls_back_to_agent_default(db, branch):
    """Null edge max_iterations falls back to the target agent's default (2)."""
    await db.execute(update(workflow_edges)
                     .where(workflow_edges.c.id == branch["e_loop"])
                     .values(max_iterations=None))
    await db.commit()

    adapter = make_scripted_adapter({"write": "looks ok", "review": "REJECTED"})
    worker = WorkflowWorker(_make_bus(), adapter_cls=adapter)
    await _start(worker, branch)
    await _drain(worker, db)

    # agent default max_feedback_iterations=2 → 2 loop-backs → Coder runs 3x
    assert len(await _tasks_for_node(db, branch["run"], branch["n_coder"])) == 3
    assert await _run_status(db, branch["run"]) == "completed"


# ── S4: correct branch selection ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_branch_selection_approved_takes_forward_edge(db, branch):
    """APPROVED takes the forward edge to Deployer, not the loop back to Coder."""
    adapter = make_scripted_adapter(
        {"write": "looks ok", "review": "APPROVED", "deploy": "shipped"}
    )
    worker = WorkflowWorker(_make_bus(), adapter_cls=adapter)
    await _start(worker, branch)
    await _drain(worker, db)

    assert len(await _tasks_for_node(db, branch["run"], branch["n_coder"])) == 1, "no loop-back"
    assert len(await _tasks_for_node(db, branch["run"], branch["n_deployer"])) == 1
    assert await _run_status(db, branch["run"]) == "completed"

    forced = (await db.execute(
        select(workflow_runs.c.forced_complete).where(workflow_runs.c.id == branch["run"])
    )).scalar_one()
    assert forced == 0, "a clean APPROVED completion is not forced"
    assert len(await _events(db, branch["run"], "feedback_sent")) == 0
    assert len(await _events(db, branch["run"], "feedback_loop_capped")) == 0


# ── S5: no_matching_edge on a non-end node ────────────────────────────────────

@pytest.mark.asyncio
async def test_no_matching_edge_fails_run(db, branch):
    """A middle node whose output matches no outgoing edge fails the run with
    reason no_matching_edge; the completed task stays completed; nothing enqueued."""
    adapter = make_scripted_adapter({"write": "looks ok", "review": "UNCLEAR"})
    bus = _make_bus()
    worker = WorkflowWorker(bus, adapter_cls=adapter)
    await _start(worker, branch)
    await _drain(worker, db)

    assert await _run_status(db, branch["run"]) == "failed"
    failed = await _events(db, branch["run"], "workflow_failed")
    assert len(failed) == 1
    assert failed[0]["data"]["reason"] == "no_matching_edge"

    reviewer_tasks = await _tasks_for_node(db, branch["run"], branch["n_reviewer"])
    assert len(reviewer_tasks) == 1
    assert reviewer_tasks[0]["status"] == "completed", "task stays completed"

    assert len(await _tasks_for_node(db, branch["run"], branch["n_deployer"])) == 0
    assert bus.queue_size() == 0


# ── S6: terminal end node completes normally ──────────────────────────────────

@pytest.mark.asyncio
async def test_end_node_completes_unforced(db, branch):
    """Reaching the Deployer (end) via APPROVED completes the run unforced."""
    adapter = make_scripted_adapter(
        {"write": "looks ok", "review": "APPROVED", "deploy": "shipped"}
    )
    worker = WorkflowWorker(_make_bus(), adapter_cls=adapter)
    await _start(worker, branch)
    await _drain(worker, db)

    deployer_tasks = await _tasks_for_node(db, branch["run"], branch["n_deployer"])
    assert len(deployer_tasks) == 1
    assert deployer_tasks[0]["status"] == "completed"
    completed = await _events(db, branch["run"], "workflow_completed")
    assert len(completed) == 1
    assert completed[0]["data"].get("forced_complete") is False


# ── S7: feedback_sent event shape ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_feedback_sent_event_shape(db, branch):
    """feedback_sent carries run_id, from_agent (Reviewer), to_agent (Coder), iteration."""
    adapter = make_scripted_adapter({"write": "looks ok", "review": "REJECTED"})
    worker = WorkflowWorker(_make_bus(), adapter_cls=adapter)
    await _start(worker, branch)
    await _drain(worker, db)

    sent = await _events(db, branch["run"], "feedback_sent")
    assert len(sent) >= 1
    first = sent[0]["data"]
    assert first["run_id"] == branch["run"]
    assert first["from_agent"] == branch["reviewer"]
    assert first["to_agent"] == branch["coder"]
    assert first["iteration"] == 1


# ── S8: feedback_loop_capped event shape ──────────────────────────────────────

@pytest.mark.asyncio
async def test_feedback_loop_capped_event_shape(db, branch):
    """feedback_loop_capped carries run_id, edge_id (the loop edge), iteration_count."""
    adapter = make_scripted_adapter({"write": "looks ok", "review": "REJECTED"})
    worker = WorkflowWorker(_make_bus(), adapter_cls=adapter)
    await _start(worker, branch)
    await _drain(worker, db)

    capped = await _events(db, branch["run"], "feedback_loop_capped")
    assert len(capped) == 1
    data = capped[0]["data"]
    assert data["run_id"] == branch["run"]
    assert data["edge_id"] == branch["e_loop"]
    assert data["iteration_count"] == 2


# ── S9: loop dispatch uses msg_type=feedback ──────────────────────────────────

@pytest.mark.asyncio
async def test_loop_handoff_is_feedback_message(db, branch):
    """The handoff message for a loop-back is msg_type=feedback (not task_output)."""
    from app.models import agent_messages

    adapter = make_scripted_adapter({"write": "looks ok", "review": "REJECTED"})
    worker = WorkflowWorker(_make_bus(), adapter_cls=adapter)
    await _start(worker, branch)
    await _drain(worker, db)

    msg_types = [r["msg_type"] for r in (await db.execute(
        select(agent_messages).where(agent_messages.c.run_id == branch["run"])
        .order_by(text("rowid"))
    )).mappings().all()]
    # Coder->Reviewer forward (task_output) interleaved with Reviewer->Coder feedback
    assert "feedback" in msg_types
    assert msg_types.count("feedback") == 2


@pytest.mark.asyncio
async def test_loop_task_records_feedback_iteration_count(db, branch):
    """The looped-back Coder tasks persist feedback_iteration_count (1, 2) on the
    row, not only in the feedback_sent event."""
    adapter = make_scripted_adapter({"write": "looks ok", "review": "REJECTED"})
    worker = WorkflowWorker(_make_bus(), adapter_cls=adapter)
    await _start(worker, branch)
    await _drain(worker, db)

    coder_tasks = await _tasks_for_node(db, branch["run"], branch["n_coder"])
    counts = [t["feedback_iteration_count"] for t in coder_tasks]
    # original pass (0) + two loop-backs (1, 2)
    assert counts == [0, 1, 2]
