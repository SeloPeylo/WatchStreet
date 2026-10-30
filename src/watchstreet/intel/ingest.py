"""Polling: feeds and search queries -> stored documents -> deterministic triage -> tickets."""

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

from watchstreet.constants import (
    FEED_FAILURE_LIMIT,
    LOW_PRIORITY,
    MAX_DOCS_PER_TRIAGE,
    MAX_OPEN_TICKETS_PER_STOCK,
    RELEVANCE_THRESHOLD,
)
from watchstreet.db import session_scope
from watchstreet.domain import TicketOrigin, WorkflowKey
from watchstreet.intel.connectors import gdelt, usgs
from watchstreet.intel.connectors.rss import parse_feed
from watchstreet.intel.connectors.types import RawItem
from watchstreet.intel.documents import store_document
from watchstreet.intel.fetch import FetchError
from watchstreet.intel.triage import (
    WatchTerm,
    queries_for,
    relevant_stocks,
    score_document,
    watch_terms,
)
from watchstreet.intel.tripwires import commodity_alerts, quake_alerts
from watchstreet.models import Document, Feed, Stock
from watchstreet.services.tickets import count_open, create_ticket
from watchstreet.timeutil import utcnow

if TYPE_CHECKING:
    from watchstreet.container import Container

logger = logging.getLogger(__name__)

DEFAULT_FEEDS: tuple[tuple[str, str, str, str, str], ...] = (
    # name, kind, url, publisher, document kind
    (
        "SEC EDGAR – aktuelle 8-K",
        "rss",
        "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=8-K&count=40&output=atom",
        "SEC EDGAR",
        "filing",
    ),
    (
        "Federal Reserve – Pressemitteilungen",
        "rss",
        "https://www.federalreserve.gov/feeds/press_all.xml",
        "Federal Reserve",
        "gov",
    ),
    ("EZB – Pressemitteilungen", "rss", "https://www.ecb.europa.eu/rss/press.xml", "EZB", "gov"),
    ("EIA – Today in Energy", "rss", "https://www.eia.gov/rss/todayinenergy.xml", "US EIA", "gov"),
    ("USGS – Erdbeben (Tripwire)", "usgs", "", "USGS", "gov"),
)


@dataclass
class IngestReport:
    documents: int = 0
    tickets: int = 0
    alerts: int = 0
    errors: list[str] = field(default_factory=list)


def seed_feeds(session: Session) -> int:
    """Insert the default feeds once (users can edit/disable them afterwards)."""
    if session.scalar(select(Feed.id).limit(1)) is not None:
        return 0
    for name, kind, url, publisher, doc_kind in DEFAULT_FEEDS:
        session.add(Feed(name=name, kind=kind, url=url, publisher=publisher, doc_kind=doc_kind))
    session.flush()
    return len(DEFAULT_FEEDS)


def _store_raw(
    session: Session,
    raw: RawItem,
    kind: str,
    terms: list[WatchTerm],
) -> Document | None:
    doc, created = store_document(
        session,
        url=raw.url,
        text=f"{raw.title}\n{raw.text}".strip(),
        kind=kind,
        publisher=raw.publisher,
        title=raw.title,
        published_at=raw.published_at,
    )
    if not created:
        return None
    scores = score_document(doc, terms)
    doc.relevance = max(scores.values(), default=0.0)
    doc.meta = {"matches": {str(k): round(v, 2) for k, v in scores.items()}}
    return doc


def _ingest_feed(
    container: "Container", session: Session, feed: Feed, terms: list[WatchTerm]
) -> int:
    fetched = container.fetcher.fetch(feed.url)
    items = parse_feed(fetched.text, feed.publisher or feed.name, feed.doc_kind)
    return sum(_store_raw(session, i, feed.doc_kind, terms) is not None for i in items)


def _record_feed_result(feed: Feed, error: str | None) -> None:
    feed.last_fetched_at = utcnow()
    feed.last_error = error or ""
    feed.failures = feed.failures + 1 if error else 0
    if feed.failures >= FEED_FAILURE_LIMIT:
        feed.enabled = False


def create_triage_tickets(session: Session) -> int:
    """One triage ticket per stock that has newly relevant documents."""
    pending = list(session.scalars(select(Document).where(Document.triaged.is_(False))))
    per_stock: dict[int, list[int]] = {}
    for doc in pending:
        scores = {int(k): v for k, v in doc.meta.get("matches", {}).items()}
        for stock_id in relevant_stocks(scores):
            per_stock.setdefault(stock_id, []).append(doc.id)
        doc.triaged = True
    created = 0
    for stock_id, ids in per_stock.items():
        stock = session.get(Stock, stock_id)
        if stock is None or count_open(session, stock_id) >= MAX_OPEN_TICKETS_PER_STOCK:
            continue
        batch = ids[:MAX_DOCS_PER_TRIAGE]
        create_ticket(
            session,
            stock,
            WorkflowKey.INTEL_TRIAGE,
            origin=TicketOrigin.EVENT,
            priority=LOW_PRIORITY,
            params={"document_ids": batch},
            title=f"Nachrichten-Zuschnitt – {stock.symbol} ({len(batch)} Quellen)",
        )
        created += 1
    return created


def run_ingest(container: "Container") -> IngestReport:
    """One polling pass. Individual source failures are recorded, never fatal."""
    report = IngestReport()
    with session_scope(container.session_factory) as session:
        terms = watch_terms(session)
        for feed in session.scalars(select(Feed).where(Feed.enabled.is_(True))):
            try:
                if feed.kind == "rss":
                    report.documents += _ingest_feed(container, session, feed, terms)
                elif feed.kind == "usgs":
                    report.alerts += quake_alerts(session, usgs.recent_quakes(container.fetcher))
                _record_feed_result(feed, None)
            except FetchError as exc:
                report.errors.append(f"{feed.name}: {exc}")
                _record_feed_result(feed, str(exc))
        for stock in session.scalars(select(Stock).where(Stock.holding.has() | Stock.watch.has())):
            for query in queries_for(session, stock):
                try:
                    for raw in gdelt.search(container.fetcher, query):
                        report.documents += _store_raw(session, raw, "news", terms) is not None
                except FetchError as exc:
                    report.errors.append(f"GDELT {query}: {exc}")
                    break
        report.alerts += commodity_alerts(session, container.market)
        session.flush()
        report.tickets = create_triage_tickets(session)
    for message in report.errors:
        logger.warning("Ingest: %s", message)
    return report


__all__ = ["DEFAULT_FEEDS", "RELEVANCE_THRESHOLD", "IngestReport", "run_ingest", "seed_feeds"]
