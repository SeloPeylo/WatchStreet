"""Pick the runner configured in settings."""

from watchstreet.agents.base import AgentError, AgentRunner
from watchstreet.agents.cli_runner import CliRunner
from watchstreet.agents.http_runners import AnthropicRunner, OpenAICompatibleRunner
from watchstreet.agents.offline import OfflineRunner
from watchstreet.config import Settings


def build_runner(settings: Settings) -> AgentRunner:
    kind = settings.agent_runner
    if kind == "offline":
        return OfflineRunner()
    if kind == "anthropic":
        return AnthropicRunner(
            settings.anthropic_api_key,
            settings.anthropic_model,
            settings.agent_timeout_s,
        )
    if kind == "openai":
        return OpenAICompatibleRunner(
            settings.openai_base_url,
            settings.openai_model,
            settings.openai_api_key,
            settings.agent_timeout_s,
        )
    if kind == "cli":
        return CliRunner(settings.agent_cli_command, settings.agent_timeout_s)
    msg = f"Unknown agent runner: {kind}"
    raise AgentError(msg)
