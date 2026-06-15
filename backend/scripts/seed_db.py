"""Initialize DB schema and seed 6 agents + 2 workflow templates."""
import asyncio
import json
import os
import sys
import uuid

# Allow running as: python3 -m scripts.seed_db from backend/
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "../../.env"))

from app.database import engine, init_db
from app.domain.remittance.types import ROUTE_ANALYST_NEEDS_MORE_DATA, ROUTE_COMPLIANCE_CLEARED
from app.models import (
    agents,
    agent_config,
    channel_connections,
    memory_entries,
    skills,
    workflow_edges,
    workflow_nodes,
    workflows,
)
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

GOOSE_MODEL = os.getenv("GOOSE_MODEL", "claude-sonnet-4-5")

# max_cost_per_run is deferred — no agent_config column yet (S4).

_DEFAULT_GUARDRAILS = {
    "max_tokens_per_run": 50000,
    "max_runs_per_minute": 6,
    "max_feedback_iterations": 2,
    "max_turns": 10,
    "timeout_seconds": 180,
}

SEED_AGENTS = [
    {
        "name": "Coder",
        "role": "Software engineer",
        "system_prompt": "You write clean, well-tested code. When given a task, produce a complete implementation.",
        "model": GOOSE_MODEL,
        "extensions": ["developer"],
        "memory": [
            {"key": "preferred_language", "value": "Python"},
            {"key": "code_style", "value": "PEP 8, type hints, docstrings"},
        ],
    },
    {
        "name": "Reviewer",
        "role": "Code reviewer",
        "system_prompt": (
            "You review code for correctness, security, and style. "
            "Reply APPROVED if the code is acceptable, or REJECTED with specific feedback."
        ),
        "model": GOOSE_MODEL,
        "extensions": ["developer"],
        "memory": [{"key": "review_standard", "value": "OWASP top 10 + PEP 8"}],
    },
    {
        "name": "Deployer",
        "role": "Deployment engineer",
        "system_prompt": "You deploy code to production. Verify the artefact exists before deploying.",
        "model": GOOSE_MODEL,
        "extensions": ["developer"],
        "memory": [],
        "requires_approval": True,
    },
    {
        "name": "Research",
        "role": "Remittance researcher",
        "system_prompt": (
            "You gather money-transfer provider quotes for a remittance request. "
            "Parse the user's request, load fixture rates when live lookup is unavailable, "
            "and return a structured TransferBrief JSON with data_source labeled."
        ),
        "model": GOOSE_MODEL,
        "extensions": ["developer"],
        "memory": [
            {"key": "sender_city", "value": "Austin, TX"},
            {"key": "sender_country", "value": "US"},
            {"key": "recipient_country", "value": "Colombia"},
            {"key": "recipient_city", "value": "Bogotá"},
            {"key": "send_currency", "value": "USD"},
            {"key": "receive_currency", "value": "COP"},
        ],
    },
    {
        "name": "Compliance",
        "role": "Compliance screening (deterministic)",
        "system_prompt": (
            "Deterministic compliance screening runs outside this prompt via ComplianceAdapter. "
            "This agent exists for workflow graph wiring and documentary memory only."
        ),
        "model": GOOSE_MODEL,
        "extensions": ["developer"],
        "memory": [],
    },
    {
        "name": "Analyst",
        "role": "Remittance analyst",
        "system_prompt": (
            "You score providers, write reports/transfer_comparison.md, and produce Telegram-ready "
            "recommendation text. Reply ANALYST=NEEDS_MORE_DATA with missing field names when "
            "provider data is incomplete; otherwise emit ANALYST=RECOMMENDATION with the winner."
        ),
        "model": GOOSE_MODEL,
        "extensions": ["developer"],
        "memory": [],
        "max_feedback_iterations": 2,
    },
]


