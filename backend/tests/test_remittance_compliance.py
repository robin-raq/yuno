"""Phase B / U4 — Compliance rules engine tests (test-first).

Covers R5, R6 and the plan's U4 verification: the five deterministic rules
(restricted-country, AML threshold, ID-requirement note, corridor support,
previously-flagged sender), fail-closed behavior for a missing
``sender_profile.previously_flagged`` field (KTD3), sentinel line-1 contract
(KTD6), and the collision-guard property that a FLAGGED output containing the
word "cleared" never matches the COMPLIANCE=CLEARED edge.

Pure function — no Goose, no DB, no network.
"""
import json
from pathlib import Path

import pytest

from app.domain.remittance.compliance import format_output, screen, screen_from_dict
from app.domain.remittance.types import (
    ROUTE_COMPLIANCE_CLEARED,
    ComplianceResult,
    SenderProfile,
    TransferBrief,
)
from app.services.workflow_graph import edge_matches

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
RULES_PATH = FIXTURES / "compliance_rules.json"


# ── Test helpers ──────────────────────────────────────────────────────────────

def _sender(*, previously_flagged: bool = False, kyc_verified: bool = True,
            account_tier: str = "standard") -> SenderProfile:
    return SenderProfile(
        previously_flagged=previously_flagged,
        kyc_verified=kyc_verified,
        account_tier=account_tier,
    )


def _brief(
    *,
    transfer_type: str = "cash_send",
    amount_usd: float = 500.0,
    sender_country: str = "US",
    recipient_country: str = "Colombia",
    send_currency: str = "USD",
    receive_currency: str = "COP",
    previously_flagged: bool = False,
) -> TransferBrief:
    return TransferBrief(
        transfer_type=transfer_type,
        amount_usd=amount_usd,
        sender_city="Austin, TX",
        sender_country=sender_country,
        recipient_country=recipient_country,
        recipient_city="Bogotá",
        send_currency=send_currency,
        receive_currency=receive_currency,
        data_source="fixture",
        sender_profile=_sender(previously_flagged=previously_flagged),
    )


def _rules_with(tmp_path: Path, **overrides) -> Path:
    """Write a modified compliance_rules.json to tmp_path and return the path."""
    rules = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    rules.update(overrides)
    p = tmp_path / "rules.json"
    p.write_text(json.dumps(rules), encoding="utf-8")
    return p


# ── Rule 1 + Rule 2 + Rule 3 + Rule 4: standard cleared ($500) ───────────────

def test_standard_cleared_500():
    """$500 USD→COP cash send against the stock fixture rules → CLEARED."""
    result = screen(_brief(amount_usd=500.0), rules_path=RULES_PATH)
    assert result.status == "CLEARED"
    assert result.issue is None


def test_cleared_500_has_id_note():
    """ID-requirement note is included for cash sends at or above the threshold."""
    result = screen(_brief(amount_usd=500.0), rules_path=RULES_PATH)
    assert any("ID" in n or "government-issued" in n for n in result.notes)


def test_cleared_500_has_corridor_note():
    """Corridor-support note is included in the CLEARED result."""
    result = screen(_brief(amount_usd=500.0), rules_path=RULES_PATH)
    assert any("corridor" in n.lower() for n in result.notes)


# ── ID requirement boundary (Rule 3) ─────────────────────────────────────────

def test_id_note_absent_below_threshold():
    """$499 cash send — one dollar under the threshold — should carry no ID note."""
    result = screen(_brief(amount_usd=499.0), rules_path=RULES_PATH)
    assert result.status == "CLEARED"
    assert not any("ID" in n or "government-issued" in n for n in result.notes)


def test_id_note_present_at_exact_threshold():
    """$500 cash send — exactly at the threshold — should carry the ID note."""
    result = screen(_brief(amount_usd=500.0), rules_path=RULES_PATH)
    assert any("ID" in n or "government-issued" in n for n in result.notes)


