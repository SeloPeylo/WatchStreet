"""System status shown on the dashboard and the system page (worker liveness, last scan)."""

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from watchstreet.constants import HEARTBEAT_STALE_AFTER, LAST_SCAN_KEY, WORKER_HEARTBEAT_KEY
from watchstreet.services.state import updated_at
from watchstreet.timeutil import utcnow


def worker_alive(beat: datetime | None, now: datetime | None = None) -> bool:
    """The worker counts as alive while its last heartbeat is recent enough."""
    return beat is not None and (now or utcnow()) - beat < HEARTBEAT_STALE_AFTER


def system_status(
    session: Session, *, market: str, runner: str, scan_interval_min: int
) -> dict[str, Any]:
    beat = updated_at(session, WORKER_HEARTBEAT_KEY)
    return {
        "market": market,
        "runner": runner,
        "worker_alive": worker_alive(beat),
        "worker_beat": beat,
        "last_scan": updated_at(session, LAST_SCAN_KEY),
        "scan_interval": scan_interval_min,
    }
