"""S2 Unit 9 — runtime wiring: start_run enqueue + worker loop."""
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import insert, select

from app.adapters.base import TaskInput, TaskResult
from app.models import agent_config, agent_tasks, agents, workflow_nodes, workflow_runs, workflows
from app.services.message_bus import get_message_bus
from app.services.workflow_service import start_run
from app.services.workflow_worker import WorkflowWorker


class _ImmediateFakeAdapter:
    def __init__(self, host: str = "", port: int = 0) -> None:
        pass

    async def invoke(self, task: TaskInput, on_event) -> TaskResult:
        return TaskResult(output="done", tokens_total=1, estimated_cost=0.0)

    async def health_check(self) -> bool:
        return True


@pytest_asyncio.fixture
async def one_node_seed(db):
    agent_id = str(uuid.uuid4())
    workflow_id = str(uuid.uuid4())
    node_id = str(uuid.uuid4())
    await db.execute(insert(agents).values(
        id=agent_id, name="WorkerTest", role="test",
        system_prompt="", model="claude-sonnet-4-5", status="active",
    ))
    await db.execute(insert(agent_config).values(id=str(uuid.uuid4()), agent_id=agent_id))
    await db.execute(insert(workflows).values(
        id=workflow_id, name="One Node", description="", template_key="test",
    ))
    await db.execute(insert(workflow_nodes).values(
        id=node_id, workflow_id=workflow_id, agent_id=agent_id,
        node_type="start", task_prompt="Go.",
    ))
    await db.commit()
    return {"workflow_id": workflow_id}


@pytest.mark.asyncio
async def test_worker_drains_queue_after_start_run(db, one_node_seed):
    bus = get_message_bus()
    snapshot = await start_run(db, one_node_seed["workflow_id"], "hello")
    assert bus.queue_size() == 1

    worker = WorkflowWorker(bus, adapter_cls=_ImmediateFakeAdapter)
    assert await worker.process_next(db) is True
    assert bus.queue_size() == 0

    run_id = snapshot["run_id"]
    status = (await db.execute(
        select(workflow_runs.c.status).where(workflow_runs.c.id == run_id)
    )).scalar_one()
    task_status = (await db.execute(
        select(agent_tasks.c.status).where(agent_tasks.c.run_id == run_id)
    )).scalar_one()
    assert status == "completed"
    assert task_status == "completed"


@pytest.mark.asyncio
async def test_worker_loop_processes_until_empty(db, one_node_seed):
    """Background loop pattern: drain until the queue is empty."""
    bus = get_message_bus()
    await start_run(db, one_node_seed["workflow_id"], "loop-test")
    worker = WorkflowWorker(bus, adapter_cls=_ImmediateFakeAdapter)

    processed = 0
    while await worker.process_next(db):
        processed += 1
    assert processed == 1
    assert bus.queue_size() == 0
