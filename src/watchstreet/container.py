"""Wires settings, database, market data and agent runner together."""

from dataclasses import dataclass

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from watchstreet.agents.base import AgentRunner
from watchstreet.agents.factory import build_runner
from watchstreet.config import Settings
from watchstreet.db import make_engine, make_session_factory
from watchstreet.market.service import MarketService, build_provider
from watchstreet.models import Base


@dataclass
class Container:
    settings: Settings
    engine: Engine
    session_factory: sessionmaker[Session]
    market: MarketService
    runner: AgentRunner


def build_container(
    settings: Settings,
    market: MarketService | None = None,
    runner: AgentRunner | None = None,
) -> Container:
    engine = make_engine(settings.database_url)
    Base.metadata.create_all(engine)
    return Container(
        settings=settings,
        engine=engine,
        session_factory=make_session_factory(engine),
        market=market or MarketService(build_provider(settings)),
        runner=runner or build_runner(settings),
    )
