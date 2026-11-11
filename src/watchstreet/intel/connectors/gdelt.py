"""GDELT DOC 2.0 search (free, no key): global news by query."""

import json
from datetime import UTC, datetime
from urllib.parse import urlencode

from watchstreet.constants import INGEST_MAX_ITEMS
from watchstreet.intel.connectors.types import RawItem
from watchstreet.intel.fetch import Fetcher, FetchError

DOC_API = "https://api.gdeltproject.org/api/v2/doc/doc"
SEEN_FORMAT = "%Y%m%dT%H%M%SZ"


def search(fetcher: Fetcher, query: str) -> list[RawItem]:
    params = urlencode(
        {
            "query": query,
            "mode": "ArtList",
            "format": "json",
            "sort": "datedesc",
            "maxrecords": INGEST_MAX_ITEMS,
        },
    )
    fetched = fetcher.fetch(f"{DOC_API}?{params}")
    try:
        articles = json.loads(fetched.text).get("articles", [])
    except json.JSONDecodeError as exc:
        msg = "GDELT returned invalid JSON"
        raise FetchError(msg) from exc
    items: list[RawItem] = []
    for article in articles:
        try:
            seen = datetime.strptime(article.get("seendate", ""), SEEN_FORMAT).replace(tzinfo=UTC)
        except ValueError:
            seen = None
        if article.get("url") and article.get("title"):
            items.append(
                RawItem(
                    article["url"], article["title"], "", seen, article.get("domain", ""), "news"
                ),
            )
    return items
