"""Wires settings, database, market data and agent runner together."""

import json
from dataclasses import dataclass, field, replace

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from watchstreet.agents.base import AgentError, AgentRunner
from watchstreet.agents.factory import build_runner
from watchstreet.config import Settings
from watchstreet.db import make_engine, make_session_factory, session_scope
from watchstreet.intel.connectors.edgar import EdgarClient
from watchstreet.intel.demo import demo_client, demo_resolver
from watchstreet.intel.fetch import Fetcher
from watchstreet.market.service import MarketService, build_provider
from watchstreet.migrate import startup_lock, upgrade_to_head
from watchstreet.models import SystemState
from watchstreet.services.demo import seed_demo

AGENT_CONFIG_KEY = "agent_config"
RUNTIME_RUNNERS = ("offline", "anthropic", "openai")  # never "cli": no commands from the UI
SEC_MIN_INTERVAL_S = 0.15  # SEC allows 10 requests per second; stay well below


@dataclass
class Container:
    settings: Settings
    engine: Engine
    session_factory: sessionmaker[Session]
    market: MarketService
    runner: AgentRunner
    fetcher: Fetcher
    edgar: EdgarClient
    runtime_runners: dict[str, AgentRunner] = field(default_factory=dict)

    @property
    def is_demo(self) -> bool:
        return self.settings.market_provider == "demo"


def agent_config(session: Session) -> dict[str, str]:
    """The agent settings entered at runtime; empty if the environment decides."""
    row = session.get(SystemState, AGENT_CONFIG_KEY)
    try:
        data = json.loads(row.value) if row and row.value else {}
    except json.JSONDecodeError:
        data = {}
    return {k: str(v) for k, v in data.items()} if isinstance(data, dict) else {}


def runner_from_config(container: Container, config: dict[str, str]) -> AgentRunner:
    """Build a runner from runtime settings; missing parts fall back to the environment."""
    base = container.settings
    return build_runner(
        replace(
            base,
            agent_runner=config.get("runner", ""),
            anthropic_api_key=config.get("api_key") or base.anthropic_api_key,
            anthropic_model=config.get("model") or base.anthropic_model,
            openai_api_key=config.get("api_key") or base.openai_api_key,
            openai_model=config.get("model") or base.openai_model,
            openai_base_url=config.get("base_url") or base.openai_base_url,
        )
    )


def runner_for(container: Container, session: Session) -> AgentRunner:
    """The runner to use now: the runtime setting if there is one, else the one from the start."""
    config = agent_config(session)
    kind = config.get("runner", "")
    if kind not in RUNTIME_RUNNERS:
        return container.runner
    cache_key = json.dumps(config, sort_keys=True)
    if cache_key not in container.runtime_runners:
        try:
            runner = runner_from_config(container, config)
        except AgentError:
            return container.runner
        container.runtime_runners.clear()
        container.runtime_runners[cache_key] = runner
    return container.runtime_runners[cache_key]


def build_container(
    settings: Settings,
    market: MarketService | None = None,
    runner: AgentRunner | None = None,
    fetcher: Fetcher | None = None,
    sec_fetcher: Fetcher | None = None,
) -> Container:
    if settings.market_provider == "demo":
        fetcher = fetcher or Fetcher(demo_client(), demo_resolver, min_interval_s=0.0)
        sec_fetcher = sec_fetcher or fetcher
    fetcher = fetcher or Fetcher()
    sec_fetcher = sec_fetcher or Fetcher(
        user_agent=settings.sec_user_agent,
        min_interval_s=SEC_MIN_INTERVAL_S,
    )
    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)
    market = market or MarketService(build_provider(settings))
    with startup_lock(engine):
        upgrade_to_head(engine)
        if settings.market_provider == "demo":
            with session_scope(factory) as session:
                seed_demo(session, market)
    return Container(
        settings=settings,
        engine=engine,
        session_factory=factory,
        market=market,
        runner=runner or build_runner(settings),
        fetcher=fetcher,
        edgar=EdgarClient(sec_fetcher),
    )
