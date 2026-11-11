"""Tiny key/value store shared by web and worker."""

from datetime import datetime

from sqlalchemy.orm import Session

from watchstreet.models import SystemState
from watchstreet.timeutil import utcnow


def touch(session: Session, key: str, value: str = "") -> None:
    row = session.get(SystemState, key)
    if row is None:
        session.add(SystemState(key=key, value=value, updated_at=utcnow()))
    else:
        row.value, row.updated_at = value, utcnow()


def updated_at(session: Session, key: str) -> datetime | None:
    row = session.get(SystemState, key)
    return row.updated_at if row else None
