"""Macro series from FRED (Federal Reserve Bank of St. Louis), read as CSV without a key.

``SERIES`` is the declarative table of everything the macro view tracks. ``scale`` converts the
published unit to the unit shown, so that sums across series never mix millions with billions.
"""

import csv
import io
from dataclasses import dataclass
from datetime import date

from watchstreet.intel.fetch import Fetcher, FetchError

CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
MISSING = "."
PER_THOUSAND = 0.001


@dataclass(frozen=True)
class Series:
    key: str  # FRED series id
    label: str
    group: str
    unit: str
    frequency: str  # daily | weekly | monthly
    note: str  # what the reader must know about lag and meaning
    scale: float = 1.0
    money: bool = False  # a price in US dollars: can be shown in gold or inflation-adjusted


SERIES: tuple[Series, ...] = (
    Series(
        "WALCL",
        "Bilanzsumme der Fed",
        "liquidity",
        "Mrd. USD",
        "weekly",
        "Mittwochswert, donnerstags veröffentlicht",
        PER_THOUSAND,
    ),
    Series(
        "WTREGEN",
        "Konto des US-Finanzministeriums bei der Fed (TGA)",
        "liquidity",
        "Mrd. USD",
        "weekly",
        "Mittwochswert, donnerstags veröffentlicht",
        PER_THOUSAND,
    ),
    Series(
        "RRPONTSYD",
        "Reverse Repo (Übernacht-Fazilität der Fed)",
        "liquidity",
        "Mrd. USD",
        "daily",
        "Tageswert, am selben Tag veröffentlicht",
    ),
    Series(
        "M2SL",
        "Geldmenge M2 (USA)",
        "liquidity",
        "Mrd. USD",
        "monthly",
        "Monatswert, rund vier Wochen verzögert, wird revidiert",
    ),
    Series(
        "DFF", "Leitzins (Fed Funds, effektiv)", "rates", "%", "daily", "ein Geschäftstag Verzug"
    ),
    Series("DGS2", "US-Staatsanleihe 2 Jahre", "rates", "%", "daily", "ein Geschäftstag Verzug"),
    Series("DGS10", "US-Staatsanleihe 10 Jahre", "rates", "%", "daily", "ein Geschäftstag Verzug"),
    Series(
        "DFII10",
        "Realzins 10 Jahre (inflationsgeschützte Anleihe)",
        "rates",
        "%",
        "daily",
        "marktbasiert, ein Geschäftstag Verzug",
    ),
    Series(
        "T10YIE",
        "Inflationserwartung 10 Jahre (Breakeven)",
        "rates",
        "%",
        "daily",
        "enthält Liquiditätsprämien, keine reine Erwartung",
    ),
    Series(
        "VIXCLS",
        "VIX (erwartete Schwankung S&P 500)",
        "risk",
        "Punkte",
        "daily",
        "Schlusswert, ein Geschäftstag Verzug",
    ),
    Series(
        "CPIAUCSL",
        "Verbraucherpreise USA (CPI, Index)",
        "inflation",
        "Index 1982-84=100",
        "monthly",
        "Monatswert, rund sechs Wochen nach Monatsbeginn veröffentlicht, saisonbereinigt",
    ),
    Series(
        "DTWEXBGS",
        "Dollar-Index breit (handelsgewichtet)",
        "dollar",
        "Index 2006=100",
        "daily",
        "handelsgewichtet, nicht der DXY; etwa eine Woche Verzug",
    ),
    Series(
        "DEXUSEU", "US-Dollar je Euro", "dollar", "USD je EUR", "daily", "etwa eine Woche Verzug"
    ),
    Series(
        "DEXCAUS",
        "Kanadische Dollar je US-Dollar",
        "dollar",
        "CAD je USD",
        "daily",
        "etwa eine Woche Verzug",
    ),
    Series(
        "DEXUSAL",
        "US-Dollar je Australischem Dollar",
        "dollar",
        "USD je AUD",
        "daily",
        "etwa eine Woche Verzug",
    ),
    Series(
        "SP500",
        "S&P 500",
        "markets",
        "Punkte (USD)",
        "daily",
        "Schlusswert; FRED führt nur die letzten zehn Jahre",
        money=True,
    ),
    Series(
        "DCOILWTICO",
        "Rohöl WTI",
        "markets",
        "USD je Barrel",
        "daily",
        "Spotpreis, einige Tage Verzug",
        money=True,
    ),
)
BY_KEY = {s.key: s for s in SERIES}


def parse(body: str) -> list[tuple[date, float]]:
    """Read FRED's two-column CSV. Days without a value (".") are skipped, never filled."""
    rows = list(csv.reader(io.StringIO(body)))
    if not rows or len(rows[0]) != 2 or "date" not in rows[0][0].lower():  # noqa: PLR2004
        msg = "FRED returned an unexpected answer"
        raise FetchError(msg)
    points: list[tuple[date, float]] = []
    for row in rows[1:]:
        if len(row) != 2 or row[1].strip() in ("", MISSING):  # noqa: PLR2004
            continue
        try:
            points.append((date.fromisoformat(row[0].strip()), float(row[1])))
        except ValueError as exc:
            msg = f"FRED row not readable: {row!r}"
            raise FetchError(msg) from exc
    return points


def observations(fetcher: Fetcher, series: Series, since: date) -> list[tuple[date, float]]:
    """Observations from ``since`` on, already converted to the unit shown."""
    url = f"{CSV_URL}?id={series.key}&cosd={since.isoformat()}"
    return [(day, value * series.scale) for day, value in parse(fetcher.fetch(url).text)]
