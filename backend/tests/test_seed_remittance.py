"""U8 — Remittance Comparison seed tests (test-first).

Verifies seed_db replaces Research Pipeline with the remittance workflow while
keeping Dev Pipeline and six agents (no Publisher).
"""
import pytest
from sqlalchemy import select

from app.domain.remittance.types import ROUTE_ANALYST_NEEDS_MORE_DATA, ROUTE_COMPLIANCE_CLEARED
from app.models import (
    agent_config,
    agent_tasks,
    agents,
    channel_connections,
    workflow_edges,
    workflow_nodes,
    workflows,
)
from app.services import workflow_service
from scripts.seed_db import populate_seed

EXPECTED_AGENTS = frozenset(
    {"Coder", "Reviewer", "Deployer", "Research", "Compliance", "Analyst"}
)


@pytest.mark.asyncio
async def test_seed_creates_six_agents_without_publisher(db):
    await populate_seed(db)
    await db.commit()

    names = {
        row["name"]
        for row in (await db.execute(select(agents.c.name))).mappings().all()
    }
    assert names == EXPECTED_AGENTS
    assert "Publisher" not in names
    assert "Researcher" not in names


@pytest.mark.asyncio
async def test_remittance_workflow_nodes_and_template_key(db):
    await populate_seed(db)
    await db.commit()

    wf = (
        await db.execute(
            select(workflows).where(workflows.c.template_key == "remittance_comparison")
        )
    ).mappings().one()
    assert wf["name"] == "Remittance Comparison"

    nodes = (
        await db.execute(
            select(workflow_nodes, agents.c.name)
            .join(agents, workflow_nodes.c.agent_id == agents.c.id)
            .where(workflow_nodes.c.workflow_id == wf["id"])
            .order_by(workflow_nodes.c.position_x)
        )
    ).mappings().all()

    assert len(nodes) == 3
    assert [(n["name"], n["node_type"]) for n in nodes] == [
        ("Research", "start"),
        ("Compliance", "end"),
        ("Analyst", "end"),
    ]


@pytest.mark.asyncio
async def test_remittance_workflow_edges(db):
    await populate_seed(db)
    await db.commit()

    wf_id = (
        await db.execute(
            select(workflows.c.id).where(workflows.c.template_key == "remittance_comparison")
        )
    ).scalar_one()

    node_rows = (
        await db.execute(
            select(workflow_nodes.c.id, agents.c.name)
            .join(agents, workflow_nodes.c.agent_id == agents.c.id)
            .where(workflow_nodes.c.workflow_id == wf_id)
        )
    ).mappings().all()
    by_name = {row["name"]: row["id"] for row in node_rows}

    edges = (
        await db.execute(
            select(workflow_edges).where(
                workflow_edges.c.from_node_id.in_(list(by_name.values()))
            )
        )
    ).mappings().all()

    def _edge(from_name, to_name, condition, max_iter=None):
        match = [
            e for e in edges
            if e["from_node_id"] == by_name[from_name]
            and e["to_node_id"] == by_name[to_name]
            and e["condition"] == condition
        ]
        assert len(match) == 1, f"missing edge {from_name}→{to_name} ({condition})"
        if max_iter is not None:
            assert match[0]["max_iterations"] == max_iter
        return match[0]

    _edge("Research", "Compliance", "always")
    _edge("Compliance", "Analyst", ROUTE_COMPLIANCE_CLEARED)
    _edge("Analyst", "Research", ROUTE_ANALYST_NEEDS_MORE_DATA, max_iter=2)
    assert len(edges) == 3


@pytest.mark.asyncio
async def test_research_channel_connection_triggers_remittance_workflow(db):
    await populate_seed(db)
    await db.commit()

    research_id = (
        await db.execute(select(agents.c.id).where(agents.c.name == "Research"))
    ).scalar_one()
    remittance_id = (
        await db.execute(
            select(workflows.c.id).where(workflows.c.template_key == "remittance_comparison")
        )
    ).scalar_one()

    row = (
        await db.execute(
            select(channel_connections).where(channel_connections.c.agent_id == research_id)
        )
    ).mappings().one()

    assert row["channel_type"] == "telegram"
    assert row["trigger_workflow_id"] == remittance_id
    assert row["active"] == 1


@pytest.mark.asyncio
async def test_start_run_passes_on_remittance_workflow(db):
    await populate_seed(db)
    await db.commit()

    wf_id = (
        await db.execute(
            select(workflows.c.id).where(workflows.c.template_key == "remittance_comparison")
        )
    ).scalar_one()

    result = await workflow_service.start_run(db, wf_id, "send $500 cash to Bogotá")

    assert result["run_id"]
    assert result["status"] == "pending"
    tasks = (
        await db.execute(
            select(agent_tasks).where(agent_tasks.c.run_id == result["run_id"])
        )
    ).mappings().all()
    assert len(tasks) == 1
    assert tasks[0]["status"] == "pending"
    assert tasks[0]["input"] == "send $500 cash to Bogotá"


@pytest.mark.asyncio
async def test_dev_pipeline_template_still_seeded(db):
    await populate_seed(db)
    await db.commit()

    dp = (
        await db.execute(
            select(workflows.c.template_key).where(workflows.c.template_key == "dev_pipeline")
        )
    ).scalar_one_or_none()
    assert dp == "dev_pipeline"

    rp = (
        await db.execute(
            select(workflows.c.template_key).where(workflows.c.template_key == "research_pipeline")
        )
    ).scalar_one_or_none()
    assert rp is None


@pytest.mark.asyncio
async def test_analyst_has_feedback_iteration_guardrail(db):
    await populate_seed(db)
    await db.commit()

    analyst_id = (
        await db.execute(select(agents.c.id).where(agents.c.name == "Analyst"))
    ).scalar_one()
    cfg = (
        await db.execute(select(agent_config).where(agent_config.c.agent_id == analyst_id))
    ).mappings().one()
    assert cfg["max_feedback_iterations"] == 2
