"""Investment theses with assumptions and linked evidence."""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from watchstreet.domain import Stance, SubjectType
from watchstreet.errors import WatchStreetError
from watchstreet.models import Thesis, ThesisAssumption, ThesisLink
from watchstreet.services.changes import log_change

LINK_TARGETS = ("asset", "company", "finding", "document", "fact")
ASSUMPTION_STATES = ("open", "supported", "contradicted", "unclear")


class ThesisError(WatchStreetError, ValueError):
    """Invalid thesis input."""


def create_thesis(
    session: Session, title: str, statement: str = "", horizon: str = "", commodity: str = ""
) -> Thesis:
    if not title.strip():
        msg = "Eine These braucht einen Titel"
        raise ThesisError(msg)
    thesis = Thesis(
        title=title.strip(),
        statement=statement.strip(),
        horizon=horizon.strip(),
        commodity=commodity,
    )
    session.add(thesis)
    session.flush()
    log_change(session, SubjectType.THESIS, thesis.id, "thesis", f"These angelegt: {thesis.title}")
    return thesis


def list_theses(session: Session) -> list[Thesis]:
    return list(
        session.scalars(
            select(Thesis)
            .options(selectinload(Thesis.assumptions), selectinload(Thesis.links))
            .order_by(Thesis.id)
        )
    )


def add_assumption(
    session: Session,
    thesis: Thesis,
    text: str,
    criterion: str = "",
    review_by: date | None = None,
) -> ThesisAssumption:
    """An assumption is testable only if it says what would refute it and when to look."""
    if not text.strip():
        msg = "Die Annahme darf nicht leer sein"
        raise ThesisError(msg)
    assumption = ThesisAssumption(
        thesis_id=thesis.id, text=text.strip(), criterion=criterion.strip(), review_by=review_by
    )
    session.add(assumption)
    session.flush()
    log_change(
        session, SubjectType.THESIS, thesis.id, "thesis", f"Annahme ergänzt: {assumption.text}"
    )
    return assumption


def set_assumption_status(
    session: Session, assumption: ThesisAssumption, status: str, reason: str = ""
) -> None:
    """A judgement without a stated reason cannot be checked against reality later."""
    if status not in ASSUMPTION_STATES:
        msg = "Unbekannter Status der Annahme"
        raise ThesisError(msg)
    if status != "open" and not reason.strip():
        msg = "Bitte begründen, warum die Annahme so eingeordnet wird"
        raise ThesisError(msg)
    old, assumption.status = assumption.status, status
    assumption.status_reason = reason.strip()
    session.flush()
    log_change(
        session,
        SubjectType.THESIS,
        assumption.thesis_id,
        "thesis",
        f"Annahme neu eingeordnet: {assumption.text} – {reason.strip() or 'ohne Begründung'}",
        old=old,
        new=status,
    )


def update_assumption_test(
    session: Session, assumption: ThesisAssumption, criterion: str, review_by: date | None
) -> None:
    assumption.criterion, assumption.review_by = criterion.strip(), review_by
    session.flush()


def link(  # noqa: PLR0913
    session: Session,
    thesis: Thesis,
    target_type: str,
    target_id: int,
    stance: str = Stance.CONTEXT,
    note: str = "",
    *,
    assumption_id: int | None = None,
) -> ThesisLink:
    if target_type not in LINK_TARGETS or stance not in tuple(Stance):
        msg = "Ungültige Verknüpfung"
        raise ThesisError(msg)
    existing = session.scalars(
        select(ThesisLink).where(
            ThesisLink.thesis_id == thesis.id,
            ThesisLink.target_type == target_type,
            ThesisLink.target_id == target_id,
        )
    ).first()
    if existing:
        existing.stance, existing.note = stance, note.strip() or existing.note
        if assumption_id is not None:
            existing.assumption_id = assumption_id
        return existing
    row = ThesisLink(
        thesis_id=thesis.id,
        target_type=target_type,
        target_id=target_id,
        stance=stance,
        note=note.strip(),
        assumption_id=assumption_id,
    )
    session.add(row)
    session.flush()
    return row
