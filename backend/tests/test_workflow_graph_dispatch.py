"""S2 Unit 6 — workflow graph traversal and next-task dispatch tests.

TDD red phase: tests import advance_after_task_completion from
app.services.workflow_graph, which does not exist yet. Running this file
produces ImportError (the expected red failure). Implementation follows in
backend/app/services/workflow_graph.py plus modifications to workflow_worker.py
and workflow_service.py.

Coverage:
  G1  Linear dispatch: first task completes → second task created (pending),
      run stays running, message persisted, dispatch item enqueued,
      workflow_completed NOT emitted.
  G2  Terminal node: single-node workflow task completes → run completed,
      workflow_completed emitted, no second task, no extra dispatch item.
      (Preserves Unit 5 terminal behavior.)
  G3  Message handoff shape: correct run_id, from_task_id, to_task_id,
      msg_type=task_output, payload is a dict with expected keys.
  G4  Dispatch item shape: next queued item carries correct run_id, task_id,
      agent_id, node_id, input.
  G5  GET /runs/{run_id} message compatibility: messages array present,
      payload decoded as dict (not raw string), ordering deterministic.
  G6  Graph traversal failure after task completion: task stays completed,
      run fails, workflow_failed event persisted, no invalid dispatch item.
  G7  Unit 3 compat: start_run does not auto-execute (queue stays empty).
  G8  Unit 4 compat: message bus persist-before-queue tests unaffected.
  G9  Unit 5 compat: existing single-node worker tests unaffected.
      (Run as part of full suite; not re-tested individually here.)
  G10 edge_matches unit tests: always, case-insensitive substring, no match,
      None output.
"""
import json
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import insert, select, text

from app.adapters.base import TaskInput, TaskResult
from app.models import (
    agent_config, agent_messages, agent_tasks, agents,
    execution_events, workflow_edges, workflow_nodes, workflow_runs, workflows,
)
from app.services.message_bus import (
    InMemoryWorkflowQueue, MessageBusService, WorkflowDispatchItem,
)
from app.services.workflow_graph import advance_after_task_completion, edge_matches
from app.services.workflow_worker import WorkflowWorker

# ── Fakes ─────────────────────────────────────────────────────────────────────

FAKE_RESULT = TaskResult(
    output="Task A done.",
    tokens_input=5,
    tokens_output=10,
    tokens_total=15,
    estimated_cost=0.001,
    session_id="test-session-id",
)


class FakeAdapter:
    def __init__(self, host="127.0.0.1", port=3284):
        self.invoke_count = 0

    async def invoke(self, task: TaskInput, on_event) -> TaskResult:
        self.invoke_count += 1
        return FAKE_RESULT

    async def health_check(self) -> bool:
        return True


class FailingAdapter:
    def __init__(self, host="127.0.0.1", port=3284): pass

    async def invoke(self, task: TaskInput, on_event) -> TaskResult:
        raise RuntimeError("Goose exploded")

    async def health_check(self) -> bool:
        return False


# ── Factory helpers ───────────────────────────────────────────────────────────

def _make_bus():
    return MessageBusService(InMemoryWorkflowQueue())


def _make_worker(adapter_cls=FakeAdapter):
    return WorkflowWorker(_make_bus(), adapter_cls=adapter_cls)


