"""The 'no agent' runner: research then consists of the deterministic steps only."""

from watchstreet.agents.base import AgentRequest


class OfflineRunner:
    """Never invents an answer; workflows check ``name`` and skip the agent step."""

    name = "offline"

    def complete(self, request: AgentRequest) -> str:  # noqa: ARG002
        return ""
