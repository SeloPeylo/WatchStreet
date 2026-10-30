import json
from datetime import timedelta

from sqlalchemy import select

from watchstreet.agents.base import AgentRequest
from watchstreet.domain import TicketStatus, WorkflowKey
from watchstreet.drafts import FollowUp
from watchstreet.harness.executor import execute_ticket
from watchstreet.harness.scheduler import run_scan, scan_due
from watchstreet.models import Insight, MarketEvent, Score, Stock, Thesis, Ticket
from watchstreet.services import portfolio, tickets
from watchstreet.services.followups import apply_followups
from watchstreet.timeutil import utcnow
from watchstreet.worker import drain_queue, tick


def add_holding(container, symbol="AAPL", intent=""):
    with container.session_factory() as s:
        portfolio.add_holding(
            s,
            container.market,
            portfolio.NewHolding(symbol, 10, 100.0, intent=intent),
        )
        s.commit()


def test_holding_intake_creates_assessment_that_stores_knowledge(container):
    add_holding(container, intent="langfristig halten")
    assert drain_queue(container) >= 1
    with container.session_factory() as s:
        first = s.scalars(select(Ticket).order_by(Ticket.id)).first()
        assert first.workflow == WorkflowKey.INITIAL_HOLDING
        assert first.status == TicketStatus.DONE and first.runner == "offline"
        stock = s.scalar(select(Stock))
        goal = [i for i in stock.insights if i.category == "goal"]
        assert goal and goal[-1].text == "langfristig halten"
        assert {sc.scheme for sc in stock.scores} == {"valuation_tech_v1", "technical_v1"}
        assert stock.theses and stock.theses[0].ticket_id == first.id
        follow = s.scalars(select(Ticket).where(Ticket.parent_id == first.id)).all()
        assert [t.workflow for t in follow] == [WorkflowKey.TOPIC_ANALYSIS]
        assert all(t.status == TicketStatus.DONE for t in s.scalars(select(Ticket)))


def test_watch_intake_runs_initial_watch(container):
    with container.session_factory() as s:
        portfolio.add_watch(s, container.market, "msft", "Cloud")
        s.commit()
    drain_queue(container)
    with container.session_factory() as s:
        ticket = s.scalars(select(Ticket).order_by(Ticket.id)).first()
        assert ticket.workflow == WorkflowKey.INITIAL_WATCH
        assert "Kaufprüfung" in ticket.summary


def test_followup_guardrails(container):
    add_holding(container)
    drain_queue(container)
    with container.session_factory() as s:
        parent = s.scalars(
            select(Ticket).where(Ticket.workflow == "topic_analysis").order_by(Ticket.id.desc()),
        ).first()  # depth 1
        assert parent.depth == 1
        decisions = apply_followups(
            s,
            parent,
            [
                FollowUp("nope"),
                FollowUp("topic_analysis", ""),
                FollowUp("topic_analysis", "Wettbewerb"),
                FollowUp("topic_analysis", "wettbewerb"),
                FollowUp("valuation_score"),
            ],
        )
        reasons = [d.reason for d in decisions]
        assert reasons[:2] == ["unknown workflow", "topic required"]
        assert decisions[2].accepted and reasons[3] == "duplicate"
        deep = s.get(Ticket, decisions[2].ticket_id)
        assert deep.depth == 2
        blocked = apply_followups(s, deep, [FollowUp("valuation_score")])
        assert blocked[0].reason == "max follow-up depth reached"


def test_backlog_limit(container, monkeypatch):
    add_holding(container)
    drain_queue(container)
    monkeypatch.setattr("watchstreet.services.followups.MAX_OPEN_TICKETS_PER_STOCK", 0)
    with container.session_factory() as s:
        parent = s.scalars(select(Ticket).order_by(Ticket.id)).first()
        decision = apply_followups(s, parent, [FollowUp("valuation_score")])[0]
        assert decision.reason == "stock backlog full"


def test_failed_ticket_is_recorded_and_retryable(container):
    class Broken:
        name = "broken"

        def complete(self, request: AgentRequest) -> str:
            return "not json"

    container.runner = Broken()
    add_holding(container)
    drain_queue(container)
    with container.session_factory() as s:
        ticket = s.scalars(select(Ticket)).first()
        assert ticket.status == TicketStatus.FAILED
        assert "AgentError" in ticket.error and ticket.runner == "broken"
        assert s.scalars(select(Insight)).first() is None
        tickets.retry(s, ticket)
        s.commit()
        assert ticket.status == TicketStatus.QUEUED and ticket.error == ""


def test_claim_cancel_and_requeue_stuck(container):
    add_holding(container)
    with container.session_factory() as s:
        t = tickets.claim_next(s)
        assert t.status == TicketStatus.RUNNING
        assert tickets.claim_next(s) is None
        t.started_at = utcnow() - timedelta(hours=2)
        s.commit()
        assert tickets.requeue_stuck(s) == 1
        s.commit()
        assert s.get(Ticket, t.id).status == TicketStatus.QUEUED
        tickets.cancel(s, t)
        assert t.status == TicketStatus.CANCELLED
        tickets.retry(s, t)
        assert t.status == TicketStatus.QUEUED


def test_priority_order(container):
    add_holding(container, "AAA")
    with container.session_factory() as s:
        stock = s.scalar(select(Stock))
        low = tickets.create_ticket(s, stock, "valuation_score", priority=1)
        s.commit()
        first = tickets.claim_next(s)
        assert first.id != low.id


def test_scan_creates_event_review_once_and_refresh_tickets(container):
    add_holding(container)
    drain_queue(container)
    assert scan_due(container)
    created = run_scan(container)
    assert created >= 2  # event review + at least one refresh
    with container.session_factory() as s:
        events = s.scalars(select(MarketEvent)).all()
        assert events and all(e.reviewed and e.ticket_id for e in events)
        review = s.scalars(select(Ticket).where(Ticket.workflow == "event_review")).one()
        assert review.params["event_ids"]
    assert not scan_due(container)
    drain_queue(container)
    assert run_scan(container) == 0  # nothing new, refreshes still recent
    with container.session_factory() as s:
        assert s.scalars(select(Score)).all()
        assert s.scalars(select(Thesis)).all()


def test_tick_forces_scan_and_user_topic_ticket(container):
    add_holding(container)
    assert tick(container, force_scan=True) >= 1
    with container.session_factory() as s:
        stock = s.scalar(select(Stock))
        t = tickets.create_ticket(s, stock, "topic_analysis", topic="Burggraben")
        s.commit()
        tid = t.id
    assert execute_ticket(container, tid) == TicketStatus.DONE
    with container.session_factory() as s:
        done = s.get(Ticket, tid)
        assert "Burggraben" in done.summary
        assert json.dumps(done.result)
