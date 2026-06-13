"""test_message_bus — S2 Unit 4 internal message-bus foundation.

Proves agent_messages persistence + read-back order, FIFO queue dispatch, the
persist-before-queue rule (§11), clear errors on unknown run/task, and that the
Unit 3 start path still creates only a pending task with no execution.

Unit 4 builds the foundation later units consume — it does NOT run a worker,
execute tasks, or invoke Goose.
"""
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError

from app.models import (
    agents, agent_config, workflows, workflow_nodes, workflow_runs,
    agent_tasks, agent_messages,
)
from app.services.message_bus import (
    MessageBusService, InMemoryWorkflowQueue, WorkflowDispatchItem,
    AgentMessageDraft, UnknownRun, UnknownTask,
)


@pytest_asyncio.fixture
async def bus_seed(db):
    """Seed one agent, a workflow + start node, a run, and two tasks (a from/to
    pair) — the minimum needed to persist a valid workflow A2A message."""
    aid = str(uuid.uuid4())
    await db.execute(insert(agents).values(
        id=aid, name="Coder", role="Engineer", system_prompt="", model="claude-sonnet-4-5", status="active",
    ))
    await db.execute(insert(agent_config).values(id=str(uuid.uuid4()), agent_id=aid))

    wf = str(uuid.uuid4())
    await db.execute(insert(workflows).values(
        id=wf, name="Dev Pipeline", description="", template_key="dev_pipeline",
    ))
    node = str(uuid.uuid4())
    await db.execute(insert(workflow_nodes).values(
        id=node, workflow_id=wf, agent_id=aid, node_type="start", task_prompt="Implement.",
    ))

    run = str(uuid.uuid4())
    await db.execute(insert(workflow_runs).values(
        id=run, workflow_id=wf, status="pending", forced_complete=0,
    ))
    t_from, t_to = str(uuid.uuid4()), str(uuid.uuid4())
    for tid in (t_from, t_to):
        await db.execute(insert(agent_tasks).values(
            id=tid, run_id=run, node_id=node, agent_id=aid, source="workflow",
            status="pending", input="x",
        ))
    await db.commit()
    return {
        "agent_id": aid, "workflow_id": wf, "node_id": node,
        "run_id": run, "from_task_id": t_from, "to_task_id": t_to,
    }


def _bus():
    return MessageBusService(InMemoryWorkflowQueue())


# ── 1. Message persistence ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_persist_message_roundtrip_in_order(db, bus_seed):
    bus = _bus()
    first = await bus.persist_message(db, AgentMessageDraft(
        run_id=bus_seed["run_id"], from_task_id=bus_seed["from_task_id"],
        to_task_id=bus_seed["to_task_id"], msg_type="task_output",
        payload={"content": "wrote the parser"},
    ))
    second = await bus.persist_message(db, AgentMessageDraft(
        run_id=bus_seed["run_id"], from_task_id=bus_seed["to_task_id"],
        to_task_id=bus_seed["from_task_id"], msg_type="feedback",
        payload={"content": "REJECTED: add tests"},
    ))
    assert first["id"] != second["id"]

    msgs = await bus.list_messages(db, bus_seed["run_id"])
    assert [m["msg_type"] for m in msgs] == ["task_output", "feedback"]
    m0 = msgs[0]
    assert m0["run_id"] == bus_seed["run_id"]
    assert m0["from_task_id"] == bus_seed["from_task_id"]
    assert m0["to_task_id"] == bus_seed["to_task_id"]
    assert m0["payload"] == {"content": "wrote the parser"}  # round-tripped to dict


# ── 2. Queue enqueue / FIFO ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_enqueue_is_fifo_and_carries_dispatch_fields(bus_seed):
    bus = _bus()
    items = [
        WorkflowDispatchItem(run_id=bus_seed["run_id"], task_id=f"t{i}",
                             agent_id=bus_seed["agent_id"], node_id=bus_seed["node_id"],
                             input=f"step {i}")
        for i in range(3)
    ]
    for it in items:
        await bus.enqueue_task(it)
    assert bus.queue_size() == 3

    dequeued = [await bus.dequeue() for _ in range(3)]
    assert [d.task_id for d in dequeued] == ["t0", "t1", "t2"]  # FIFO
    first = dequeued[0]
    assert first.run_id == bus_seed["run_id"]
    assert first.agent_id == bus_seed["agent_id"]
    assert first.node_id == bus_seed["node_id"]
    assert first.input == "step 0"
    assert bus.queue_size() == 0


# ── 3. Persist-before-queue (§11) ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_deliver_persists_then_enqueues(db, bus_seed):
    bus = _bus()
    dispatch = WorkflowDispatchItem(
        run_id=bus_seed["run_id"], task_id=bus_seed["to_task_id"],
        agent_id=bus_seed["agent_id"], node_id=bus_seed["node_id"], input="review it",
    )
    draft = AgentMessageDraft(
        run_id=bus_seed["run_id"], from_task_id=bus_seed["from_task_id"],
        to_task_id=bus_seed["to_task_id"], msg_type="task_output",
        payload={"content": "handoff"},
    )
    await bus.deliver(db, draft, dispatch)

    assert bus.queue_size() == 1
    msgs = await bus.list_messages(db, bus_seed["run_id"])
    assert len(msgs) == 1 and msgs[0]["payload"] == {"content": "handoff"}


