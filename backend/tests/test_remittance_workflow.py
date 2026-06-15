"""U9 — Remittance workflow integration tests.

Drives the seeded Remittance Comparison graph through the worker with a
programmable fake for Research/Analyst and the real ComplianceAdapter.
"""
from __future__ import annotations

import json
from collections import deque
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select, text

from app.adapters.base import TaskInput, TaskResult
from app.domain.remittance.research import assemble_brief
from app.domain.remittance.types import (
    ROUTE_ANALYST_NEEDS_MORE_DATA,
    ROUTE_ANALYST_RECOMMENDATION,
    ROUTE_COMPLIANCE_CLEARED,
)
from app.models import agent_tasks, agents, execution_events, workflow_nodes, workflow_runs, workflows
from app.services import workflow_service
from app.services.message_bus import InMemoryWorkflowQueue, MessageBusService, WorkflowDispatchItem
from app.services.workflow_worker import WorkflowWorker
from scripts.seed_db import populate_seed

FIXTURE_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "transfer_fixture.json"
MEMORY_DEFAULTS = {
    "sender_city": "Austin, TX",
    "sender_country": "US",
    "recipient_country": "Colombia",
    "recipient_city": "Bogotá",
    "send_currency": "USD",
    "receive_currency": "COP",
}


def _brief_json(amount_text: str = "send $500 cash to Bogotá") -> str:
    brief = assemble_brief(
        amount_text,
        memory_defaults=MEMORY_DEFAULTS,
        fixture_path=FIXTURE_PATH,
    )
    return json.dumps(brief.to_dict())


def _brief_json_flagged_3500() -> str:
    return _brief_json("send $3500 cash to Bogotá")


def _brief_json_missing_flag() -> str:
    brief = assemble_brief(
        "send $500 cash to Bogotá",
        memory_defaults=MEMORY_DEFAULTS,
        fixture_path=FIXTURE_PATH,
    )
    data = brief.to_dict()
    data["sender_profile"] = {"kyc_verified": True, "account_tier": "standard"}
    return json.dumps(data)


def _brief_json_missing_rate() -> str:
    """Valid for Compliance screening; Analyst returns NEEDS_MORE_DATA via missing_fields."""
    data = json.loads(_brief_json())
    data["missing_fields"] = ["moneygram.rate_cop"]
    return json.dumps(data)


def _recommendation_output() -> str:
    return (
        f"{ROUTE_ANALYST_RECOMMENDATION}\n"
        "RECOMMENDATION: MoneyGram\n"
        "Fee $9.99 · Rate 4,155 COP/USD · You receive 2,035,992 COP\n"
        "Full report: reports/transfer_comparison.md"
    )


def _needs_more_data_output(field: str = "moneygram.rate_cop") -> str:
    return f"{ROUTE_ANALYST_NEEDS_MORE_DATA}\nMissing: {field}"


def make_remittance_fake_adapter(
    research_outputs: list[str],
    analyst_outputs: list[str] | None = None,
    *,
    analyst_handler=None,
):
    """Fake adapter for Research and Analyst nodes; Compliance stays scripted."""
    research_q: deque[str] = deque(research_outputs)
    analyst_q: deque[str] = deque(analyst_outputs or [])

    class _Fake:
        def __init__(self, host="127.0.0.1", port=3284):
            pass

        async def invoke(self, task: TaskInput, on_event) -> TaskResult:
            content = task.task_content or ""
            is_analyst = False
            try:
                data = json.loads(content)
                is_analyst = isinstance(data, dict) and "brief" in data and "compliance" in data
            except json.JSONDecodeError:
                is_analyst = (
                    "Score providers" in content
                    or ROUTE_COMPLIANCE_CLEARED in content
                )
            if is_analyst:
                if analyst_handler is not None:
                    return await analyst_handler(task, on_event)
                if not analyst_q:
                    raise RuntimeError("unexpected Analyst invoke — queue empty")
                return TaskResult(output=analyst_q.popleft())
            if not research_q:
                raise RuntimeError("unexpected Research invoke — queue empty")
            return TaskResult(output=research_q.popleft())

        async def health_check(self) -> bool:
            return True

    return _Fake


async def _agent_ids(db) -> dict[str, str]:
    rows = (await db.execute(select(agents.c.name, agents.c.id))).mappings().all()
    return {row["name"]: row["id"] for row in rows}