# ── Two-node fixture ──────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def two_node(db):
    """Workflow with two nodes: start(always)→end. One pending task for node A.

    Returns ids needed by tests.
    """
    agent_a_id = str(uuid.uuid4())
    agent_b_id = str(uuid.uuid4())
    workflow_id = str(uuid.uuid4())
    node_a_id = str(uuid.uuid4())
    node_b_id = str(uuid.uuid4())
    edge_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    task_a_id = str(uuid.uuid4())

    for aid, name in [(agent_a_id, "AgentA"), (agent_b_id, "AgentB")]:
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
        id=workflow_id, name="Two Node Workflow", description="",
    ))
    await db.execute(insert(workflow_nodes).values(
        id=node_a_id, workflow_id=workflow_id, agent_id=agent_a_id,
        node_type="start", task_prompt="Do task A.", position_x=0, position_y=0,
    ))
    await db.execute(insert(workflow_nodes).values(
        id=node_b_id, workflow_id=workflow_id, agent_id=agent_b_id,
        node_type="end", task_prompt="Do task B.", position_x=100, position_y=0,
    ))
    await db.execute(insert(workflow_edges).values(
        id=edge_id, from_node_id=node_a_id, to_node_id=node_b_id, condition="always",
    ))
    await db.execute(insert(workflow_runs).values(
        id=run_id, workflow_id=workflow_id, status="pending",
        forced_complete=0, started_at="2026-01-01T00:00:00+00:00",
    ))
    await db.execute(insert(agent_tasks).values(
        id=task_a_id, run_id=run_id, node_id=node_a_id, agent_id=agent_a_id,
        source="workflow", status="pending", input="Do task A.",
    ))
    await db.commit()

    return {
        "agent_a_id": agent_a_id,
        "agent_b_id": agent_b_id,
        "workflow_id": workflow_id,
        "node_a_id": node_a_id,
        "node_b_id": node_b_id,
        "edge_id": edge_id,
        "run_id": run_id,
        "task_a_id": task_a_id,
    }


@pytest_asyncio.fixture
async def one_node(db):
    """Single-node workflow (no outgoing edges). Mirrors Unit 5 seed."""
    agent_id = str(uuid.uuid4())
    workflow_id = str(uuid.uuid4())
    node_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    task_id = str(uuid.uuid4())

    await db.execute(insert(agents).values(
        id=agent_id, name="SingleAgent", role="tester",
        system_prompt="You are a test agent.", model="claude-haiku-4-5-20251001",
        status="active",
    ))
    await db.execute(insert(agent_config).values(
        id=str(uuid.uuid4()), agent_id=agent_id,
        extensions='["developer"]', requires_approval=0,
        max_tokens_per_run=50000, max_runs_per_minute=6,
        blocked_extensions="[]", max_feedback_iterations=2,
        max_turns=5, timeout_seconds=60,
    ))
    await db.execute(insert(workflows).values(
        id=workflow_id, name="Single Node Workflow", description="",
    ))
    await db.execute(insert(workflow_nodes).values(
        id=node_id, workflow_id=workflow_id, agent_id=agent_id,
        node_type="start", task_prompt="Do task.", position_x=0, position_y=0,
    ))
    await db.execute(insert(workflow_runs).values(
        id=run_id, workflow_id=workflow_id, status="pending",
        forced_complete=0, started_at="2026-01-01T00:00:00+00:00",
    ))
    await db.execute(insert(agent_tasks).values(
        id=task_id, run_id=run_id, node_id=node_id, agent_id=agent_id,
        source="workflow", status="pending", input="Do task.",
    ))
    await db.commit()

    return {
        "agent_id": agent_id,
        "workflow_id": workflow_id,
        "node_id": node_id,
        "run_id": run_id,
        "task_id": task_id,
    }


# ── G10: edge_matches unit tests ──────────────────────────────────────────────

def test_edge_matches_always():
    assert edge_matches("always", None) is True
    assert edge_matches("always", "anything") is True
    assert edge_matches("ALWAYS", "x") is True


def test_edge_matches_substring_case_insensitive():
    assert edge_matches("approved", "The code is APPROVED.") is True
    assert edge_matches("APPROVED", "approved here") is True
    assert edge_matches("rejected", "All tests passed") is False


def test_edge_matches_none_output():
    assert edge_matches("always", None) is True
    assert edge_matches("keyword", None) is False


def test_edge_matches_sentinel_conditions_use_first_line_only():
    """KTD6: COMPLIANCE= conditions must not match sentinels echoed in the body."""
    output = "COMPLIANCE=FLAGGED\nCountry COMPLIANCE=CLEARED is restricted."
    assert edge_matches("COMPLIANCE=CLEARED", output) is False
    assert edge_matches("COMPLIANCE=FLAGGED", output) is True
    cleared = "COMPLIANCE=CLEARED\nNotes only."
    assert edge_matches("COMPLIANCE=CLEARED", cleared) is True


