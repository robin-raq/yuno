"""Workflow worker — S2 Unit 5.

Consumes one WorkflowDispatchItem at a time from the MessageBus queue and
executes it through the Goose adapter, persisting task and run lifecycle
events per BUILD_SPEC §12.

Dispatch semantics (this phase): **at-most-once, in-memory**. `try_dequeue`
removes the item before processing; there is no retry, requeue, idempotency,
stale-dispatch protection, or multi-task run semantics yet — all deferred to a
later unit. The worker is explicitly invoked: no background loop, no FastAPI
startup hook.

Design constraints:
- Step 1 (mark running + task_started) commits on the passed `db` session, so
  the session is clean before the adapter call.
- Context assembly (get_agent, preamble, TaskInput) runs INSIDE the
  failure-handled region — a missing agent or context error fails the task and
  run loudly, exactly like an adapter error (BUILD_SPEC §9 L503).
- adapter.invoke is wrapped in asyncio.wait_for(timeout=timeout_seconds) per
  BUILD_SPEC §9 L497 — a TimeoutError fails the task and run.
- The failure path records task_failed/workflow_failed on a FRESH session in
  its own try/except (mirroring S1 task_service "Finding #6"), so a poisoned
  outer session cannot prevent the failure from being recorded. If even that
  fails, it logs that the row may be stuck in 'running' and re-raises.
- Streaming on_event uses AsyncSessionLocal() (one session per event) matching
  the S1 pattern; only exercised in live tests.
- Adapter injected via adapter_cls so unit tests supply a fake without patching.
"""
import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Callable

from sqlalchemy import insert, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.acp_goose import AcpGooseAdapter
from app.adapters.base import TaskInput, TaskResult
from app.database import AsyncSessionLocal
from app.models import agent_tasks, execution_events, workflow_runs
from app.services.agent_service import assemble_context_preamble, get_agent
from app.services.message_bus import MessageBusService, WorkflowDispatchItem

if TYPE_CHECKING:
    from app.adapters.base import AgentRuntimeAdapter

log = logging.getLogger(__name__)

_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 3284
_DEFAULT_MODEL = "claude-haiku-4-5-20251001"


