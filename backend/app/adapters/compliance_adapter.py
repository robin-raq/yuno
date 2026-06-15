"""ComplianceAdapter (U5): deterministic compliance check behind AgentRuntimeAdapter.

Pure Python — no Goose, no DB, no network. Parses the Research brief JSON from
``task.task_content``, runs the U4 compliance engine, and returns a ``TaskResult``
whose first output line is a KTD6 sentinel (``COMPLIANCE=CLEARED`` /
``COMPLIANCE=FLAGGED`` / ``COMPLIANCE=NEEDS_REVIEW``).

Fail-closed on any parse failure: :class:`JsonExtractError` or validation errors
return ``COMPLIANCE=FLAGGED`` rather than raising. A raise would route through the
worker's ``task_failed``/``workflow_failed`` path and leave the run ``failed``
with the issue suppressed; the graph needs a visible FLAGGED terminal output
so it can route deterministically (R10, KTD6).

Constructor accepts ``host`` and ``port`` to remain swap-compatible with
``AcpGooseAdapter``; both are ignored. Pass ``rules_path`` to inject the
compliance rules JSON (default: the committed fixture file).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Awaitable, Callable

from app.adapters.base import AgentRuntimeAdapter, TaskInput, TaskResult
from app.domain.remittance.compliance import format_output, screen_from_dict
from app.domain.remittance.json_extract import JsonExtractError, extract_json_object
from app.domain.remittance.types import ComplianceResult

log = logging.getLogger(__name__)

_DEFAULT_RULES_PATH = (
    Path(__file__).resolve().parent.parent.parent / "fixtures" / "compliance_rules.json"
)


class ComplianceAdapter(AgentRuntimeAdapter):
    """Scripted adapter for the Compliance node — deterministic, no LLM."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 0,
        *,
        rules_path: str | Path | None = None,
    ) -> None:
        # host and port accepted for swap-compatibility with AcpGooseAdapter;
        # a deterministic adapter needs neither.
        self._rules_path = Path(rules_path) if rules_path else _DEFAULT_RULES_PATH

    async def invoke(
        self,
        task: TaskInput,
        on_event: Callable[[dict], Awaitable[None]],
    ) -> TaskResult:
        """Screen the Research brief and return a sentinel-prefixed TaskResult.

        Never calls ``on_event`` — there are no Goose streaming events to forward.
        """
        try:
            brief_dict = extract_json_object(task.task_content)
            result = screen_from_dict(brief_dict, rules_path=self._rules_path)
        except (
            JsonExtractError,
            json.JSONDecodeError,
            ValueError,
            TypeError,
            KeyError,
            AttributeError,
            OSError,
        ) as exc:
            # Fail closed on any parse or validation failure — a raise here would
            # route through the worker's task_failed/workflow_failed path and suppress
            # the issue; the graph needs a visible FLAGGED terminal output (R10).
            log.warning("ComplianceAdapter: failed to process task_content: %s", exc)
            result = ComplianceResult(
                status="FLAGGED",
                issue=(
                    "Compliance input could not be processed; "
                    f"failing closed. Detail: {exc}"
                ),
            )
        return TaskResult(output=format_output(result))

    async def health_check(self) -> bool:
        return True