# ── G1: Linear graph dispatch ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_linear_dispatch_creates_second_task(db, two_node):
    """After node A completes, a second task for node B must be created pending."""
    worker = _make_worker()
    item = WorkflowDispatchItem(
        run_id=two_node["run_id"],
        task_id=two_node["task_a_id"],
        agent_id=two_node["agent_a_id"],
        node_id=two_node["node_a_id"],
        input="Do task A.",
    )
    await worker.process_dispatch_item(db, item)

    tasks = (await db.execute(
        select(agent_tasks).where(agent_tasks.c.run_id == two_node["run_id"])
        .order_by(text("rowid"))
    )).mappings().all()

    assert len(tasks) == 2, "should have task A + task B"
    task_a = tasks[0]
    task_b = tasks[1]

    assert task_a["id"] == two_node["task_a_id"]
    assert task_a["status"] == "completed"
    assert task_b["node_id"] == two_node["node_b_id"]
    assert task_b["agent_id"] == two_node["agent_b_id"]
    assert task_b["status"] == "pending"
    assert task_b["source"] == "workflow"


@pytest.mark.asyncio
async def test_linear_dispatch_run_stays_running(db, two_node):
    """Run must remain 'running' (not 'completed') when a next task exists."""
    worker = _make_worker()
    item = WorkflowDispatchItem(
        run_id=two_node["run_id"],
        task_id=two_node["task_a_id"],
        agent_id=two_node["agent_a_id"],
        node_id=two_node["node_a_id"],
        input="Do task A.",
    )
    await worker.process_dispatch_item(db, item)

    run_status = (await db.execute(
        select(workflow_runs.c.status).where(workflow_runs.c.id == two_node["run_id"])
    )).scalar_one()

    assert run_status == "running"


@pytest.mark.asyncio
async def test_linear_dispatch_no_workflow_completed_event(db, two_node):
    """workflow_completed must NOT be emitted when there is a next task."""
    worker = _make_worker()
    item = WorkflowDispatchItem(
        run_id=two_node["run_id"],
        task_id=two_node["task_a_id"],
        agent_id=two_node["agent_a_id"],
        node_id=two_node["node_a_id"],
        input="Do task A.",
    )
    await worker.process_dispatch_item(db, item)

    event_types = [r["event_type"] for r in (await db.execute(
        select(execution_events.c.event_type)
        .where(execution_events.c.run_id == two_node["run_id"])
        .order_by(text("rowid"))
    )).mappings().all()]

    assert "task_started" in event_types
    assert "task_completed" in event_types
    assert "workflow_completed" not in event_types


@pytest.mark.asyncio
async def test_linear_dispatch_enqueues_next_item(db, two_node):
    """A dispatch item for node B must be enqueued after node A completes."""
    bus = _make_bus()
    worker = WorkflowWorker(bus, adapter_cls=FakeAdapter)
    item = WorkflowDispatchItem(
        run_id=two_node["run_id"],
        task_id=two_node["task_a_id"],
        agent_id=two_node["agent_a_id"],
        node_id=two_node["node_a_id"],
        input="Do task A.",
    )
    await worker.process_dispatch_item(db, item)

    assert bus.queue_size() == 1
    next_item = bus.try_dequeue()
    assert next_item is not None
    assert next_item.run_id == two_node["run_id"]
    assert next_item.node_id == two_node["node_b_id"]
    assert next_item.agent_id == two_node["agent_b_id"]
    assert bus.queue_size() == 0


# ── G2: Terminal node preserves Unit 5 behavior ───────────────────────────────

@pytest.mark.asyncio
async def test_terminal_node_completes_run(db, one_node):
    """Single-node workflow: run must be completed and workflow_completed emitted."""
    worker = _make_worker()
    item = WorkflowDispatchItem(
        run_id=one_node["run_id"],
        task_id=one_node["task_id"],
        agent_id=one_node["agent_id"],
        node_id=one_node["node_id"],
        input="Do task.",
    )
    await worker.process_dispatch_item(db, item)

    run_status = (await db.execute(
        select(workflow_runs.c.status).where(workflow_runs.c.id == one_node["run_id"])
    )).scalar_one()
    assert run_status == "completed"

    event_types = [r["event_type"] for r in (await db.execute(
        select(execution_events.c.event_type)
        .where(execution_events.c.run_id == one_node["run_id"])
        .order_by(text("rowid"))
    )).mappings().all()]
    assert "workflow_completed" in event_types


