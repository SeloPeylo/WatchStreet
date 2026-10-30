"""Rules that used to live in the web layer and are now plain services."""

from datetime import timedelta

import pytest
from sqlalchemy import select

from watchstreet.constants import HEARTBEAT_STALE_AFTER, SCORE_HISTORY_POINTS
from watchstreet.drafts import IntelDraft
from watchstreet.models import Document, Feed, Score, Stock
from watchstreet.services import entities, feeds, graph, intel, portfolio
from watchstreet.services.entities import RelationInput
from watchstreet.services.scores import latest_per_scheme
from watchstreet.services.status import system_status, worker_alive
from watchstreet.timeutil import utcnow


def test_worker_alive_rule():
    now = utcnow()
    assert not worker_alive(None, now)
    assert worker_alive(now - HEARTBEAT_STALE_AFTER / 2, now)
    assert not worker_alive(now - HEARTBEAT_STALE_AFTER - timedelta(seconds=1), now)


def test_system_status_reports_names_and_interval(session):
    status = system_status(session, market="demo", runner="offline", scan_interval_min=15)
    assert status["market"] == "demo" and status["runner"] == "offline"
    assert status["scan_interval"] == 15 and status["worker_alive"] is False


def test_latest_per_scheme_bounds_history(session, container):
    stock = portfolio.get_or_create_stock(session, container.market, "AAA")
    for i in range(SCORE_HISTORY_POINTS + 5):
        session.add(Score(stock_id=stock.id, scheme="s1", value=float(i), label="x"))
    session.add(Score(stock_id=stock.id, scheme="s2", value=1.0, label="y"))
    session.flush()
    session.refresh(stock)
    by_scheme = {row["latest"].scheme: row for row in latest_per_scheme(stock)}
    assert set(by_scheme) == {"s1", "s2"}
    assert len(by_scheme["s1"]["history"]) == SCORE_HISTORY_POINTS
    assert by_scheme["s1"]["latest"].value == SCORE_HISTORY_POINTS + 4.0
    assert by_scheme["s1"]["history"][-1] == SCORE_HISTORY_POINTS + 4.0


def test_add_feed_validates_and_defaults(session):
    with pytest.raises(feeds.FeedError):
        feeds.add_feed(session, name="x", url="ftp://nope")
    with pytest.raises(feeds.FeedError):
        feeds.add_feed(session, name="  ", url="https://example.org/rss")
    feed = feeds.add_feed(session, name=" Test ", url="https://example.org/rss ", doc_kind="weird")
    assert (feed.name, feed.url, feed.publisher, feed.doc_kind) == (
        "Test",
        "https://example.org/rss",
        "Test",
        "news",
    )
    gov = feeds.add_feed(session, name="G", url="https://g.example/rss", doc_kind="gov")
    assert gov.doc_kind == "gov" and session.scalar(select(Feed).where(Feed.id == gov.id))


def test_list_items_filters_and_primary_only(session, container):
    stock = portfolio.get_or_create_stock(session, container.market, "AAA")
    primary = Document(
        url="https://sec.example/1", kind="filing", title="f", text="t", content_hash="1"
    )
    secondary = Document(
        url="https://news.example/1", kind="news", title="n", text="t", content_hash="2"
    )
    session.add_all([primary, secondary])
    session.flush()
    for key, doc, category in (("a", primary, "company"), ("b", secondary, "macro")):
        intel.create_intel(
            session,
            IntelDraft(
                headline=key,
                document_id=doc.id,
                category=category,
                severity=4 if key == "a" else 1,
                impacts=((stock.id, "bearish", ""),) if key == "a" else (),
                dedupe_key=key,
            ),
            author="test",
        )
    assert {i.headline for i in intel.list_items(session)} == {"a", "b"}
    assert [i.headline for i in intel.list_items(session, category="macro")] == ["b"]
    assert [i.headline for i in intel.list_items(session, min_severity=3)] == ["a"]
    assert [i.headline for i in intel.list_items(session, stock_id=stock.id)] == ["a"]
    assert [i.headline for i in intel.list_items(session, primary_only=True)] == ["a"]
    assert {i.headline for i in intel.list_items(session, category="unknown")} == {"a", "b"}


def test_relations_for_document_resolves_names(session, container):
    stock = portfolio.get_or_create_stock(session, container.market, "AAA")
    doc = Document(
        url="https://sec.example/2", kind="filing", title="f", text="t", content_hash="3"
    )
    session.add(doc)
    session.flush()
    company = entities.get_or_create_entity(session, "Acme", "company", stock_id=stock.id)
    supplier = entities.get_or_create_entity(session, "Supplier", "supplier")
    relation = entities.add_relation(
        session, supplier, company, RelationInput("supplies", 0.1, origin="user")
    )
    relation.document_id = doc.id
    session.flush()
    rows = graph.relations_for_document(session, doc.id)
    assert [(r["source"], r["target"]) for r in rows] == [("Supplier", "Acme")]
    assert graph.relations_for_document(session, doc.id + 99) == []
    assert isinstance(session.scalars(select(Stock)).first(), Stock)
