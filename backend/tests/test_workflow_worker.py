"""S2 Unit 5 — workflow worker tests.

TDD red phase: all tests import WorkflowWorker from app.services.workflow_worker,
which does not exist yet. Running this file produces ImportError (the expected
red failure). Implementation follows in backend/app/services/workflow_worker.py.

Coverage:
  W1  try_dequeue returns None when queue is empty
  W2  try_dequeue returns item when one is present
  W3  process_next returns False when queue is empty
  W4  process_next returns True and decrements queue
  W5  success path: task transitions pending→running→completed
  W6  success path: run transitions pending→running→completed
  W7  success path: task_started + task_completed + workflow_completed events
  W8  adapter is invoked exactly once with a TaskInput
  W9  failure path: task=failed, run=failed
  W10 failure path: task_failed + workflow_failed events emitted
  W11 failure path: db session remains usable after failure
  W12 Unit 9: start_run enqueues first task (worker loop disabled in tests)
  W13 Unit 4 compat: MessageBusService tests are unaffected (bus unused here)
  W14 Compliance agent routes through scripted ComplianceAdapter (U6)
  W15 Analyst agent routes through scripted AnalystAdapter
"""
import asyncio
import json
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy import delete, insert, select, text

from app.adapters.base import TaskInput, TaskResult
from app.domain.remittance.analyst import compose_analyst_task_input
from app.domain.remittance.compliance import format_output, screen_from_dict
from app.domain.remittance.research import assemble_brief
from app.models import agent_config, agents, agent_tasks, execution_events, workflow_nodes, workflow_runs, workflows
from app.services.message_bus import (
    InMemoryWorkflowQueue,
    MessageBusService,
    WorkflowDispatchItem,
)
from app.services.workflow_worker import WorkflowWorker

# ── Fakes ────────────────────────────────────────────────────────────────────

FAKE_RESULT = TaskResult(
    output="All done.",
    tokens_input=5,
    tokens_output=10,
    tokens_total=15,
    estimated_cost=0.001,
    session_id="test-session-id",
)


class FakeAdapter:
    """Stand-in for AcpGooseAdapter — returns FAKE_RESULT immediately.

    Tracks invoke_count so tests can prove the adapter is invoked exactly once.
    """
    def __init__(self, host="127.0.0.1", port=3284):
        self.invoked_with: TaskInput | None = None
        self.invoke_count = 0

    async def invoke(self, task: TaskInput, on_event) -> TaskResult:
        self.invoke_count += 1
        self.invoked_with = task
        return FAKE_RESULT

    async def health_check(self) -> bool:
        return True


class FailingAdapter:
    """Simulates an adapter that always raises."""
    def __init__(self, host="127.0.0.1", port=3284): pass

    async def invoke(self, task: TaskInput, on_event) -> TaskResult:
        raise RuntimeError("Goose exploded")

    async def health_check(self) -> bool:
        return False


class HangingAdapter:
    """Sleeps far longer than any test timeout — proves worker-level wait_for."""
    def __init__(self, host="127.0.0.1", port=3284): pass

    async def invoke(self, task: TaskInput, on_event) -> TaskResult:
        await asyncio.sleep(30)
        return FAKE_RESULT  # pragma: no cover — never reached under timeout

    async def health_check(self) -> bool:
        return True


# ── Shared factory helpers ────────────────────────────────────────────────────

def _make_item(seed: dict) -> WorkflowDispatchItem:
    return WorkflowDispatchItem(
        run_id=seed["run_id"],
        task_id=seed["task_id"],
        agent_id=seed["agent_id"],
        node_id=seed["node_id"],
        input="Do the test.",
    )


def _make_worker(adapter_cls=FakeAdapter) -> WorkflowWorker:
    bus = MessageBusService(InMemoryWorkflowQueue())
    return WorkflowWorker(bus, adapter_cls=adapter_cls)


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def seed(db):
    """One agent, workflow, run, and pending task — mirrors what start_run creates."""
    agent_id = str(uuid.uuid4())
    workflow_id = str(uuid.uuid4())
    node_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    task_id = str(uuid.uuid4())

    await db.execute(insert(agents).values(
        id=agent_id, name="WorkerTestAgent", role="tester",
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
        id=workflow_id, name="Test Workflow", description="",
    ))
    await db.execute(insert(workflow_nodes).values(
        id=node_id, workflow_id=workflow_id, agent_id=agent_id,
        node_type="start", task_prompt="Do the test.",
        position_x=0, position_y=0,
    ))
    await db.execute(insert(workflow_runs).values(
        id=run_id, workflow_id=workflow_id, status="pending",
        forced_complete=0, started_at="2026-01-01T00:00:00+00:00",
    ))
    await db.execute(insert(agent_tasks).values(
        id=task_id, run_id=run_id, node_id=node_id, agent_id=agent_id,
        source="workflow", status="pending", input="Do the test.",
    ))
    await db.commit()

    return {
        "agent_id": agent_id,
        "workflow_id": workflow_id,
        "node_id": node_id,
        "run_id": run_id,
        "task_id": task_id,
    }


