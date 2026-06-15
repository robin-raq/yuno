"""S2 Unit 8b — approval gate (BUILD_SPEC §13–§14).

Tests the pre-dispatch gate: run pauses before a requires_approval agent,
approve resumes via enqueue, reject fails the run.
"""
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import insert, select, text

from app.models import (
    agent_config, agent_messages, agent_tasks, agents, approval_requests,
    execution_events, workflow_edges, workflow_nodes, workflow_runs, workflows,
)
from app.services.approval_service import (
    ApprovalAlreadyResolved, ApprovalNotFound, approve_task, reject_task,
)
from app.services.message_bus import MessageBusService, WorkflowDispatchItem
from app.services.workflow_graph import advance_after_task_completion


@pytest_asyncio.fixture
async def dev_pipeline_with_approval(db):
    """Coder → Reviewer → Deployer (requires_approval)."""
    ids: dict[str, str] = {}

    async def agent(name: str, role: str, requires: bool = False) -> str:
        aid = str(uuid.uuid4())
        await db.execute(insert(agents).values(
            id=aid, name=name, role=role, system_prompt=f"You are {name}.",
            model="claude-sonnet-4-5", status="active",
        ))
        await db.execute(insert(agent_config).values(
            id=str(uuid.uuid4()), agent_id=aid,
            requires_approval=1 if requires else 0,
        ))
        ids[f"{name.lower()}_agent"] = aid
        return aid

    coder = await agent("Coder", "engineer")
    reviewer = await agent("Reviewer", "reviewer")
    deployer = await agent("Deployer", "deployer", requires=True)

    wf = str(uuid.uuid4())
    ids["workflow_id"] = wf
    await db.execute(insert(workflows).values(
        id=wf, name="Dev Pipeline", description="", template_key="dev_pipeline",
    ))

    n_coder, n_reviewer, n_deployer = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    ids["coder_node"] = n_coder
    ids["reviewer_node"] = n_reviewer
    ids["deployer_node"] = n_deployer
    for nid, aid, ntype, prompt, x in [
        (n_coder, coder, "start", "Implement.", 0),
        (n_reviewer, reviewer, "middle", "Review.", 100),
        (n_deployer, deployer, "end", "Deploy.", 200),
    ]:
        await db.execute(insert(workflow_nodes).values(
            id=nid, workflow_id=wf, agent_id=aid, node_type=ntype,
            task_prompt=prompt, position_x=x, position_y=0,
        ))
    await db.execute(insert(workflow_edges).values(
        id=str(uuid.uuid4()), from_node_id=n_coder, to_node_id=n_reviewer, condition="always",
    ))
    await db.execute(insert(workflow_edges).values(
        id=str(uuid.uuid4()), from_node_id=n_reviewer, to_node_id=n_deployer, condition="APPROVED",
    ))

    run_id = str(uuid.uuid4())
    ids["run_id"] = run_id
    await db.execute(insert(workflow_runs).values(
        id=run_id, workflow_id=wf, status="running", forced_complete=0,
        started_at="2026-06-12T00:00:00+00:00",
    ))

    tasks: list[str] = []
    for nid, aid, inp, status, out in [
        (n_coder, coder, "Build auth", "completed", "def auth(): pass"),
        (n_reviewer, reviewer, "def auth(): pass", "completed", "APPROVED"),
    ]:
        tid = str(uuid.uuid4())
        tasks.append(tid)
        await db.execute(insert(agent_tasks).values(
            id=tid, run_id=run_id, node_id=nid, agent_id=aid,
            source="workflow", status=status, input=inp, output=out,
        ))
    ids["coder_task"] = tasks[0]
    ids["reviewer_task"] = tasks[1]
    await db.commit()
    return ids


def _item(seed: dict, task_key: str, node_key: str, agent_key: str, inp: str) -> WorkflowDispatchItem:
    return WorkflowDispatchItem(
        run_id=seed["run_id"],
        task_id=seed[task_key],
        agent_id=seed[agent_key],
        node_id=seed[node_key],
        input=inp,
    )


@pytest.mark.asyncio
async def test_gate_pauses_before_requires_approval_agent(db, dev_pipeline_with_approval):
    bus = MessageBusService()
    seed = dev_pipeline_with_approval

    # Reviewer completes with APPROVED — next is Deployer (gate fires).
    advance = await advance_after_task_completion(
        db,
        _item(seed, "reviewer_task", "reviewer_node", "reviewer_agent", "APPROVED"),
        "APPROVED",
        bus,
    )
    assert advance.status == "awaiting_approval"
    assert bus.queue_size() == 0

    run_status = (await db.execute(
        select(workflow_runs.c.status).where(workflow_runs.c.id == seed["run_id"])
    )).scalar_one()
    assert run_status == "awaiting_approval"

    deployer_status = (await db.execute(
        select(agent_tasks.c.status)
        .where(agent_tasks.c.run_id == seed["run_id"])
        .where(agent_tasks.c.node_id == seed["deployer_node"])
    )).scalar_one()
    assert deployer_status == "pending"

    approval = (await db.execute(
        select(approval_requests).where(approval_requests.c.run_id == seed["run_id"])
    )).mappings().one()
    deployer_task_id = approval["task_id"]
    assert approval["status"] == "pending"

    events = [r["event_type"] for r in (await db.execute(
        select(execution_events.c.event_type)
        .where(execution_events.c.run_id == seed["run_id"])
        .order_by(text("rowid"))
    )).mappings().all()]
    assert "approval_required" in events
    assert (await db.execute(select(agent_messages).where(agent_messages.c.run_id == seed["run_id"]))).first() is None