@pytest.mark.asyncio
async def test_terminal_node_creates_no_second_task(db, one_node):
    """Single-node workflow: no second task should be created."""
    worker = _make_worker()
    item = WorkflowDispatchItem(
        run_id=one_node["run_id"],
        task_id=one_node["task_id"],
        agent_id=one_node["agent_id"],
        node_id=one_node["node_id"],
        input="Do task.",
    )
    await worker.process_dispatch_item(db, item)

    tasks = (await db.execute(
        select(agent_tasks).where(agent_tasks.c.run_id == one_node["run_id"])
    )).mappings().all()
    assert len(tasks) == 1
    assert tasks[0]["status"] == "completed"


@pytest.mark.asyncio
async def test_terminal_node_does_not_enqueue(db, one_node):
    """Single-node workflow: the queue must remain empty after completion."""
    bus = _make_bus()
    worker = WorkflowWorker(bus, adapter_cls=FakeAdapter)
    item = WorkflowDispatchItem(
        run_id=one_node["run_id"],
        task_id=one_node["task_id"],
        agent_id=one_node["agent_id"],
        node_id=one_node["node_id"],
        input="Do task.",
    )
    await worker.process_dispatch_item(db, item)
    assert bus.queue_size() == 0


# ── G3: Message handoff shape ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_message_handoff_shape(db, two_node):
    """Persisted agent_message must have correct ids, msg_type, and payload."""
    worker = _make_worker()
    item = WorkflowDispatchItem(
        run_id=two_node["run_id"],
        task_id=two_node["task_a_id"],
        agent_id=two_node["agent_a_id"],
        node_id=two_node["node_a_id"],
        input="Do task A.",
    )
    await worker.process_dispatch_item(db, item)

    msgs = (await db.execute(
        select(agent_messages).where(agent_messages.c.run_id == two_node["run_id"])
    )).mappings().all()
    assert len(msgs) == 1, "exactly one handoff message"
    msg = dict(msgs[0])

    assert msg["run_id"] == two_node["run_id"]
    assert msg["from_task_id"] == two_node["task_a_id"]
    assert msg["msg_type"] == "task_output"

    # to_task_id must reference the newly created task B
    tasks = (await db.execute(
        select(agent_tasks).where(agent_tasks.c.run_id == two_node["run_id"])
        .order_by(text("rowid"))
    )).mappings().all()
    task_b_id = tasks[1]["id"]
    assert msg["to_task_id"] == task_b_id

    # payload must be a JSON-encoded dict with 'content' key
    payload = json.loads(msg["payload"])
    assert isinstance(payload, dict)
    assert "content" in payload


# ── G4: Dispatch item shape ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dispatch_item_shape(db, two_node):
    """Next queued WorkflowDispatchItem must carry the correct run/task/agent/node ids."""
    bus = _make_bus()
    worker = WorkflowWorker(bus, adapter_cls=FakeAdapter)
    item = WorkflowDispatchItem(
        run_id=two_node["run_id"],
        task_id=two_node["task_a_id"],
        agent_id=two_node["agent_a_id"],
        node_id=two_node["node_a_id"],
        input="Do task A.",
    )
    await worker.process_dispatch_item(db, item)

    next_item = bus.try_dequeue()
    assert next_item is not None
    assert next_item.run_id == two_node["run_id"]
    assert next_item.node_id == two_node["node_b_id"]
    assert next_item.agent_id == two_node["agent_b_id"]
    assert isinstance(next_item.input, str) and len(next_item.input) > 0

    # task_id must reference the newly created task B
    tasks = (await db.execute(
        select(agent_tasks).where(agent_tasks.c.run_id == two_node["run_id"])
        .order_by(text("rowid"))
    )).mappings().all()
    task_b_id = tasks[1]["id"]
    assert next_item.task_id == task_b_id