_COMPLIANCE_MEMORY = {
    "sender_city": "Austin, TX",
    "sender_country": "US",
    "recipient_country": "Colombia",
    "recipient_city": "Bogotá",
    "send_currency": "USD",
    "receive_currency": "COP",
}
_COMPLIANCE_FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "transfer_fixture.json"


def _compliance_brief_json() -> str:
    brief = assemble_brief(
        "send $500 cash to Bogotá",
        memory_defaults=_COMPLIANCE_MEMORY,
        fixture_path=_COMPLIANCE_FIXTURE,
    )
    return json.dumps(brief.to_dict())


@pytest_asyncio.fixture
async def compliance_seed(db):
    """Compliance agent on a terminal node — for U6 scripted-adapter routing."""
    agent_id = str(uuid.uuid4())
    workflow_id = str(uuid.uuid4())
    node_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    task_id = str(uuid.uuid4())
    brief_json = _compliance_brief_json()

    await db.execute(insert(agents).values(
        id=agent_id, name="Compliance", role="compliance",
        system_prompt="Deterministic compliance screening.", model="claude-haiku-4-5-20251001",
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
        id=workflow_id, name="Compliance Worker Test", description="",
    ))
    await db.execute(insert(workflow_nodes).values(
        id=node_id, workflow_id=workflow_id, agent_id=agent_id,
        node_type="end", task_prompt="Screen the transfer brief.",
        position_x=0, position_y=0,
    ))
    await db.execute(insert(workflow_runs).values(
        id=run_id, workflow_id=workflow_id, status="pending",
        forced_complete=0, started_at="2026-01-01T00:00:00+00:00",
    ))
    await db.execute(insert(agent_tasks).values(
        id=task_id, run_id=run_id, node_id=node_id, agent_id=agent_id,
        source="workflow", status="pending", input=brief_json,
    ))
    await db.commit()

    return {
        "agent_id": agent_id,
        "workflow_id": workflow_id,
        "node_id": node_id,
        "run_id": run_id,
        "task_id": task_id,
        "brief_json": brief_json,
    }


# ── W1: try_dequeue returns None when empty ───────────────────────────────────

@pytest.mark.asyncio
async def test_try_dequeue_returns_none_when_empty():
    q = InMemoryWorkflowQueue()
    assert q.try_dequeue() is None


# ── W2: try_dequeue returns item when present ─────────────────────────────────

@pytest.mark.asyncio
async def test_try_dequeue_returns_item_when_present():
    q = InMemoryWorkflowQueue()
    item = WorkflowDispatchItem(
        run_id="r1", task_id="t1", agent_id="a1", node_id="n1", input="x"
    )
    await q.enqueue(item)
    result = q.try_dequeue()
    assert result is item
    assert q.size() == 0


# ── W3: process_next returns False when queue is empty ────────────────────────

@pytest.mark.asyncio
async def test_process_next_returns_false_when_empty(db, seed):
    worker = _make_worker()
    did_work = await worker.process_next(db)
    assert did_work is False


# ── W4: process_next returns True and drains one item ────────────────────────

@pytest.mark.asyncio
async def test_process_next_returns_true_and_processes(db, seed):
    worker = _make_worker()
    item = _make_item(seed)
    await worker.bus.enqueue_task(item)

    assert worker.bus.queue_size() == 1
    did_work = await worker.process_next(db)
    assert did_work is True
    assert worker.bus.queue_size() == 0


# ── W5: task transitions pending→running→completed ───────────────────────────

@pytest.mark.asyncio
async def test_success_task_status_completed(db, seed):
    worker = _make_worker()
    await worker.process_dispatch_item(db, _make_item(seed))

    row = (await db.execute(
        select(agent_tasks.c.status, agent_tasks.c.output)
        .where(agent_tasks.c.id == seed["task_id"])
    )).mappings().one()

    assert row["status"] == "completed"
    assert row["output"] == FAKE_RESULT.output


# ── W6: run transitions pending→running→completed ────────────────────────────

@pytest.mark.asyncio
async def test_success_run_status_completed(db, seed):
    worker = _make_worker()
    await worker.process_dispatch_item(db, _make_item(seed))

    row = (await db.execute(
        select(workflow_runs.c.status)
        .where(workflow_runs.c.id == seed["run_id"])
    )).mappings().one()

    assert row["status"] == "completed"


