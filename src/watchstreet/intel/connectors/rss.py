"""RSS 2.0 / Atom parsing (defusedxml: no entity expansion or external fetches)."""

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

from watchstreet.constants import INGEST_MAX_ITEMS
from watchstreet.intel.connectors.types import RawItem

ATOM = "{http://www.w3.org/2005/Atom}"


def _date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        parsed = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _text(node: object, tag: str) -> str:
    found = node.find(tag)  # type: ignore[attr-defined]
    return (found.text or "").strip() if found is not None else ""


def parse_feed(xml: str, publisher: str, kind: str) -> list[RawItem]:
    try:
        root = ElementTree.fromstring(xml)
    except (ElementTree.ParseError, DefusedXmlException):
        return []
    items: list[RawItem] = []
    for node in root.iter("item"):
        link = _text(node, "link")
        if link:
            items.append(
                RawItem(
                    link,
                    _text(node, "title"),
                    _text(node, "description"),
                    _date(_text(node, "pubDate")),
                    publisher,
                    kind,
                ),
            )
    for node in root.iter(f"{ATOM}entry"):
        link_node = node.find(f"{ATOM}link")
        link = (link_node.get("href") or "") if link_node is not None else ""
        if link:
            items.append(
                RawItem(
                    link,
                    _text(node, f"{ATOM}title"),
                    _text(node, f"{ATOM}summary"),
                    _date(_text(node, f"{ATOM}updated")),
                    publisher,
                    kind,
                ),
            )
    return items[:INGEST_MAX_ITEMS]
