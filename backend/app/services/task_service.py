"""Single-agent task execution service.

Dispatches tasks through AcpGooseAdapter, persists every event to execution_events,
and updates the agent_task row on completion.
"""
import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone

from sqlalchemy import insert, update, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters import AcpGooseAdapter, TaskInput
from app.database import AsyncSessionLocal
from app.models import agent_tasks, execution_events
from app.services.agent_service import get_agent, assemble_context_preamble

log = logging.getLogger(__name__)

_GOOSE_HOST = os.getenv("GOOSE_HOST", "127.0.0.1")
_GOOSE_PORT = int(os.getenv("GOOSE_PORT", "3284"))


async def submit_task(db: AsyncSession, agent_id: str, input_text: str) -> dict:
    """Create an agent_task and run it synchronously through the adapter."""
    agent = await get_agent(db, agent_id)
    if not agent:
        raise ValueError(f"Agent {agent_id} not found")

    task_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    await db.execute(insert(agent_tasks).values(
        id=task_id,
        run_id=None,
        node_id=None,
        agent_id=agent_id,
        source="conversational",
        status="running",
        input=input_text,
        started_at=now,
    ))
    await db.commit()

    cfg = agent.get("config", {})
    extensions = cfg.get("extensions", ["developer"])
    max_turns = cfg.get("max_turns", 10)
    timeout = cfg.get("timeout_seconds", 180)

    preamble = await assemble_context_preamble(db, agent_id)
    task_input = TaskInput(
        context_preamble=preamble,
        task_content=input_text,
        model=agent["model"],
        extensions=extensions,
        max_turns=max_turns,
        timeout_seconds=timeout,
    )

    # Finding #5 fix: each event gets its own session so intermediate commits
    # don't corrupt the outer session's transaction state.
    async def persist_event(event: dict) -> None:
        async with AsyncSessionLocal() as event_db:
            await event_db.execute(insert(execution_events).values(
                id=str(uuid.uuid4()),
                run_id=None,
                agent_id=agent_id,
                task_id=task_id,
                event_type=event.get("type", "unknown"),
                data=json.dumps(event.get("data", {})),
            ))
            await event_db.commit()

    adapter = AcpGooseAdapter(host=_GOOSE_HOST, port=_GOOSE_PORT)

    try:
        result = await asyncio.wait_for(
            adapter.invoke(task_input, persist_event),
            timeout=timeout,
        )
        completed_at = datetime.now(timezone.utc).isoformat()
        await db.execute(
            update(agent_tasks).where(agent_tasks.c.id == task_id).values(
                status="completed",
                output=result.output,
                tokens_used=result.tokens_total,
                cost_usd=result.estimated_cost,
                completed_at=completed_at,
            )
        )
        await db.execute(insert(execution_events).values(
            id=str(uuid.uuid4()),
            run_id=None,
            agent_id=agent_id,
            task_id=task_id,
            event_type="task_completed",
            data=json.dumps({
                "output": result.output,
                "tokens_total": result.tokens_total,
                "tool_calls": result.tool_calls,
                "estimated_cost": result.estimated_cost,
                "session_id": result.session_id,
            }),
        ))
        await db.commit()
    except Exception as exc:
        log.exception("Task %s failed", task_id)
        # Finding #6 fix: use a separate try/except so a broken outer session
        # doesn't prevent the task row from being marked failed.
        try:
            async with AsyncSessionLocal() as fail_db:
                await fail_db.execute(
                    update(agent_tasks).where(agent_tasks.c.id == task_id).values(
                        status="failed",
                        output=str(exc),
                        completed_at=datetime.now(timezone.utc).isoformat(),
                    )
                )
                await fail_db.execute(insert(execution_events).values(
                    id=str(uuid.uuid4()),
                    run_id=None,
                    agent_id=agent_id,
                    task_id=task_id,
                    event_type="task_failed",
                    data=json.dumps({"error": str(exc)}),
                ))
                await fail_db.commit()
        except Exception:
            log.exception("Failed to record task failure for task %s — row may be stuck in 'running'", task_id)
        raise

    return await get_task_with_events(db, task_id)


async def get_task_with_events(db: AsyncSession, task_id: str) -> dict | None:
    row = await db.execute(select(agent_tasks).where(agent_tasks.c.id == task_id))
    task = row.mappings().first()
    if not task:
        return None
    task = dict(task)
    events_rows = await db.execute(
        select(execution_events)
        .where(execution_events.c.task_id == task_id)
        .order_by(execution_events.c.created_at)
    )
    task["events"] = [dict(e) for e in events_rows.mappings()]
    return task
