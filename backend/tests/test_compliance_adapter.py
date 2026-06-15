"""Phase B / U5 — ComplianceAdapter tests (test-first).

Verifies that ComplianceAdapter conforms to AgentRuntimeAdapter, applies the
U4 compliance engine deterministically, produces KTD6 sentinel output on line 1,
and fails closed on every bad-input path without touching Goose, DB, or network.

Pure function — no Goose, no DB, no live network calls.
"""
import json
from pathlib import Path

import pytest

from app.adapters.base import AgentRuntimeAdapter, TaskInput
from app.adapters.compliance_adapter import ComplianceAdapter
from app.domain.remittance.compliance import format_output, screen_from_dict
from app.domain.remittance.types import ROUTE_COMPLIANCE_CLEARED
from app.services.workflow_graph import edge_matches

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
RULES_PATH = FIXTURES / "compliance_rules.json"


# ── Test helpers ───────────────────────────────────────────────────────────────

def _task(content: str) -> TaskInput:
    return TaskInput(
        context_preamble="",
        task_content=content,
        model="none",
        extensions=[],
        max_turns=1,
        timeout_seconds=30,
    )


def _valid_brief() -> dict:
    """Return a mutable $500 USD→COP cash_send brief dict with a clean sender profile."""
    return {
        "transfer_type": "cash_send",
        "amount_usd": 500.0,
        "sender_city": "Austin, TX",
        "sender_country": "US",
        "recipient_country": "Colombia",
        "recipient_city": "Bogotá",
        "send_currency": "USD",
        "receive_currency": "COP",
        "data_source": "fixture",
        "sender_profile": {
            "previously_flagged": False,
            "kyc_verified": True,
            "account_tier": "standard",
        },
        "missing_fields": [],
    }


async def _no_event(event: dict) -> None:
    raise AssertionError(
        f"ComplianceAdapter must not call on_event (deterministic, no Goose); got {event!r}"
    )


@pytest.fixture
def adapter() -> ComplianceAdapter:
    return ComplianceAdapter(rules_path=RULES_PATH)


# ── 1. Interface conformance ──────────────────────────────────────────────────

def test_compliance_adapter_conforms_to_interface():
    """ComplianceAdapter must be a concrete subclass of AgentRuntimeAdapter."""
    assert issubclass(ComplianceAdapter, AgentRuntimeAdapter)
    assert isinstance(ComplianceAdapter(rules_path=RULES_PATH), AgentRuntimeAdapter)


def test_host_port_accepted_and_ignored():
    """Constructor accepts host/port for swap-compatibility with AcpGooseAdapter."""
    a = ComplianceAdapter(host="goose.local", port=9000, rules_path=RULES_PATH)
    assert isinstance(a, AgentRuntimeAdapter)


# ── 2. Happy path: $500 USD→COP → CLEARED ────────────────────────────────────

@pytest.mark.asyncio
async def test_invoke_cleared_500_sentinel_on_line_1(adapter):
    """Valid $500 brief against fixture rules → COMPLIANCE=CLEARED on output line 1."""
    result = await adapter.invoke(_task(json.dumps(_valid_brief())), _no_event)
    assert result.output.splitlines()[0] == "COMPLIANCE=CLEARED"


@pytest.mark.asyncio
async def test_invoke_cleared_returns_zero_tokens(adapter):
    """Scripted adapter emits no tokens and has no cost (no LLM involved)."""
    result = await adapter.invoke(_task(json.dumps(_valid_brief())), _no_event)
    assert result.tokens_total == 0
    assert result.estimated_cost == 0.0


# ── 3. Previously flagged sender → FLAGGED ───────────────────────────────────

@pytest.mark.asyncio
async def test_invoke_flagged_previously_flagged_sender(adapter):
    """previously_flagged=True → COMPLIANCE=FLAGGED on line 1."""
    b = _valid_brief()
    b["sender_profile"]["previously_flagged"] = True
    result = await adapter.invoke(_task(json.dumps(b)), _no_event)
    assert result.output.splitlines()[0] == "COMPLIANCE=FLAGGED"


# ── 4. Missing previously_flagged fails closed (KTD3) ────────────────────────

@pytest.mark.asyncio
async def test_invoke_missing_previously_flagged_fails_closed(adapter):
    """Raw brief dict lacking sender_profile.previously_flagged → COMPLIANCE=FLAGGED (KTD3)."""
    b = _valid_brief()
    del b["sender_profile"]["previously_flagged"]
    result = await adapter.invoke(_task(json.dumps(b)), _no_event)
    assert result.output.splitlines()[0] == "COMPLIANCE=FLAGGED"


# ── 5. sender_profile: null fails closed (KTD3) ──────────────────────────────

@pytest.mark.asyncio
async def test_invoke_null_sender_profile_fails_closed(adapter):
    """``"sender_profile": null`` in the raw payload → COMPLIANCE=FLAGGED, not TypeError."""
    b = _valid_brief()
    b["sender_profile"] = None
    result = await adapter.invoke(_task(json.dumps(b)), _no_event)
    assert result.output.splitlines()[0] == "COMPLIANCE=FLAGGED"


