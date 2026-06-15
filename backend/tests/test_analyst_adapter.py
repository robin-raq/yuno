"""AnalystAdapter — deterministic Analyst node behind AgentRuntimeAdapter."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.adapters.analyst_adapter import AnalystAdapter
from app.adapters.base import AgentRuntimeAdapter, TaskInput
from app.domain.remittance.analyst import compose_analyst_task_input
from app.domain.remittance.compliance import format_output, screen_from_dict
from app.domain.remittance.research import assemble_brief
from app.domain.remittance.types import (
    ROUTE_ANALYST_NEEDS_MORE_DATA,
    ROUTE_ANALYST_RECOMMENDATION,
    AnalystInput,
)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
RULES_PATH = FIXTURES / "compliance_rules.json"
FIXTURE_PATH = FIXTURES / "transfer_fixture.json"
MEMORY_DEFAULTS = {
    "sender_city": "Austin, TX",
    "sender_country": "US",
    "recipient_country": "Colombia",
    "recipient_city": "Bogotá",
    "send_currency": "USD",
    "receive_currency": "COP",
}


def _task(content: str) -> TaskInput:
    return TaskInput(
        context_preamble="",
        task_content=content,
        model="none",
        extensions=[],
        max_turns=1,
        timeout_seconds=30,
    )


async def _no_event(event: dict) -> None:
    raise AssertionError(f"AnalystAdapter must not call on_event; got {event!r}")


def _analyst_input_json(amount_text: str = "send $500 cash to Bogotá") -> str:
    brief = assemble_brief(
        amount_text,
        memory_defaults=MEMORY_DEFAULTS,
        fixture_path=FIXTURE_PATH,
    )
    compliance = screen_from_dict(brief.to_dict(), rules_path=RULES_PATH)
    return compose_analyst_task_input(json.dumps(brief.to_dict()), format_output(compliance))


@pytest.fixture
def adapter(tmp_path: Path) -> AnalystAdapter:
    return AnalystAdapter(reports_dir=tmp_path / "reports")


def test_analyst_adapter_conforms_to_interface():
    assert issubclass(AnalystAdapter, AgentRuntimeAdapter)


def test_compose_analyst_task_input_round_trips():
    payload = _analyst_input_json()
    restored = AnalystInput.from_dict(json.loads(payload))
    assert restored.brief.amount_usd == 500.0
    assert restored.compliance.status == "CLEARED"


def test_compose_analyst_task_input_parses_prose_wrapped_brief():
    brief = assemble_brief(
        "send $500 cash to Bogotá",
        memory_defaults=MEMORY_DEFAULTS,
        fixture_path=FIXTURE_PATH,
    )
    compliance = screen_from_dict(brief.to_dict(), rules_path=RULES_PATH)
    wrapped_brief = f"Research complete.\n{json.dumps(brief.to_dict())}\nThanks."
    payload = compose_analyst_task_input(wrapped_brief, format_output(compliance))
    restored = AnalystInput.from_dict(json.loads(payload))
    assert restored.brief.amount_usd == 500.0
    assert restored.compliance.status == "CLEARED"


@pytest.mark.asyncio
async def test_invoke_recommendation_from_prose_wrapped_analyst_input(adapter):
    payload = _analyst_input_json()
    wrapped = f"Analyst input follows:\n```json\n{payload}\n```"
    result = await adapter.invoke(_task(wrapped), _no_event)
    assert result.output.splitlines()[0] == ROUTE_ANALYST_RECOMMENDATION


@pytest.mark.asyncio
async def test_invoke_recommendation_from_analyst_input(adapter):
    result = await adapter.invoke(_task(_analyst_input_json()), _no_event)
    assert result.output.splitlines()[0] == ROUTE_ANALYST_RECOMMENDATION
    assert "RECOMMENDATION: MoneyGram" in result.output
    assert (adapter._reports_dir / "transfer_comparison.md").exists()


@pytest.mark.asyncio
async def test_invoke_rejects_compliance_prose_only(adapter):
    brief = assemble_brief(
        "send $500 cash to Bogotá",
        memory_defaults=MEMORY_DEFAULTS,
        fixture_path=FIXTURE_PATH,
    )
    compliance_only = format_output(
        screen_from_dict(brief.to_dict(), rules_path=RULES_PATH)
    )
    result = await adapter.invoke(_task(compliance_only), _no_event)
    assert result.output.splitlines()[0] == ROUTE_ANALYST_NEEDS_MORE_DATA
    assert "could not be processed" in result.output.lower()
