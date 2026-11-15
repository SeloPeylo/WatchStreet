"""Canned responses for every external host, so the full ingest path runs offline.

Used with ``WATCHSTREET_MARKET_PROVIDER=demo`` for development, tests and documentation. All
content is synthetic and labelled as such; nothing here resembles a real filing or article.
"""

import math
from datetime import UTC, date, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import httpx

from watchstreet.intel.connectors.fred import SERIES as FRED_SERIES

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


# Synthetic levels (published unit) and relative swing of the demo macro series.
DEMO_MACRO: dict[str, tuple[float, float]] = {
    "WALCL": (6_800_000.0, 0.04),
    "WTREGEN": (800_000.0, 0.15),
    "RRPONTSYD": (300.0, 0.5),
    "M2SL": (22_000.0, 0.02),
    "DFF": (4.0, 0.2),
    "DGS2": (4.2, 0.15),
    "DGS10": (4.5, 0.1),
    "DFII10": (2.0, 0.2),
    "T10YIE": (2.3, 0.05),
    "VIXCLS": (18.0, 0.3),
    "CPIAUCSL": (320.0, 0.004),
    "DTWEXBGS": (122.0, 0.03),
    "DEXUSEU": (1.1, 0.04),
    "DEXCAUS": (1.38, 0.03),
    "DEXUSAL": (0.66, 0.04),
    "SP500": (6_000.0, 0.1),
    "DCOILWTICO": (75.0, 0.15),
}
DEMO_MACRO_YEARS = 4
DEMO_MACRO_PERIOD = {"daily": 60.0, "weekly": 12.0, "monthly": 3.0}
DEMO_MACRO_DRIFT = {"daily": 0.0004, "weekly": 0.002, "monthly": 0.009}
WEDNESDAY, SATURDAY = 2, 5


class DemoTransport(httpx.BaseTransport):
    """Routes by host/path to deterministic fixtures."""

    def handle_request(self, request: httpx.Request) -> httpx.Response:  # noqa: PLR0911
        url = urlparse(str(request.url))
        host, path = url.hostname or "", url.path
        if host == "api.gdeltproject.org":
            return self._gdelt(parse_qs(url.query).get("query", [""])[0])
        if host == "fred.stlouisfed.org":
            return self._fred(parse_qs(url.query).get("id", [""])[0])
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
    def _fred(series_id: str) -> httpx.Response:
        """Synthetic macro series: a level with a slow wave, in the published unit."""
        level, swing = DEMO_MACRO.get(series_id, (100.0, 0.1))
        frequency = next((s.frequency for s in FRED_SERIES if s.key == series_id), "daily")
        today = datetime.now(UTC).date()
        day = date(today.year - DEMO_MACRO_YEARS, 1, 1)
        rows = ["observation_date," + series_id]
        index = 0
        while day <= today:
            wanted = (
                day.day == 1
                if frequency == "monthly"
                else day.weekday() == WEDNESDAY
                if frequency == "weekly"
                else day.weekday() < SATURDAY
            )
            if wanted:
                index += 1
                wave = (
                    math.sin(index / DEMO_MACRO_PERIOD[frequency])
                    + index * DEMO_MACRO_DRIFT[frequency]
                )
                rows.append(f"{day.isoformat()},{level * (1 + swing * wave):.4f}")
            day += timedelta(days=1)
        return httpx.Response(
            200, text="\n".join(rows), headers={"content-type": "application/csv"}
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
