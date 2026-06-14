"""Phase A / U2 — remittance shared-contract type tests.

TDD red phase: imports from app.domain.remittance.types, which does not exist
yet (ImportError = expected red failure). Implementation follows in
backend/app/domain/remittance/types.py.

Covers the user's Phase-A testing requirements 3, 5, 6 and the plan's U2
verification: status literals reject invalid values, round-trip is lossless,
the three compliance routes are representable, and routing uses the KTD6
sentinel convention (no stale bare-token assumptions).
"""
import pytest

from app.domain.remittance.types import (
    ANALYST_SENTINELS,
    COMPLIANCE_SENTINELS,
    AnalystInput,
    AnalystResult,
    ComplianceResult,
    NearestLocation,
    ProviderQuote,
    SenderProfile,
    TransferBrief,
    analyst_sentinel,
    compliance_sentinel,
)


# ── Sentinel convention (KTD6) ────────────────────────────────────────────────

def test_compliance_sentinels_are_exact_and_anchored():
    assert compliance_sentinel("CLEARED") == "COMPLIANCE=CLEARED"
    assert compliance_sentinel("FLAGGED") == "COMPLIANCE=FLAGGED"
    assert compliance_sentinel("NEEDS_REVIEW") == "COMPLIANCE=NEEDS_REVIEW"
    assert COMPLIANCE_SENTINELS == {
        "COMPLIANCE=CLEARED",
        "COMPLIANCE=FLAGGED",
        "COMPLIANCE=NEEDS_REVIEW",
    }


def test_analyst_sentinels_are_exact_and_anchored():
    assert analyst_sentinel("RECOMMENDATION") == "ANALYST=RECOMMENDATION"
    assert analyst_sentinel("NEEDS_MORE_DATA") == "ANALYST=NEEDS_MORE_DATA"
    assert ANALYST_SENTINELS == {"ANALYST=RECOMMENDATION", "ANALYST=NEEDS_MORE_DATA"}


def test_no_sentinel_is_a_substring_of_another():
    """Substring containment between any two routing tokens would resurrect the
    fail-open collision the sentinel convention exists to prevent."""
    all_tokens = list(COMPLIANCE_SENTINELS | ANALYST_SENTINELS)
    for a in all_tokens:
        for b in all_tokens:
            if a != b:
                assert a not in b, f"{a!r} is a substring of {b!r}"


def test_sentinel_helpers_reject_invalid_status():
    with pytest.raises(ValueError):
        compliance_sentinel("MAYBE")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        analyst_sentinel("CLEARED")  # type: ignore[arg-type]


# ── Three compliance routes are representable ─────────────────────────────────

@pytest.mark.parametrize("status", ["CLEARED", "FLAGGED", "NEEDS_REVIEW"])
def test_compliance_result_represents_all_three_routes(status):
    result = ComplianceResult(status=status, notes=["demo note"], issue=None)
    assert result.status == status
    assert result.sentinel() == f"COMPLIANCE={status}"


def test_compliance_result_rejects_invalid_status_on_from_dict():
    with pytest.raises(ValueError):
        ComplianceResult.from_dict({"status": "PENDING", "notes": [], "issue": None})


def test_analyst_result_rejects_invalid_status_on_from_dict():
    with pytest.raises(ValueError):
        AnalystResult.from_dict({"status": "DONE"})


# ── TransferBrief round-trip (lossless) ───────────────────────────────────────

def _cash_brief() -> TransferBrief:
    return TransferBrief(
        transfer_type="cash_send",
        amount_usd=500,
        sender_city="Austin, TX",
        sender_country="US",
        recipient_country="Colombia",
        recipient_city="Bogotá",
        send_currency="USD",
        receive_currency="COP",
        data_source="fixture",
        sender_profile=SenderProfile(
            previously_flagged=False, kyc_verified=True, account_tier="standard"
        ),
        western_union=ProviderQuote(
            fee_usd=12.99, rate_cop=4180, cop_received=2035702, delivery_minutes=10,
            nearest_location=NearestLocation(
                name="H-E-B Money Services", distance="1.2 miles", hours="Mon-Sat 8am-9pm"
            ),
        ),
        moneygram=ProviderQuote(
            fee_usd=9.99, rate_cop=4155, cop_received=2035992, delivery_minutes=15,
            nearest_location=NearestLocation(
                name="Walmart Supercenter", distance="3.8 miles", hours="Daily 7am-11pm"
            ),
        ),
        wise=None,
        missing_fields=[],
    )


def test_transfer_brief_round_trips_losslessly():
    brief = _cash_brief()
    assert TransferBrief.from_dict(brief.to_dict()) == brief


def test_transfer_brief_wise_none_round_trips_as_none():
    brief = _cash_brief()
    restored = TransferBrief.from_dict(brief.to_dict())
    assert restored.wise is None


def test_transfer_brief_rejects_invalid_transfer_type():
    d = _cash_brief().to_dict()
    d["transfer_type"] = "crypto_send"
    with pytest.raises(ValueError):
        TransferBrief.from_dict(d)


def test_transfer_brief_rejects_invalid_data_source():
    d = _cash_brief().to_dict()
    d["data_source"] = "imagined"
    with pytest.raises(ValueError):
        TransferBrief.from_dict(d)


def test_digital_brief_round_trips_with_wise_block():
    brief = _cash_brief()
    brief.transfer_type = "digital_send"
    brief.wise = ProviderQuote(
        fee_usd=7.45, rate_cop=4205, cop_received=2071273, delivery_minutes=1440,
        nearest_location=None,
    )
    restored = TransferBrief.from_dict(brief.to_dict())
    assert restored == brief
    assert restored.wise is not None
    assert restored.wise.nearest_location is None


# ── AnalystInput carries the cross-role payload ───────────────────────────────

def test_analyst_input_round_trips():
    ai = AnalystInput(brief=_cash_brief(), compliance=ComplianceResult(status="CLEARED"))
    assert AnalystInput.from_dict(ai.to_dict()) == ai


def test_analyst_result_recommendation_round_trips():
    res = AnalystResult(
        status="RECOMMENDATION",
        winner="Western Union",
        scores={"western_union": 0.82, "moneygram": 0.76},
        telegram_message="RECOMMENDATION: Western Union\n...",
        report_path="reports/transfer_comparison.md",
    )
    assert AnalystResult.from_dict(res.to_dict()) == res
    assert res.sentinel() == "ANALYST=RECOMMENDATION"


def test_analyst_result_needs_more_data_round_trips():
    res = AnalystResult(status="NEEDS_MORE_DATA", missing_fields=["moneygram.rate_cop"])
    assert AnalystResult.from_dict(res.to_dict()) == res
    assert res.sentinel() == "ANALYST=NEEDS_MORE_DATA"
