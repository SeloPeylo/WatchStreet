"""Canned responses for every external host, so the full ingest path runs offline.

Used with ``WATCHSTREET_MARKET_PROVIDER=demo`` for development, tests and documentation. The
text fixtures are synthetic and labelled as such. The FRED macro series and the World Bank
monthly gold price are a real snapshot of the published history, bundled in ``data/`` (refresh:
``scripts/snapshot_macro_history.py``).
"""

import functools
import gzip
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx

from watchstreet.constants import MACRO_HISTORY_FILE
from watchstreet.intel.connectors import gold_monthly

MACRO_HISTORY = Path(__file__).resolve().parents[1] / "data" / MACRO_HISTORY_FILE

DEMO_IP = "93.184.216.34"
DEMO_CIKS = {"NEM": 9_000_001, "AAPL": 9_000_002, "XOM": 9_000_003, "NVDA": 9_000_004}
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


@functools.lru_cache(maxsize=1)
def macro_history() -> dict[str, tuple[tuple[str, str], ...]]:
    """Bundled FRED rows per series as ``(day, value)`` text, in the published unit."""
    text = gzip.decompress(MACRO_HISTORY.read_bytes()).decode("utf-8")
    rows: dict[str, list[tuple[str, str]]] = {}
    for line in text.splitlines()[1:]:
        series_id, day, value = line.split(",")
        rows.setdefault(series_id, []).append((day, value))
    return {series_id: tuple(points) for series_id, points in rows.items()}


class DemoTransport(httpx.BaseTransport):
    """Routes by host/path to deterministic fixtures."""

    def handle_request(self, request: httpx.Request) -> httpx.Response:  # noqa: PLR0911
        url = urlparse(str(request.url))
        host, path = url.hostname or "", url.path
        if host == "fred.stlouisfed.org":
            query = parse_qs(url.query)
            return self._fred(query.get("id", [""])[0], query.get("cosd", [""])[0])
        if str(request.url) == gold_monthly.CSV_URL:
            return self._gold()
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
        return httpx.Response(
            404, text="demo: unknown host", headers={"content-type": "text/plain"}
        )

    @staticmethod
    def _fred(series_id: str, since: str) -> httpx.Response:
        """The bundled FRED series from ``since`` (ISO date, ``cosd``) on, as FRED's CSV."""
        rows = macro_history().get(series_id)
        if rows is None:
            return httpx.Response(
                404, text="demo: unknown series", headers={"content-type": "text/plain"}
            )
        lines = [f"observation_date,{series_id}"]
        lines += [f"{day},{value}" for day, value in rows if day >= since]
        return httpx.Response(
            200, text="\n".join(lines), headers={"content-type": "application/csv"}
        )

    @staticmethod
    def _gold() -> httpx.Response:
        """The bundled monthly gold prices, as the public data package publishes them."""
        rows = macro_history().get(gold_monthly.SERIES.key, ())
        lines = [",".join(gold_monthly.HEADER)]
        lines += [f"{day[: gold_monthly.MONTH_TEXT_CHARS]},{value}" for day, value in rows]
        return httpx.Response(200, text="\n".join(lines), headers={"content-type": "text/plain"})

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