# ── G5: GET /runs/{run_id} message compatibility ──────────────────────────────

@pytest.mark.asyncio
async def test_get_run_messages_payload_decoded(client, db, two_node):
    """GET /runs/{run_id} must return messages with payload as dict, not raw string."""
    worker = WorkflowWorker(_make_bus(), adapter_cls=FakeAdapter)
    item = WorkflowDispatchItem(
        run_id=two_node["run_id"],
        task_id=two_node["task_a_id"],
        agent_id=two_node["agent_a_id"],
        node_id=two_node["node_a_id"],
        input="Do task A.",
    )
    await worker.process_dispatch_item(db, item)

    r = await client.get(f"/runs/{two_node['run_id']}")
    assert r.status_code == 200, r.text
    snap = r.json()

    assert isinstance(snap["messages"], list)
    assert len(snap["messages"]) == 1
    msg = snap["messages"][0]
    assert isinstance(msg["payload"], dict), (
        f"payload must be a dict, got {type(msg['payload'])!r}: {msg['payload']!r}"
    )
    assert "content" in msg["payload"]


@pytest.mark.asyncio
async def test_get_run_messages_ordering_deterministic(client, db, two_node):
    """Multiple messages must be returned in deterministic insertion order."""
    # Seed two messages manually (same created_at to stress rowid tiebreak)
    from app.services.message_bus import AgentMessageDraft
    bus = _make_bus()
    tasks = (await db.execute(
        select(agent_tasks).where(agent_tasks.c.run_id == two_node["run_id"])
        .order_by(text("rowid"))
    )).mappings().all()
    task_a_id = tasks[0]["id"]

    # create a dummy second task to be to_task_id
    dummy_task_id = str(uuid.uuid4())
    await db.execute(insert(agent_tasks).values(
        id=dummy_task_id, run_id=two_node["run_id"], node_id=two_node["node_b_id"],
        agent_id=two_node["agent_b_id"], source="workflow", status="pending", input="x",
    ))
    await db.commit()

    for i in range(3):
        await bus.persist_message(db, AgentMessageDraft(
            run_id=two_node["run_id"],
            from_task_id=task_a_id,
            to_task_id=dummy_task_id,
            msg_type="task_output",
            payload={"content": f"msg {i}", "chat_id": None, "agent_id": None},
        ))

    r = await client.get(f"/runs/{two_node['run_id']}")
    assert r.status_code == 200
    msgs = r.json()["messages"]
    assert len(msgs) == 3
    for m in msgs:
        assert isinstance(m["payload"], dict)


# ── G6: Graph traversal failure after task completion ─────────────────────────

@pytest.mark.asyncio
async def test_graph_failure_task_stays_completed(db, two_node):
    """If graph traversal fails (e.g. missing next node), task must stay completed."""
    # Delete node B so advance_after_task_completion raises on lookup
    await db.execute(workflow_nodes.delete().where(workflow_nodes.c.id == two_node["node_b_id"]))
    await db.commit()

    worker = _make_worker()
    item = WorkflowDispatchItem(
        run_id=two_node["run_id"],
        task_id=two_node["task_a_id"],
        agent_id=two_node["agent_a_id"],
        node_id=two_node["node_a_id"],
        input="Do task A.",
    )
    await worker.process_dispatch_item(db, item)

    task_status = (await db.execute(
        select(agent_tasks.c.status).where(agent_tasks.c.id == two_node["task_a_id"])
    )).scalar_one()
    assert task_status == "completed"


@pytest.mark.asyncio
async def test_graph_failure_run_fails(db, two_node):
    """If graph traversal fails, the run must be marked failed (not stuck running)."""
    await db.execute(workflow_nodes.delete().where(workflow_nodes.c.id == two_node["node_b_id"]))
    await db.commit()

    worker = _make_worker()
    item = WorkflowDispatchItem(
        run_id=two_node["run_id"],
        task_id=two_node["task_a_id"],
        agent_id=two_node["agent_a_id"],
        node_id=two_node["node_a_id"],
        input="Do task A.",
    )
    await worker.process_dispatch_item(db, item)

    run_status = (await db.execute(
        select(workflow_runs.c.status).where(workflow_runs.c.id == two_node["run_id"])
    )).scalar_one()
    assert run_status == "failed"