async def populate_seed(conn: AsyncConnection | AsyncSession) -> None:
    """Insert demo agents and workflow templates if the database is empty."""
    result = await conn.execute(select(agents))
    if result.fetchone():
        return

    agent_ids: dict[str, str] = {}

    for agent in SEED_AGENTS:
        aid = str(uuid.uuid4())
        agent_ids[agent["name"]] = aid
        await conn.execute(insert(agents).values(
            id=aid,
            name=agent["name"],
            role=agent["role"],
            system_prompt=agent["system_prompt"],
            model=agent["model"],
            status="active",
        ))
        guardrails = {**_DEFAULT_GUARDRAILS}
        if "max_feedback_iterations" in agent:
            guardrails["max_feedback_iterations"] = agent["max_feedback_iterations"]
        await conn.execute(insert(agent_config).values(
            id=str(uuid.uuid4()),
            agent_id=aid,
            extensions=json.dumps(agent.get("extensions", ["developer"])),
            requires_approval=1 if agent.get("requires_approval") else 0,
            **guardrails,
        ))
        for entry in agent.get("memory", []):
            await conn.execute(insert(memory_entries).values(
                id=str(uuid.uuid4()),
                agent_id=aid,
                key=entry["key"],
                value=entry["value"],
            ))

    # Template 1: Dev Pipeline — Coder → Reviewer → (REJECTED loop | APPROVED → Deployer)
    dp_id = str(uuid.uuid4())
    await conn.execute(insert(workflows).values(
        id=dp_id,
        name="Dev Pipeline",
        description="Coder writes code, Reviewer approves or sends back, Deployer deploys.",
        template_key="dev_pipeline",
    ))
    n_coder = str(uuid.uuid4())
    n_reviewer = str(uuid.uuid4())
    n_deployer = str(uuid.uuid4())
    for node_id, agent_name, ntype, px, py, prompt in [
        (n_coder, "Coder", "start", 0, 0, "Implement the requested feature."),
        (n_reviewer, "Reviewer", "middle", 300, 0, "Review the code produced by the Coder."),
        (n_deployer, "Deployer", "end", 600, 0, "Deploy the approved code."),
    ]:
        await conn.execute(insert(workflow_nodes).values(
            id=node_id,
            workflow_id=dp_id,
            agent_id=agent_ids[agent_name],
            node_type=ntype,
            task_prompt=prompt,
            position_x=px,
            position_y=py,
        ))
    await conn.execute(insert(workflow_edges).values(
        id=str(uuid.uuid4()), from_node_id=n_coder, to_node_id=n_reviewer, condition="always",
    ))
    await conn.execute(insert(workflow_edges).values(
        id=str(uuid.uuid4()), from_node_id=n_reviewer, to_node_id=n_coder,
        condition="REJECTED", max_iterations=2,
    ))
    await conn.execute(insert(workflow_edges).values(
        id=str(uuid.uuid4()), from_node_id=n_reviewer, to_node_id=n_deployer, condition="APPROVED",
    ))

    # Template 2: Remittance Comparison — Research → Compliance → Analyst
    rc_id = str(uuid.uuid4())
    await conn.execute(insert(workflows).values(
        id=rc_id,
        name="Remittance Comparison",
        description=(
            "Research gathers provider quotes, Compliance screens deterministically, "
            "Analyst scores and recommends."
        ),
        template_key="remittance_comparison",
    ))
    n_research = str(uuid.uuid4())
    n_compliance = str(uuid.uuid4())
    n_analyst = str(uuid.uuid4())
    for node_id, agent_name, ntype, px, py, prompt in [
        (
            n_research,
            "Research",
            "start",
            0,
            0,
            "Gather provider quotes for the remittance request and return TransferBrief JSON.",
        ),
        (
            n_compliance,
            "Compliance",
            "end",
            300,
            0,
            "Screen the transfer brief against compliance rules.",
        ),
        (
            n_analyst,
            "Analyst",
            "end",
            600,
            0,
            "Score providers, write the comparison report, and produce the recommendation message.",
        ),
    ]:
        await conn.execute(insert(workflow_nodes).values(
            id=node_id,
            workflow_id=rc_id,
            agent_id=agent_ids[agent_name],
            node_type=ntype,
            task_prompt=prompt,
            position_x=px,
            position_y=py,
        ))
    await conn.execute(insert(workflow_edges).values(
        id=str(uuid.uuid4()), from_node_id=n_research, to_node_id=n_compliance, condition="always",
    ))
    await conn.execute(insert(workflow_edges).values(
        id=str(uuid.uuid4()), from_node_id=n_compliance, to_node_id=n_analyst,
        condition=ROUTE_COMPLIANCE_CLEARED,
    ))
    await conn.execute(insert(workflow_edges).values(
        id=str(uuid.uuid4()), from_node_id=n_analyst, to_node_id=n_research,
        condition=ROUTE_ANALYST_NEEDS_MORE_DATA, max_iterations=2,
    ))

    await conn.execute(insert(channel_connections).values(
        id=str(uuid.uuid4()),
        agent_id=agent_ids["Research"],
        channel_type="telegram",
        channel_id=os.getenv("DEMO_TELEGRAM_CHAT_ID", "0"),
        trigger_workflow_id=rc_id,
        active=1,
    ))


async def seed() -> None:
    await init_db()
    async with engine.begin() as conn:
        await populate_seed(conn)
    print(f"  Seeded {len(SEED_AGENTS)} agents and 2 workflow templates.")


if __name__ == "__main__":
    asyncio.run(seed())