async def _remittance_workflow_id(db) -> str:
    return (
        await db.execute(
            select(workflows.c.id).where(workflows.c.template_key == "remittance_comparison")
        )
    ).scalar_one()


async def _drain_worker(worker: WorkflowWorker, db, *, max_steps: int = 20) -> int:
    steps = 0
    while True:
        item = worker.bus.try_dequeue()
        if item is None:
            break
        await worker.process_dispatch_item(db, item)
        steps += 1
        if steps > max_steps:
            raise AssertionError(f"drain exceeded {max_steps} steps")
    return steps


async def _run_remittance(
    db,
    *,
    research_outputs: list[str],
    analyst_outputs: list[str] | None = None,
    analyst_handler=None,
    initial_input: str = "send $500 cash to Bogotá",
):
    await populate_seed(db)
    await db.commit()
    wf_id = await _remittance_workflow_id(db)
    run = await workflow_service.start_run(db, wf_id, initial_input)
    run_id = run["run_id"]

    first_task = (
        await db.execute(
            select(agent_tasks)
            .where(agent_tasks.c.run_id == run_id)
            .order_by(text("rowid"))
        )
    ).mappings().one()

    bus = MessageBusService(InMemoryWorkflowQueue())
    worker = WorkflowWorker(
        bus,
        adapter_cls=make_remittance_fake_adapter(
            research_outputs,
            analyst_outputs,
            analyst_handler=analyst_handler,
        ),
    )
    await bus.enqueue_task(WorkflowDispatchItem(
        run_id=run_id,
        task_id=first_task["id"],
        agent_id=first_task["agent_id"],
        node_id=first_task["node_id"],
        input=first_task["input"],
    ))
    await _drain_worker(worker, db)
    return run_id


async def _tasks_by_agent(db, run_id: str) -> dict[str, list[dict]]:
    ids = await _agent_ids(db)
    name_by_id = {v: k for k, v in ids.items()}
    rows = (
        await db.execute(
            select(agent_tasks)
            .where(agent_tasks.c.run_id == run_id)
            .order_by(text("rowid"))
        )
    ).mappings().all()
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        name = name_by_id[row["agent_id"]]
        grouped.setdefault(name, []).append(dict(row))
    return grouped


async def _run_row(db, run_id: str) -> dict:
    return (
        await db.execute(select(workflow_runs).where(workflow_runs.c.id == run_id))
    ).mappings().one()


# ── FLAGGED stop ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_flagged_amount_stops_before_analyst(db):
    run_id = await _run_remittance(db, research_outputs=[_brief_json_flagged_3500()])
    by_agent = await _tasks_by_agent(db, run_id)
    run = await _run_row(db, run_id)

    assert "Analyst" not in by_agent
    assert len(by_agent["Compliance"]) == 1
    assert by_agent["Compliance"][0]["output"].startswith("COMPLIANCE=FLAGGED")
    assert run["status"] == "completed"
    assert run["forced_complete"] == 0


@pytest.mark.asyncio
async def test_flagged_sentinel_does_not_route_to_analyst(db):
    """KTD6: COMPLIANCE=FLAGGED must not match the CLEARED edge → Analyst never runs."""
    run_id = await _run_remittance(db, research_outputs=[_brief_json_missing_flag()])
    by_agent = await _tasks_by_agent(db, run_id)
    run = await _run_row(db, run_id)

    assert "Analyst" not in by_agent
    output = by_agent["Compliance"][0]["output"]
    assert output.startswith("COMPLIANCE=FLAGGED")
    assert "COMPLIANCE=CLEARED" not in output
    assert run["status"] == "completed"


# ── NEEDS_MORE_DATA loop with targeted re-request (U12) ───────────────────────

@pytest.mark.asyncio
async def test_needs_more_data_loops_with_feedback_in_research_input(db, monkeypatch, tmp_path):
    monkeypatch.setattr(
        "app.adapters.analyst_adapter._DEFAULT_REPORTS_DIR",
        tmp_path / "reports",
    )
    missing = "moneygram.rate_cop"
    run_id = await _run_remittance(
        db,
        research_outputs=[_brief_json_missing_rate(), _brief_json()],
    )
    by_agent = await _tasks_by_agent(db, run_id)
    run = await _run_row(db, run_id)

    assert len(by_agent["Research"]) == 2
    looped_input = by_agent["Research"][1]["input"]
    assert missing in looped_input
    assert len(by_agent["Analyst"]) == 2
    assert by_agent["Analyst"][0]["output"].startswith("ANALYST=NEEDS_MORE_DATA")
    assert by_agent["Analyst"][1]["output"].startswith("ANALYST=RECOMMENDATION")
    assert run["status"] == "completed"
    assert run["forced_complete"] == 0

    feedback_events = (
        await db.execute(
            select(execution_events)
            .where(execution_events.c.run_id == run_id)
            .where(execution_events.c.event_type == "feedback_sent")
        )
    ).mappings().all()
    assert len(feedback_events) == 1


