"""Charts beyond a single line: yardstick matrix, lever chain, lenses and the regime map.

Everything here is arithmetic on stored observations. Exact identities (ratios, log changes) are
labelled as such; nothing is fitted, searched or forecast.
"""

import math
from collections import Counter
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from watchstreet.analysis import macro as rules
from watchstreet.analysis.expression import ExpressionError, Operand, evaluate
from watchstreet.analysis.macro import Link, Points
from watchstreet.commodities import BY_KEY as COMMODITY
from watchstreet.constants import (
    CYCLE_SECTORS,
    CYCLE_SPAN,
    DAYS_PER_YEAR,
    DRIVER_PATH_POINTS,
    LADDER_MAX_RUNGS,
    LENS_NAME_CHARS,
    MACRO_CHANGE_DAYS,
    MATRIX_CELL_POINTS,
    MATRIX_MIN_POINTS,
    MATRIX_YEARS,
    MOVE_SPAN,
    PERCENT,
    REGIME_MAX_POINTS,
    SENSITIVITY_MIN_OBS,
    SERIES_MAX_GAP_DAYS,
)
from watchstreet.errors import WatchStreetError
from watchstreet.models import (
    Asset,
    AssetCommodity,
    Company,
    Decision,
    Holding,
    Lens,
    SharePrice,
    Stake,
    Stock,
)
from watchstreet.services import macro

SHARE_PREFIX = "S:"
SLOT = "$objekt"
MIN_PATH = 2  # a change needs a start and an end
USD = "USD"
# listing currency -> (FRED series, True if the series is quoted as US dollars per unit)
FX: dict[str, tuple[str, bool]] = {
    "CAD": ("DEXCAUS", False),
    "AUD": ("DEXUSAL", True),
    "EUR": ("DEXUSEU", True),
}
YARDSTICKS: tuple[tuple[str, str, str], ...] = (
    ("usd", "US-Dollar", "nominal"),
    ("gold", "Gold", "Unzen Gold"),
    ("real", "Verbraucherpreise", "Preis ÷ Verbraucherpreisindex (Monatsmittel)"),
    ("m2", "Geldmenge M2", "Preis ÷ Geldmenge M2 (Monatsmittel)"),
    ("oil", "Rohöl", "Barrel Rohöl"),
)
MONTHLY_YARDSTICK = {"real": "CPIAUCSL", "m2": "M2SL"}
ACCOUNTING = "Rechnung, keine Aussage über Ursachen: „gemessen in“, nicht „wegen“."


class ChartError(WatchStreetError):
    """The requested chart cannot be built from what is stored."""


