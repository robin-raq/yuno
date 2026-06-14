"""Phase B / U3 — Research domain helper tests (test-first).

Covers R1–R4 and the plan's U3 verification: modality + amount parsing,
fixture fallback (the default path), missing-field labeling, and memory
defaults filling unspecified locality. Pure function — no Goose, no DB.
"""
import json
from pathlib import Path

from app.domain.remittance.research import assemble_brief
from app.domain.remittance.types import TransferBrief

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
FIXTURE_PATH = FIXTURES / "transfer_fixture.json"

MEMORY_DEFAULTS = {
    "sender_city": "Austin, TX",
    "sender_country": "US",
    "recipient_country": "Colombia",
    "recipient_city": "Bogotá",
    "send_currency": "USD",
    "receive_currency": "COP",
}


def _assemble(text: str, fixture_path: Path | None = None) -> TransferBrief:
    return assemble_brief(
        text,
        memory_defaults=MEMORY_DEFAULTS,
        fixture_path=fixture_path or FIXTURE_PATH,
    )


# ── Cash parse ────────────────────────────────────────────────────────────────

def test_cash_parse_sets_type_amount_and_cash_providers():
    brief = _assemble("send $500 cash to Bogotá")
    assert isinstance(brief, TransferBrief)
    assert brief.transfer_type == "cash_send"
    assert brief.amount_usd == 500
    assert brief.western_union is not None
    assert brief.moneygram is not None
    assert brief.wise is None  # cash send does not quote Wise


# ── Digital parse ─────────────────────────────────────────────────────────────

def test_digital_parse_includes_wise():
    brief = _assemble("send $500 to a bank account in Bogotá")
    assert brief.transfer_type == "digital_send"
    assert brief.wise is not None


# ── Fixture fallback is the default path ──────────────────────────────────────

def test_fixture_fallback_is_default():
    brief = _assemble("send $500 cash to Bogotá")
    assert brief.data_source == "fixture"
    assert brief.western_union is not None and brief.moneygram is not None


# ── Missing-field labeling ────────────────────────────────────────────────────

def test_missing_provider_rate_is_labeled(tmp_path):
    fx = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    del fx["western_union"]["rate_cop"]
    broken = tmp_path / "broken_fixture.json"
    broken.write_text(json.dumps(fx), encoding="utf-8")

    brief = _assemble("send $500 cash to Bogotá", fixture_path=broken)
    assert "western_union.rate_cop" in brief.missing_fields


# ── Memory defaults fill unspecified locality ─────────────────────────────────

def test_memory_defaults_fill_unspecified_locality():
    brief = _assemble("send $500 cash")
    assert brief.sender_city == "Austin, TX"
    assert brief.recipient_city == "Bogotá"
    assert brief.send_currency == "USD"
    assert brief.receive_currency == "COP"


# ── Amount parsing variants ───────────────────────────────────────────────────

def test_amount_parses_without_dollar_sign():
    assert _assemble("send 500 usd cash to Bogotá").amount_usd == 500


# ── Modality keyword boundary ─────────────────────────────────────────────────

def test_location_containing_bank_does_not_force_digital():
    # "Burbank" contains "bank" as a substring — must NOT trigger digital_send.
    brief = _assemble("send $500 cash to Burbank")
    assert brief.transfer_type == "cash_send"


# ── Digital includes all three providers ──────────────────────────────────────

def test_digital_includes_western_union_and_moneygram():
    # R2: digital_send quotes WU + MG + Wise, not Wise only.
    brief = _assemble("send $500 to a bank account in Bogotá")
    assert brief.western_union is not None
    assert brief.moneygram is not None
    assert brief.wise is not None


# ── Gapped quote becomes None, not a partial quote ────────────────────────────

def test_missing_field_yields_none_quote_not_partial(tmp_path):
    fx = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    del fx["western_union"]["rate_cop"]
    broken = tmp_path / "broken_fixture.json"
    broken.write_text(json.dumps(fx), encoding="utf-8")

    brief = _assemble("send $500 cash to Bogotá", fixture_path=broken)
    # The gapped provider must be None — no partial quote leaks downstream.
    assert brief.western_union is None
    assert "western_union.rate_cop" in brief.missing_fields
