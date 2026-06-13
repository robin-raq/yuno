"""Adapter ABC — the seam isolating all runtime coupling from the orchestrator."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Awaitable, Callable


@dataclass
class TaskInput:
    context_preamble: str   # role + instructions + memory + skills + interaction rules
    task_content: str       # the actual task content
    model: str
    extensions: list[str]
    max_turns: int
    timeout_seconds: int


@dataclass
class TaskResult:
    output: str
    tool_calls: list[dict] = field(default_factory=list)
    tokens_input: int = 0
    tokens_output: int = 0
    tokens_total: int = 0
    estimated_cost: float = 0.0
    session_id: str | None = None


class AgentRuntimeAdapter(ABC):
    @abstractmethod
    async def invoke(
        self,
        task: TaskInput,
        on_event: Callable[[dict], Awaitable[None]],
    ) -> TaskResult: ...

    @abstractmethod
    async def health_check(self) -> bool: ...
