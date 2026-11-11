"""Tool-calling primitives shared by runners and workflows."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from watchstreet.agents.base import AgentRequest
from watchstreet.errors import WatchStreetError


class ToolError(WatchStreetError, ValueError):
    """A tool call the model got wrong; the message is returned to the model so it can retry."""


@dataclass(frozen=True)
class Tool:
    """A function the agent may call. ``parameters`` is a JSON schema object."""

    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[[dict[str, Any]], str]

    def spec(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass(frozen=True)
class ToolRun:
    """Outcome of one agent session with tools."""

    text: str
    steps: int
    tool_calls: int
    prompt_tokens: int = 0
    completion_tokens: int = 0


class ToolCapableRunner(Protocol):
    name: str
    supports_tools: bool

    def complete(self, request: AgentRequest) -> str: ...

    def run_with_tools(self, system: str, prompt: str, tools: Sequence[Tool]) -> ToolRun: ...
