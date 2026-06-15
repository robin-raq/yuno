"""Compliance rules engine (U4): TransferBrief + rules → ComplianceResult.

Pure function, no Goose, no DB, no network. The five rules are loaded from
``rules_path`` (default ``fixtures/compliance_rules.json``); thresholds are
never hardcoded here.

The sentinel-line formatting (KTD6) is owned by the adapter (U5), not by
``screen``. A ``format_output`` helper is provided here so tests can verify
the sentinel contract without importing the adapter, and so U5 can import it
rather than re-implement the convention.

Decision — NEEDS_REVIEW not emitted by this engine: the five configured rules
each resolve to either CLEARED or FLAGGED. NEEDS_REVIEW is a representable
status (types.py) whose trigger conditions are deferred to U8 (seed graph).
No rule in the current ``compliance_rules.json`` schema triggers it.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.domain.remittance.types import (
    ComplianceResult,
    TransferBrief,
    compliance_sentinel,
)


def _load_rules(rules_path: str | Path) -> dict[str, Any]:
    return json.loads(Path(rules_path).read_text(encoding="utf-8"))


def screen(brief: TransferBrief, *, rules_path: str | Path) -> ComplianceResult:
    """Apply five deterministic compliance rules to a transfer brief.

    Rules are evaluated in priority order; the first failure short-circuits
    with a FLAGGED result. All non-flagging checks accumulate notes that appear
    in the CLEARED result.
    """
    rules = _load_rules(rules_path)
    notes: list[str] = []

    # Rule 1: Restricted country — any restricted sender or recipient flags.
    restricted: list[str] = rules.get("restricted_countries", [])
    for country in (brief.sender_country, brief.recipient_country):
        if country in restricted:
            return ComplianceResult(
                status="FLAGGED",
                issue=f"{country} is restricted under the configured rules.",
            )

    # Rule 2: AML reporting threshold (cash send only).
    # Threshold is EXCLUSIVE: plan U4 specifies `amount_usd > threshold`, so
    # a transfer exactly at $3000 is CLEARED; $3001+ is FLAGGED. This differs
    # from real-world FinCEN CTR semantics (at-or-above). See AI_USAGE U4.
    aml_threshold: float = rules["aml_reporting_threshold_usd"]
    if brief.transfer_type == "cash_send" and brief.amount_usd > aml_threshold:
        return ComplianceResult(
            status="FLAGGED",
            issue=(
                f"Cash send amount ${brief.amount_usd:.0f} exceeds the configured "
                f"${aml_threshold:.0f} AML reporting threshold."
            ),
        )

    # Rule 3: ID requirement note (cash send only, >= threshold — note, not FLAGGED).
    id_threshold: float = rules["id_required_threshold_usd"]
    if brief.transfer_type == "cash_send" and brief.amount_usd >= id_threshold:
        notes.append(
            f"Cash send of ${brief.amount_usd:.0f} or more requires valid "
            "government-issued ID at the send location."
        )

    # Rule 4: Corridor support — fail closed if the send/receive pair is absent.
    corridor_ok = any(
        c["send"] == brief.send_currency and c["receive"] == brief.receive_currency
        for c in rules.get("supported_corridors", [])
    )
    if not corridor_ok:
        return ComplianceResult(
            status="FLAGGED",
            issue=(
                f"{brief.send_currency} to {brief.receive_currency} corridor "
                "is not supported under the configured rules."
            ),
        )
    notes.append(
        f"{brief.send_currency} to {brief.receive_currency} corridor is supported."
    )

    # Rule 5: Previously flagged sender.
    if brief.sender_profile.previously_flagged:
        return ComplianceResult(
            status="FLAGGED",
            issue="Sender has been previously flagged; transfer is not permitted.",
        )

    return ComplianceResult(status="CLEARED", notes=notes)


def screen_from_dict(brief_dict: dict[str, Any], *, rules_path: str | Path) -> ComplianceResult:
    """Validate a raw brief dict and screen it. Missing ``previously_flagged`` fails closed.

    This is the compliance input-validation seam: the typed ``SenderProfile``
    cannot represent a missing flag (it always has ``previously_flagged: bool``),
    but a raw adapter payload can omit it. A missing flag is treated as FLAGGED
    (fail-closed, KTD3) — never silently defaulted to ``False``.
    """
    sp = brief_dict.get("sender_profile") or {}
    if "previously_flagged" not in sp:
        return ComplianceResult(
            status="FLAGGED",
            issue=(
                "sender_profile.previously_flagged is absent from the compliance input; "
                "failing closed per KTD3 (missing flag ≠ not flagged)."
            ),
        )
    flagged = sp.get("previously_flagged")
    if not isinstance(flagged, bool):
        return ComplianceResult(
            status="FLAGGED",
            issue=(
                "sender_profile.previously_flagged must be a boolean; "
                f"got {type(flagged).__name__!r} — failing closed per KTD3."
            ),
        )
    brief = TransferBrief.from_dict(brief_dict)
    return screen(brief, rules_path=rules_path)


def format_output(result: ComplianceResult) -> str:
    """Format a ComplianceResult as adapter-ready text with the sentinel on line 1 (KTD6).

    U5 imports this to build ``TaskResult.output``; U4 tests use it to verify
    the sentinel and collision-guard properties without importing the adapter.
    """
    sentinel = compliance_sentinel(result.status)
    if result.status == "FLAGGED":
        body = result.issue or ""
    else:
        body = " ".join(result.notes)
    return f"{sentinel}\n{body}" if body else sentinel