# ── W7: task_started + task_completed + workflow_completed events ─────────────

@pytest.mark.asyncio
async def test_success_events_persisted(db, seed):
    worker = _make_worker()
    await worker.process_dispatch_item(db, _make_item(seed))

    # rowid is SQLite insertion order — the deterministic-replay ordering the
    # spec calls for. (execution_events.id is a random UUID, so ordering by it
    # would be meaningless.)
    rows = (await db.execute(
        select(execution_events.c.event_type, execution_events.c.data)
        .where(execution_events.c.run_id == seed["run_id"])
        .order_by(text("rowid"))
    )).mappings().all()

    types = [r["event_type"] for r in rows]
    assert "task_started" in types
    assert "task_completed" in types
    assert "workflow_completed" in types

    # Explicit sequence: started → completed → workflow_completed
    assert types.index("task_started") < types.index("task_completed")
    assert types.index("task_completed") < types.index("workflow_completed")

    # Payloads carry the correct ids
    for r in rows:
        if r["event_type"] in ("task_started", "task_completed"):
            data = json.loads(r["data"])
            assert data["run_id"] == seed["run_id"]
            assert data["task_id"] == seed["task_id"]


# ── W8: adapter invoked exactly once with correct TaskInput ──────────────────

@pytest.mark.asyncio
async def test_adapter_invoked_exactly_once_with_task_input(db, seed):
    fake = FakeAdapter()
    # adapter_cls is a factory returning the SAME fake so we can inspect it.
    worker = WorkflowWorker(
        MessageBusService(InMemoryWorkflowQueue()),
        adapter_cls=lambda **_: fake,
    )
    await worker.process_dispatch_item(db, _make_item(seed))

    assert fake.invoke_count == 1
    assert isinstance(fake.invoked_with, TaskInput)
    assert fake.invoked_with.task_content == "Do the test."


# ── W9: failure path — task=failed, run=failed ───────────────────────────────

@pytest.mark.asyncio
async def test_failure_task_and_run_failed(db, seed):
    worker = _make_worker(adapter_cls=FailingAdapter)
    await worker.process_dispatch_item(db, _make_item(seed))

    task_row = (await db.execute(
        select(agent_tasks.c.status).where(agent_tasks.c.id == seed["task_id"])
    )).mappings().one()
    run_row = (await db.execute(
        select(workflow_runs.c.status).where(workflow_runs.c.id == seed["run_id"])
    )).mappings().one()

    assert task_row["status"] == "failed"
    assert run_row["status"] == "failed"


# ── W10: failure path — task_failed + workflow_failed events ─────────────────

@pytest.mark.asyncio
async def test_failure_events_persisted(db, seed):
    worker = _make_worker(adapter_cls=FailingAdapter)
    await worker.process_dispatch_item(db, _make_item(seed))

    rows = (await db.execute(
        select(execution_events.c.event_type)
        .where(execution_events.c.run_id == seed["run_id"])
        .order_by(text("rowid"))
    )).mappings().all()

    types = [r["event_type"] for r in rows]
    assert "task_started" in types
    assert "task_failed" in types
    assert "workflow_failed" in types

    # Explicit sequence: started → failed → workflow_failed
    assert types.index("task_started") < types.index("task_failed")
    assert types.index("task_failed") < types.index("workflow_failed")


# ── W11: db session is reusable after failure ─────────────────────────────────

@pytest.mark.asyncio
async def test_failure_session_remains_usable(db, seed):
    worker = _make_worker(adapter_cls=FailingAdapter)
    await worker.process_dispatch_item(db, _make_item(seed))

    # Session must still be usable — we should be able to read without error.
    row = (await db.execute(
        select(workflow_runs.c.status).where(workflow_runs.c.id == seed["run_id"])
    )).mappings().one()
    assert row["status"] == "failed"


# ── W12: Unit 9 — start_run enqueues but does not execute without worker ─────

@pytest.mark.asyncio
async def test_start_run_enqueues_without_executing(client, db, seed):
    """POST /workflows/{id}/runs enqueues the first dispatch item. With the
    worker loop disabled in tests, the task stays pending."""
    from app.services.message_bus import get_message_bus

    resp = await client.post(
        f"/workflows/{seed['workflow_id']}/runs",
        json={"input": "Hello from compat test"},
    )
    assert resp.status_code == 201

    new_run_id = resp.json()["run_id"]
    task_row = (await db.execute(
        select(agent_tasks.c.status).where(agent_tasks.c.run_id == new_run_id)
    )).mappings().one()
    assert task_row["status"] == "pending"
    assert get_message_bus().queue_size() == 1


