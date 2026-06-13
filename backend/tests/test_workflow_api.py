"""test_workflow_api — S2 Unit 3 workflow API spine.

Covers GET /workflows, POST /workflows/{id}/runs, GET /runs/{id}, and error
cases. Unit 3 creates the run + first pending task + workflow_started event only;
it does NOT execute the task (no Goose, no worker).
"""
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import insert, select

from app.models import (
    agents, agent_config, workflows, workflow_nodes, workflow_edges,
    workflow_runs, agent_tasks, execution_events,
)


@pytest_asyncio.fixture
async def seeded_workflows(db):
    """Seed two valid templates (dev_pipeline, research_pipeline) and one broken
    workflow (no start node), inserted through the same session the client uses.

    Returns a dict of ids the tests reference by template_key — never hardcoded UUIDs.
    """
    ids = {}

    async def add_agent(name: str, role: str) -> str:
        aid = str(uuid.uuid4())
        await db.execute(insert(agents).values(
            id=aid, name=name, role=role, system_prompt="", model="claude-sonnet-4-5", status="active",
        ))
        await db.execute(insert(agent_config).values(id=str(uuid.uuid4()), agent_id=aid))
        return aid

    coder = await add_agent("Coder", "Engineer")
    reviewer = await add_agent("Reviewer", "Reviewer")
    deployer = await add_agent("Deployer", "Deployer")

    # --- dev_pipeline: Coder(start) -> Reviewer(middle) -> Deployer(end) ---
    dp = str(uuid.uuid4())
    ids["dev_pipeline"] = dp
    await db.execute(insert(workflows).values(
        id=dp, name="Dev Pipeline", description="Coder, Reviewer, Deployer.", template_key="dev_pipeline",
    ))
    n_coder, n_reviewer, n_deployer = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    ids["dev_pipeline_start_node"] = n_coder
    ids["dev_pipeline_coder_agent"] = coder
    for node_id, agent_id, ntype, prompt in [
        (n_coder, coder, "start", "Implement the feature."),
        (n_reviewer, reviewer, "middle", "Review the code."),
        (n_deployer, deployer, "end", "Deploy the code."),
    ]:
        await db.execute(insert(workflow_nodes).values(
            id=node_id, workflow_id=dp, agent_id=agent_id, node_type=ntype, task_prompt=prompt,
        ))
    await db.execute(insert(workflow_edges).values(
        id=str(uuid.uuid4()), from_node_id=n_coder, to_node_id=n_reviewer, condition="always",
    ))
    await db.execute(insert(workflow_edges).values(
        id=str(uuid.uuid4()), from_node_id=n_reviewer, to_node_id=n_deployer, condition="APPROVED",
    ))

    # --- research_pipeline: single workflow row (proves GET returns >1) ---
    rp = str(uuid.uuid4())
    ids["research_pipeline"] = rp
    await db.execute(insert(workflows).values(
        id=rp, name="Research Pipeline", description="Research, analyse, publish.",
        template_key="research_pipeline",
    ))
    n_res = str(uuid.uuid4())
    await db.execute(insert(workflow_nodes).values(
        id=n_res, workflow_id=rp, agent_id=coder, node_type="start", task_prompt="Research.",
    ))

    # --- broken: a workflow with NO start node (graph validation must reject) ---
    broken = str(uuid.uuid4())
    ids["broken"] = broken
    await db.execute(insert(workflows).values(
        id=broken, name="Broken", description="No start node.", template_key="broken",
    ))
    await db.execute(insert(workflow_nodes).values(
        id=str(uuid.uuid4()), workflow_id=broken, agent_id=coder, node_type="middle", task_prompt="x",
    ))

    # --- missing_agent: has a start node, but its agent_id references no agent ---
    missing = str(uuid.uuid4())
    ids["missing_agent"] = missing
    await db.execute(insert(workflows).values(
        id=missing, name="Missing Agent", description="Start node points to a ghost agent.",
        template_key="missing_agent",
    ))
    await db.execute(insert(workflow_nodes).values(
        id=str(uuid.uuid4()), workflow_id=missing, agent_id=str(uuid.uuid4()),  # no such agent
        node_type="start", task_prompt="x",
    ))

    await db.commit()
    return ids


# ── GET /workflows ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_workflows_returns_seeded(client, seeded_workflows):
    r = await client.get("/workflows")
    assert r.status_code == 200, r.text
    data = r.json()
    assert isinstance(data, list)
    by_key = {w["template_key"]: w for w in data}
    # both seeded templates must be listed (L4: prove "returns seeded workflows" plural)
    assert "dev_pipeline" in by_key, "dev_pipeline template must be present"
    assert "research_pipeline" in by_key, "research_pipeline template must be present"
    dp = by_key["dev_pipeline"]
    for field in ("id", "name", "description", "template_key"):
        assert field in dp
    assert dp["name"] == "Dev Pipeline"
    # ids discovered from response, not hardcoded
    assert dp["id"] == seeded_workflows["dev_pipeline"]
    assert by_key["research_pipeline"]["id"] == seeded_workflows["research_pipeline"]


