"""The macro layer: stored series, derived measures and prices in other denominators."""

import logging
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from sqlalchemy import insert, select, update
from sqlalchemy.orm import Session

from watchstreet.analysis import macro as rules
from watchstreet.analysis.macro import Points
from watchstreet.commodities import COMMODITIES
from watchstreet.constants import (
    MACRO_CHANGE_DAYS,
    MACRO_HISTORY_START_YEAR,
    MACRO_REVISION_DAYS,
    MACRO_SPARK_POINTS,
    MACRO_SYNC_KEY,
)
from watchstreet.intel.connectors import fred, gold_monthly
from watchstreet.intel.fetch import Fetcher, FetchError
from watchstreet.models import MacroPoint, PricePoint
from watchstreet.services.state import touch, updated_at

logger = logging.getLogger(__name__)
GROUPS: tuple[tuple[str, str], ...] = (
    ("liquidity", "Liquidität"),
    ("rates", "Zinsen"),
    ("inflation", "Inflation"),
    ("dollar", "Dollar und Währungen"),
    ("risk", "Risiko"),
    ("housing", "Bau und Wohnen (Holznachfrage)"),
    ("markets", "Märkte und Rohstoffe"),
    ("ratios", "Verhältnisse"),
)
DENOMINATORS = {"usd": "US-Dollar (nominal)", "gold": "Gold (Unzen)", "real": "inflationsbereinigt"}
SAME_DAY = "nur an Tagen gebildet, an denen beide Reihen einen eigenen Wert haben"
Reader = Callable[[Fetcher, fred.Series, date], list[tuple[date, float]]]
# every stored external series with the connector that reads it
SOURCES: tuple[tuple[fred.Series, Reader], ...] = (
    *((series, fred.observations) for series in fred.SERIES),
    (gold_monthly.SERIES, gold_monthly.observations),
)


@dataclass(frozen=True)
class Item:
    """One thing the macro view can chart: a stored series, a price or a derived measure."""

    key: str
    label: str
    group: str
    unit: str
    frequency: str
    note: str
    money: bool = False
    formula: str = ""
    inputs: tuple[str, ...] = ()
    op: str = ""


def _ratio(key: str, label: str, top: str, bottom: str, unit: str) -> Item:
    return Item(
        key,
        label,
        "ratios",
        unit,
        "wie die gröbere Reihe",
        SAME_DAY,
        formula=f"{top} ÷ {bottom}",
        inputs=(top, bottom),
        op="ratio",
    )


DERIVED: tuple[Item, ...] = (
    Item(
        "NETLIQ",
        "Nettoliquidität (Näherung)",
        "liquidity",
        "Mrd. USD",
        "weekly",
        "wöchentlich an Bilanzstichtagen der Fed, bis acht Tage alt; eine verbreitete Näherung, "
        "keine amtliche Grösse",
        formula="Bilanzsumme der Fed − Konto des Finanzministeriums − Reverse Repo",
        inputs=("WALCL", "WTREGEN", "RRPONTSYD"),
        op="netliq",
    ),
    Item(
        "CURVE",
        "Zinskurve 10 Jahre − 2 Jahre",
        "rates",
        "Prozentpunkte",
        "daily",
        SAME_DAY,
        formula="DGS10 − DGS2",
        inputs=("DGS10", "DGS2"),
        op="diff",
    ),
    Item(
        "CPIYOY",
        "Inflation USA (CPI, Jahresrate)",
        "inflation",
        "% gegen Vorjahresmonat",
        "monthly",
        "Jahresrate aus dem saisonbereinigten Index; rund sechs Wochen verzögert",
        formula="CPI ÷ CPI zwölf Monate zuvor − 1",
        inputs=("CPIAUCSL",),
        op="yoy",
    ),
    Item(
        "M2YOY",
        "Geldmenge M2 (Jahresrate)",
        "liquidity",
        "% gegen Vorjahresmonat",
        "monthly",
        "rund vier Wochen verzögert, wird revidiert",
        formula="M2 ÷ M2 zwölf Monate zuvor − 1",
        inputs=("M2SL",),
        op="yoy",
    ),
    _ratio("GOLD_SILVER", "Gold ÷ Silber", "gold", "silver", "Unzen Silber je Unze Gold"),
    _ratio("COPPER_GOLD", "Kupfer ÷ Gold", "copper", "gold", "Unzen Gold je Pfund Kupfer"),
    _ratio("URANIUM_GOLD", "Uran ÷ Gold", "uranium", "gold", "Unzen Gold je Pfund Uran"),
    _ratio("SP500_GOLD", "S&P 500 ÷ Gold", "SP500", "gold", "Unzen Gold je Indexpunkt"),
    _ratio("OIL_GOLD", "Rohöl ÷ Gold", "DCOILWTICO", "gold", "Unzen Gold je Barrel"),
    _ratio("LUMBER_GOLD", "Holz ÷ Gold", "lumber", "gold", "Unzen Gold je 1.000 Board Feet"),
)