@pytest.mark.asyncio
async def test_approve_resumes_and_enqueues(db, dev_pipeline_with_approval):
    bus = MessageBusService()
    seed = dev_pipeline_with_approval
    advance = await advance_after_task_completion(
        db,
        _item(seed, "reviewer_task", "reviewer_node", "reviewer_agent", "APPROVED"),
        "APPROVED",
        bus,
    )
    deployer_task_id = advance.next_task_id
    assert deployer_task_id is not None

    await approve_task(db, seed["run_id"], deployer_task_id, bus)

    run_status = (await db.execute(
        select(workflow_runs.c.status).where(workflow_runs.c.id == seed["run_id"])
    )).scalar_one()
    assert run_status == "running"
    assert bus.queue_size() == 1

    msgs = (await db.execute(
        select(agent_messages).where(agent_messages.c.run_id == seed["run_id"])
    )).mappings().all()
    assert len(msgs) == 1
    assert msgs[0]["msg_type"] == "task_output"

    events = [r["event_type"] for r in (await db.execute(
        select(execution_events.c.event_type)
        .where(execution_events.c.run_id == seed["run_id"])
        .order_by(text("rowid"))
    )).mappings().all()]
    assert "approval_resolved" in events


@pytest.mark.asyncio
async def test_reject_fails_run(db, dev_pipeline_with_approval):
    bus = MessageBusService()
    seed = dev_pipeline_with_approval
    advance = await advance_after_task_completion(
        db,
        _item(seed, "reviewer_task", "reviewer_node", "reviewer_agent", "APPROVED"),
        "APPROVED",
        bus,
    )
    deployer_task_id = advance.next_task_id
    assert deployer_task_id is not None

    await reject_task(db, seed["run_id"], deployer_task_id)

    run_status = (await db.execute(
        select(workflow_runs.c.status).where(workflow_runs.c.id == seed["run_id"])
    )).scalar_one()
    task_status = (await db.execute(
        select(agent_tasks.c.status).where(agent_tasks.c.id == deployer_task_id)
    )).scalar_one()
    assert run_status == "failed"
    assert task_status == "failed"
    assert bus.queue_size() == 0

    events = [r["event_type"] for r in (await db.execute(
        select(execution_events.c.event_type)
        .where(execution_events.c.run_id == seed["run_id"])
        .order_by(text("rowid"))
    )).mappings().all()]
    assert "approval_resolved" in events
    assert "workflow_failed" in events


@pytest.mark.asyncio
async def test_api_approve_and_reject(client, db, dev_pipeline_with_approval):
    bus = MessageBusService()
    seed = dev_pipeline_with_approval
    advance = await advance_after_task_completion(
        db,
        _item(seed, "reviewer_task", "reviewer_node", "reviewer_agent", "APPROVED"),
        "APPROVED",
        bus,
    )
    deployer_task_id = advance.next_task_id
    assert deployer_task_id is not None

    ok = await client.post(f"/runs/{seed['run_id']}/tasks/{deployer_task_id}/approve")
    assert ok.status_code == 200
    assert ok.json()["status"] == "running"

    dup = await client.post(f"/runs/{seed['run_id']}/tasks/{deployer_task_id}/approve")
    assert dup.status_code == 409


@pytest.mark.asyncio
async def test_api_reject(client, db, dev_pipeline_with_approval):
    bus = MessageBusService()
    seed = dev_pipeline_with_approval
    advance = await advance_after_task_completion(
        db,
        _item(seed, "reviewer_task", "reviewer_node", "reviewer_agent", "APPROVED"),
        "APPROVED",
        bus,
    )
    deployer_task_id = advance.next_task_id
    assert deployer_task_id is not None

    resp = await client.post(f"/runs/{seed['run_id']}/tasks/{deployer_task_id}/reject")
    assert resp.status_code == 200
    assert resp.json()["status"] == "failed"


@pytest.mark.asyncio
async def test_approve_unknown_task_raises(db, dev_pipeline_with_approval):
    bus = MessageBusService()
    with pytest.raises(ApprovalNotFound):
        await approve_task(db, dev_pipeline_with_approval["run_id"], str(uuid.uuid4()), bus)
