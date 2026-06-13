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
from app.models import (
    agents, agent_config, memory_entries, skills,
    workflows, workflow_nodes, workflow_edges,
)
from sqlalchemy import insert, select


GOOSE_MODEL = os.getenv("GOOSE_MODEL", "claude-sonnet-4-5")

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
        "name": "Researcher",
        "role": "Research analyst",
        "system_prompt": "You gather information and produce structured research reports.",
        "model": GOOSE_MODEL,
        "extensions": ["developer"],
        "memory": [
            {"key": "report_format", "value": "Markdown with executive summary"},
            {"key": "sources", "value": "Prefer primary sources; cite everything"},
        ],
        "channels": [{"channel_type": "telegram", "channel_id": os.getenv("DEMO_TELEGRAM_CHAT_ID", "0")}],
    },
    {
        "name": "Analyst",
        "role": "Data analyst",
        "system_prompt": "You analyse research findings and produce actionable insights.",
        "model": GOOSE_MODEL,
        "extensions": ["developer"],
        "memory": [],
    },
    {
        "name": "Publisher",
        "role": "Content publisher",
        "system_prompt": "You format and publish content. Reply NEEDS_MORE_DATA if the content is insufficient.",
        "model": GOOSE_MODEL,
        "extensions": ["developer"],
        "memory": [],
    },
]


async def seed() -> None:
    await init_db()
    async with engine.begin() as conn:
        # Check if already seeded
        result = await conn.execute(select(agents))
        if result.fetchone():
            print("  DB already seeded — skipping")
            return

        agent_ids: dict[str, str] = {}

        for a in SEED_AGENTS:
            aid = str(uuid.uuid4())
            agent_ids[a["name"]] = aid
            await conn.execute(insert(agents).values(
                id=aid,
                name=a["name"],
                role=a["role"],
                system_prompt=a["system_prompt"],
                model=a["model"],
                status="active",
            ))
            await conn.execute(insert(agent_config).values(
                id=str(uuid.uuid4()),
                agent_id=aid,
                extensions=json.dumps(a.get("extensions", ["developer"])),
                requires_approval=1 if a.get("requires_approval") else 0,
            ))
            for m in a.get("memory", []):
                await conn.execute(insert(memory_entries).values(
                    id=str(uuid.uuid4()),
                    agent_id=aid,
                    key=m["key"],
                    value=m["value"],
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
        # Loop: REJECTED → back to Coder (max 2 iterations)
        await conn.execute(insert(workflow_edges).values(
            id=str(uuid.uuid4()), from_node_id=n_reviewer, to_node_id=n_coder,
            condition="REJECTED", max_iterations=2,
        ))
        # Forward: APPROVED → Deployer
        await conn.execute(insert(workflow_edges).values(
            id=str(uuid.uuid4()), from_node_id=n_reviewer, to_node_id=n_deployer, condition="APPROVED",
        ))

        # Template 2: Research Pipeline — Researcher → Analyst → Publisher
        rp_id = str(uuid.uuid4())
        await conn.execute(insert(workflows).values(
            id=rp_id,
            name="Research Pipeline",
            description="Researcher gathers data, Analyst processes it, Publisher formats and delivers.",
            template_key="research_pipeline",
        ))
        n_researcher = str(uuid.uuid4())
        n_analyst = str(uuid.uuid4())
        n_publisher = str(uuid.uuid4())
        for node_id, agent_name, ntype, px, py, prompt in [
            (n_researcher, "Researcher", "start", 0, 0, "Research the given topic thoroughly."),
            (n_analyst, "Analyst", "middle", 300, 0, "Analyse the research findings."),
            (n_publisher, "Publisher", "end", 600, 0, "Publish the analysis. Reply NEEDS_MORE_DATA if insufficient."),
        ]:
            await conn.execute(insert(workflow_nodes).values(
                id=node_id,
                workflow_id=rp_id,
                agent_id=agent_ids[agent_name],
                node_type=ntype,
                task_prompt=prompt,
                position_x=px,
                position_y=py,
            ))
        await conn.execute(insert(workflow_edges).values(
            id=str(uuid.uuid4()), from_node_id=n_researcher, to_node_id=n_analyst, condition="always",
        ))
        await conn.execute(insert(workflow_edges).values(
            id=str(uuid.uuid4()), from_node_id=n_analyst, to_node_id=n_publisher, condition="always",
        ))
        # Loop: NEEDS_MORE_DATA → back to Researcher
        await conn.execute(insert(workflow_edges).values(
            id=str(uuid.uuid4()), from_node_id=n_publisher, to_node_id=n_researcher,
            condition="NEEDS_MORE_DATA", max_iterations=2,
        ))

    print(f"  Seeded {len(SEED_AGENTS)} agents and 2 workflow templates.")


if __name__ == "__main__":
    asyncio.run(seed())