def test_id_note_absent_for_digital_send():
    """ID requirement is cash-only; digital $500 should carry no ID note."""
    result = screen(_brief(amount_usd=500.0, transfer_type="digital_send"), rules_path=RULES_PATH)
    assert result.status == "CLEARED"
    assert not any("ID" in n or "government-issued" in n for n in result.notes)


# ── Rule 2: AML threshold ─────────────────────────────────────────────────────

def test_aml_threshold_flagged():
    """Cash send above the $3000 AML threshold → FLAGGED with threshold in issue."""
    result = screen(_brief(amount_usd=3001.0), rules_path=RULES_PATH)
    assert result.status == "FLAGGED"
    assert result.issue is not None
    assert "3000" in result.issue or "AML" in result.issue.upper()


def test_exactly_at_aml_threshold_is_not_flagged():
    """$3000 exactly at threshold → CLEARED (plan U4: `amount_usd > threshold`, exclusive).

    Decision (Option B): the plan's Approach section uses `>` not `>=`. Real-world
    FinCEN CTR uses at-or-above, but this demo engine follows the plan's explicit
    operator. Documented in AI_USAGE.md U4 threshold decision.
    """
    result = screen(_brief(amount_usd=3000.0), rules_path=RULES_PATH)
    assert result.status == "CLEARED"


def test_aml_threshold_is_cash_only():
    """The AML rule is cash-only; a digital $5000 over USD→COP is CLEARED.

    What this proves: for the default brief (USD→COP corridor, non-flagged sender,
    no restricted countries), a digital send above the $3000 AML threshold is
    CLEARED because (a) the AML rule skips non-cash transfers and (b) no other
    rule triggers on these default parameters.
    """
    result = screen(_brief(amount_usd=5000.0, transfer_type="digital_send"), rules_path=RULES_PATH)
    assert result.status == "CLEARED"


# ── Rule 1: Restricted country ────────────────────────────────────────────────

def test_restricted_recipient_country_flagged(tmp_path):
    """Recipient in restricted_countries → FLAGGED."""
    rules_path = _rules_with(tmp_path, restricted_countries=["Cuba"])
    result = screen(_brief(recipient_country="Cuba"), rules_path=rules_path)
    assert result.status == "FLAGGED"
    assert result.issue is not None
    assert "Cuba" in result.issue or "restricted" in result.issue.lower()


def test_restricted_sender_country_flagged(tmp_path):
    """Sender in restricted_countries → FLAGGED."""
    rules_path = _rules_with(tmp_path, restricted_countries=["Iran"])
    result = screen(_brief(sender_country="Iran"), rules_path=rules_path)
    assert result.status == "FLAGGED"


# ── Rule 4: Corridor support ──────────────────────────────────────────────────

def test_unsupported_corridor_fails_closed(tmp_path):
    """A send/receive pair not in supported_corridors must FLAGGED (fail-closed)."""
    rules_path = _rules_with(
        tmp_path,
        supported_corridors=[{"send": "USD", "receive": "COP", "providers": ["western_union"]}],
    )
    # MXN not in corridors
    result = screen(_brief(receive_currency="MXN"), rules_path=rules_path)
    assert result.status == "FLAGGED"
    assert result.issue is not None


def test_empty_corridors_fails_closed(tmp_path):
    """No supported_corridors at all → FLAGGED (fail-closed, not silently CLEARED)."""
    rules_path = _rules_with(tmp_path, supported_corridors=[])
    result = screen(_brief(), rules_path=rules_path)
    assert result.status == "FLAGGED"


# ── Rule 5: Previously flagged sender ────────────────────────────────────────

def test_previously_flagged_sender_flagged():
    """previously_flagged=True → FLAGGED regardless of amount."""
    result = screen(_brief(amount_usd=100.0, previously_flagged=True), rules_path=RULES_PATH)
    assert result.status == "FLAGGED"
    assert result.issue is not None


def test_previously_flagged_overrides_otherwise_cleared():
    """A $100 send that would otherwise be CLEARED is FLAGGED by the sender flag."""
    result = screen(_brief(amount_usd=100.0, previously_flagged=True), rules_path=RULES_PATH)
    assert result.status == "FLAGGED"