# ── Loop cap ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_needs_more_data_loop_caps_at_two(db, monkeypatch, tmp_path):
    monkeypatch.setattr(
        "app.adapters.analyst_adapter._DEFAULT_REPORTS_DIR",
        tmp_path / "reports",
    )
    run_id = await _run_remittance(
        db,
        research_outputs=[_brief_json_missing_rate()] * 3,
    )
    by_agent = await _tasks_by_agent(db, run_id)
    run = await _run_row(db, run_id)

    assert len(by_agent["Research"]) == 3
    assert len(by_agent["Analyst"]) == 3
    assert all(
        t["output"].startswith("ANALYST=NEEDS_MORE_DATA")
        for t in by_agent["Analyst"]
    )
    assert run["status"] == "completed"
    assert run["forced_complete"] == 1

    capped = (
        await db.execute(
            select(execution_events)
            .where(execution_events.c.run_id == run_id)
            .where(execution_events.c.event_type == "feedback_loop_capped")
        )
    ).mappings().all()
    assert len(capped) == 1


# ── Recommended success ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cleared_path_completes_with_recommendation(db, monkeypatch, tmp_path):
    monkeypatch.setattr(
        "app.adapters.analyst_adapter._DEFAULT_REPORTS_DIR",
        tmp_path / "reports",
    )
    run_id = await _run_remittance(db, research_outputs=[_brief_json()])
    by_agent = await _tasks_by_agent(db, run_id)
    run = await _run_row(db, run_id)

    assert set(by_agent) == {"Research", "Compliance", "Analyst"}
    assert by_agent["Compliance"][0]["output"].startswith("COMPLIANCE=CLEARED")
    assert by_agent["Analyst"][0]["output"].startswith("ANALYST=RECOMMENDATION")
    assert "RECOMMENDATION: MoneyGram" in by_agent["Analyst"][0]["output"]
    assert run["status"] == "completed"
    assert run["forced_complete"] == 0
    assert (tmp_path / "reports" / "transfer_comparison.md").exists()


@pytest.mark.asyncio
async def test_analyst_receives_analyst_input_json(db):
    """Compliance→Analyst forward handoff must pass AnalystInput JSON, not compliance prose."""
    run_id = await _run_remittance(
        db,
        research_outputs=[_brief_json()],
        analyst_outputs=[_recommendation_output()],
    )
    by_agent = await _tasks_by_agent(db, run_id)
    payload = json.loads(by_agent["Analyst"][0]["input"])
    research_brief = json.loads(by_agent["Research"][0]["output"])

    assert payload["brief"]["amount_usd"] == research_brief["amount_usd"] == 500.0
    assert payload["compliance"]["status"] == "CLEARED"
    assert ROUTE_COMPLIANCE_CLEARED not in by_agent["Analyst"][0]["input"]


# ── Real analyst output routing (anti-laundering guard F3) ────────────────────

@pytest.mark.asyncio
async def test_real_analyst_output_routes_to_completion_not_loop(db, monkeypatch, tmp_path):
    monkeypatch.setattr(
        "app.adapters.analyst_adapter._DEFAULT_REPORTS_DIR",
        tmp_path / "reports",
    )
    run_id = await _run_remittance(db, research_outputs=[_brief_json()])
    by_agent = await _tasks_by_agent(db, run_id)
    run = await _run_row(db, run_id)

    assert len(by_agent["Analyst"]) == 1
    output = by_agent["Analyst"][0]["output"]
    assert output.startswith("ANALYST=RECOMMENDATION")
    assert ROUTE_ANALYST_NEEDS_MORE_DATA not in output
    assert "MoneyGram" in output
    assert run["status"] == "completed"
    assert run["forced_complete"] == 0
    assert (tmp_path / "reports" / "transfer_comparison.md").exists()
