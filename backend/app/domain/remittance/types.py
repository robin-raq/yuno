"""Shared typed contracts for the remittance comparison workflow (U2).

Pure data contracts passed between the Research, Compliance, and Analyst roles.
No Goose, no DB, no I/O — dataclasses in the same style as `app.adapters.base`
(TaskInput/TaskResult) and `app.services.message_bus` (AgentMessageDraft).

Routing uses the KTD6 sentinel convention — `COMPLIANCE=<STATUS>` /
`ANALYST=<STATUS>` — because the graph engine's edge matcher is unanchored,
case-insensitive substring containment (`workflow_graph.edge_matches`). A bare
`CLEARED` edge collides with the word "cleared" inside a FLAGGED issue and routes
a rejected transfer onward (fail-open). The `=`-anchored sentinels cannot occur
inside free-text prose, so they are collision-proof.

NOTE (scope divergence from the plan): the plan defines Compliance as binary
(CLEARED/FLAGGED). Per an execution-time decision, a third route NEEDS_REVIEW is
included here. Its *semantics* (trigger conditions, routing target) are NOT yet
defined by the plan — U4 (engine) and U8 (seed graph) must define them, and
KTD6/U4/U5/U8 need plan updates before those units are built. This module only
makes NEEDS_REVIEW a representable status + sentinel.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Any, Literal, get_args

TransferType = Literal["cash_send", "digital_send"]
ComplianceStatus = Literal["CLEARED", "FLAGGED", "NEEDS_REVIEW"]
AnalystStatus = Literal["RECOMMENDATION", "NEEDS_MORE_DATA"]
DataSource = Literal["live", "fixture"]


# ── Routing sentinels (KTD6) ──────────────────────────────────────────────────

COMPLIANCE_PREFIX = "COMPLIANCE="
ANALYST_PREFIX = "ANALYST="


def compliance_sentinel(status: str) -> str:
    """Return the anchored Compliance routing token, e.g. `COMPLIANCE=CLEARED`."""
    if status not in get_args(ComplianceStatus):
        raise ValueError(f"invalid compliance status: {status!r}")
    return f"{COMPLIANCE_PREFIX}{status}"


def analyst_sentinel(status: str) -> str:
    """Return the anchored Analyst routing token, e.g. `ANALYST=RECOMMENDATION`."""
    if status not in get_args(AnalystStatus):
        raise ValueError(f"invalid analyst status: {status!r}")
    return f"{ANALYST_PREFIX}{status}"


# Edge-condition route labels — what seed `workflow_edges.condition` values match.
ROUTE_COMPLIANCE_CLEARED = compliance_sentinel("CLEARED")
ROUTE_COMPLIANCE_FLAGGED = compliance_sentinel("FLAGGED")
ROUTE_COMPLIANCE_NEEDS_REVIEW = compliance_sentinel("NEEDS_REVIEW")
ROUTE_ANALYST_RECOMMENDATION = analyst_sentinel("RECOMMENDATION")
ROUTE_ANALYST_NEEDS_MORE_DATA = analyst_sentinel("NEEDS_MORE_DATA")

COMPLIANCE_SENTINELS = frozenset(
    {ROUTE_COMPLIANCE_CLEARED, ROUTE_COMPLIANCE_FLAGGED, ROUTE_COMPLIANCE_NEEDS_REVIEW}
)
ANALYST_SENTINELS = frozenset({ROUTE_ANALYST_RECOMMENDATION, ROUTE_ANALYST_NEEDS_MORE_DATA})


def _require(value: str, allowed: tuple[str, ...], label: str) -> str:
    if value not in allowed:
        raise ValueError(f"invalid {label}: {value!r} (allowed: {', '.join(allowed)})")
    return value


# ── Provider + sender value objects ───────────────────────────────────────────

@dataclass
class NearestLocation:
    name: str
    distance: str
    hours: str

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> NearestLocation:
        return cls(name=d["name"], distance=d["distance"], hours=d["hours"])


@dataclass
class ProviderQuote:
    fee_usd: float
    rate_cop: float
    cop_received: int
    delivery_minutes: int | None = None
    nearest_location: NearestLocation | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "fee_usd": self.fee_usd,
            "rate_cop": self.rate_cop,
            "cop_received": self.cop_received,
            "delivery_minutes": self.delivery_minutes,
            "nearest_location": (
                self.nearest_location.to_dict() if self.nearest_location else None
            ),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ProviderQuote:
        loc = d.get("nearest_location")
        return cls(
            fee_usd=d["fee_usd"],
            rate_cop=d["rate_cop"],
            cop_received=d["cop_received"],
            delivery_minutes=d.get("delivery_minutes"),
            nearest_location=NearestLocation.from_dict(loc) if loc else None,
        )


@dataclass
class SenderProfile:
    previously_flagged: bool
    kyc_verified: bool
    account_tier: str

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SenderProfile:
        return cls(
            previously_flagged=d["previously_flagged"],
            kyc_verified=d["kyc_verified"],
            account_tier=d["account_tier"],
        )


# ── Research output: the transfer brief ───────────────────────────────────────

@dataclass
class TransferBrief:
    transfer_type: TransferType
    amount_usd: float
    sender_city: str
    sender_country: str
    recipient_country: str
    recipient_city: str
    send_currency: str
    receive_currency: str
    data_source: DataSource
    sender_profile: SenderProfile
    western_union: ProviderQuote | None = None
    moneygram: ProviderQuote | None = None
    wise: ProviderQuote | None = None
    missing_fields: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "transfer_type": self.transfer_type,
            "amount_usd": self.amount_usd,
            "sender_city": self.sender_city,
            "sender_country": self.sender_country,
            "recipient_country": self.recipient_country,
            "recipient_city": self.recipient_city,
            "send_currency": self.send_currency,
            "receive_currency": self.receive_currency,
            "data_source": self.data_source,
            "sender_profile": self.sender_profile.to_dict(),
            "western_union": self.western_union.to_dict() if self.western_union else None,
            "moneygram": self.moneygram.to_dict() if self.moneygram else None,
            "wise": self.wise.to_dict() if self.wise else None,
            "missing_fields": list(self.missing_fields),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TransferBrief:
        _require(d["transfer_type"], get_args(TransferType), "transfer_type")
        _require(d["data_source"], get_args(DataSource), "data_source")

        def _quote(key: str) -> ProviderQuote | None:
            raw = d.get(key)
            return ProviderQuote.from_dict(raw) if raw else None

        return cls(
            transfer_type=d["transfer_type"],
            amount_usd=d["amount_usd"],
            sender_city=d["sender_city"],
            sender_country=d["sender_country"],
            recipient_country=d["recipient_country"],
            recipient_city=d["recipient_city"],
            send_currency=d["send_currency"],
            receive_currency=d["receive_currency"],
            data_source=d["data_source"],
            sender_profile=SenderProfile.from_dict(d["sender_profile"]),
            western_union=_quote("western_union"),
            moneygram=_quote("moneygram"),
            wise=_quote("wise"),
            missing_fields=list(d.get("missing_fields", [])),
        )


# ── Compliance output ─────────────────────────────────────────────────────────

@dataclass
class ComplianceResult:
    status: ComplianceStatus
    notes: list[str] = field(default_factory=list)
    issue: str | None = None

    def sentinel(self) -> str:
        return compliance_sentinel(self.status)

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "notes": list(self.notes), "issue": self.issue}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ComplianceResult:
        _require(d["status"], get_args(ComplianceStatus), "compliance status")
        return cls(
            status=d["status"],
            notes=list(d.get("notes", [])),
            issue=d.get("issue"),
        )


# ── Analyst input + output ────────────────────────────────────────────────────

@dataclass
class AnalystInput:
    """The cross-role payload the Analyst receives: the Research brief plus the
    Compliance clearance. (Compliance must be CLEARED for the Analyst to run; the
    routing that enforces that lives in the graph, not here.)"""
    brief: TransferBrief
    compliance: ComplianceResult

    def to_dict(self) -> dict[str, Any]:
        return {"brief": self.brief.to_dict(), "compliance": self.compliance.to_dict()}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> AnalystInput:
        return cls(
            brief=TransferBrief.from_dict(d["brief"]),
            compliance=ComplianceResult.from_dict(d["compliance"]),
        )


@dataclass
class AnalystResult:
    status: AnalystStatus
    winner: str | None = None
    scores: dict[str, float] = field(default_factory=dict)
    telegram_message: str | None = None
    report_path: str | None = None
    missing_fields: list[str] = field(default_factory=list)

    def sentinel(self) -> str:
        return analyst_sentinel(self.status)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "winner": self.winner,
            "scores": dict(self.scores),
            "telegram_message": self.telegram_message,
            "report_path": self.report_path,
            "missing_fields": list(self.missing_fields),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> AnalystResult:
        _require(d["status"], get_args(AnalystStatus), "analyst status")
        return cls(
            status=d["status"],
            winner=d.get("winner"),
            scores=dict(d.get("scores", {})),
            telegram_message=d.get("telegram_message"),
            report_path=d.get("report_path"),
            missing_fields=list(d.get("missing_fields", [])),
        )
