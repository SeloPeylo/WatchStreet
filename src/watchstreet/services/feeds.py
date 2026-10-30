"""Default intel feeds."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from watchstreet.constants import FEED_DOC_KINDS
from watchstreet.models import Feed

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


def seed_feeds(session: Session) -> int:
    """Insert the default feeds once (users can edit/disable them afterwards)."""
    if session.scalar(select(Feed.id).limit(1)) is not None:
        return 0
    for name, kind, url, publisher, doc_kind in DEFAULT_FEEDS:
        session.add(Feed(name=name, kind=kind, url=url, publisher=publisher, doc_kind=doc_kind))
    session.flush()
    return len(DEFAULT_FEEDS)


class FeedError(ValueError):
    """A feed the user entered is not acceptable."""


def add_feed(
    session: Session, *, name: str, url: str, publisher: str = "", doc_kind: str = ""
) -> Feed:
    """Add a user RSS feed; unknown document kinds fall back to ``news``."""
    if not url.startswith(("http://", "https://")) or not name.strip():
        msg = "Name und http(s)-URL sind nötig"
        raise FeedError(msg)
    name = name.strip()
    feed = Feed(
        name=name,
        kind="rss",
        url=url.strip(),
        publisher=publisher.strip() or name,
        doc_kind=doc_kind if doc_kind in FEED_DOC_KINDS else "news",
    )
    session.add(feed)
    session.flush()
    return feed