# ── POST /workflows/{id}/runs ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_start_run_creates_run_and_first_task(client, seeded_workflows, db):
    wf_id = seeded_workflows["dev_pipeline"]
    r = await client.post(f"/workflows/{wf_id}/runs", json={"input": "Build a parser"})
    assert r.status_code == 201, r.text
    body = r.json()

    for field in ("run_id", "workflow_id", "status", "forced_complete", "started_at"):
        assert field in body, f"missing {field} in run-create response"
    assert body["workflow_id"] == wf_id
    assert body["forced_complete"] is False
    assert body["status"] == "pending"
    run_id = body["run_id"]

    # workflow_runs row created
    runs = (await db.execute(
        select(workflow_runs).where(workflow_runs.c.id == run_id)
    )).mappings().all()
    assert len(runs) == 1

    # first agent_tasks row: source=workflow, run_id, node_id == start node, pending
    tasks = (await db.execute(
        select(agent_tasks).where(agent_tasks.c.run_id == run_id)
    )).mappings().all()
    assert len(tasks) == 1, "exactly one start task should be created in Unit 3"
    task = tasks[0]
    assert task["source"] == "workflow"
    assert task["run_id"] == run_id
    assert task["node_id"] == seeded_workflows["dev_pipeline_start_node"]
    assert task["status"] == "pending"
    assert task["output"] is None  # Goose not invoked

    # workflow_started event persisted with run_id + workflow_id
    events = (await db.execute(
        select(execution_events).where(execution_events.c.run_id == run_id)
    )).mappings().all()
    started = [e for e in events if e["event_type"] == "workflow_started"]
    assert len(started) == 1
    import json
    payload = json.loads(started[0]["data"])
    assert payload["run_id"] == run_id
    assert payload["workflow_id"] == wf_id


@pytest.mark.asyncio
async def test_start_run_unknown_workflow(client, seeded_workflows):
    r = await client.post("/workflows/does-not-exist/runs", json={"input": "x"})
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "workflow_not_found"


@pytest.mark.asyncio
async def test_start_run_invalid_graph_creates_no_rows(client, seeded_workflows, db):
    broken_id = seeded_workflows["broken"]
    r = await client.post(f"/workflows/{broken_id}/runs", json={"input": "x"})
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "graph_validation_failed"

    # no run rows created for the broken workflow
    runs = (await db.execute(
        select(workflow_runs).where(workflow_runs.c.workflow_id == broken_id)
    )).mappings().all()
    assert runs == []


@pytest.mark.asyncio
async def test_start_run_missing_start_agent_creates_no_rows(client, seeded_workflows, db):
    """M2: a start node whose agent_id references no agent must be rejected with
    graph_validation_failed and leave zero run/task rows."""
    wf_id = seeded_workflows["missing_agent"]
    r = await client.post(f"/workflows/{wf_id}/runs", json={"input": "x"})
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "graph_validation_failed"

    runs = (await db.execute(
        select(workflow_runs).where(workflow_runs.c.workflow_id == wf_id)
    )).mappings().all()
    assert runs == []

    # no agent_tasks created for any of this workflow's nodes
    node_ids = [n["id"] for n in (await db.execute(
        select(workflow_nodes).where(workflow_nodes.c.workflow_id == wf_id)
    )).mappings()]
    tasks = (await db.execute(
        select(agent_tasks).where(agent_tasks.c.node_id.in_(node_ids))
    )).mappings().all()
    assert tasks == []


# ── GET /runs/{id} ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_run_snapshot(client, seeded_workflows):
    wf_id = seeded_workflows["dev_pipeline"]
    run_id = (await client.post(f"/workflows/{wf_id}/runs", json={"input": "Build"})).json()["run_id"]

    r = await client.get(f"/runs/{run_id}")
    assert r.status_code == 200, r.text
    snap = r.json()

    assert snap["run_id"] == run_id
    assert snap["workflow_id"] == wf_id
    assert snap["forced_complete"] is False
    # workflow metadata
    assert snap["workflow"]["name"] == "Dev Pipeline"
    assert snap["workflow"]["template_key"] == "dev_pipeline"
    # tasks in created order
    assert isinstance(snap["tasks"], list) and len(snap["tasks"]) == 1
    assert snap["tasks"][0]["node_id"] == seeded_workflows["dev_pipeline_start_node"]
    # messages present even if empty; no pending approval in Unit 3
    assert snap["messages"] == []
    assert snap["pending_approval"] is None


@pytest.mark.asyncio
async def test_get_run_unknown_returns_404(client, seeded_workflows):
    r = await client.get("/runs/nope")
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "run_not_found"
