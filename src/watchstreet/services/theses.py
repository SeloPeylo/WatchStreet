"""Investment theses with assumptions and linked evidence."""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from watchstreet.domain import Stance, SubjectType
from watchstreet.errors import WatchStreetError
from watchstreet.models import (
    Asset,
    Company,
    Document,
    Fact,
    Finding,
    Thesis,
    ThesisAssumption,
    ThesisLink,
)
from watchstreet.services.changes import log_change

LINK_TARGETS = ("asset", "company", "finding", "document", "fact")
ASSUMPTION_STATES = ("open", "supported", "contradicted", "unclear")
STATE_LABEL = {"open": "offen", "supported": "gestützt"}
STATE_LABEL |= {"contradicted": "widerlegt", "unclear": "unklar"}
STANCE_LABEL = {"supports": "stützt", "contradicts": "widerspricht", "context": "Kontext"}
LINK_MODELS: dict[str, type[Asset | Company | Finding | Document | Fact]] = {
    "asset": Asset, "company": Company, "finding": Finding, "document": Document, "fact": Fact,
}  # fmt: skip


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
    if not reason.strip() and (status != "open" or assumption.status != "open"):
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
        f"Annahme jetzt „{STATE_LABEL[status]}“: {assumption.text} – "
        f"{reason.strip() or 'ohne Begründung'}",
        old=STATE_LABEL.get(old, old),
        new=STATE_LABEL[status],
    )


def update_assumption_test(
    session: Session, assumption: ThesisAssumption, criterion: str, review_by: date | None
) -> None:
    before = f"{assumption.criterion or '–'} (prüfen bis {assumption.review_by or '–'})"
    assumption.criterion, assumption.review_by = criterion.strip(), review_by
    session.flush()
    after = f"{assumption.criterion or '–'} (prüfen bis {assumption.review_by or '–'})"
    if before != after:  # moving the bar afterwards must leave a trace
        log_change(
            session, SubjectType.THESIS, assumption.thesis_id, "thesis",
            f"Kriterium geändert: {assumption.text}", old=before, new=after,
        )  # fmt: skip


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
    if session.get(LINK_MODELS[target_type], target_id) is None:
        msg = "Das verknüpfte Objekt existiert nicht"
        raise ThesisError(msg)
    log_change(
        session, SubjectType.THESIS, thesis.id, "thesis",
        f"Evidenz zugeordnet ({STANCE_LABEL.get(stance, stance)}): {target_type} #{target_id}",
    )  # fmt: skip
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
