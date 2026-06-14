"""Phase A / U1 — remittance fixture tests.

TDD red phase: the fixture files under backend/fixtures/ do not exist yet
(FileNotFoundError = expected red failure). Files created in U1.

Covers the user's Phase-A testing requirements 1, 2, 3, 4, 6 and the plan's U1
verification: fixtures load, required fields exist, sentinel values are exact,
the collision-guard case exists, and the sentinel design defeats the prior
fail-open bug when run through the REAL graph matcher (no stale bare tokens).
"""
import json
from pathlib import Path

import pytest

from app.domain.remittance.types import (
    COMPLIANCE_SENTINELS,
    ROUTE_COMPLIANCE_CLEARED,
)
# Read-only import of the production matcher — proves the fixture data routes
# correctly through the real engine without modifying it.
from app.services.workflow_graph import edge_matches

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
REPO_ROOT = Path(__file__).resolve().parents[2]


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


# ── Requirement 1: fixtures load successfully ─────────────────────────────────

def test_transfer_fixture_loads():
    assert _load("transfer_fixture.json")


def test_compliance_rules_loads():
    assert _load("compliance_rules.json")


def test_compliance_cases_loads():
    assert _load("compliance_cases.json")


# ── Requirement 2: required fields exist ──────────────────────────────────────

def test_transfer_fixture_has_required_brief_fields():
    fx = _load("transfer_fixture.json")
    for key in (
        "transfer_type", "amount_usd", "sender_city", "sender_country",
        "recipient_country", "recipient_city", "send_currency", "receive_currency",
        "data_source", "sender_profile", "western_union", "moneygram",
    ):
        assert key in fx, f"missing brief field: {key}"
    assert fx["data_source"] == "fixture"
    for prov in ("western_union", "moneygram"):
        for f in ("fee_usd", "rate_cop", "cop_received", "delivery_minutes", "nearest_location"):
            assert f in fx[prov], f"{prov} missing {f}"
    for f in ("previously_flagged", "kyc_verified", "account_tier"):
        assert f in fx["sender_profile"], f"sender_profile missing {f}"


def test_transfer_fixture_is_labeled_demo_data():
    assert "_note" in _load("transfer_fixture.json")


def test_reports_dir_is_gitignored():
    """Plan U1 verification: the writable reports/ dir must be ignored so a
    workflow dry-run cannot stage transfer_comparison.md."""
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "reports/" in gitignore


def test_compliance_rules_has_the_five_rule_keys():
    rules = _load("compliance_rules.json")
    for key in (
        "restricted_countries",
        "aml_reporting_threshold_usd",
        "id_required_threshold_usd",
        "supported_corridors",
        "flag_previously_flagged_senders",
    ):
        assert key in rules, f"missing rule key: {key}"
    corridor = rules["supported_corridors"][0]
    assert corridor["send"] == "USD" and corridor["receive"] == "COP"


# ── Requirement 3: sentinel values are valid + exact ──────────────────────────

def test_every_case_uses_an_exact_known_sentinel():
    cases = _load("compliance_cases.json")["cases"]
    for case in cases:
        assert case["expected_sentinel"] in COMPLIANCE_SENTINELS
        # Line 1 of the output IS the sentinel — exact, anchored.
        assert case["output"].splitlines()[0] == case["expected_sentinel"]
        assert case["expected_sentinel"].endswith(case["expected_status"])


def test_all_three_routes_present_in_cases():
    statuses = {c["expected_status"] for c in _load("compliance_cases.json")["cases"]}
    assert statuses == {"CLEARED", "FLAGGED", "NEEDS_REVIEW"}


# ── Requirement 4: the collision-guard case exists ────────────────────────────

def test_collision_guard_case_exists():
    cases = _load("compliance_cases.json")["cases"]
    guards = [c for c in cases if c.get("collision_guard")]
    assert guards, "no collision_guard case present"
    guard = guards[0]
    # The whole point: a FLAGGED output whose prose contains 'cleared'.
    assert guard["expected_status"] == "FLAGGED"
    assert "cleared" in guard["output"].lower()


# ── Requirement 6: no stale bare-token routing — proven via the REAL matcher ───

def test_collision_guard_does_not_route_as_cleared_through_real_matcher():
    """This is the regression test for the prior fail-open bug. With the old
    bare-token edge ('CLEARED'), this output would have matched and routed a
    FLAGGED transfer to the Analyst. With the sentinel it must not."""
    guard = next(c for c in _load("compliance_cases.json")["cases"] if c.get("collision_guard"))
    out = guard["output"]
    # Prose really does contain the word — the trap is real.
    assert "cleared" in out.lower()
    # ...but the sentinel edge must NOT match it.
    assert edge_matches(ROUTE_COMPLIANCE_CLEARED, out) is False
    # ...and the correct FLAGGED edge DOES match.
    assert edge_matches("COMPLIANCE=FLAGGED", out) is True


def test_cleared_case_routes_as_cleared_through_real_matcher():
    cleared = next(
        c for c in _load("compliance_cases.json")["cases"]
        if c["expected_status"] == "CLEARED"
    )
    assert edge_matches(ROUTE_COMPLIANCE_CLEARED, cleared["output"]) is True


@pytest.mark.parametrize("status", ["FLAGGED", "NEEDS_REVIEW"])
def test_non_cleared_cases_never_match_cleared_edge(status):
    cases = [c for c in _load("compliance_cases.json")["cases"] if c["expected_status"] == status]
    assert cases
    for c in cases:
        assert edge_matches(ROUTE_COMPLIANCE_CLEARED, c["output"]) is False
