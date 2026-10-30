"""Canned responses for every external host, so the full ingest path runs offline.

Used with ``WATCHSTREET_MARKET_PROVIDER=demo`` for development, tests and documentation. All
content is synthetic and labelled as such; nothing here resembles a real filing or article.
"""

from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import httpx

DEMO_IP = "93.184.216.34"
DEMO_NEWS_HOST = "https://news.demo.example"
DEMO_CIKS = {"NEM": 9_000_001, "AAPL": 9_000_002, "XOM": 9_000_003, "NVDA": 9_000_004}
DEMO_NEWS_TOPICS = ("Carlin", "Cadia", "Boddington", "Orica Limited", "Caterpillar Inc.")
DEMO_BANNER = "DEMO DOCUMENT - synthetic text for software testing, not a real filing."
MS_PER_S = 1000

DEMO_10K = f"""{DEMO_BANNER}
Item 1. Business
Demo Gold Corp is a producer of gold with operations in the United States and Australia.
Item 1A. Risk Factors
Our results depend on the market price of gold and on the cost of diesel, explosives and steel.
We rely on a limited number of suppliers, which exposes us to supply interruptions.
Item 2. Properties
Our Carlin operations in Nevada, United States produced 900,000 ounces of gold in 2025 at all-in sustaining costs of $1,500 per ounce, with proven and probable reserves of 12,000,000 ounces.
Our Cadia operations in New South Wales, Australia produced 500,000 ounces of gold in 2025 at all-in sustaining costs of $1,100 per ounce, with proven and probable reserves of 9,000,000 ounces.
Item 7. Management's Discussion
Orica Limited supplies substantially all of the explosives used at our Australian operations.
Caterpillar Inc. supplies the majority of our haul trucks and mining equipment.
We sell our doré to a small group of refiners; Metalor Technologies accounted for approximately 30% of our gold sales in 2025.
"""


def _json(data: object) -> httpx.Response:
    return httpx.Response(200, json=data)


def _rss(items: list[tuple[str, str, str]]) -> httpx.Response:
    body = "".join(
        f"<item><title>{t}</title><link>{u}</link><description>{d}</description>"
        "<pubDate>Thu, 30 Oct 2025 12:00:00 GMT</pubDate></item>"
        for t, u, d in items
    )
    xml = f'<?xml version="1.0"?><rss version="2.0"><channel><title>demo</title>{body}</channel></rss>'
    return httpx.Response(200, text=xml, headers={"content-type": "application/rss+xml"})


class DemoTransport(httpx.BaseTransport):
    """Routes by host/path to deterministic fixtures."""

    def handle_request(self, request: httpx.Request) -> httpx.Response:  # noqa: PLR0911
        url = urlparse(str(request.url))
        host, path = url.hostname or "", url.path
        if host == "api.gdeltproject.org":
            return self._gdelt(parse_qs(url.query).get("query", [""])[0])
        if host == "earthquake.usgs.gov":
            return self._usgs()
        if host == "www.sec.gov" and path.endswith("company_tickers.json"):
            return _json(
                {
                    str(i): {"cik_str": c, "ticker": t, "title": f"Demo {t}"}
                    for i, (t, c) in enumerate(DEMO_CIKS.items())
                }
            )
        if host == "data.sec.gov" and "/submissions/" in path:
            return self._submissions(int(path.rsplit("CIK", 1)[1].split(".")[0]))
        if host == "data.sec.gov" and "/companyfacts/" in path:
            return self._facts()
        if host == "www.sec.gov" and "/Archives/" in path:
            return httpx.Response(
                200,
                text=f"<html><body><pre>{DEMO_10K}</pre></body></html>",
                headers={"content-type": "text/html"},
            )
        if host == "quake.demo.example":
            return httpx.Response(
                200, text="demo quake page", headers={"content-type": "text/plain"}
            )
        return _rss(
            [
                (
                    "Demo: Zentralbank hält Leitzins stabil",
                    f"{DEMO_NEWS_HOST}/macro/rates",
                    "Synthetische Demo-Meldung.",
                ),
                (
                    "Demo: Rohstoffpreise geben nach",
                    f"{DEMO_NEWS_HOST}/commodities/prices",
                    "Synthetische Demo-Meldung.",
                ),
            ]
        )

    @staticmethod
    def _gdelt(query: str) -> httpx.Response:
        term = query.strip('"') or "Markt"
        if term not in DEMO_NEWS_TOPICS:
            return _json({"articles": []})
        seen = datetime(2025, 10, 30, 9, 0, tzinfo=UTC).strftime("%Y%m%dT%H%M%SZ")
        slug = term.lower().replace(" ", "-")
        return _json(
            {
                "articles": [
                    {
                        "url": f"{DEMO_NEWS_HOST}/{slug}/{i}",
                        "title": title.format(term=term),
                        "seendate": seen,
                        "domain": "news.demo.example",
                    }
                    for i, title in enumerate(
                        (
                            "Demo: {term} meldet Streik an wichtigem Standort",
                            "Demo: Analysten diskutieren Kostenentwicklung bei {term}",
                        )
                    )
                ]
            }
        )

    @staticmethod
    def _usgs() -> httpx.Response:
        quake_ms = int((datetime.now(UTC) - timedelta(days=1)).timestamp() * MS_PER_S)

        def feature(eid: str, mag: float, place: str, lon: float, lat: float) -> dict[str, object]:
            return {
                "id": eid,
                "properties": {
                    "mag": mag,
                    "place": place,
                    "time": quake_ms,
                    "url": f"https://quake.demo.example/{eid}",
                },
                "geometry": {"coordinates": [lon, lat, 10.0]},
            }

        return _json(
            {
                "features": [
                    feature("demo-q1", 5.6, "120 km NW of Elko, Nevada (Demo)", -116.9, 41.6),
                    feature("demo-q2", 6.4, "Mid-Pacific Ocean (Demo)", -150.0, 5.0),
                ]
            }
        )

    @staticmethod
    def _submissions(cik: int) -> httpx.Response:
        return _json(
            {
                "filings": {
                    "recent": {
                        "form": ["10-K", "8-K"],
                        "accessionNumber": [f"{cik:010d}-25-000001", f"{cik:010d}-25-000002"],
                        "primaryDocument": ["demo-10k.htm", "demo-8k.htm"],
                        "filingDate": ["2025-02-20", "2025-10-28"],
                        "primaryDocDescription": ["Annual report (demo)", "Current report (demo)"],
                    }
                }
            }
        )

    @staticmethod
    def _facts() -> httpx.Response:
        def unit(val: float, unit_name: str) -> dict[str, object]:
            return {
                "units": {
                    unit_name: [
                        {"end": "2025-06-30", "val": val, "form": "10-Q", "filed": "2025-08-01"}
                    ]
                }
            }

        return _json(
            {
                "facts": {
                    "dei": {"EntityCommonStockSharesOutstanding": unit(55_000_000, "shares")},
                    "us-gaap": {
                        "LongTermDebt": unit(6_500_000_000, "USD"),
                        "CashAndCashEquivalentsAtCarryingValue": unit(500_000_000, "USD"),
                    },
                }
            }
        )


def demo_client() -> httpx.Client:
    return httpx.Client(transport=DemoTransport())


def demo_resolver(_host: str) -> list[str]:
    return [DEMO_IP]