class Universe:
    """Every series a chart can use: macro items, commodity prices and share prices."""

    def __init__(self, session: Session) -> None:
        self.store = macro.Store(session)
        self.stocks = {s.symbol: s for s in session.scalars(select(Stock))}
        self.shares: dict[str, Points] = {symbol: [] for symbol in self.stocks}
        rows = session.execute(
            select(SharePrice.symbol, SharePrice.day, SharePrice.close).order_by(SharePrice.day)
        )
        for symbol, day, close in rows:
            self.shares.setdefault(symbol, []).append((day, close))
        self.held = set(
            session.scalars(select(Stock.symbol).join(Holding, Holding.stock_id == Stock.id))
        )
        self._commodity = _company_commodities(session)

    def is_share(self, key: str) -> bool:
        return key.startswith(SHARE_PREFIX) and key[len(SHARE_PREFIX) :] in self.shares

    def known(self, key: str) -> bool:
        return self.is_share(key) or key in macro.ITEMS

    def points(self, key: str) -> Points:
        if self.is_share(key):
            return self.shares[key[len(SHARE_PREFIX) :]]
        return self.store.points(key)

    def currency(self, key: str) -> str:
        if not self.is_share(key):
            return USD
        return (self.stocks[key[len(SHARE_PREFIX) :]].currency or USD).upper()

    def label(self, key: str) -> str:
        if self.is_share(key):
            stock = self.stocks[key[len(SHARE_PREFIX) :]]
            return f"{stock.name or stock.symbol} ({stock.symbol})"
        return macro.ITEMS[key].label

    def unit(self, key: str) -> str:
        return self.currency(key) if self.is_share(key) else macro.ITEMS[key].unit

    def money(self, key: str) -> bool:
        return self.is_share(key) or macro.ITEMS[key].money

    def frequency(self, key: str) -> str:
        return "weekly" if self.is_share(key) else macro.ITEMS[key].frequency

    def commodity(self, key: str) -> str:
        """Main commodity of the company behind a share ('' if unknown)."""
        return self._commodity.get(key[len(SHARE_PREFIX) :], "") if self.is_share(key) else ""

    def local_per_usd(self, currency: str) -> Points | None:
        if currency == USD:
            return None
        if currency not in FX:
            raise ChartError(f"Für die Währung {currency} ist kein Wechselkurs gespeichert")
        series, inverted = FX[currency]
        points = self.store.points(series)
        return [(d, 1 / v) for d, v in points if v] if inverted else points

    def in_usd(self, key: str) -> Points:
        rate = self.local_per_usd(self.currency(key))
        return self.points(key) if rate is None else rules.combine(self.points(key), rate, "ratio")

    def catalog(self) -> list[dict[str, Any]]:
        shares = [SHARE_PREFIX + s for s in sorted(self.shares) if self.shares[s]]
        return [
            {
                "key": key,
                "label": self.label(key),
                "unit": self.unit(key),
                "money": self.money(key),
                "frequency": self.frequency(key),
                "share": self.is_share(key),
            }
            for key in (*shares, *macro.ITEMS)
        ]


def _company_commodities(session: Session) -> dict[str, str]:
    """Most frequent primary commodity among the assets of each listed company."""
    rows = session.execute(
        select(Stock.symbol, AssetCommodity.commodity)
        .join(Company, Company.stock_id == Stock.id)
        .join(Stake, Stake.company_id == Company.id)
        .join(Asset, Asset.id == Stake.asset_id)
        .join(AssetCommodity, AssetCommodity.asset_id == Asset.id)
        .where(AssetCommodity.role == "primary")
    )
    counts: dict[str, Counter[str]] = {}
    for symbol, commodity in rows:
        counts.setdefault(symbol, Counter())[commodity] += 1
    return {symbol: counter.most_common(1)[0][0] for symbol, counter in counts.items()}


def _pct(log_change: float) -> float:
    return (math.exp(log_change) - 1) * PERCENT


# --- yardstick matrix ---------------------------------------------------------------------


def _measured(universe: Universe, usd: Points, yardstick: str) -> Points:
    if yardstick == "usd":
        return usd
    if yardstick in MONTHLY_YARDSTICK:
        return rules.monthly_ratio(usd, universe.store.points(MONTHLY_YARDSTICK[yardstick]))
    return rules.combine(usd, universe.store.points(yardstick), "ratio")