# ── W13: Unit 4 compat — bus persists messages independently ──────────────────

@pytest.mark.asyncio
async def test_bus_persist_message_still_works(db, seed):
    """MessageBusService.persist_message must still commit agent_messages rows
    without interference from the worker. The bus and worker are independent."""
    from app.services.message_bus import AgentMessageDraft

    bus = MessageBusService(InMemoryWorkflowQueue())
    draft = AgentMessageDraft(
        run_id=seed["run_id"],
        from_task_id=seed["task_id"],
        to_task_id=None,
        msg_type="task_output",
        payload={"text": "hello"},
    )
    msg = await bus.persist_message(db, draft)
    assert msg["run_id"] == seed["run_id"]
    assert bus.queue_size() == 0  # persist_message does not enqueue


# ── B1: agent deleted before pickup → failed, not stuck running ──────────────

@pytest.mark.asyncio
async def test_missing_agent_fails_task_and_run(db, seed):
    """If the agent is deleted between start_run and worker pickup, context
    assembly raises. The failure must route through the failure handler:
    task=failed, run=failed, task_failed + workflow_failed events, nothing
    left in 'running'. (Regression guard for review finding B1.)"""
    # Delete the agent (and its config) before processing.
    await db.execute(delete(agent_config).where(agent_config.c.agent_id == seed["agent_id"]))
    await db.execute(delete(agents).where(agents.c.id == seed["agent_id"]))
    await db.commit()

    worker = _make_worker()  # FakeAdapter — but we never reach it
    await worker.process_dispatch_item(db, _make_item(seed))

    task_status = (await db.execute(
        select(agent_tasks.c.status).where(agent_tasks.c.id == seed["task_id"])
    )).scalar_one()
    run_status = (await db.execute(
        select(workflow_runs.c.status).where(workflow_runs.c.id == seed["run_id"])
    )).scalar_one()

    assert task_status == "failed"
    assert run_status == "failed"
    # Nothing left running
    assert task_status != "running"
    assert run_status != "running"

    types = [r["event_type"] for r in (await db.execute(
        select(execution_events.c.event_type)
        .where(execution_events.c.run_id == seed["run_id"])
        .order_by(text("rowid"))
    )).mappings().all()]
    assert "task_started" in types
    assert "task_failed" in types
    assert "workflow_failed" in types


# ── B2: worker-level timeout (asyncio.wait_for) ──────────────────────────────

@pytest.mark.asyncio
async def test_adapter_timeout_fails_without_hanging(db, seed):
    """A hanging adapter must be bounded by asyncio.wait_for(timeout_seconds);
    the task and run fail and the worker returns promptly instead of hanging.
    (Regression guard for review finding B2.)"""
    # Drive the worker's timeout to 0 via the agent's config.
    await db.execute(
        agent_config.update()
        .where(agent_config.c.agent_id == seed["agent_id"])
        .values(timeout_seconds=0)
    )
    await db.commit()

    worker = _make_worker(adapter_cls=HangingAdapter)

    # The whole call must finish well under the adapter's 30s sleep.
    await asyncio.wait_for(
        worker.process_dispatch_item(db, _make_item(seed)),
        timeout=5,
    )

    task_status = (await db.execute(
        select(agent_tasks.c.status).where(agent_tasks.c.id == seed["task_id"])
    )).scalar_one()
    run_status = (await db.execute(
        select(workflow_runs.c.status).where(workflow_runs.c.id == seed["run_id"])
    )).scalar_one()
    assert task_status == "failed"
    assert run_status == "failed"

    types = [r["event_type"] for r in (await db.execute(
        select(execution_events.c.event_type).where(execution_events.c.run_id == seed["run_id"])
    )).mappings().all()]
    assert "workflow_failed" in types


# ── B3: failure-handler write failure is surfaced, not swallowed ─────────────

@pytest.mark.asyncio
async def test_failure_handler_write_failure_is_surfaced(db, seed, caplog):
    """If the failure-recording write itself fails, the worker must not swallow
    the error silently: it logs that the row may be stuck in 'running' and
    re-raises. (Regression guard for review finding B3.)"""
    import logging

    class _BoomSession:
        async def __aenter__(self): raise RuntimeError("fail_db unavailable")
        async def __aexit__(self, *a): return False

    worker = _make_worker(adapter_cls=FailingAdapter)

    with patch("app.services.workflow_worker.AsyncSessionLocal", lambda: _BoomSession()):
        with caplog.at_level(logging.ERROR):
            with pytest.raises(Exception):
                await worker.process_dispatch_item(db, _make_item(seed))

    assert any("may be stuck in 'running'" in r.message for r in caplog.records)


