"""Analyst domain helper (U7): validate, score, report, and Telegram text.

Pure domain logic with filesystem I/O confined to an injected ``reports_dir``.
No Goose, no DB, no worker.
"""
from __future__ import annotations

from pathlib import Path

from app.domain.remittance.scoring import pick_winner, provider_label, providers_for_brief, score_providers
from app.domain.remittance.types import AnalystResult, ProviderQuote, TransferBrief

_RATE_FIELDS = ("rate_cop", "cop_received")
_REPORT_FILENAME = "transfer_comparison.md"
_REPORT_RELATIVE = "reports/transfer_comparison.md"


def _collect_gaps(brief: TransferBrief) -> list[str]:
    if brief.missing_fields:
        return list(brief.missing_fields)
    gaps: list[str] = []
    for key in providers_for_brief(brief):
        quote = getattr(brief, key)
        for field in _RATE_FIELDS:
            if getattr(quote, field, None) is None:
                gaps.append(f"{key}.{field}")
    return gaps


def _format_cop(amount: int) -> str:
    return f"{amount:,}"


def _format_rate(rate: float) -> str:
    return f"{rate:,.0f}"


def _pickup_line(quote: ProviderQuote) -> str | None:
    if not quote.nearest_location:
        return None
    loc = quote.nearest_location
    distance = loc.distance.replace(" miles", " mi").replace(" mile", " mi")
    return f"Pickup: {loc.name}, {distance} ({loc.hours})"


def _runner_up_key(brief: TransferBrief, scores: dict[str, float], winner_key: str) -> str | None:
    remaining = {key: score for key, score in scores.items() if key != winner_key}
    if not remaining:
        return None
    return pick_winner(brief, remaining)


def _runner_up_summary(brief: TransferBrief, winner_key: str, runner_key: str) -> str:
    winner = getattr(brief, winner_key)
    runner = getattr(brief, runner_key)
    fee_delta = runner.fee_usd - winner.fee_usd
    rate_delta = runner.rate_cop - winner.rate_cop
    cop_delta = runner.cop_received - winner.cop_received
    parts: list[str] = []
    if fee_delta != 0:
        direction = "lower" if fee_delta < 0 else "higher"
        parts.append(f"${abs(fee_delta):.2f} {direction} fee")
    if rate_delta != 0:
        direction = "better" if rate_delta > 0 else "worse"
        parts.append(f"{abs(rate_delta):,.0f} COP/USD {direction} rate")
    if cop_delta != 0 and not parts:
        parts.append(f"{cop_delta:+,} COP")
    detail = " but ".join(parts) if parts else "comparable overall"
    return f"{provider_label(runner_key)} — {detail}"


def _build_telegram_message(brief: TransferBrief, winner_key: str, scores: dict[str, float]) -> str:
    winner = getattr(brief, winner_key)
    lines = [
        f"RECOMMENDATION: {provider_label(winner_key)}",
        (
            f"Fee ${winner.fee_usd:.2f} · Rate {_format_rate(winner.rate_cop)} COP/USD · "
            f"You receive {_format_cop(winner.cop_received)} COP"
        ),
    ]
    pickup = _pickup_line(winner)
    if pickup:
        lines.append(pickup)
    runner_key = _runner_up_key(brief, scores, winner_key)
    if runner_key:
        lines.append(f"Runner-up: {_runner_up_summary(brief, winner_key, runner_key)}")
    lines.append(f"Full report: {_REPORT_RELATIVE}")
    return "\n".join(lines)


def _build_report(
    brief: TransferBrief,
    winner_key: str,
    scores: dict[str, float],
    *,
    compliance_notes: list[str] | None,
) -> str:
    winner_label = provider_label(winner_key)
    lines = [
        "# Transfer Comparison Report",
        "",
        f"**Recommendation:** {winner_label}",
        "",
        "## Winner",
        f"{winner_label} scored highest ({scores[winner_key]:.3f}) on value, location, and speed.",
        "",
        "## Provider comparison",
    ]
    for key in providers_for_brief(brief):
        quote = getattr(brief, key)
        label = provider_label(key)
        lines.append(f"### {label}")
        lines.append(
            f"- Fee: ${quote.fee_usd:.2f} · Rate: {_format_rate(quote.rate_cop)} COP/USD · "
            f"Recipient receives: {_format_cop(quote.cop_received)} COP"
        )
        if quote.nearest_location and brief.transfer_type == "cash_send":
            loc = quote.nearest_location
            lines.append(f"- Nearest location: {loc.name}, {loc.distance} ({loc.hours})")
        lines.append(f"- Weighted score: {scores.get(key, 0.0):.3f}")
        lines.append("")

    runner_key = _runner_up_key(brief, scores, winner_key)
    if runner_key:
        lines.extend(
            [
                "## Runner-up",
                f"{provider_label(runner_key)} — {_runner_up_summary(brief, winner_key, runner_key)}",
                "",
            ]
        )

    notes = compliance_notes or []
    lines.append("## Compliance notes")
    lines.append(notes[0] if notes else "(none)")
    lines.append("")
    return "\n".join(lines)


def format_output(result: AnalystResult) -> str:
    """KTD6 line-1 sentinel plus optional Telegram body."""
    sentinel = result.sentinel()
    if result.status == "NEEDS_MORE_DATA":
        body = "Missing: " + ", ".join(result.missing_fields)
        return f"{sentinel}\n{body}"
    if result.telegram_message:
        return f"{sentinel}\n{result.telegram_message}"
    return sentinel


def analyze(
    brief: TransferBrief,
    *,
    reports_dir: Path,
    compliance_notes: list[str] | None = None,
) -> AnalystResult:
    """Validate provider data, score, write the report, and build Telegram text."""
    gaps = _collect_gaps(brief)
    if gaps:
        return AnalystResult(status="NEEDS_MORE_DATA", missing_fields=gaps)

    scores = score_providers(brief)
    winner_key = pick_winner(brief, scores)
    winner_label = provider_label(winner_key)

    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / _REPORT_FILENAME
    report_path.write_text(
        _build_report(brief, winner_key, scores, compliance_notes=compliance_notes),
        encoding="utf-8",
    )

    return AnalystResult(
        status="RECOMMENDATION",
        winner=winner_label,
        scores=scores,
        telegram_message=_build_telegram_message(brief, winner_key, scores),
        report_path=_REPORT_RELATIVE,
    )
