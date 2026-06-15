"""Weighted provider scoring (U7 / KTD5). Pure math — no I/O."""
from __future__ import annotations

import re

from app.domain.remittance.types import TransferBrief

_WEIGHT_VALUE = 0.50
_WEIGHT_LOCATION = 0.30
_WEIGHT_SPEED = 0.20

_PROVIDER_KEYS = ("western_union", "moneygram", "wise")

_LABELS = {
    "western_union": "Western Union",
    "moneygram": "MoneyGram",
    "wise": "Wise",
}

_DISTANCE_RE = re.compile(r"([\d.]+)")


def provider_label(key: str) -> str:
    return _LABELS.get(key, key)


def providers_for_brief(brief: TransferBrief) -> list[str]:
    """Return provider attribute keys expected and present for this transfer type."""
    if brief.transfer_type == "cash_send":
        expected = ("western_union", "moneygram")
    else:
        expected = _PROVIDER_KEYS
    return [key for key in expected if getattr(brief, key) is not None]


def _min_max_normalize(values: dict[str, float], *, higher_is_better: bool = True) -> dict[str, float]:
    if not values:
        return {}
    if len(values) == 1:
        return {key: 1.0 for key in values}
    lo, hi = min(values.values()), max(values.values())
    if lo == hi:
        return {key: 1.0 for key in values}
    if higher_is_better:
        return {key: (value - lo) / (hi - lo) for key, value in values.items()}
    return {key: (hi - value) / (hi - lo) for key, value in values.items()}


def _parse_distance_miles(distance: str) -> float:
    match = _DISTANCE_RE.search(distance)
    return float(match.group(1)) if match else float("inf")


def score_breakdown(brief: TransferBrief) -> dict[str, dict[str, float]]:
    """Return per-provider value/location/speed/total subscores (for tests)."""
    providers = providers_for_brief(brief)
    if not providers:
        return {}

    cop = {key: getattr(brief, key).cop_received for key in providers}
    value_n = _min_max_normalize(cop, higher_is_better=True)

    speed_raw = {
        key: 1.0 / max(getattr(brief, key).delivery_minutes or 1, 1)
        for key in providers
    }
    speed_n = _min_max_normalize(speed_raw, higher_is_better=True)

    if brief.transfer_type == "digital_send":
        location_n = {key: 1.0 for key in providers}
    else:
        loc_raw: dict[str, float] = {}
        for key in providers:
            quote = getattr(brief, key)
            if quote.nearest_location and quote.nearest_location.distance:
                loc_raw[key] = 1.0 / _parse_distance_miles(quote.nearest_location.distance)
            else:
                loc_raw[key] = 0.0
        location_n = _min_max_normalize(loc_raw, higher_is_better=True)

    breakdown: dict[str, dict[str, float]] = {}
    for key in providers:
        total = (
            _WEIGHT_VALUE * value_n[key]
            + _WEIGHT_LOCATION * location_n[key]
            + _WEIGHT_SPEED * speed_n[key]
        )
        breakdown[key] = {
            "value": value_n[key],
            "location": location_n[key],
            "speed": speed_n[key],
            "total": total,
        }
    return breakdown


def score_providers(brief: TransferBrief) -> dict[str, float]:
    """Return weighted total scores keyed by provider attribute name."""
    return {key: parts["total"] for key, parts in score_breakdown(brief).items()}


def pick_winner(brief: TransferBrief, scores: dict[str, float]) -> str:
    """Pick the winning provider key; tie-break on higher ``cop_received``."""
    if not scores:
        return ""
    top = max(scores.values())
    tied = [key for key, score in scores.items() if score == top]
    if len(tied) == 1:
        return tied[0]
    return max(tied, key=lambda key: getattr(brief, key).cop_received)