class WorkflowWorker:
    """Dequeues and executes one workflow task at a time."""

    def __init__(
        self,
        bus: MessageBusService,
        host: str = _DEFAULT_HOST,
        port: int = _DEFAULT_PORT,
        adapter_cls: "Callable[..., AgentRuntimeAdapter] | None" = None,
    ) -> None:
        self.bus = bus
        self._host = host
        self._port = port
        self._adapter_cls = adapter_cls or AcpGooseAdapter

    async def process_next(self, db: AsyncSession) -> bool:
        """Dequeue one item (non-blocking) and execute it. Returns False if empty."""
        item = self.bus.try_dequeue()
        if item is None:
            return False
        await self.process_dispatch_item(db, item)
        return True

    async def process_dispatch_item(
        self, db: AsyncSession, item: WorkflowDispatchItem
    ) -> None:
        """Execute one workflow task end-to-end.

        Step 1 marks running and commits. Everything after — context assembly,
        the adapter call, and its timeout — is failure-handled: any exception
        routes through _record_failure, so the task and run never stay stuck in
        'running'.
        """
        await self._mark_running(db, item)

        try:
            agent = await get_agent(db, item.agent_id)
            preamble = await assemble_context_preamble(db, item.agent_id)
            task_input = self._build_task_input(item, agent, preamble)

            # on_event uses its own session per event (S1 pattern; only exercised
            # in live tests — the mock adapter never calls this).
            async def _persist_event(event: dict) -> None:
                async with AsyncSessionLocal() as s:
                    await s.execute(
                        insert(execution_events).values(
                            id=str(uuid.uuid4()),
                            run_id=item.run_id,
                            task_id=item.task_id,
                            agent_id=item.agent_id,
                            event_type=event.get("type", "tool_called"),
                            data=json.dumps(event),
                        )
                    )
                    await s.commit()

            adapter = self._adapter_cls(host=self._host, port=self._port)
            result = await asyncio.wait_for(
                adapter.invoke(task_input, _persist_event),
                timeout=task_input.timeout_seconds,
            )
        except Exception as exc:
            await self._record_failure(db, item, exc)
            return

        await self._record_success(db, item, result)

    # ── Step 1: mark running ─────────────────────────────────────────────────

    async def _mark_running(self, db: AsyncSession, item: WorkflowDispatchItem) -> None:
        now = datetime.now(timezone.utc).isoformat()
        await db.execute(
            update(workflow_runs)
            .where(workflow_runs.c.id == item.run_id)
            .values(status="running")
        )
        await db.execute(
            update(agent_tasks)
            .where(agent_tasks.c.id == item.task_id)
            .values(status="running", started_at=now)
        )
        await self._emit(
            db,
            run_id=item.run_id,
            event_type="task_started",
            data={"run_id": item.run_id, "task_id": item.task_id, "agent_id": item.agent_id},
            task_id=item.task_id,
            agent_id=item.agent_id,
        )
        await db.commit()

    def _build_task_input(
        self, item: WorkflowDispatchItem, agent: dict | None, preamble: str
    ) -> TaskInput:
        cfg = agent.get("config", {}) if agent else {}
        return TaskInput(
            context_preamble=preamble,
            task_content=item.input,
            model=agent["model"] if agent else _DEFAULT_MODEL,
            extensions=cfg.get("extensions", ["developer"]),
            max_turns=cfg.get("max_turns", 10),
            timeout_seconds=cfg.get("timeout_seconds", 180),
        )

    # ── Step 4a: success ─────────────────────────────────────────────────────

    async def _record_success(
        self, db: AsyncSession, item: WorkflowDispatchItem, result: TaskResult
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        output_preview = (result.output or "")[:200]
        await db.execute(
            update(agent_tasks)
            .where(agent_tasks.c.id == item.task_id)
            .values(
                status="completed",
                output=result.output,
                completed_at=now,
                tokens_used=result.tokens_total,
                cost_usd=result.estimated_cost,
            )
        )
        await self._emit(
            db,
            run_id=item.run_id,
            event_type="task_completed",
            data={"run_id": item.run_id, "task_id": item.task_id, "output_preview": output_preview},
            task_id=item.task_id,
            agent_id=item.agent_id,
        )
        await db.execute(
            update(workflow_runs)
            .where(workflow_runs.c.id == item.run_id)
            .values(
                status="completed",
                completed_at=now,
                total_tokens=result.tokens_total,
                total_cost=result.estimated_cost,
            )
        )
        # Single-node workflow only: this task is the terminal node, so the run
        # completes here. Multi-node edge traversal is deferred to a later unit.
        await self._emit(
            db,
            run_id=item.run_id,
            event_type="workflow_completed",
            data={"run_id": item.run_id, "forced_complete": False},
        )
        await db.commit()

    # ── Step 4b: failure (fresh session, guarded — S1 "Finding #6") ──────────

    async def _record_failure(
        self, db: AsyncSession, item: WorkflowDispatchItem, exc: Exception
    ) -> None:
        """Record task_failed/workflow_failed on a fresh session, guarded.

        A context-assembly read may have left an open transaction on the shared
        connection, so reset the outer session first, then write the failure on
        a fresh session that a poisoned outer session cannot block. If even the
        failure write fails, log that the row may be stuck in 'running' and
        re-raise rather than swallow the error.
        """
        error = str(exc) or exc.__class__.__name__
        try:
            await db.rollback()
        except Exception:
            pass
        now = datetime.now(timezone.utc).isoformat()
        try:
            async with AsyncSessionLocal() as fail_db:
                await fail_db.execute(
                    update(agent_tasks)
                    .where(agent_tasks.c.id == item.task_id)
                    .values(status="failed", output=error, completed_at=now)
                )
                await self._emit(
                    fail_db,
                    run_id=item.run_id,
                    event_type="task_failed",
                    data={
                        "run_id": item.run_id,
                        "task_id": item.task_id,
                        "agent_id": item.agent_id,
                        "error": error,
                    },
                    task_id=item.task_id,
                    agent_id=item.agent_id,
                )
                await fail_db.execute(
                    update(workflow_runs)
                    .where(workflow_runs.c.id == item.run_id)
                    .values(status="failed", completed_at=now)
                )
                await self._emit(
                    fail_db,
                    run_id=item.run_id,
                    event_type="workflow_failed",
                    data={"run_id": item.run_id, "reason": error},
                )
                await fail_db.commit()
        except Exception:
            log.exception(
                "Failed to record failure for task %s — task/run may be stuck in 'running'",
                item.task_id,
            )
            raise

    # ── Event persistence helper ─────────────────────────────────────────────

    async def _emit(
        self,
        session: AsyncSession,
        *,
        run_id: str,
        event_type: str,
        data: dict,
        task_id: str | None = None,
        agent_id: str | None = None,
    ) -> None:
        """Insert one execution_events row. Run-level events omit task_id/agent_id."""
        await session.execute(
            insert(execution_events).values(
                id=str(uuid.uuid4()),
                run_id=run_id,
                task_id=task_id,
                agent_id=agent_id,
                event_type=event_type,
                data=json.dumps(data),
            )
        )