@pytest.mark.asyncio
async def test_graph_failure_emits_workflow_failed(db, two_node):
    """If graph traversal fails, a workflow_failed event must be persisted."""
    await db.execute(workflow_nodes.delete().where(workflow_nodes.c.id == two_node["node_b_id"]))
    await db.commit()

    worker = _make_worker()
    item = WorkflowDispatchItem(
        run_id=two_node["run_id"],
        task_id=two_node["task_a_id"],
        agent_id=two_node["agent_a_id"],
        node_id=two_node["node_a_id"],
        input="Do task A.",
    )
    await worker.process_dispatch_item(db, item)

    event_types = [r["event_type"] for r in (await db.execute(
        select(execution_events.c.event_type)
        .where(execution_events.c.run_id == two_node["run_id"])
        .order_by(text("rowid"))
    )).mappings().all()]
    assert "workflow_failed" in event_types


@pytest.mark.asyncio
async def test_graph_failure_no_invalid_dispatch_item(db, two_node):
    """If graph traversal fails, no invalid dispatch item must be enqueued."""
    await db.execute(workflow_nodes.delete().where(workflow_nodes.c.id == two_node["node_b_id"]))
    await db.commit()

    bus = _make_bus()
    worker = WorkflowWorker(bus, adapter_cls=FakeAdapter)
    item = WorkflowDispatchItem(
        run_id=two_node["run_id"],
        task_id=two_node["task_a_id"],
        agent_id=two_node["agent_a_id"],
        node_id=two_node["node_a_id"],
        input="Do task A.",
    )
    await worker.process_dispatch_item(db, item)
    assert bus.queue_size() == 0


# ── G7: Unit 3 compat — start_run does NOT auto-execute ──────────────────────

@pytest.mark.asyncio
async def test_start_run_does_not_auto_execute_two_node(client, db, two_node):
    """POST /workflows/{id}/runs must NOT execute tasks or drain the queue.
    The first task must remain pending; no second task is created."""
    resp = await client.post(
        f"/workflows/{two_node['workflow_id']}/runs",
        json={"input": "Another run"},
    )
    assert resp.status_code == 201
    new_run_id = resp.json()["run_id"]

    tasks = (await db.execute(
        select(agent_tasks).where(agent_tasks.c.run_id == new_run_id)
    )).mappings().all()
    assert len(tasks) == 1
    assert tasks[0]["status"] == "pending"


# ── G8: Unit 4 compat — message bus persist-before-queue ─────────────────────

@pytest.mark.asyncio
async def test_bus_persist_before_enqueue_still_guaranteed(db, two_node):
    """MessageBusService.deliver must persist before enqueuing (Unit 4 contract).
    Verifies that the bus behavior is unchanged by Unit 6 additions."""
    from app.services.message_bus import AgentMessageDraft

    bus = _make_bus()
    tasks = (await db.execute(
        select(agent_tasks).where(agent_tasks.c.run_id == two_node["run_id"])
        .order_by(text("rowid"))
    )).mappings().all()
    from_task_id = tasks[0]["id"]

    dummy_task_id = str(uuid.uuid4())
    await db.execute(insert(agent_tasks).values(
        id=dummy_task_id, run_id=two_node["run_id"], node_id=two_node["node_b_id"],
        agent_id=two_node["agent_b_id"], source="workflow", status="pending", input="x",
    ))
    await db.commit()

    draft = AgentMessageDraft(
        run_id=two_node["run_id"],
        from_task_id=from_task_id,
        to_task_id=dummy_task_id,
        msg_type="task_output",
        payload={"content": "hello", "chat_id": None, "agent_id": None},
    )
    dispatch = WorkflowDispatchItem(
        run_id=two_node["run_id"],
        task_id=dummy_task_id,
        agent_id=two_node["agent_b_id"],
        node_id=two_node["node_b_id"],
        input="x",
    )
    msg = await bus.deliver(db, draft, dispatch)
    assert msg["run_id"] == two_node["run_id"]
    assert bus.queue_size() == 1