# ── W14: Compliance agent uses scripted adapter (U6) ─────────────────────────

@pytest.mark.asyncio
async def test_compliance_agent_uses_scripted_adapter(db, compliance_seed):
    """Compliance node must invoke ComplianceAdapter, not the injected FakeAdapter."""
    fake = FakeAdapter()
    worker = WorkflowWorker(
        MessageBusService(InMemoryWorkflowQueue()),
        adapter_cls=lambda **_: fake,
    )
    item = WorkflowDispatchItem(
        run_id=compliance_seed["run_id"],
        task_id=compliance_seed["task_id"],
        agent_id=compliance_seed["agent_id"],
        node_id=compliance_seed["node_id"],
        input=compliance_seed["brief_json"],
    )

    await worker.process_dispatch_item(db, item)

    assert fake.invoke_count == 0
    task = (
        await db.execute(select(agent_tasks).where(agent_tasks.c.id == compliance_seed["task_id"]))
    ).mappings().one()
    assert task["status"] == "completed"
    assert task["output"].startswith("COMPLIANCE=CLEARED")
    run = (
        await db.execute(select(workflow_runs).where(workflow_runs.c.id == compliance_seed["run_id"]))
    ).mappings().one()
    assert run["status"] == "completed"


@pytest_asyncio.fixture
async def analyst_seed(db):
    """Analyst agent on a terminal node — for scripted-adapter routing."""
    agent_id = str(uuid.uuid4())
    workflow_id = str(uuid.uuid4())
    node_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    task_id = str(uuid.uuid4())
    brief_json = _compliance_brief_json()
    compliance_output = format_output(
        screen_from_dict(json.loads(brief_json), rules_path=_COMPLIANCE_FIXTURE.parent / "compliance_rules.json")
    )
    analyst_input = compose_analyst_task_input(brief_json, compliance_output)

    await db.execute(insert(agents).values(
        id=agent_id, name="Analyst", role="analyst",
        system_prompt="Score providers and recommend.", model="claude-haiku-4-5-20251001",
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
        id=workflow_id, name="Analyst Worker Test", description="",
    ))
    await db.execute(insert(workflow_nodes).values(
        id=node_id, workflow_id=workflow_id, agent_id=agent_id,
        node_type="end", task_prompt="Score providers and recommend.",
        position_x=0, position_y=0,
    ))
    await db.execute(insert(workflow_runs).values(
        id=run_id, workflow_id=workflow_id, status="pending",
        forced_complete=0, started_at="2026-01-01T00:00:00+00:00",
    ))
    await db.execute(insert(agent_tasks).values(
        id=task_id, run_id=run_id, node_id=node_id, agent_id=agent_id,
        source="workflow", status="pending", input=analyst_input,
    ))
    await db.commit()

    return {
        "agent_id": agent_id,
        "workflow_id": workflow_id,
        "node_id": node_id,
        "run_id": run_id,
        "task_id": task_id,
        "analyst_input": analyst_input,
    }


# ── W15: Analyst agent uses scripted adapter ──────────────────────────────────

@pytest.mark.asyncio
async def test_analyst_agent_uses_scripted_adapter(db, analyst_seed, tmp_path, monkeypatch):
    """Analyst node must invoke AnalystAdapter, not the injected FakeAdapter."""
    monkeypatch.setattr(
        "app.adapters.analyst_adapter._DEFAULT_REPORTS_DIR",
        tmp_path / "reports",
    )
    fake = FakeAdapter()
    worker = WorkflowWorker(
        MessageBusService(InMemoryWorkflowQueue()),
        adapter_cls=lambda **_: fake,
    )
    item = WorkflowDispatchItem(
        run_id=analyst_seed["run_id"],
        task_id=analyst_seed["task_id"],
        agent_id=analyst_seed["agent_id"],
        node_id=analyst_seed["node_id"],
        input=analyst_seed["analyst_input"],
    )

    await worker.process_dispatch_item(db, item)

    assert fake.invoke_count == 0
    task = (
        await db.execute(select(agent_tasks).where(agent_tasks.c.id == analyst_seed["task_id"]))
    ).mappings().one()
    assert task["status"] == "completed"
    assert task["output"].startswith("ANALYST=RECOMMENDATION")
    assert "MoneyGram" in task["output"]
    run = (
        await db.execute(select(workflow_runs).where(workflow_runs.c.id == analyst_seed["run_id"]))
    ).mappings().one()
    assert run["status"] == "completed"
