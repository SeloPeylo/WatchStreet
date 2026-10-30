"""Transaction ownership, worker races and query counts (no N+1)."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import event, select
from sqlalchemy.engine import Engine

from watchstreet.domain import TicketStatus
from watchstreet.models import Entity, Stock, Ticket
from watchstreet.services import entities, portfolio, tickets
from watchstreet.services.entities import RelationInput

SYMBOLS = ("AAA", "BBB", "CCC", "DDD")


def _add_holdings(container, symbols) -> None:
    with container.session_factory() as s:
        for symbol in symbols:
            portfolio.add_holding(s, container.market, portfolio.NewHolding(symbol, 10, 100.0))
        s.commit()


@contextmanager
def _count_selects(engine: Engine) -> Iterator[list[str]]:
    seen: list[str] = []

    def record(_conn, _cursor, statement, *_args) -> None:
        if statement.lstrip().upper().startswith("SELECT"):
            seen.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        yield seen
    finally:
        event.remove(engine, "before_cursor_execute", record)


def test_claim_next_leaves_the_commit_to_the_caller(container):
    _add_holdings(container, SYMBOLS[:1])
    with container.session_factory() as claimer:
        claimed = tickets.claim_next(claimer)
        assert claimed is not None
        with container.session_factory() as observer:
            # not committed yet: other workers still see the ticket as queued
            statuses = {t.status for t in observer.scalars(select(Ticket))}
            assert statuses == {TicketStatus.QUEUED}
        claimer.commit()
        with container.session_factory() as observer:
            assert observer.get(Ticket, claimed.id).status == TicketStatus.RUNNING


def test_claim_next_moves_on_when_another_worker_wins_the_candidate(container):
    _add_holdings(container, SYMBOLS[:2])
    stolen: list[int] = []

    def steal_first_candidate(_conn, _cursor, statement, parameters, *_args) -> None:
        # Another worker commits the same candidate between our SELECT and our UPDATE.
        if statement.lstrip().upper().startswith("UPDATE TICKETS") and not stolen:
            stolen.append(1)
            with container.session_factory() as rival:
                first = rival.scalars(
                    select(Ticket).order_by(Ticket.priority.desc(), Ticket.id).limit(1)
                ).one()
                first.status = TicketStatus.RUNNING
                stolen.append(first.id)
                rival.commit()

    event.listen(container.engine, "before_cursor_execute", steal_first_candidate)
    try:
        with container.session_factory() as worker:
            claimed = tickets.claim_next(worker)
            worker.commit()
    finally:
        event.remove(container.engine, "before_cursor_execute", steal_first_candidate)
    assert claimed is not None
    assert claimed.id != stolen[1]
    assert claimed.status == TicketStatus.RUNNING


def test_holding_rows_use_a_constant_number_of_selects(container):
    _add_holdings(container, SYMBOLS[:1])
    with container.session_factory() as s, _count_selects(container.engine) as one:
        portfolio.holding_rows(s, container.market)
    _add_holdings(container, SYMBOLS[1:])
    with container.session_factory() as s, _count_selects(container.engine) as many:
        rows = portfolio.holding_rows(s, container.market)
    assert len(rows) == len(SYMBOLS)
    assert len(many) == len(one)


def test_holding_rows_can_be_limited_to_one_stock(container):
    _add_holdings(container, SYMBOLS[:2])
    with container.session_factory() as s:
        stock = s.scalars(select(Stock).where(Stock.symbol == SYMBOLS[1])).one()
        rows = portfolio.holding_rows(s, container.market, stock.id)
        assert [r.holding.stock.symbol for r in rows] == [SYMBOLS[1]]


def test_country_exposure_uses_a_constant_number_of_selects(container):
    _add_holdings(container, SYMBOLS)
    with container.session_factory() as s:
        values = {}
        for stock in s.scalars(select(Stock)):
            company = entities.get_or_create_entity(
                s, stock.symbol, "company", stock_id=stock.id, country="Canada"
            )
            mine = entities.get_or_create_entity(
                s, f"{stock.symbol} mine", "mine", stock_id=stock.id, country="Peru"
            )
            entities.add_relation(s, company, mine, RelationInput("owns", 1.0, origin="user"))
            values[stock.id] = 100.0
        s.commit()
        assert s.scalars(select(Entity)).all()
        small = dict(list(values.items())[:1])
        with _count_selects(container.engine) as few:
            entities.country_exposure(s, small)
        with _count_selects(container.engine) as many:
            result = entities.country_exposure(s, values)
    assert len(many) == len(few)
    assert result["Peru"].share == 1.0 or abs(result["Peru"].share - 1.0) < 1e-9
