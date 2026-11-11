"""Change log and visits: the source of the 'since your last visit' report."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from watchstreet.constants import CHANGES_LIMIT, LAST_VISIT_KEY
from watchstreet.models import ChangeEntry
from watchstreet.services.state import touch, updated_at


def log_change(  # noqa: PLR0913
    session: Session,
    subject_type: str,
    subject_id: int,
    kind: str,
    summary: str,
    *,
    old: str = "",
    new: str = "",
) -> None:
    session.add(
        ChangeEntry(
            subject_type=subject_type,
            subject_id=subject_id,
            kind=kind,
            summary=summary,
            old=old,
            new=new,
        )
    )


def last_visit(session: Session) -> datetime | None:
    return updated_at(session, LAST_VISIT_KEY)


def mark_visit(session: Session) -> None:
    """Only an explicit 'mark as read' moves the visit marker."""
    touch(session, LAST_VISIT_KEY)


def changes_since(session: Session, since: datetime | None) -> list[ChangeEntry]:
    query = select(ChangeEntry).order_by(ChangeEntry.id.desc()).limit(CHANGES_LIMIT)
    if since is not None:
        query = query.where(ChangeEntry.at > since)
    return list(session.scalars(query))
