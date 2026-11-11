"""Research API: proposals (backlog), tickets, theses, the situation report."""

from datetime import UTC, date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from watchstreet.domain import OPEN_STATUSES, Stance, SubjectType, TicketStatus
from watchstreet.models import (
    Asset,
    Company,
    Fact,
    Finding,
    Proposal,
    Thesis,
    ThesisAssumption,
    Ticket,
)
from watchstreet.services import changes, proposals, theses, tickets
from watchstreet.web import payloads
from watchstreet.web.deps import SessionDep, get_or_404

router = APIRouter(prefix="/api/v1", tags=["research"])


def _names(session: Session) -> dict[tuple[str, int], str]:
    """Subject labels for lists (three small queries instead of one per row)."""
    names: dict[tuple[str, int], str] = {}
    for asset in session.scalars(select(Asset)):
        names[(SubjectType.ASSET, asset.id)] = asset.name
    for company in session.scalars(select(Company)):
        names[(SubjectType.COMPANY, company.id)] = company.name
    for thesis in session.scalars(select(Thesis)):
        names[(SubjectType.THESIS, thesis.id)] = thesis.title
    return names


# --- proposals -------------------------------------------------------------------


class ProposalBody(BaseModel):
    subject_type: str = SubjectType.ASSET
    subject_id: int
    template: str
    question: str = ""
    metric: str = ""
    url: str = ""
    thesis_id: int | None = None
    start: bool = False


@router.get("/proposals")
def list_proposals(session: SessionDep) -> list[dict[str, Any]]:
    names = _names(session)
    return [
        payloads.proposal(p, names.get((p.subject_type, p.subject_id), ""))
        for p in proposals.list_proposals(session)
    ]


@router.get("/templates")
def templates() -> list[dict[str, str]]:
    return [{"key": t.key, "label": t.label} for t in proposals.TEMPLATES.values()]


@router.post("/proposals")
def create_proposal(body: ProposalBody, session: SessionDep) -> dict[str, Any]:
    params = {k: v for k, v in (("metric", body.metric), ("url", body.url)) if v}
    proposal = proposals.create_proposal(
        session,
        body.subject_type,
        body.subject_id,
        body.template,
        question=body.question,
        params=params,
        thesis_id=body.thesis_id,
    )
    if proposal is None:  # only machine-made proposals are ever dropped
        raise proposals.ProposalError("Vorschlag konnte nicht angelegt werden")
    if body.start:
        proposals.start(session, proposal)
    return payloads.proposal(proposal)


class QuestionBody(BaseModel):
    question: str


@router.patch("/proposals/{proposal_id}")
def edit_proposal(proposal_id: int, body: QuestionBody, session: SessionDep) -> dict[str, Any]:
    proposal = get_or_404(session, Proposal, proposal_id)
    proposals.update_question(session, proposal, body.question)
    return payloads.proposal(proposal)


class IdsBody(BaseModel):
    ids: list[int]


@router.post("/proposals/start")
def start_proposals(body: IdsBody, session: SessionDep) -> list[dict[str, Any]]:
    """The deliberate start, for one or many collected proposals."""
    started = [
        proposals.start(session, get_or_404(session, Proposal, proposal_id))
        for proposal_id in body.ids
    ]
    return [payloads.ticket(t) for t in started]


@router.post("/proposals/{proposal_id}/dismiss")
def dismiss_proposal(proposal_id: int, session: SessionDep) -> dict[str, Any]:
    proposal = get_or_404(session, Proposal, proposal_id)
    proposals.dismiss(session, proposal)
    return payloads.proposal(proposal)


# --- tickets ---------------------------------------------------------------------


@router.get("/tickets")
def list_tickets(session: SessionDep, status: str = "") -> list[dict[str, Any]]:
    names = _names(session)
    return [
        payloads.ticket(t, names.get((t.subject_type, t.subject_id), ""))
        for t in tickets.list_tickets(session, status or None)
    ]


@router.get("/tickets/{ticket_id}")
def ticket_detail(ticket_id: int, session: SessionDep) -> dict[str, Any]:
    ticket = get_or_404(session, Ticket, ticket_id)
    name = _names(session).get((ticket.subject_type, ticket.subject_id), "")
    return payloads.ticket(ticket, name, full=True)


@router.post("/tickets/{ticket_id}/retry")
def retry_ticket(ticket_id: int, session: SessionDep) -> dict[str, Any]:
    ticket = get_or_404(session, Ticket, ticket_id)
    tickets.retry(session, ticket)
    return payloads.ticket(ticket)


