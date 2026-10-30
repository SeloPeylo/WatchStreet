"""Persist what a finished workflow learned so it survives the ticket."""

from sqlalchemy.orm import Session

from watchstreet.models import Insight, Score, Thesis, Ticket
from watchstreet.workflows.base import WorkflowResult


def store_result(session: Session, ticket: Ticket, result: WorkflowResult) -> None:
    for draft in result.insights:
        session.add(
            Insight(
                stock_id=ticket.stock_id,
                ticket_id=ticket.id,
                category=draft.category,
                text=draft.text,
            ),
        )
    for score in result.scores:
        session.add(
            Score(
                stock_id=ticket.stock_id,
                ticket_id=ticket.id,
                scheme=score.scheme,
                value=score.value,
                label=score.label,
                details=score.details,
            ),
        )
    if result.thesis:
        session.add(
            Thesis(
                stock_id=ticket.stock_id,
                ticket_id=ticket.id,
                text=result.thesis.text,
                status=result.thesis.status,
            ),
        )