# ── 6. Malformed payload fails closed ────────────────────────────────────────

@pytest.mark.asyncio
async def test_invoke_malformed_payload_fails_closed(adapter):
    """Non-JSON task_content → COMPLIANCE=FLAGGED, no exception raised."""
    result = await adapter.invoke(_task("not json at all"), _no_event)
    assert result.output.splitlines()[0] == "COMPLIANCE=FLAGGED"


@pytest.mark.asyncio
async def test_invoke_empty_payload_fails_closed(adapter):
    """Empty string task_content → COMPLIANCE=FLAGGED, no exception raised."""
    result = await adapter.invoke(_task(""), _no_event)
    assert result.output.splitlines()[0] == "COMPLIANCE=FLAGGED"


@pytest.mark.asyncio
async def test_invoke_incomplete_json_payload_fails_closed(adapter):
    """Structurally valid JSON missing required TransferBrief fields → COMPLIANCE=FLAGGED.

    json.loads succeeds; TransferBrief.from_dict raises KeyError on the absent field.
    The adapter must catch this and fail closed rather than letting KeyError propagate
    to the worker's task_failed path (which would suppress the issue).
    """
    result = await adapter.invoke(_task('{"amount_usd": 500}'), _no_event)
    assert result.output.splitlines()[0] == "COMPLIANCE=FLAGGED"


@pytest.mark.asyncio
async def test_invoke_non_dict_json_fails_closed(adapter):
    """Valid JSON that is not a dict (list, string) → COMPLIANCE=FLAGGED, no AttributeError.

    json.loads succeeds but returns a list; brief_dict.get() raises AttributeError.
    The adapter must catch this and fail closed.
    """
    result = await adapter.invoke(_task('[1, 2, 3]'), _no_event)
    assert result.output.splitlines()[0] == "COMPLIANCE=FLAGGED"


# ── 7. Output uses U4 format_output convention ───────────────────────────────

@pytest.mark.asyncio
async def test_output_matches_format_output_cleared(adapter):
    """Adapter output must equal format_output(screen_from_dict(brief)) exactly."""
    brief = _valid_brief()
    result = await adapter.invoke(_task(json.dumps(brief)), _no_event)
    expected = format_output(screen_from_dict(brief, rules_path=RULES_PATH))
    assert result.output == expected


@pytest.mark.asyncio
async def test_output_matches_format_output_flagged(adapter):
    """Adapter FLAGGED output must equal format_output(screen_from_dict(brief)) exactly."""
    b = _valid_brief()
    b["amount_usd"] = 3001.0  # triggers AML rule
    result = await adapter.invoke(_task(json.dumps(b)), _no_event)
    expected = format_output(screen_from_dict(b, rules_path=RULES_PATH))
    assert result.output == expected


# ── 8. FLAGGED output never contains COMPLIANCE=CLEARED (KTD6 collision guard) ─

@pytest.mark.asyncio
async def test_flagged_output_never_contains_cleared_sentinel(adapter):
    """Every FLAGGED path the adapter can emit must not contain 'COMPLIANCE=CLEARED'."""
    # Build the full set of FLAGGED scenarios reachable through the adapter.
    b_aml = _valid_brief()
    b_aml["amount_usd"] = 3001.0

    b_sender = _valid_brief()
    b_sender["sender_profile"]["previously_flagged"] = True

    b_missing_flag = _valid_brief()
    del b_missing_flag["sender_profile"]["previously_flagged"]

    b_null_profile = _valid_brief()
    b_null_profile["sender_profile"] = None

    scenarios = [
        _task(json.dumps(b_aml)),
        _task(json.dumps(b_sender)),
        _task(json.dumps(b_missing_flag)),
        _task(json.dumps(b_null_profile)),
        _task("not json"),
    ]

    for task in scenarios:
        result = await adapter.invoke(task, _no_event)
        assert result.output.splitlines()[0] == "COMPLIANCE=FLAGGED"
        assert ROUTE_COMPLIANCE_CLEARED not in result.output, (
            f"Sentinel contamination in FLAGGED output: {result.output!r}"
        )
        assert edge_matches(ROUTE_COMPLIANCE_CLEARED, result.output) is False


# ── 9. No Goose, DB, network, or worker dependency ───────────────────────────

@pytest.mark.asyncio
async def test_on_event_never_called(adapter):
    """ComplianceAdapter must never call on_event (it has no Goose stream to forward)."""
    # _no_event raises on any call — if this passes, on_event was not called.
    result = await adapter.invoke(_task(json.dumps(_valid_brief())), _no_event)
    assert result is not None


@pytest.mark.asyncio
async def test_health_check_returns_true_without_server():
    """health_check must return True — no Goose server required."""
    a = ComplianceAdapter(rules_path=RULES_PATH)
    assert await a.health_check() is True
