"""Monthly gold price (World Bank "Pink Sheet"), read as CSV without a key.

FRED stopped carrying the London gold price in 2022, so the long gold history comes from the
World Bank's monthly averages, as republished in the public-domain data package
``datasets/gold-prices`` (ODC-PDDL-1.0; the World Bank data itself is CC BY 4.0). Rows before
1960 repeat an annual average for every month and are never read: history starts in
``MACRO_HISTORY_START_YEAR``.
"""

import csv
import io
from datetime import date

from watchstreet.intel.connectors.fred import Series
from watchstreet.intel.fetch import Fetcher, FetchError

CSV_URL = "https://raw.githubusercontent.com/datasets/gold-prices/main/data/monthly.csv"
HEADER = ("Date", "Price")
MONTH_TEXT_CHARS = 7  # YYYY-MM

SERIES = Series(
    "GOLDWB",
    "Gold (Weltbank, Monatsmittel)",
    "markets",
    "USD je Unze",
    "monthly",
    "Monatsmittel der Londoner Notierung aus dem Pink Sheet der Weltbank; erscheint Anfang des "
    "Folgemonats",
    money=True,
)


def parse(body: str) -> list[tuple[date, float]]:
    """Rows ``YYYY-MM,price`` as (first day of the month, price). Empty prices are skipped."""
    rows = list(csv.reader(io.StringIO(body)))
    if not rows or tuple(cell.strip() for cell in rows[0]) != HEADER:
        msg = "gold price file has an unexpected header"
        raise FetchError(msg)
    points: list[tuple[date, float]] = []
    for row in rows[1:]:
        if len(row) != len(HEADER) or not row[1].strip():
            continue
        month = row[0].strip()
        try:
            day = date.fromisoformat(f"{month[:MONTH_TEXT_CHARS]}-01")
            points.append((day, float(row[1])))
        except ValueError as exc:
            msg = f"gold price row not readable: {row!r}"
            raise FetchError(msg) from exc
    return points


def observations(fetcher: Fetcher, series: Series, since: date) -> list[tuple[date, float]]:
    """Monthly averages from ``since`` on, in the unit shown (same signature as FRED's)."""
    return [
        (day, value * series.scale)
        for day, value in parse(fetcher.fetch(CSV_URL).text)
        if day >= since
    ]
