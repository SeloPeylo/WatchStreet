"""Wires settings, database, market data and agent runner together."""

from dataclasses import dataclass

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from watchstreet.agents.base import AgentRunner
from watchstreet.agents.factory import build_runner
from watchstreet.config import Settings
from watchstreet.db import make_engine, make_session_factory, session_scope
from watchstreet.intel.connectors.edgar import EdgarClient
from watchstreet.intel.demo import demo_client, demo_resolver
from watchstreet.intel.fetch import Fetcher
from watchstreet.intel.ingest import seed_feeds
from watchstreet.market.service import MarketService, build_provider
from watchstreet.models import Base

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
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    with session_scope(factory) as session:
        seed_feeds(session)
    return Container(
        settings=settings,
        engine=engine,
        session_factory=factory,
        market=market or MarketService(build_provider(settings)),
        runner=runner or build_runner(settings),
        fetcher=fetcher,
        edgar=EdgarClient(sec_fetcher),
    )
