"""Workflow worker — S2 Units 5–6.

Consumes one WorkflowDispatchItem at a time from the MessageBus queue,
executes it through the Goose adapter, persists task and run lifecycle
events per BUILD_SPEC §12, and advances the workflow graph on success.

Dispatch semantics: **at-most-once, in-memory**. `try_dequeue` removes the
item before processing; retry, requeue, idempotency, stale-dispatch protection,
multi-task run-status precedence, and loop cap are deferred.

Two independent error domains:
1. Adapter execution error (get_agent/context assembly/invoke/timeout) → task
   AND run marked failed via _record_failure.
2. Graph traversal error (advance_after_task_completion) → task stays completed;
   only the run is marked failed via _record_run_failed_post_completion.

Other design constraints:
- Step 1 (mark running + task_started) commits first so the session is clean.
- Context assembly runs INSIDE the adapter-error try-block (B1 fix).
- adapter.invoke is wrapped in asyncio.wait_for per BUILD_SPEC §9 L497 (B2 fix).
- Failure paths use a fresh AsyncSessionLocal session (S1 "Finding #6" parity).
- Streaming on_event uses AsyncSessionLocal (one session per event).
- Adapter injected via adapter_cls for unit-test injection.
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
from app.services.workflow_graph import advance_after_task_completion

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

        Error domain 1 (adapter): context assembly + invoke + timeout. Any
        exception → _record_failure (task AND run fail).

        Error domain 2 (graph): advance_after_task_completion. Any exception →
        _record_run_failed_post_completion (task stays completed; only run fails).
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

        # Task succeeded. Commit task completion first (clean error domain boundary).
        await self._record_task_completed(db, item, result)

        # Graph advancement is a separate error domain: if it fails, the task
        # stays completed and only the run is marked failed.
        try:
            next_info = await advance_after_task_completion(
                db, item, result.output, self.bus
            )
        except Exception as exc:
            await self._record_run_failed_post_completion(db, item, exc)
            return

        if next_info is None:
            # Terminal node — no outgoing matched edges.
            await self._record_run_completed(db, item, result)
        # else: run stays 'running'; next task and message already committed by
        # advance_after_task_completion; dispatch item already enqueued.

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

    # ── Step 4a: task completed (commits before graph advancement) ────────────

    async def _record_task_completed(
        self, db: AsyncSession, item: WorkflowDispatchItem, result: TaskResult
    ) -> None:
        """Commit task completion. Called before advance_after_task_completion so
        the task is definitively completed regardless of graph traversal outcome."""
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
        await db.commit()

    # ── Step 4b: terminal node — run completed ────────────────────────────────

    async def _record_run_completed(
        self, db: AsyncSession, item: WorkflowDispatchItem, result: TaskResult
    ) -> None:
        """Mark run completed and emit workflow_completed. Called only when
        advance_after_task_completion returns None (no matched outgoing edge)."""
        now = datetime.now(timezone.utc).isoformat()
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
        await self._emit(
            db,
            run_id=item.run_id,
            event_type="workflow_completed",
            data={"run_id": item.run_id, "forced_complete": False},
        )
        await db.commit()

    # ── Step 4c: graph traversal failed after task completed ──────────────────

    async def _record_run_failed_post_completion(
        self, db: AsyncSession, item: WorkflowDispatchItem, exc: Exception
    ) -> None:
        """Mark run failed when graph traversal raises after the task completed.

        Task status is NOT changed — it was committed as 'completed' already.
        Only the run is marked failed. Uses a fresh session (same discipline as
        _record_failure) so a poisoned outer session cannot block this write.
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
                "Failed to record graph failure for run %s — run may be stuck in 'running'",
                item.run_id,
            )
            raise

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
