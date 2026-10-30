"""Persist what a finished workflow learned so it survives the ticket."""

import logging

from sqlalchemy.orm import Session

from watchstreet.models import Briefing, Insight, Score, Thesis, Ticket
from watchstreet.services.datapoints import DatapointError, DatapointInput, add_datapoint
from watchstreet.services.profiles import assign_profile
from watchstreet.workflows.base import WorkflowResult

logger = logging.getLogger(__name__)


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

    for point in result.datapoints:
        try:
            add_datapoint(
                session,
                ticket.stock,
                DatapointInput(
                    point.key,
                    point.subject,
                    point.value,
                    point.text,
                    point.unit,
                    point.source,
                    point.confidence,
                    point.as_of,
                ),
                origin="agent",
                ticket_id=ticket.id,
            )
        except DatapointError as exc:
            logger.warning("Dropped datapoint %s: %s", point.key, exc)
    if result.profile:
        assign_profile(ticket.stock, result.profile.profile, "agent")
    if result.briefing:
        session.add(
            Briefing(
                stock_id=ticket.stock_id,
                ticket_id=ticket.id,
                headline=result.briefing.headline,
                bullets=result.briefing.bullets,
                focus=result.briefing.focus,
                author=result.briefing.author,
            ),
        )