def _items() -> dict[str, Item]:
    items = {
        s.key: Item(s.key, s.label, s.group, s.unit, s.frequency, s.note, s.money)
        for s, _ in SOURCES
    }
    for c in COMMODITIES:
        note = "Wochenschlusskurs des Terminkontrakts"
        items[c.key] = Item(c.key, c.label, "markets", c.price_unit, "weekly", note, money=True)
    items.update({d.key: d for d in DERIVED})
    return items


ITEMS = _items()


class Store:
    """All stored observations, read once per request."""

    def __init__(self, session: Session) -> None:
        self._raw: dict[str, Points] = defaultdict(list)
        for series, day, value in session.execute(
            select(MacroPoint.series, MacroPoint.day, MacroPoint.value).order_by(MacroPoint.day)
        ):
            self._raw[series].append((day, value))
        for commodity, day, close in session.execute(
            select(PricePoint.commodity, PricePoint.day, PricePoint.close).order_by(PricePoint.day)
        ):
            self._raw[commodity].append((day, close))

    def points(self, key: str) -> Points:
        item = ITEMS[key]
        if not item.inputs:
            return self._raw.get(key, [])
        parts = [self.points(name) for name in item.inputs]
        if item.op == "netliq":
            return rules.net_liquidity(*parts)
        if item.op == "yoy":
            return rules.year_over_year(parts[0])
        return rules.combine(parts[0], parts[1], item.op)


def sync(session: Session, fetcher: Fetcher) -> dict[str, Any]:
    """Fetch every series; recent observations are overwritten because they get revised."""
    added = updated = 0
    failed: list[str] = []
    start = date(MACRO_HISTORY_START_YEAR, 1, 1)
    for series, read in SOURCES:
        rows = session.execute(
            select(MacroPoint.day, MacroPoint.value).where(MacroPoint.series == series.key)
        )
        known: dict[date, float] = {row[0]: row[1] for row in rows}
        since = max(known) - timedelta(days=MACRO_REVISION_DAYS) if known else start
        try:
            fresh = read(fetcher, series, max(since, start))
        except FetchError as exc:
            logger.warning("Macro series %s unavailable: %s", series.key, exc)
            failed.append(series.key)
            continue
        new = [
            {"series": series.key, "day": day, "value": value}
            for day, value in fresh
            if day not in known
        ]
        if new:
            session.execute(insert(MacroPoint), new)
        for day, value in fresh:
            if day in known and known[day] != value:
                session.execute(
                    update(MacroPoint)
                    .where(MacroPoint.series == series.key, MacroPoint.day == day)
                    .values(value=value)
                )
                updated += 1
        added += len(new)
    touch(session, MACRO_SYNC_KEY)
    session.flush()
    return {"added": added, "updated": updated, "failed": failed}


