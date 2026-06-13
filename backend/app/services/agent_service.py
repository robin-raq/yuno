"""Agent CRUD service — wraps DB operations for the agent + config pair."""
import json
import uuid
from typing import Any

from sqlalchemy import select, insert, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import agents, agent_config, memory_entries, skills as skills_table


async def list_agents(db: AsyncSession) -> list[dict]:
    rows = await db.execute(select(agents).order_by(agents.c.created_at))
    result = []
    for row in rows.mappings():
        agent = dict(row)
        cfg = await _get_config(db, agent["id"])
        agent["config"] = cfg
        result.append(agent)
    return result


async def get_agent(db: AsyncSession, agent_id: str) -> dict | None:
    row = await db.execute(select(agents).where(agents.c.id == agent_id))
    agent = row.mappings().first()
    if not agent:
        return None
    agent = dict(agent)
    agent["config"] = await _get_config(db, agent_id)
    agent["memory"] = await _get_memory(db, agent_id)
    agent["skills"] = await _get_skills(db, agent_id)
    return agent


async def create_agent(db: AsyncSession, data: dict) -> dict:
    agent_id = str(uuid.uuid4())
    await db.execute(insert(agents).values(
        id=agent_id,
        name=data["name"],
        role=data["role"],
        system_prompt=data.get("system_prompt", ""),
        model=data["model"],
        status="active",
    ))
    await db.execute(insert(agent_config).values(
        id=str(uuid.uuid4()),
        agent_id=agent_id,
        extensions=json.dumps(data.get("tool_access", ["developer"])),
        requires_approval=0,
    ))
    await db.commit()
    return await get_agent(db, agent_id)


async def update_agent(db: AsyncSession, agent_id: str, data: dict) -> dict | None:
    allowed = {"name", "role", "system_prompt", "model", "status"}
    values = {k: v for k, v in data.items() if k in allowed}
    if not values:
        return await get_agent(db, agent_id)
    await db.execute(update(agents).where(agents.c.id == agent_id).values(**values))
    await db.commit()
    return await get_agent(db, agent_id)


async def delete_agent(db: AsyncSession, agent_id: str) -> bool:
    result = await db.execute(delete(agents).where(agents.c.id == agent_id))
    await db.commit()
    return result.rowcount > 0


async def _get_config(db: AsyncSession, agent_id: str) -> dict:
    row = await db.execute(select(agent_config).where(agent_config.c.agent_id == agent_id))
    cfg = row.mappings().first()
    if not cfg:
        return {}
    cfg = dict(cfg)
    cfg["extensions"] = json.loads(cfg.get("extensions", '["developer"]'))
    cfg["blocked_extensions"] = json.loads(cfg.get("blocked_extensions", "[]"))
    return cfg


async def _get_memory(db: AsyncSession, agent_id: str) -> list[dict]:
    rows = await db.execute(
        select(memory_entries).where(memory_entries.c.agent_id == agent_id)
    )
    return [dict(r) for r in rows.mappings()]


async def _get_skills(db: AsyncSession, agent_id: str) -> list[dict]:
    rows = await db.execute(
        select(skills_table).where(skills_table.c.agent_id == agent_id)
    )
    result = []
    for r in rows.mappings():
        s = dict(r)
        s["steps"] = json.loads(s.get("steps", "[]"))
        result.append(s)
    return result


def _sanitize_user_content(text: str) -> str:
    """Indent lines starting with ## to prevent section-header injection in the preamble."""
    lines = text.split("\n")
    return "\n".join(
        f"  {line}" if line.lstrip().startswith("##") else line
        for line in lines
    )


async def assemble_context_preamble(db: AsyncSession, agent_id: str) -> str:
    """Build the preamble injected as the first prompt turn per BUILD_SPEC §8."""
    agent = await get_agent(db, agent_id)
    if not agent:
        raise ValueError(f"Agent {agent_id} not found")

    lines = [
        f"## Role\n{agent['role']} — {agent['name']}",
        f"\n## Instructions\n{agent['system_prompt']}",
    ]

    if agent.get("memory"):
        mem_lines = "\n".join(
            f"- {m['key']}: {_sanitize_user_content(m['value'])}"
            for m in agent["memory"]
        )
        lines.append(f"\n## Memory (persistent facts — honor these)\n{mem_lines}")

    if agent.get("skills"):
        skill_blocks = []
        for s in agent["skills"]:
            steps = "\n".join(
                f"{i+1}. {_sanitize_user_content(step)}"
                for i, step in enumerate(s["steps"])
            )
            skill_blocks.append(f"### {s['name']}\n{steps}")
        lines.append("\n## Skills (follow the matching procedure step by step)\n" + "\n".join(skill_blocks))

    cfg = agent.get("config", {})
    if cfg.get("requires_approval"):
        lines.append("\n## Interaction rules\nDestructive or irreversible actions are pre-approved by the operator for this run.")

    return "\n".join(lines)
