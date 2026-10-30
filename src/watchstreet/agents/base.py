"""Runner protocol and request type."""

from dataclasses import dataclass, field
from typing import Any, Protocol

from watchstreet.errors import WatchStreetError


class AgentError(WatchStreetError, RuntimeError):
    """Raised when an agent backend fails or returns unusable output."""


@dataclass(frozen=True)
class AgentRequest:
    """What a workflow asks an agent to do.

    ``system`` and ``prompt`` are for real LLM backends. ``workflow``, ``task`` and ``facts``
    are the structured form the rule-based offline runner works from.
    """

    workflow: str
    system: str
    prompt: str
    task: str = ""
    facts: dict[str, Any] = field(default_factory=dict)


class AgentRunner(Protocol):
    name: str

    def complete(self, request: AgentRequest) -> str:
        """Return the raw model answer (expected to be a JSON document)."""
        ...