def _summary(item: Item, points: Points) -> dict[str, Any]:
    last = points[-1] if points else None
    before = rules.value_on(points, last[0] - timedelta(days=MACRO_CHANGE_DAYS)) if last else None
    step = max(len(points) // MACRO_SPARK_POINTS, 1)
    recent = [p for p in points if last and p[0] >= last[0] - timedelta(days=2 * MACRO_CHANGE_DAYS)]
    return {
        "key": item.key,
        "label": item.label,
        "unit": item.unit,
        "frequency": item.frequency,
        "note": item.note,
        "formula": item.formula,
        "money": item.money,
        "value": last[1] if last else None,
        "day": last[0].isoformat() if last else None,
        "year_ago": before[1] if before else None,
        "spark": [v for _, v in recent[:: max(len(recent) // MACRO_SPARK_POINTS, 1)]]
        if step
        else [],
    }


def overview(session: Session) -> dict[str, Any]:
    store = Store(session)
    synced = updated_at(session, MACRO_SYNC_KEY)
    groups = [
        {
            "key": key,
            "label": label,
            "items": [_summary(i, store.points(i.key)) for i in ITEMS.values() if i.group == key],
        }
        for key, label in GROUPS
    ]
    return {
        "synced_at": synced.isoformat() if synced else None,
        "groups": groups,
        "denominators": DENOMINATORS,
    }


def chart(session: Session, key: str, denominator: str = "usd") -> dict[str, Any]:
    """One series, optionally in gold or in money of the last published CPI month."""
    item = ITEMS[key]
    store = Store(session)
    nominal = store.points(key)
    points, unit, rule = nominal, item.unit, ""
    if denominator != "usd" and not item.money:
        denominator = "usd"
    if denominator == "gold":
        points = rules.combine(nominal, store.points("gold"), "ratio")
        unit, rule = (
            "Unzen Gold",
            f"{item.label} ÷ Goldpreis; {SAME_DAY}. Keine Kaufkraftbereinigung.",
        )
    elif denominator == "real":
        points, base = rules.deflate(nominal, store.points("CPIAUCSL"))
        unit = f"{item.unit}, in Kaufkraft von {base:%m/%Y}" if base else item.unit
        rule = (
            "Monatsmittel ÷ Verbraucherpreisindex des Monats; endet mit dem letzten "
            "veröffentlichten CPI-Monat, spätere Kurse werden nicht geschätzt."
        )
    return {
        "key": key,
        "label": item.label,
        "unit": unit,
        "note": item.note,
        "formula": item.formula,
        "rule": rule,
        "money": item.money,
        "denominator": denominator,
        "points": [{"day": d.isoformat(), "value": v} for d, v in points],
        "split": _split(nominal, store.points("gold")) if item.money and key != "gold" else [],
    }


def _split(asset: Points, gold: Points) -> list[dict[str, Any]]:
    """Dollar change split into "in gold" and "gold itself", over one and five years."""
    shared = rules.combine(asset, gold, "ratio")
    if not shared:
        return []
    end = shared[-1][0]
    out = []
    for years in (1, 5):
        start = end - timedelta(days=years * MACRO_CHANGE_DAYS)
        parts = rules.decompose(asset, gold, start, end) if shared[0][0] <= start else None
        if parts:
            out.append({"years": years, "from": start.isoformat(), "to": end.isoformat(), **parts})
    return out


def snapshot(session: Session, day: date) -> dict[str, Any]:
    """The macro picture as stored for a day; kept with a portfolio decision."""
    store = Store(session)
    out: dict[str, Any] = {}
    for key in ("DFII10", "DGS10", "DFF", "DTWEXBGS", "VIXCLS", "NETLIQ", "CPIYOY"):
        hit = rules.value_on(store.points(key), day)
        if hit:
            item = ITEMS[key]
            out[key] = {
                "label": item.label,
                "value": hit[1],
                "unit": item.unit,
                "day": hit[0].isoformat(),
            }
    return out
