"""Research domain helper (U3): free-text request → ``TransferBrief``.

Pure function, no Goose and no DB. Provider quotes load from an injected
fixture path; ``live_lookup`` is a stubbed hook that is off by default, so the
fixture fallback is the default path and live rates are never fabricated (R3).
Amount and modality parse from the request text; locality and currency default
from injected ``memory_defaults``; the ``sender_profile`` rides in the fixture
(KTD3). Any absent provider rate is labeled in ``missing_fields`` rather than
raising, so the Analyst (U7) can return ``NEEDS_MORE_DATA`` downstream (R4).
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable

from app.domain.remittance.types import (
    ProviderQuote,
    SenderProfile,
    TransferBrief,
)

# Word-boundary pattern so "Burbank" / "Wiseman" / "Bankstown" don't trigger
# digital classification. Uses \b (ASCII word boundary) — sufficient for the
# demo corridor's Latin-script inputs.
_DIGITAL_RE = re.compile(r"\b(?:digital|bank|wise|account)\b", re.IGNORECASE)
# Matches "$500", "500 usd", or a bare "500" (commas + decimals allowed).
_AMOUNT_RE = re.compile(r"\$?\s*([0-9][0-9,]*(?:\.[0-9]+)?)")
# Rate fields a usable provider quote must carry (R4).
_RATE_FIELDS = ("fee_usd", "rate_cop", "cop_received")
# Which providers Research is expected to quote per modality (R2).
_PROVIDERS_BY_TYPE = {
    "cash_send": ("western_union", "moneygram"),
    "digital_send": ("western_union", "moneygram", "wise"),
}

LiveLookup = Callable[[str], dict[str, Any]]


def _detect_modality(text: str) -> str:
    if _DIGITAL_RE.search(text):
        return "digital_send"
    return "cash_send"


def _parse_amount(text: str) -> float | None:
    match = _AMOUNT_RE.search(text)
    return float(match.group(1).replace(",", "")) if match else None


def _build_quote(name: str, block: dict[str, Any] | None) -> tuple[ProviderQuote | None, list[str]]:
    """Return ``(quote, missing_labels)``. A gap yields ``(None, [...])`` rather
    than constructing through ``ProviderQuote.from_dict`` (which would KeyError
    on the very field we need to report)."""
    if not block:
        return None, [name]
    gaps = [f"{name}.{field}" for field in _RATE_FIELDS if block.get(field) is None]
    if gaps:
        return None, gaps
    return ProviderQuote.from_dict(block), []


def assemble_brief(
    request_text: str,
    *,
    memory_defaults: dict[str, str],
    fixture_path: str | Path,
    live_lookup: LiveLookup | None = None,
) -> TransferBrief:
    """Assemble a ``TransferBrief`` from a free-text remittance request.

    ``memory_defaults`` must supply all six locality/currency keys:
    ``sender_city``, ``sender_country``, ``recipient_country``,
    ``recipient_city``, ``send_currency``, ``receive_currency``.

    When ``live_lookup`` is ``None`` (the default), rates load from the JSON
    file at ``fixture_path`` — the intended path for demo and test runs.
    """
    transfer_type = _detect_modality(request_text)

    if live_lookup is not None:
        data = live_lookup(request_text)
        data_source = "live"
    else:
        data = json.loads(Path(fixture_path).read_text(encoding="utf-8"))
        data_source = "fixture"

    amount = _parse_amount(request_text)
    if amount is None:
        # Intentional fixture-demo fallback: when the request carries no
        # parseable number, use the fixture's amount so the demo stays coherent.
        amount = float(data.get("amount_usd", 0.0))

    missing_fields: list[str] = []
    quotes: dict[str, ProviderQuote | None] = {
        "western_union": None,
        "moneygram": None,
        "wise": None,
    }
    for name in _PROVIDERS_BY_TYPE[transfer_type]:
        quote, gaps = _build_quote(name, data.get(name))
        quotes[name] = quote
        missing_fields.extend(gaps)

    md = memory_defaults
    return TransferBrief(
        transfer_type=transfer_type,
        amount_usd=amount,
        sender_city=md["sender_city"],
        sender_country=md["sender_country"],
        recipient_country=md["recipient_country"],
        recipient_city=md["recipient_city"],
        send_currency=md["send_currency"],
        receive_currency=md["receive_currency"],
        data_source=data_source,
        sender_profile=SenderProfile.from_dict(data["sender_profile"]),
        western_union=quotes["western_union"],
        moneygram=quotes["moneygram"],
        wise=quotes["wise"],
        missing_fields=missing_fields,
    )