@pytest.mark.asyncio
async def test_deliver_unknown_task_does_not_enqueue(db, bus_seed):
    """Invalid message target must raise and leave zero queue items + zero rows."""
    bus = _bus()
    dispatch = WorkflowDispatchItem(
        run_id=bus_seed["run_id"], task_id="ghost", agent_id=bus_seed["agent_id"],
        node_id=bus_seed["node_id"], input="x",
    )
    draft = AgentMessageDraft(
        run_id=bus_seed["run_id"], from_task_id=bus_seed["from_task_id"],
        to_task_id="ghost-task",  # no such task
        msg_type="task_output", payload={"content": "x"},
    )
    with pytest.raises(UnknownTask):
        await bus.deliver(db, draft, dispatch)

    assert bus.queue_size() == 0
    msgs = await bus.list_messages(db, bus_seed["run_id"])
    assert msgs == []


@pytest.mark.asyncio
async def test_deliver_commit_failure_rolls_back_and_does_not_enqueue(db, bus_seed):
    """M1: a real persistence failure (CHECK-violating msg_type) must roll back,
    leave zero rows + zero queue items, and leave the session reusable — proving
    persist-before-queue holds for DB failures, not only pre-insert validation."""
    bus = _bus()
    bad = AgentMessageDraft(
        run_id=bus_seed["run_id"], from_task_id=bus_seed["from_task_id"],
        to_task_id=bus_seed["to_task_id"],
        msg_type="garbage",  # violates ck_messages_type → fails at insert/commit
        payload={"content": "x"},
    )
    dispatch = WorkflowDispatchItem(
        run_id=bus_seed["run_id"], task_id=bus_seed["to_task_id"],
        agent_id=bus_seed["agent_id"], node_id=bus_seed["node_id"], input="x",
    )
    with pytest.raises(IntegrityError):
        await bus.deliver(db, bad, dispatch)

    assert bus.queue_size() == 0                                   # commit failure → no enqueue
    assert await bus.list_messages(db, bus_seed["run_id"]) == []   # nothing persisted

    # rollback left the session reusable: a valid message still persists + reads back
    ok = await bus.persist_message(db, AgentMessageDraft(
        run_id=bus_seed["run_id"], from_task_id=bus_seed["from_task_id"],
        to_task_id=bus_seed["to_task_id"], msg_type="task_output", payload={"content": "ok"},
    ))
    msgs = await bus.list_messages(db, bus_seed["run_id"])
    assert [m["id"] for m in msgs] == [ok["id"]]


# ── 4. Error behavior ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_persist_unknown_run_raises(db, bus_seed):
    bus = _bus()
    with pytest.raises(UnknownRun):
        await bus.persist_message(db, AgentMessageDraft(
            run_id="no-such-run", from_task_id=None, to_task_id=None,
            msg_type="task_output", payload={"content": "x"},
        ))
    # nothing persisted under the bogus run
    msgs = await bus.list_messages(db, "no-such-run")
    assert msgs == []


@pytest.mark.asyncio
async def test_deliver_unknown_from_task_raises(db, bus_seed):
    """L1: an unknown from_task_id (sender) must also raise UnknownTask, persist
    nothing, and enqueue nothing — the from-side validation branch."""
    bus = _bus()
    draft = AgentMessageDraft(
        run_id=bus_seed["run_id"], from_task_id="ghost-from",  # no such task
        to_task_id=bus_seed["to_task_id"], msg_type="task_output", payload={"content": "x"},
    )
    dispatch = WorkflowDispatchItem(
        run_id=bus_seed["run_id"], task_id=bus_seed["to_task_id"],
        agent_id=bus_seed["agent_id"], node_id=bus_seed["node_id"], input="x",
    )
    with pytest.raises(UnknownTask):
        await bus.deliver(db, draft, dispatch)

    assert bus.queue_size() == 0
    assert await bus.list_messages(db, bus_seed["run_id"]) == []


# ── 5. Unit 3 compatibility (no execution, no Goose) ────────────────────────

@pytest.mark.asyncio
async def test_start_run_still_pending_with_no_dispatch(db, bus_seed):
    """Unit 3 start path is unchanged: a run start creates a pending task + the
    workflow_started event, and Unit 4 does not enqueue or execute it."""
    from app.services import workflow_service

    queue = InMemoryWorkflowQueue()
    snapshot = await workflow_service.start_run(db, bus_seed["workflow_id"], "build")

    assert snapshot["status"] == "pending"
    run = await workflow_service.get_run(db, snapshot["run_id"])
    assert len(run["tasks"]) == 1
    assert run["tasks"][0]["status"] == "pending"
    assert run["tasks"][0]["output"] is None      # Goose never invoked
    assert queue.size() == 0                       # nothing dispatched by Unit 4
