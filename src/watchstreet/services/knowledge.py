"""Persist what a finished workflow learned so it survives the ticket."""

import logging

from sqlalchemy.orm import Session

from watchstreet.domain import DataOrigin, ProfileSource
from watchstreet.drafts import EntityDraft, WorkflowResult
from watchstreet.models import Briefing, Entity, Insight, Score, Thesis, Ticket
from watchstreet.services.datapoints import DatapointError, DatapointInput, add_datapoint
from watchstreet.services.entities import (
    GraphError,
    RelationInput,
    add_relation,
    entity_for_stock,
    get_or_create_entity,
)
from watchstreet.services.intel import IntelError, create_intel
from watchstreet.services.profiles import assign_profile

SELF = "SELF"

logger = logging.getLogger(__name__)


def store_result(session: Session, ticket: Ticket, result: WorkflowResult) -> None:
    for draft in result.insights:
        session.add(
            Insight(
                stock_id=ticket.stock_id,
                ticket_id=ticket.id,
                category=draft.category,
                text=draft.text,
                document_id=draft.document_id,
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
                    point.document_id,
                    point.quote,
                ),
                origin=point.origin,
                ticket_id=ticket.id,
            )
        except DatapointError as exc:
            logger.warning("Dropped datapoint %s: %s", point.key, exc)
    _store_graph_and_intel(session, ticket, result)
    if result.profile:
        assign_profile(ticket.stock, result.profile.profile, ProfileSource.AGENT)
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


def _entity(session: Session, ticket: Ticket, draft: EntityDraft) -> Entity:
    if draft.name == SELF:
        return entity_for_stock(session, ticket.stock)
    return get_or_create_entity(
        session,
        draft.name,
        draft.kind,
        country=draft.country,
        lat=draft.lat,
        lon=draft.lon,
        origin=DataOrigin.AGENT,
    )


def _store_graph_and_intel(session: Session, ticket: Ticket, result: WorkflowResult) -> None:
    author = "rules" if result.data.get("runner", "offline") == "offline" else "agent"
    for rel in result.relations:
        try:
            add_relation(
                session,
                _entity(session, ticket, rel.source),
                _entity(session, ticket, rel.target),
                RelationInput(
                    rel.kind,
                    rel.strength,
                    rel.note,
                    rel.document_id,
                    rel.quote,
                    rel.confidence,
                    DataOrigin.AGENT,
                    ticket.id,
                ),
            )
        except GraphError as exc:
            logger.warning("Dropped relation %s: %s", rel.kind, exc)
    for item in result.intel:
        try:
            create_intel(
                session,
                item,
                author=author,
                ticket_id=ticket.id,
            )
        except IntelError as exc:
            logger.warning("Dropped intel item: %s", exc)
