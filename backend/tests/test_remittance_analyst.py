"""Phase B / U7 — Analyst scoring, report, and message tests (test-first)."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from app.domain.remittance.analyst import analyze, format_output
from app.domain.remittance.research import assemble_brief
from app.domain.remittance.scoring import pick_winner, provider_label, score_breakdown, score_providers
from app.domain.remittance.types import (
    NearestLocation,
    ProviderQuote,
    SenderProfile,
    TransferBrief,
)

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


def _brief_from_fixture(**overrides) -> TransferBrief:
    data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    data.update(overrides)
    return TransferBrief.from_dict(data)


# ── Scoring: winner by value + location ───────────────────────────────────────

def test_wu_wins_when_higher_cop_and_closer_location():
    brief = _brief_from_fixture(
        western_union={
            "fee_usd": 10.0,
            "rate_cop": 4200,
            "cop_received": 2_060_000,
            "delivery_minutes": 10,
            "nearest_location": {
                "name": "Near Store",
                "distance": "0.5 miles",
                "hours": "Daily 9am-9pm",
            },
        },
        moneygram={
            "fee_usd": 12.0,
            "rate_cop": 4100,
            "cop_received": 2_000_000,
            "delivery_minutes": 15,
            "nearest_location": {
                "name": "Far Store",
                "distance": "5.0 miles",
                "hours": "Daily 9am-9pm",
            },
        },
    )
    scores = score_providers(brief)
    assert pick_winner(brief, scores) == "western_union"
    assert provider_label(pick_winner(brief, scores)) == "Western Union"
    assert scores["western_union"] > scores["moneygram"]


# ── Digital equalization ──────────────────────────────────────────────────────

def test_digital_equalizes_location_scores():
    brief = _brief_from_fixture(transfer_type="digital_send")
    breakdown = score_breakdown(brief)
    location_scores = {key: parts["location"] for key, parts in breakdown.items()}
    assert len(set(location_scores.values())) == 1


def test_digital_ranking_ignores_distance_swap():
    base = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    base["transfer_type"] = "digital_send"
    brief_a = TransferBrief.from_dict(deepcopy(base))
    swapped = deepcopy(base)
    swapped["western_union"]["nearest_location"]["distance"] = "20 miles"
    swapped["moneygram"]["nearest_location"]["distance"] = "0.1 miles"
    brief_b = TransferBrief.from_dict(swapped)
    assert pick_winner(brief_a, score_providers(brief_a)) == pick_winner(
        brief_b, score_providers(brief_b)
    )


# ── Tie-break ─────────────────────────────────────────────────────────────────

def test_tie_break_favors_higher_cop_received():
    brief = TransferBrief(
        transfer_type="cash_send",
        amount_usd=500,
        sender_city="Austin, TX",
        sender_country="US",
        recipient_country="Colombia",
        recipient_city="Bogotá",
        send_currency="USD",
        receive_currency="COP",
        data_source="fixture",
        sender_profile=SenderProfile(previously_flagged=False, kyc_verified=True, account_tier="standard"),
        western_union=ProviderQuote(
            fee_usd=10.0,
            rate_cop=4000,
            cop_received=2_000_000,
            delivery_minutes=10,
            nearest_location=NearestLocation(name="A", distance="2.0 miles", hours="9-5"),
        ),
        moneygram=ProviderQuote(
            fee_usd=10.0,
            rate_cop=4000,
            cop_received=2_000_100,
            delivery_minutes=10,
            nearest_location=NearestLocation(name="B", distance="2.0 miles", hours="9-5"),
        ),
    )
    tied_scores = {"western_union": 0.75, "moneygram": 0.75}
    assert pick_winner(brief, tied_scores) == "moneygram"


# ── NEEDS_MORE_DATA ───────────────────────────────────────────────────────────

def test_needs_more_data_when_rate_missing(tmp_path):
    fx = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    del fx["moneygram"]["rate_cop"]
    broken = tmp_path / "broken.json"
    broken.write_text(json.dumps(fx), encoding="utf-8")
    brief = _assemble("send $500 cash to Bogotá", fixture_path=broken)

    result = analyze(brief, reports_dir=tmp_path / "reports")

    assert result.status == "NEEDS_MORE_DATA"
    assert "moneygram.rate_cop" in result.missing_fields
    assert result.report_path is None
    assert not (tmp_path / "reports" / "transfer_comparison.md").exists()
    assert format_output(result).startswith("ANALYST=NEEDS_MORE_DATA")


# ── Report write ──────────────────────────────────────────────────────────────

def test_successful_analyze_writes_report(tmp_path):
    brief = _assemble("send $500 cash to Bogotá")
    reports_dir = tmp_path / "reports"

    result = analyze(brief, reports_dir=reports_dir)

    report_file = reports_dir / "transfer_comparison.md"
    assert report_file.exists()
    content = report_file.read_text(encoding="utf-8")
    assert result.winner
    assert result.winner in content
    assert "2,035,702" in content or "2035702" in content.replace(",", "")
    assert "2,035,992" in content or "2035992" in content.replace(",", "")
    assert result.report_path == "reports/transfer_comparison.md"


# ── Telegram text ─────────────────────────────────────────────────────────────

def test_telegram_message_shape(tmp_path):
    brief = _assemble("send $500 cash to Bogotá")
    result = analyze(brief, reports_dir=tmp_path / "reports")

    assert result.telegram_message
    assert result.telegram_message.startswith("RECOMMENDATION:")
    assert result.winner in result.telegram_message
    assert "Fee $" in result.telegram_message
    assert "COP/USD" in result.telegram_message
    assert "reports/transfer_comparison.md" in result.telegram_message
    assert "\n" in result.telegram_message

    output = format_output(result)
    assert output.startswith("ANALYST=RECOMMENDATION")
    assert "RECOMMENDATION:" in output
