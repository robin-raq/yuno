"""Execution event bus — S2 Unit 8.

Persists every event to execution_events, then fans out to in-process SSE
subscriber queues. BUILD_SPEC §12: persist before deliver; reconnect uses
GET /runs/{id}/events for history then resubscribes to GET /events.
"""
import asyncio
import json
import logging
import uuid

from sqlalchemy import insert, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import execution_events

log = logging.getLogger(__name__)

_SUBSCRIBER_QUEUE_MAXSIZE = 1000


class EventService:
    """In-process pub/sub over execution_events persistence."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue]] = {}

    def subscribe(self, channel: str) -> asyncio.Queue:
        """Register a live SSE subscriber for run_id or agent_id."""
        queue: asyncio.Queue = asyncio.Queue(maxsize=_SUBSCRIBER_QUEUE_MAXSIZE)
        self._subscribers.setdefault(channel, []).append(queue)
        return queue

    def unsubscribe(self, channel: str, queue: asyncio.Queue) -> None:
        subs = self._subscribers.get(channel, [])
        if queue in subs:
            subs.remove(queue)
        if not subs:
            self._subscribers.pop(channel, None)

    async def emit(
        self,
        db: AsyncSession,
        *,
        event_type: str,
        data: dict,
        run_id: str | None = None,
        agent_id: str | None = None,
        task_id: str | None = None,
    ) -> dict:
        """Insert one execution_events row (caller commits) and fan out immediately."""
        event_id = str(uuid.uuid4())
        await db.execute(insert(execution_events).values(
            id=event_id,
            run_id=run_id,
            agent_id=agent_id,
            task_id=task_id,
            event_type=event_type,
            data=json.dumps(data),
        ))
        envelope = {
            "id": event_id,
            "run_id": run_id,
            "agent_id": agent_id,
            "task_id": task_id,
            "event_type": event_type,
            "data": data,
        }
        channel = run_id or agent_id
        if channel:
            self._fan_out(channel, envelope)
        return envelope

    def notify(self, channel: str, envelope: dict) -> None:
        """Fan-out only — for callers that already persisted inside a transaction."""
        self._fan_out(channel, envelope)

    async def list_run_events(self, db: AsyncSession, run_id: str) -> list[dict]:
        rows = await db.execute(
            select(execution_events)
            .where(execution_events.c.run_id == run_id)
            .order_by(execution_events.c.created_at, text("rowid"))
        )
        return [_decode_event_row(r) for r in rows.mappings()]

    async def list_agent_events(self, db: AsyncSession, agent_id: str) -> list[dict]:
        rows = await db.execute(
            select(execution_events)
            .where(execution_events.c.agent_id == agent_id)
            .where(execution_events.c.run_id.is_(None))
            .order_by(execution_events.c.created_at, text("rowid"))
        )
        return [_decode_event_row(r) for r in rows.mappings()]

    def _fan_out(self, channel: str, envelope: dict) -> None:
        for queue in self._subscribers.get(channel, []):
            try:
                queue.put_nowait(envelope)
            except asyncio.QueueFull:
                log.warning("sse_subscriber_lagging", extra={"channel": channel})


def _decode_event_row(row) -> dict:
    d = dict(row)
    d["data"] = json.loads(d["data"])
    return d


_event_service: EventService | None = None


def get_event_service() -> EventService:
    global _event_service
    if _event_service is None:
        _event_service = EventService()
    return _event_service


def reset_event_service() -> None:
    """Test helper — drop all subscribers between tests."""
    global _event_service
    _event_service = EventService()