@router.post("/tickets/{ticket_id}/cancel")
def cancel_ticket(ticket_id: int, session: SessionDep) -> dict[str, Any]:
    ticket = get_or_404(session, Ticket, ticket_id)
    tickets.cancel(session, ticket)
    return payloads.ticket(ticket)


@router.post("/tickets/{ticket_id}/seen")
def mark_seen(ticket_id: int, session: SessionDep) -> dict[str, Any]:
    ticket = get_or_404(session, Ticket, ticket_id)
    ticket.seen = True
    return payloads.ticket(ticket)


@router.get("/notifications")
def notifications(session: SessionDep) -> dict[str, Any]:
    """What the bell shows: finished results not yet opened, and how much is still running."""
    names = _names(session)
    rows = list(session.scalars(select(Ticket).order_by(Ticket.id.desc())))
    finished = (TicketStatus.DONE, TicketStatus.FAILED)
    return {
        "running": sum(1 for t in rows if t.status in OPEN_STATUSES),
        "unseen": [
            payloads.ticket(t, names.get((t.subject_type, t.subject_id), ""))
            for t in rows
            if t.status in finished and not t.seen
        ],
    }


# --- theses ----------------------------------------------------------------------


class ThesisBody(BaseModel):
    title: str
    statement: str = ""
    horizon: str = ""
    commodity: str = ""


@router.get("/theses")
def list_theses(session: SessionDep) -> list[dict[str, Any]]:
    findings = {f.id: f for f in session.scalars(select(Finding))}
    rows = theses.list_theses(session)
    fact_ids = {x.target_id for t in rows for x in t.links if x.target_type == "fact"}
    facts = {f.id: f for f in session.scalars(select(Fact).where(Fact.id.in_(fact_ids)))}
    return [payloads.thesis(t, findings, facts) for t in rows]


@router.post("/theses")
def create_thesis(body: ThesisBody, session: SessionDep) -> dict[str, Any]:
    thesis = theses.create_thesis(session, body.title, body.statement, body.horizon, body.commodity)
    return payloads.thesis(thesis)


class LinkBody(BaseModel):
    target_type: str
    target_id: int
    stance: str = Stance.CONTEXT
    note: str = ""
    assumption_id: int | None = None


@router.post("/theses/{thesis_id}/links")
def link_thesis(thesis_id: int, body: LinkBody, session: SessionDep) -> dict[str, Any]:
    thesis = get_or_404(session, Thesis, thesis_id)
    theses.link(
        session,
        thesis,
        body.target_type,
        body.target_id,
        body.stance,
        body.note,
        assumption_id=body.assumption_id,
    )
    session.refresh(thesis)
    return payloads.thesis(thesis)


class AssumptionBody(BaseModel):
    text: str = ""
    status: str = ""
    reason: str = ""
    criterion: str | None = None
    review_by: date | None = None


@router.post("/theses/{thesis_id}/assumptions")
def add_assumption(thesis_id: int, body: AssumptionBody, session: SessionDep) -> dict[str, Any]:
    thesis = get_or_404(session, Thesis, thesis_id)
    theses.add_assumption(session, thesis, body.text, body.criterion or "", body.review_by)
    session.refresh(thesis)
    return payloads.thesis(thesis)


@router.patch("/assumptions/{assumption_id}")
def update_assumption(
    assumption_id: int, body: AssumptionBody, session: SessionDep
) -> dict[str, Any]:
    assumption = get_or_404(session, ThesisAssumption, assumption_id)
    if body.criterion is not None:
        theses.update_assumption_test(session, assumption, body.criterion, body.review_by)
    if body.status:
        theses.set_assumption_status(session, assumption, body.status, body.reason)
    return {"id": assumption.id, "status": assumption.status}


def _parse_since(raw: str) -> datetime | None:
    """Accepts a date or a timestamp; a date means the start of that day (UTC)."""
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Ungültiges Datum") from exc
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


# --- situation report --------------------------------------------------------------


@router.get("/changes")
def situation_report(
    session: SessionDep, since_raw: Annotated[str, Query(alias="since")] = ""
) -> dict[str, Any]:
    """Changes since the last visit, or since a freely chosen date."""
    since = _parse_since(since_raw)
    visit = changes.last_visit(session)
    names = _names(session)
    start = since or visit
    rows = changes.changes_since(session, start)
    return {
        "last_visit": visit.isoformat() if visit else None,
        "since": start.isoformat() if start else None,
        "changes": [
            payloads.change(c, names.get((c.subject_type, c.subject_id), "")) for c in rows
        ],
    }


@router.post("/visits")
def mark_visit(session: SessionDep) -> dict[str, str]:
    changes.mark_visit(session)
    return {"status": "ok"}