# ── KTD3: Missing previously_flagged fails closed ────────────────────────────

def test_missing_previously_flagged_fails_closed():
    """Raw brief dict lacking sender_profile.previously_flagged → FLAGGED (KTD3).

    The typed SenderProfile cannot represent a missing flag; the seam function
    must intercept before construction and return FLAGGED, never silently False.
    """
    raw = {
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
            # previously_flagged deliberately absent — must fail closed
            "kyc_verified": True,
            "account_tier": "standard",
        },
    }
    result = screen_from_dict(raw, rules_path=RULES_PATH)
    assert result.status == "FLAGGED"
    assert result.issue is not None
    assert "previously_flagged" in result.issue or "absent" in result.issue.lower()


def test_null_sender_profile_fails_closed():
    """Raw brief dict with ``"sender_profile": null`` must fail closed, not raise TypeError.

    ``dict.get(key, default)`` returns the explicit ``None`` value (ignoring the
    default), so the seam uses ``or {}`` to collapse both absent and null into an
    empty dict — which lacks ``previously_flagged`` and therefore returns FLAGGED.
    """
    raw = {
        "transfer_type": "cash_send",
        "amount_usd": 500.0,
        "sender_city": "Austin, TX",
        "sender_country": "US",
        "recipient_country": "Colombia",
        "recipient_city": "Bogotá",
        "send_currency": "USD",
        "receive_currency": "COP",
        "data_source": "fixture",
        "sender_profile": None,
    }
    result = screen_from_dict(raw, rules_path=RULES_PATH)
    assert result.status == "FLAGGED"
    formatted = format_output(result)
    assert formatted.splitlines()[0] == "COMPLIANCE=FLAGGED"


def test_screen_from_dict_passes_through_for_valid_input():
    """When previously_flagged is present, screen_from_dict delegates to screen."""
    raw = {
        "transfer_type": "cash_send",
        "amount_usd": 500.0,
        "sender_city": "Austin, TX",
        "sender_country": "US",
        "recipient_country": "Colombia",
        "recipient_city": "Bogotá",
        "send_currency": "USD",
        "receive_currency": "COP",
        "data_source": "fixture",
        "sender_profile": {"previously_flagged": False, "kyc_verified": True, "account_tier": "standard"},
        "missing_fields": [],
    }
    result = screen_from_dict(raw, rules_path=RULES_PATH)
    assert result.status == "CLEARED"


# ── KTD6: Sentinel line-1 and collision-guard ─────────────────────────────────

def test_format_output_sentinel_is_line_1_for_cleared():
    """format_output must put COMPLIANCE=CLEARED on line 1 (KTD6)."""
    result = ComplianceResult(status="CLEARED", notes=["ID required."])
    out = format_output(result)
    assert out.splitlines()[0] == "COMPLIANCE=CLEARED"


def test_format_output_sentinel_is_line_1_for_flagged():
    """format_output must put COMPLIANCE=FLAGGED on line 1 (KTD6)."""
    result = ComplianceResult(status="FLAGGED", issue="Amount too high.")
    out = format_output(result)
    assert out.splitlines()[0] == "COMPLIANCE=FLAGGED"


def test_collision_guard_flagged_with_cleared_prose():
    """A FLAGGED result whose issue contains 'cleared' must not match the CLEARED edge.

    This is the regression for the KTD6 fail-open bug: an unanchored substring
    matcher would route 'COMPLIANCE=FLAGGED\\nRecipient not cleared...' to Analyst
    because the word 'cleared' appears in the body.
    """
    result = ComplianceResult(
        status="FLAGGED",
        issue="Recipient country is not cleared for the configured corridor.",
    )
    formatted = format_output(result)
    # The probe: prose really does contain 'cleared'.
    assert "cleared" in formatted.lower()
    # The sentinel line must be FLAGGED, not CLEARED.
    assert formatted.splitlines()[0] == "COMPLIANCE=FLAGGED"
    # The CLEARED edge must NOT match through the real engine matcher.
    assert edge_matches(ROUTE_COMPLIANCE_CLEARED, formatted) is False
    # The FLAGGED edge DOES match.
    assert edge_matches("COMPLIANCE=FLAGGED", formatted) is True