def _cell(points: Points) -> dict[str, Any]:
    if points:
        start = points[-1][0] - timedelta(days=round(MATRIX_YEARS * DAYS_PER_YEAR))
        points = [p for p in points if p[0] >= start]
    if len(points) < MATRIX_MIN_POINTS:
        return {"state": "thin", "n": len(points)}
    last_day, last = points[-1]
    before = rules.level_on(
        points, last_day - timedelta(days=MACRO_CHANGE_DAYS), SERIES_MAX_GAP_DAYS * 4
    )
    step = max(len(points) // MATRIX_CELL_POINTS, 1)
    shown = points[::step] if points[-1] in points[::step] else [*points[::step], points[-1]]
    return {
        "state": "ok",
        "n": len(points),
        "from": points[0][0].isoformat(),
        "to": last_day.isoformat(),
        "change_1y_pct": (last / before[1] - 1) * PERCENT if before and before[1] else None,
        "position": rules.range_position(points),
        "points": [{"day": d.isoformat(), "value": v} for d, v in shown],
    }


def matrix(session: Session) -> dict[str, Any]:
    """Everything held or tracked, measured in every yardstick."""
    universe = Universe(session)
    shares = sorted(
        (s for s, points in universe.shares.items() if points),
        key=lambda s: (s not in universe.held, s),
    )
    keys = [SHARE_PREFIX + s for s in shares] + list(COMMODITY)
    rows = []
    for key in keys:
        try:
            usd = universe.in_usd(key)
        except ChartError:
            usd = []
        cells = {
            yardstick: {"state": "identity"}
            if yardstick == key
            else _cell(_measured(universe, usd, yardstick))
            for yardstick, _, _ in YARDSTICKS
        }
        rows.append(
            {
                "key": key,
                "label": universe.label(key),
                "held": key[len(SHARE_PREFIX) :] in universe.held,
                "share": universe.is_share(key),
                "cells": cells,
            }
        )
    return {
        "yardsticks": [{"key": k, "label": label, "rule": rule} for k, label, rule in YARDSTICKS],
        "rows": rows,
        "years": MATRIX_YEARS,
        "note": (
            "Jede Zelle hat ihre eigene Skala; vergleichbar sind die Prozentzahlen, nicht die "
            "Formen. Verhältnisse entstehen nur an Tagen bzw. in Monaten, in denen beide Reihen "
            "einen eigenen Wert haben."
        ),
    }


# --- lever chain --------------------------------------------------------------------------


def _chain_links(universe: Universe, key: str) -> tuple[dict[str, Points], list[Link]]:
    series: dict[str, Points] = {
        "asset": universe.points(key),
        "gold": universe.store.points("gold"),
    }
    links: list[Link] = []
    bottom: tuple[str, ...] = ()
    rate = universe.local_per_usd(universe.currency(key))
    if rate is not None:
        series["fx"] = rate
        links.append((f"Währung: {universe.currency(key)} je US-Dollar", ("fx",), ()))
        bottom = ("fx",)
    commodity = universe.commodity(key) if universe.is_share(key) else key
    if not universe.is_share(key) and key not in COMMODITY and not universe.money(key):
        raise ChartError("Die Hebelkette gibt es nur für Preise (Aktien, Rohstoffe, Indizes)")
    if key == "gold":
        raise ChartError("Gold ist selbst der Massstab; es gibt nichts zu zerlegen")
    links.append(("Goldpreis in US-Dollar", ("gold",), ()))
    if universe.is_share(key) and commodity and commodity != "gold":
        series["commodity"] = universe.store.points(commodity)
        label = COMMODITY[commodity].label
        links.append((f"{label}, gemessen in Gold", ("commodity",), ("gold",)))
        links.append((f"Unternehmen, gemessen in {label}", ("asset",), (*bottom, "commodity")))
    else:
        own = "Unternehmen" if universe.is_share(key) else universe.label(key)
        links.append((f"{own}, gemessen in Gold", ("asset",), (*bottom, "gold")))
    return series, links


def chain(session: Session, key: str, years: float) -> dict[str, Any]:
    """Change of a price as a chain of ratios whose log changes add up exactly."""
    universe = Universe(session)
    if not universe.known(key):
        raise ChartError("Unbekannte Reihe")
    series, links = _chain_links(universe, key)
    asset = series["asset"]
    if not asset:
        raise ChartError("Für diese Reihe ist kein Kursverlauf gespeichert")
    end = asset[-1][0]
    start = end - timedelta(days=round(years * DAYS_PER_YEAR))
    days = [d for d, _ in asset if d >= start]
    path = rules.chain_path(series, links, days, SERIES_MAX_GAP_DAYS)
    if len(path) < MIN_PATH:
        raise ChartError("Zu wenige gemeinsame Beobachtungen für diesen Zeitraum")
    first_day, last_day = path[0][0], path[-1][0]
    final = path[-1][1]
    used = rules.chain_levels(series, links, last_day, SERIES_MAX_GAP_DAYS)
    total = sum(final)
    return {
        "key": key,
        "label": universe.label(key),
        "currency": universe.currency(key),
        "from": first_day.isoformat(),
        "to": last_day.isoformat(),
        "total_pct": _pct(total),
        "total_log": total * PERCENT,
        "links": [
            {"label": label, "log": value * PERCENT, "pct": _pct(value)}
            for (label, _, _), value in zip(links, final, strict=True)
        ],
        "path": [
            {"day": d.isoformat(), "values": [v * PERCENT for v in values]} for d, values in path
        ],
        "observed": {name: day.isoformat() for name, day in (used[1] if used else {}).items()},
        "commodity": universe.commodity(key),
        "note": (
            f"{ACCOUNTING} Die Glieder multiplizieren sich zum Kurs; ihre Beiträge sind "
            "Logarithmus-Punkte und addieren sich exakt zur Gesamtänderung. Für andere Reihen "
            f"gilt der letzte Wert, der höchstens {SERIES_MAX_GAP_DAYS} Tage alt ist."
        ),
    }


# --- lenses -------------------------------------------------------------------------------


def lens(session: Session, expression: str, subject: str = "") -> dict[str, Any]:
    """Evaluate a formula; ``$objekt`` stands for ``subject``."""
    universe = Universe(session)

    def resolve(name: str) -> Operand:
        key = subject if name == SLOT else name
        if name == SLOT and not subject:
            raise ExpressionError(f"Die Formel enthält {SLOT}; bitte ein Objekt wählen")
        if name.startswith("$") and name != SLOT:
            raise ExpressionError(f"Unbekannter Platzhalter {name} (bekannt: {SLOT})")
        if not universe.known(key):
            raise ExpressionError(f"Unbekannte Reihe „{key}“")
        if universe.is_share(key):
            return Operand(universe.in_usd(key), USD)
        return Operand(universe.points(key), universe.unit(key))

    result = evaluate(expression, resolve)
    terms = []
    for name in result.terms:
        key = subject if name == SLOT else name
        points = universe.points(key)
        terms.append(
            {
                "name": name,
                "key": key,
                "label": universe.label(key),
                "unit": universe.unit(key),
                "frequency": universe.frequency(key),
                "last_day": points[-1][0].isoformat() if points else None,
            }
        )
    return {
        "expression": expression,
        "subject": subject,
        "unit": result.unit,
        "terms": terms,
        "dropped": result.dropped,
        "points": [{"day": d.isoformat(), "value": v} for d, v in result.points],
        "note": (
            "Preise gehen in US-Dollar in die Formel ein (Aktien zum Tageskurs der Währung). "
            "Zwei Reihen werden nur an Tagen verrechnet, an denen beide einen eigenen Wert haben."
        ),
    }


def lenses(session: Session) -> list[dict[str, Any]]:
    return [
        {"id": row.id, "name": row.name, "expression": row.expression}
        for row in session.scalars(select(Lens).order_by(Lens.name))
    ]


def save_lens(session: Session, name: str, expression: str) -> dict[str, Any]:
    name = name.strip()
    if not name or len(name) > LENS_NAME_CHARS:
        raise ChartError(f"Der Name braucht 1 bis {LENS_NAME_CHARS} Zeichen")
    universe = Universe(session)
    subject = next((item["key"] for item in universe.catalog() if item["money"]), "")
    lens(session, expression, subject)  # a lens that cannot be evaluated is not saved
    row = session.scalars(select(Lens).where(Lens.name == name)).first()
    if row is None:
        row = Lens(name=name, expression=expression)
        session.add(row)
    else:
        row.expression = expression
    session.flush()
    return {"id": row.id, "name": row.name, "expression": row.expression}


def delete_lens(session: Session, lens_id: int) -> bool:
    row = session.get(Lens, lens_id)
    if row is None:
        return False
    session.delete(row)
    session.flush()
    return True


# --- regime map ---------------------------------------------------------------------------


def regime(session: Session, x: str, y: str, years: float) -> dict[str, Any]:
    """Path of two series through their common plane, with the user's decisions on it."""
    universe = Universe(session)
    for key in (x, y):
        if not universe.known(key):
            raise ChartError(f"Unbekannte Reihe „{key}“")
    if x == y:
        raise ChartError("Die beiden Achsen brauchen verschiedene Reihen")
    xs, ys = universe.points(x), universe.points(y)
    other = dict(ys)
    shared = [(d, v, other[d]) for d, v in xs if d in other]
    if shared:
        start = shared[-1][0] - timedelta(days=round(years * DAYS_PER_YEAR))
        shared = [p for p in shared if p[0] >= start]
    if len(shared) < MIN_PATH:
        raise ChartError("Die beiden Reihen haben in diesem Zeitraum keine gemeinsamen Tage")
    step = max(math.ceil(len(shared) / REGIME_MAX_POINTS), 1)
    path = shared[::step]
    if path[-1] != shared[-1]:
        path.append(shared[-1])
    decisions = []
    rows = session.execute(
        select(Decision, Stock.symbol)
        .join(Stock, Stock.id == Decision.stock_id)
        .order_by(Decision.day)
    )
    for decision, symbol in rows:
        at_x = rules.level_on(xs, decision.day, SERIES_MAX_GAP_DAYS)
        at_y = rules.level_on(ys, decision.day, SERIES_MAX_GAP_DAYS)
        if at_x and at_y:
            decisions.append(
                {
                    "day": decision.day.isoformat(),
                    "kind": decision.kind,
                    "symbol": symbol,
                    "reason": decision.reason,
                    "x": at_x[1],
                    "y": at_y[1],
                    "in_window": decision.day >= path[0][0],
                }
            )
    return {
        "x": {"key": x, "label": universe.label(x), "unit": universe.unit(x)},
        "y": {"key": y, "label": universe.label(y), "unit": universe.unit(y)},
        "from": path[0][0].isoformat(),
        "to": path[-1][0].isoformat(),
        "path": [{"day": d.isoformat(), "x": a, "y": b} for d, a, b in path],
        "decisions": decisions,
        "note": (
            "Der Weg zeigt, wo beide Grössen gemeinsam standen. Aufeinanderfolgende Tage sind "
            "nicht unabhängig: wenige Episoden sehen wie viele Punkte aus. Die Karte sagt "
            "nichts darüber, was als Nächstes geschieht."
        ),
    }


# --- driver ladder ------------------------------------------------------------------------

# What the application assumes stands behind a series, nearest driver first. A declared view of
# the world, not a finding: the chart shows whether the data agree with it.
DRIVERS: dict[str, tuple[str, ...]] = {
    "gold": ("DFII10", "DTWEXBGS"),
    "silver": ("gold", "DFII10"),
    "copper": ("DTWEXBGS", "DFII10"),
    "uranium": ("DTWEXBGS",),
    "oil": ("DTWEXBGS",),
    "gas": ("oil",),
    "lumber": ("HOUST", "MORTGAGE30US"),
    "HOUST": ("MORTGAGE30US",),
    "MORTGAGE30US": ("DGS10",),
    "DGS10": ("DFII10", "T10YIE"),
    "DFII10": ("CPIYOY", "DFF"),
    "DTWEXBGS": ("DFII10", "NETLIQ"),
    "DFF": ("CPIYOY",),
    "T10YIE": ("CPIYOY", "oil"),
    "CPIYOY": ("oil", "M2YOY"),
    "M2YOY": ("NETLIQ",),
    "SP500": ("NETLIQ", "DFII10"),
}
RATE_UNITS = ("%", "Prozentpunkte")
ESTIMATE = (
    "Schätzung aus vergangenen Änderungen, keine Regel: Steigungen schwanken mit dem Zeitraum, "
    "und ein Zusammenhang ist keine Ursache."
)


def _drivers(universe: Universe, key: str) -> tuple[str, ...]:
    if universe.is_share(key):
        return (universe.commodity(key) or "gold",)
    return DRIVERS.get(key, ())


def _relative(universe: Universe, key: str) -> bool:
    return not universe.unit(key).startswith(RATE_UNITS)


def _pair(universe: Universe, first: str, second: str) -> tuple[Points, Points]:
    """Both series on a common grid: months if either is monthly, else their own days."""
    a = universe.in_usd(first) if universe.money(first) else universe.points(first)
    b = universe.in_usd(second) if universe.money(second) else universe.points(second)
    if "monthly" in (universe.frequency(first), universe.frequency(second)):
        return rules.monthly_mean(a), rules.monthly_mean(b)
    return a, b


def _slope(universe: Universe, target: str, driver: str, start: date) -> dict[str, Any] | None:
    a, b = _pair(universe, target, driver)
    a, b = [p for p in a if p[0] >= start], [p for p in b if p[0] >= start]
    kind = {
        "relative_target": _relative(universe, target),
        "relative_driver": _relative(universe, driver),
    }
    whole = rules.sensitivity(a, b, min_obs=SENSITIVITY_MIN_OBS, **kind)
    if whole is None:
        return None
    middle = a[len(a) // 2][0] if a else start
    halves = [
        rules.sensitivity(part, b, min_obs=SENSITIVITY_MIN_OBS // 2, **kind)
        for part in ([p for p in a if p[0] < middle], [p for p in a if p[0] >= middle])
    ]
    return {
        **whole,
        "first_half": halves[0]["beta"] if halves[0] else None,
        "second_half": halves[1]["beta"] if halves[1] else None,
        "unit": ("% je 1 %" if kind["relative_target"] else "Punkte je 1 %")
        if kind["relative_driver"]
        else ("% je Prozentpunkt" if kind["relative_target"] else "Punkte je Prozentpunkt"),
    }


def ladder(session: Session, key: str, driver: str, years: float) -> dict[str, Any]:
    """A series against what stands behind it, and what in turn depends on it."""
    universe = Universe(session)
    if not universe.known(key):
        raise ChartError("Unbekannte Reihe")
    declared = _drivers(universe, key)
    chosen = driver or (declared[0] if declared else "")
    if chosen and (not universe.known(chosen) or chosen == key):
        raise ChartError("Unbekannter Treiber")
    stored = _grid(universe, key)
    if not stored:
        raise ChartError("Für diese Reihe ist nichts gespeichert")
    start = stored[-1][0] - timedelta(days=round(years * DAYS_PER_YEAR))
    path: list[dict[str, Any]] = []
    own: list[dict[str, Any]] = []
    slope = None
    if chosen:
        a, b = _pair(universe, key, chosen)
        other = dict(b)
        shared = [(d, other[d], v) for d, v in a if d in other and d >= start]
        step = max(math.ceil(len(shared) / DRIVER_PATH_POINTS), 1)
        shown = shared[::step]
        if shared and shown[-1] != shared[-1]:
            shown.append(shared[-1])
        path = [{"day": d.isoformat(), "x": x, "y": y} for d, x, y in shown]
        slope = _slope(universe, key, chosen, start)
        if _relative(universe, key) and _relative(universe, chosen):
            own = [
                {
                    "day": d.isoformat(),
                    "values": [explained * PERCENT, (total - explained) * PERCENT],
                    "slope": used,
                }
                for d, total, explained, used in rules.own_path(
                    [p for p in a if p[0] >= start], b, SENSITIVITY_MIN_OBS
                )
            ]
    dependents = [
        name
        for name in (*(SHARE_PREFIX + s for s in sorted(universe.shares)), *DRIVERS)
        if key in _drivers(universe, name) and universe.points(name)
    ]
    rows: list[tuple[float, dict[str, Any]]] = []
    for name in dependents:
        estimate = _slope(universe, name, key, start)
        row = {
            "key": name,
            "label": universe.label(name),
            "share": universe.is_share(name),
            "slope": estimate,
        }
        rows.append((-abs(estimate["beta"]) if estimate else 1.0, row))
    rows.sort(key=lambda item: item[0])

    def meta(name: str) -> dict[str, Any]:
        unit = USD if universe.is_share(name) else universe.unit(name)
        return {
            "key": name,
            "label": universe.label(name),
            "unit": unit,
            "has_drivers": bool(_drivers(universe, name)),
        }

    return {
        "subject": meta(key),
        "drivers": [meta(name) for name in declared if universe.known(name)],
        "driver": meta(chosen) if chosen else None,
        "from": path[0]["day"] if path else None,
        "to": path[-1]["day"] if path else None,
        "path": path,
        "slope": slope,
        "own": own,
        "own_note": (
            "Vom Treiber erklärt = Summe aus (Änderung des Treibers × Empfindlichkeit), wobei die "
            "Empfindlichkeit an jedem Tag nur aus früheren Änderungen geschätzt ist. Der Rest ist "
            "der eigene Anteil. Beide addieren sich zur Gesamtänderung seit dem ersten Tag mit "
            f"mindestens {SENSITIVITY_MIN_OBS} Beobachtungen. {ESTIMATE}"
        ),
        "dependents": [row for _, row in rows],
        "note": (
            "Die Treiber sind eine hinterlegte Annahme über die Welt, kein Befund; der Weg zeigt, "
            f"ob die Daten dazu passen. {ESTIMATE}"
        ),
    }


def _grid(universe: Universe, key: str) -> Points:
    return universe.in_usd(key) if universe.money(key) else universe.points(key)


def sheet(session: Session, key: str, years: float) -> dict[str, Any]:
    """The whole ladder below a series on one sheet, with what moved unusually of late."""
    universe = Universe(session)
    if not universe.known(key):
        raise ChartError("Unbekannte Reihe")
    chain_keys = [key]
    while len(chain_keys) < LADDER_MAX_RUNGS:
        following = [d for d in _drivers(universe, chain_keys[-1]) if universe.known(d)]
        if not following or following[0] in chain_keys:
            break
        chain_keys.append(following[0])
    rungs = []
    for index, name in enumerate(chain_keys):
        points = _grid(universe, name)
        if points:
            start = points[-1][0] - timedelta(days=round(years * DAYS_PER_YEAR))
            points = [p for p in points if p[0] >= start]
        span = MOVE_SPAN[universe.frequency(name)]
        move = (
            rules.unusual_move(points, span, relative=_relative(universe, name)) if points else None
        )
        step = max(len(points) // MATRIX_CELL_POINTS, 1)
        upper = chain_keys[index + 1] if index + 1 < len(chain_keys) else ""
        rungs.append(
            {
                "key": name,
                "label": universe.label(name),
                "unit": USD if universe.is_share(name) else universe.unit(name),
                "value": points[-1][1] if points else None,
                "day": points[-1][0].isoformat() if points else None,
                "spark": [v for _, v in points[::step]],
                "position": rules.range_position(points),
                "move": move[0] if move else None,
                "move_unit": "%" if _relative(universe, name) else "Punkte",
                "unusual": move[1] if move else None,
                "slope": _slope(universe, name, upper, points[0][0]) if upper and points else None,
                "next": universe.label(upper) if upper else "",
            }
        )
    return {
        "rungs": rungs,
        "years": years,
        "note": (
            "„Ungewöhnlich“ misst die Änderung des letzten Monats in Standardabweichungen aller "
            "Monatsänderungen des gezeigten Zeitraums: ab etwa ±2 ist die Bewegung selten. Es ist "
            "eine Beschreibung der Vergangenheit, kein Signal."
        ),
    }


SECTOR_LABELS = (
    "hoch, kaum Bewegung", "hoch und steigend", "mittel, steigt stark", "tief und steigend",
    "tief, kaum Bewegung", "tief und fallend", "mittel, fällt stark", "hoch und fallend",
)  # fmt: skip


def _episodes(rows: list[dict[str, Any]], sector: int) -> list[dict[str, Any]]:
    """Stretches of consecutive observations in one sector, with the subject's change in each."""
    out: list[dict[str, Any]] = []
    run: list[dict[str, Any]] = []
    for row in [*rows, {"sector": -1}]:
        if row["sector"] == sector:
            run.append(row)
        elif run:
            first, last = run[0], run[-1]
            change = (last["y"] / first["y"] - 1) * PERCENT if first["y"] else None
            out.append(
                {"from": first["day"], "to": last["day"], "n": len(run), "change_pct": change}
            )
            run = []
    return out


def cycle(session: Session, key: str, driver: str, years: float) -> dict[str, Any]:
    """The subject on the cycle clock of its driver: equal phases lie on the same ray."""
    universe = Universe(session)
    if not universe.known(key):
        raise ChartError("Unbekannte Reihe")
    declared = [d for d in _drivers(universe, key) if universe.known(d)]
    chosen = driver or (declared[0] if declared else "")
    if not chosen or not universe.known(chosen) or chosen == key:
        raise ChartError("Für diese Reihe ist kein Treiber hinterlegt")
    a, b = _pair(universe, key, chosen)
    if not a or not b:
        raise ChartError("Für diese Reihen ist nichts gespeichert")
    start = min(a[-1][0], b[-1][0]) - timedelta(days=round(years * DAYS_PER_YEAR))
    monthly = "monthly" in (universe.frequency(key), universe.frequency(chosen))
    span = CYCLE_SPAN["monthly" if monthly else universe.frequency(chosen)]
    phases = rules.cycle([p for p in b if p[0] >= start], span)
    own = dict(a)
    width = 360 / CYCLE_SECTORS
    rows: list[dict[str, Any]] = []
    for day, level, momentum in phases:
        if day not in own:
            continue
        angle = math.degrees(math.atan2(momentum, level)) % 360
        rows.append(
            {
                "day": day.isoformat(),
                "level": level,
                "momentum": momentum,
                "angle": angle,
                "sector": int(((angle + width / 2) % 360) // width),
                "y": own[day],
            }
        )
    if len(rows) < MIN_PATH:
        raise ChartError("Zu wenige gemeinsame Werte für eine Zyklusuhr in diesem Zeitraum")
    today = int(rows[-1]["sector"])

    def meta(name: str) -> dict[str, Any]:
        unit = USD if universe.is_share(name) else universe.unit(name)
        return {"key": name, "label": universe.label(name), "unit": unit}

    return {
        "subject": meta(key),
        "driver": meta(chosen),
        "drivers": [meta(name) for name in declared],
        "points": rows,
        "sectors": list(SECTOR_LABELS),
        "today": today,
        "episodes": _episodes(rows, today),
        "span": span,
        "note": (
            "Winkel = Phase des Treibers (rechts hoch, links tief, oben steigend, unten fallend), "
            "Abstand vom Mittelpunkt = Wert des Gegenstands. Zeiträume in derselben Phase liegen "
            "auf demselben Strahl. „Hoch“ und „tief“ beziehen sich auf den Durchschnitt des "
            "gezeigten Zeitraums – das ist Rückschau, keine Prognose, und wenige Umläufe sind "
            "wenige Beobachtungen."
        ),
    }
