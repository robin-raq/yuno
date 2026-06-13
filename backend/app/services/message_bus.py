"""Internal message-bus foundation for workflow execution (S2 Unit 4).

Provides the two halves later units (worker, orchestrator) build on:
  - persistence of agent-to-agent messages (`agent_messages` is the trail of record)
  - an in-process FIFO dispatch queue for workflow tasks

Per BUILD_SPEC §11 the sender persists the message row first, then makes the
dispatch item visible on the queue. This module does NOT run a worker, execute
tasks, evaluate edges, or invoke Goose — those are later units.
"""
import asyncio
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import insert, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import agent_messages, agent_tasks, workflow_runs

_QUEUE_MAXSIZE = 1000  # BUILD_SPEC §11: single asyncio.Queue, maxsize=1000


class UnknownRun(Exception):
    """Message references a run id that does not exist."""


class UnknownTask(Exception):
    """Message references a from/to task id that does not exist."""


@dataclass
class AgentMessageDraft:
    """An unsaved agent message (envelope per §11; id/created_at assigned on persist)."""
    run_id: str | None
    from_task_id: str | None
    to_task_id: str | None
    msg_type: str
    payload: dict = field(default_factory=dict)


@dataclass
class WorkflowDispatchItem:
    """A unit of work for the future worker — everything it needs to run one task."""
    run_id: str
    task_id: str
    agent_id: str
    node_id: str
    input: str


class InMemoryWorkflowQueue:
    """Thin FIFO wrapper over asyncio.Queue. Injectable/resettable so tests never
    share state. `size()` is a test-and-monitor inspection helper."""

    def __init__(self, maxsize: int = _QUEUE_MAXSIZE) -> None:
        self._q: asyncio.Queue[WorkflowDispatchItem] = asyncio.Queue(maxsize=maxsize)

    async def enqueue(self, item: WorkflowDispatchItem) -> None:
        await self._q.put(item)

    async def dequeue(self) -> WorkflowDispatchItem:
        return await self._q.get()

    def try_dequeue(self) -> "WorkflowDispatchItem | None":
        """Non-blocking dequeue; returns None if the queue is empty."""
        try:
            return self._q.get_nowait()
        except asyncio.QueueEmpty:
            return None

    def size(self) -> int:
        return self._q.qsize()


class MessageBusService:
    """Persist-then-enqueue message delivery over an injectable queue."""

    def __init__(self, queue: InMemoryWorkflowQueue | None = None) -> None:
        self.queue = queue or InMemoryWorkflowQueue()

    async def persist_message(self, db: AsyncSession, draft: AgentMessageDraft) -> dict:
        """Validate targets, then write the agent_messages row. Raises (and rolls
        back) before any insert if a referenced run/task does not exist —
        SQLite does not enforce these FKs, so the check is explicit."""
        await self._require_run(db, draft.run_id)
        await self._require_task(db, draft.from_task_id)
        await self._require_task(db, draft.to_task_id)

        msg_id = str(uuid.uuid4())
        # Explicit ISO timestamp (the server default is 1-second granularity).
        # Deterministic message order comes from the rowid tiebreak in list_messages,
        # not from the timestamp alone — isoformat() omits microseconds when they are 0.
        created_at = datetime.now(timezone.utc).isoformat()
        try:
            await db.execute(insert(agent_messages).values(
                id=msg_id,
                run_id=draft.run_id,
                from_task_id=draft.from_task_id,
                to_task_id=draft.to_task_id,
                msg_type=draft.msg_type,
                payload=json.dumps(draft.payload),
                created_at=created_at,
            ))
            await db.commit()
        except Exception:
            await db.rollback()
            raise

        return {
            "id": msg_id,
            "run_id": draft.run_id,
            "from_task_id": draft.from_task_id,
            "to_task_id": draft.to_task_id,
            "msg_type": draft.msg_type,
            "payload": draft.payload,
            "created_at": created_at,
        }

    async def enqueue_task(self, item: WorkflowDispatchItem) -> None:
        await self.queue.enqueue(item)

    async def deliver(
        self, db: AsyncSession, draft: AgentMessageDraft, dispatch: WorkflowDispatchItem
    ) -> dict:
        """§11 delivery: persist the message (committed) first; only on success
        make the dispatch item visible on the queue. If persistence raises, the
        item is never enqueued."""
        message = await self.persist_message(db, draft)
        await self.enqueue_task(dispatch)
        return message

    async def dequeue(self) -> WorkflowDispatchItem:
        return await self.queue.dequeue()

    def try_dequeue(self) -> "WorkflowDispatchItem | None":
        """Non-blocking dequeue; returns None if the queue is empty."""
        return self.queue.try_dequeue()

    def queue_size(self) -> int:
        return self.queue.size()

    async def list_messages(self, db: AsyncSession, run_id: str) -> list[dict]:
        """Run's message trail in created order (created_at, then rowid tiebreak)."""
        rows = await db.execute(
            select(agent_messages)
            .where(agent_messages.c.run_id == run_id)
            .order_by(agent_messages.c.created_at, text("rowid"))
        )
        out: list[dict] = []
        for m in rows.mappings():
            d = dict(m)
            d["payload"] = json.loads(d["payload"])
            out.append(d)
        return out

    async def _require_run(self, db: AsyncSession, run_id: str | None) -> None:
        if run_id is None:
            return
        row = await db.execute(select(workflow_runs.c.id).where(workflow_runs.c.id == run_id))
        if row.first() is None:
            raise UnknownRun(run_id)

    async def _require_task(self, db: AsyncSession, task_id: str | None) -> None:
        if task_id is None:
            return
        row = await db.execute(select(agent_tasks.c.id).where(agent_tasks.c.id == task_id))
        if row.first() is None:
            raise UnknownTask(task_id)
