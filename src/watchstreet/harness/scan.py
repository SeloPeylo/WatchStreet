"""The periodic background scan: prices, events and the deterministic engine. No LLM runs here."""

import logging
from datetime import timedelta

from watchstreet.constants import LAST_SCAN_KEY, SCAN_REQUEST_KEY
from watchstreet.container import Container
from watchstreet.db import session_scope
from watchstreet.intel.connectors.usgs import recent_quakes
from watchstreet.intel.fetch import FetchError
from watchstreet.services.engine import EngineReport, run_engine
from watchstreet.services.events import record_quakes
from watchstreet.services.prices import sync_history
from watchstreet.services.state import touch, updated_at
from watchstreet.services.viewing import build_view
from watchstreet.services.world import load_bundle
from watchstreet.timeutil import utcnow

logger = logging.getLogger(__name__)


def run_scan(container: Container) -> EngineReport:
    """Each step is isolated: a failing source never blocks the others."""
    with session_scope(container.session_factory) as session:
        touch(session, LAST_SCAN_KEY)
        sync_history(session, container.market)
    try:
        quakes = recent_quakes(container.fetcher)
    except FetchError as exc:
        logger.warning("Earthquake feed unavailable: %s", exc)
        quakes = []
    with session_scope(container.session_factory) as session:
        record_quakes(session, quakes, is_demo=container.is_demo)
    with session_scope(container.session_factory) as session:
        return run_engine(session, load_bundle(session), build_view(session, container.market))


def scan_due(container: Container) -> bool:
    interval = timedelta(minutes=container.settings.event_scan_interval_min)
    with session_scope(container.session_factory) as session:
        last = updated_at(session, LAST_SCAN_KEY)
        requested = updated_at(session, SCAN_REQUEST_KEY)
    if last is None or utcnow() - last >= interval:
        return True
    return requested is not None and requested > last
