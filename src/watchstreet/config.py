"""Runtime configuration, read from environment variables."""

import os
from dataclasses import dataclass

from watchstreet.constants import DEFAULT_EVENT_SCAN_INTERVAL_MIN, DEFAULT_WORKER_POLL_S

ENV_PREFIX = "WATCHSTREET_"
DEFAULT_AGENT_TIMEOUT_S = 180.0
DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-5-5"


@dataclass(frozen=True)
class Settings:
    """Immutable application settings."""

    database_url: str = "sqlite:///./data/watchstreet.db"
    market_provider: str = "yahoo"
    agent_runner: str = "offline"
    anthropic_api_key: str = ""
    anthropic_model: str = DEFAULT_ANTHROPIC_MODEL
    openai_base_url: str = "http://host.docker.internal:11434/v1"
    openai_model: str = "llama3.1"
    openai_api_key: str = ""
    agent_cli_command: str = "claude -p"
    agent_timeout_s: float = DEFAULT_AGENT_TIMEOUT_S
    worker_poll_s: float = DEFAULT_WORKER_POLL_S
    event_scan_interval_min: int = DEFAULT_EVENT_SCAN_INTERVAL_MIN
    docs_dir: str = "docs"
    llama_base_url: str = "http://llama:8080/v1"
    agent_tools: bool = True
    password: str = ""  # empty = no login (only safe on localhost)
    secret_key: str = ""  # signs session cookies; random per start if empty
    sec_user_agent: str = "WatchStreet (set WATCHSTREET_SEC_USER_AGENT to your name and e-mail)"


def _env(name: str, default: str) -> str:
    return os.environ.get(f"{ENV_PREFIX}{name}", default)


def load_settings() -> Settings:
    """Build settings from the environment, falling back to defaults."""
    base = Settings()
    return Settings(
        database_url=_env("DATABASE_URL", base.database_url),
        market_provider=_env("MARKET_PROVIDER", base.market_provider).lower(),
        agent_runner=_env("AGENT_RUNNER", base.agent_runner).lower(),
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", base.anthropic_api_key),
        anthropic_model=_env("ANTHROPIC_MODEL", base.anthropic_model),
        openai_base_url=_env("OPENAI_BASE_URL", base.openai_base_url),
        openai_model=_env("OPENAI_MODEL", base.openai_model),
        openai_api_key=_env("OPENAI_API_KEY", base.openai_api_key),
        agent_cli_command=_env("AGENT_CLI_COMMAND", base.agent_cli_command),
        agent_timeout_s=float(_env("AGENT_TIMEOUT_S", str(base.agent_timeout_s))),
        worker_poll_s=float(_env("WORKER_POLL_S", str(base.worker_poll_s))),
        event_scan_interval_min=int(
            _env("EVENT_SCAN_INTERVAL_MIN", str(base.event_scan_interval_min)),
        ),
        docs_dir=_env("DOCS_DIR", base.docs_dir),
        llama_base_url=_env("LLAMA_BASE_URL", base.llama_base_url),
        sec_user_agent=_env("SEC_USER_AGENT", base.sec_user_agent),
        password=_env("PASSWORD", base.password),
        secret_key=_env("SECRET_KEY", base.secret_key),
        agent_tools=_env("AGENT_TOOLS", "true").lower() in ("1", "true", "yes"),
    )
