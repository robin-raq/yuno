"""AnalystAdapter: deterministic scoring and report generation behind AgentRuntimeAdapter."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Awaitable, Callable

from app.adapters.base import AgentRuntimeAdapter, TaskInput, TaskResult
from app.domain.remittance.analyst import analyze, format_output
from app.domain.remittance.json_extract import JsonExtractError, extract_json_object
from app.domain.remittance.types import (
    AnalystInput,
    AnalystResult,
)

log = logging.getLogger(__name__)

_DEFAULT_REPORTS_DIR = (
    Path(__file__).resolve().parent.parent.parent.parent / "reports"
)


class AnalystAdapter(AgentRuntimeAdapter):
    """Scripted adapter for the Analyst node — deterministic, no LLM."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 0,
        *,
        reports_dir: str | Path | None = None,
    ) -> None:
        self._reports_dir = Path(reports_dir) if reports_dir else _DEFAULT_REPORTS_DIR

    async def invoke(
        self,
        task: TaskInput,
        on_event: Callable[[dict], Awaitable[None]],
    ) -> TaskResult:
        try:
            payload = extract_json_object(task.task_content)
            analyst_input = AnalystInput.from_dict(payload)
            if analyst_input.compliance.status != "CLEARED":
                return TaskResult(
                    output=format_output(
                        AnalystResult(
                            status="NEEDS_MORE_DATA",
                            missing_fields=[
                                f"compliance status is {analyst_input.compliance.status}, expected CLEARED"
                            ],
                        )
                    )
                )
            result = analyze(
                analyst_input.brief,
                reports_dir=self._reports_dir,
                compliance_notes=analyst_input.compliance.notes,
            )
        except (JsonExtractError, json.JSONDecodeError, ValueError, TypeError, KeyError, AttributeError, OSError) as exc:
            log.warning("AnalystAdapter: failed to process task_content: %s", exc)
            result = AnalystResult(
                status="NEEDS_MORE_DATA",
                missing_fields=[f"Analyst input could not be processed; failing closed. Detail: {exc}"],
            )
        return TaskResult(output=format_output(result))

    async def health_check(self) -> bool:
        return True