def test_collision_guard_using_existing_fixture_case():
    """Regression using the compliance_cases.json collision_guard fixture (Phase A)."""
    cases = json.loads((FIXTURES / "compliance_cases.json").read_text(encoding="utf-8"))["cases"]
    guard = next(c for c in cases if c.get("collision_guard"))
    # The fixture output starts with COMPLIANCE=FLAGGED and contains 'cleared'.
    assert guard["expected_status"] == "FLAGGED"
    out = guard["output"]
    assert "cleared" in out.lower()
    assert out.splitlines()[0] == "COMPLIANCE=FLAGGED"
    assert edge_matches(ROUTE_COMPLIANCE_CLEARED, out) is False


def test_flagged_output_never_contains_compliance_cleared_sentinel(tmp_path):
    """All FLAGGED paths the engine can produce must not contain 'COMPLIANCE=CLEARED'.

    This is the stronger form of the collision guard: not just lowercase prose
    ('cleared'), but the exact sentinel token that the unanchored graph matcher
    would route as CLEARED. Enumerates every FLAGGED code path in screen().
    """
    restricted_rules = _rules_with(tmp_path, restricted_countries=["Cuba"])
    no_corridor_rules = _rules_with(tmp_path, supported_corridors=[])

    flagged_scenarios = [
        screen(_brief(amount_usd=3001.0), rules_path=RULES_PATH),                      # AML
        screen(_brief(previously_flagged=True), rules_path=RULES_PATH),                 # sender flag
        screen(_brief(recipient_country="Cuba"), rules_path=restricted_rules),           # restricted
        screen(_brief(receive_currency="MXN"), rules_path=no_corridor_rules),            # corridor
        screen_from_dict(                                                                 # missing flag
            {
                "transfer_type": "cash_send", "amount_usd": 500.0,
                "sender_city": "Austin, TX", "sender_country": "US",
                "recipient_country": "Colombia", "recipient_city": "Bogotá",
                "send_currency": "USD", "receive_currency": "COP",
                "data_source": "fixture",
                "sender_profile": {"kyc_verified": True, "account_tier": "standard"},
            },
            rules_path=RULES_PATH,
        ),
    ]

    cleared_sentinel = "COMPLIANCE=CLEARED"
    for result in flagged_scenarios:
        assert result.status == "FLAGGED"
        formatted = format_output(result)
        # Exact sentinel must be absent from every FLAGGED output.
        assert cleared_sentinel not in formatted, (
            f"Sentinel contamination detected in FLAGGED output: {formatted!r}"
        )
        # Verify through the real graph matcher.
        assert edge_matches(ROUTE_COMPLIANCE_CLEARED, formatted) is False


# ── Test 9: ComplianceResult stable typed fields ──────────────────────────────

def test_compliance_result_round_trips():
    """ComplianceResult.to_dict / from_dict must be lossless (U5/U8 contract)."""
    original = ComplianceResult(
        status="CLEARED",
        notes=["ID required.", "Corridor supported."],
        issue=None,
    )
    d = original.to_dict()
    restored = ComplianceResult.from_dict(d)
    assert restored.status == original.status
    assert restored.notes == original.notes
    assert restored.issue == original.issue


def test_compliance_result_flagged_round_trips():
    original = ComplianceResult(status="FLAGGED", issue="AML threshold exceeded.")
    d = original.to_dict()
    restored = ComplianceResult.from_dict(d)
    assert restored.status == "FLAGGED"
    assert restored.issue == original.issue


# ── Test 10: No natural-language status accepted ──────────────────────────────

def test_natural_language_status_rejected():
    """Status literals must reject lowercase or prose values ('cleared', 'ok', etc.)."""
    with pytest.raises(ValueError, match="invalid compliance status"):
        ComplianceResult.from_dict({"status": "cleared", "notes": []})


def test_unknown_status_rejected():
    with pytest.raises(ValueError):
        ComplianceResult.from_dict({"status": "PASSED", "notes": []})
