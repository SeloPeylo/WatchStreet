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
from watchstreet.analysis import plain
from watchstreet.analysis.expression import (
    RATIO_UNIT,
    ExpressionError,
    Operand,
    evaluate,
    series_names,
)
from watchstreet.analysis.macro import Link, Points
from watchstreet.commodities import BY_KEY as COMMODITY
from watchstreet.constants import (
    CYCLE_MIN_EPISODE_POINTS,
    CYCLE_SECTORS,
    CYCLE_SPAN,
    DAYS_PER_YEAR,
    DRIVER_LIST_CHARS,
    DRIVER_PATH_POINTS,
    GRIDS,
    LADDER_MAX_RUNGS,
    LENS_NAME_CHARS,
    MACRO_CHANGE_DAYS,
    MATRIX_CELL_POINTS,
    MATRIX_MIN_POINTS,
    MATRIX_YEARS,
    MAX_JOINT_DRIVERS,
    MOVE_SPAN,
    PERCENT,
    REGIME_MAX_POINTS,
    SENSITIVITY_MIN_OBS,
    SERIES_MAX_GAP_DAYS,
    UNUSUAL_SCORE,
)
from watchstreet.errors import WatchStreetError
from watchstreet.models import (
    Asset,
    AssetCommodity,
    Company,
    Decision,
    DriverSet,
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
POINTS = (
    "Ein Punkt ist der Logarithmus der Änderung mal 100: bei kleinen Änderungen etwa ein "
    "Prozent, und im Unterschied zu Prozenten lassen sich Punkte addieren."
)
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
        self.driver_sets: dict[str, tuple[str, ...]] = {
            row.key: tuple(part for part in row.drivers.split(",") if part)
            for row in session.scalars(select(DriverSet))
        }

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

    def grid_of(self, key: str) -> str:
        """Own frequency of a series; read off the spacing where none is declared."""
        declared = self.frequency(key)
        return declared if declared in GRIDS else rules.infer_frequency(self.points(key))

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


def _change(cell: dict[str, Any]) -> float | None:
    return cell.get("change_1y_pct") if cell.get("state") == "ok" else None


def matrix(session: Session) -> dict[str, Any]:
    """Everything held or tracked, measured in every yardstick."""
    universe = Universe(session)
    shares = sorted(
        (s for s, points in universe.shares.items() if points),
        key=lambda s: (s not in universe.held, s),
    )
    keys = [SHARE_PREFIX + s for s in shares] + list(COMMODITY)
    rows: list[dict[str, Any]] = []
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
    examples = [
        (
            row["label"],
            _change(row["cells"].get("usd", {})),
            _change(row["cells"].get("gold", {})),
        )
        for row in rows
    ]
    return {
        "plain": plain.matrix_sentence(examples),
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
    base = rules.level_on(asset, start, SERIES_MAX_GAP_DAYS * 4)  # same base day as the matrix
    days = [d for d, _ in asset if d >= (base[0] if base else start)]
    path = rules.chain_path(series, links, days, SERIES_MAX_GAP_DAYS)
    if len(path) < MIN_PATH:
        raise ChartError("Zu wenige gemeinsame Beobachtungen für diesen Zeitraum")
    first_day, last_day = path[0][0], path[-1][0]
    final = path[-1][1]
    used = rules.chain_levels(series, links, last_day, SERIES_MAX_GAP_DAYS)
    total = sum(final)
    parts = [(label, value * PERCENT) for (label, _, _), value in zip(links, final, strict=True)]
    return {
        "plain": plain.chain_sentence(
            universe.label(key),
            universe.currency(key),
            (last_day - first_day).days,
            _pct(total),
            parts,
        ),
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
            f"{ACCOUNTING} Die Glieder multiplizieren sich zum Kurs; ihre Beiträge sind Punkte "
            f"und addieren sich exakt zur Gesamtänderung. {POINTS} Für andere Reihen "
            f"gilt der letzte Wert, der höchstens {SERIES_MAX_GAP_DAYS} Tage alt ist."
        ),
    }


# --- lenses -------------------------------------------------------------------------------


def lens(session: Session, expression: str, subject: str = "") -> dict[str, Any]:
    """Evaluate a formula; ``$objekt`` stands for ``subject``.

    All series of one formula are first brought to the coarsest frequency among them (monthly
    means if any is monthly, else weekly means if any is weekly, else the days as they are).
    """
    universe = Universe(session)

    def key_of(name: str) -> str:
        key = subject if name == SLOT else name
        if name == SLOT and not subject:
            raise ExpressionError(f"Die Formel enthält {SLOT}; bitte ein Objekt wählen")
        if name.startswith("$") and name != SLOT:
            raise ExpressionError(f"Unbekannter Platzhalter {name} (bekannt: {SLOT})")
        if not universe.known(key):
            raise ExpressionError(f"Unbekannte Reihe „{key}“")
        return key

    keys = {name: key_of(name) for name in series_names(expression)}
    operands: dict[str, Operand] = {}
    for key in keys.values():
        if universe.is_share(key):
            operands[key] = Operand(universe.in_usd(key), USD)
        else:
            operands[key] = Operand(universe.points(key), universe.unit(key))
    own_grids = {key: universe.grid_of(key) for key in operands}
    grid = rules.coarsest_grid(own_grids.values())
    if len(operands) > 1:  # one series alone keeps its own days
        operands = {
            key: Operand(rules.resample(op.points, grid), op.unit) for key, op in operands.items()
        }
    result = evaluate(expression, lambda name: operands[keys[name]])
    terms = []
    for name in result.terms:
        key = keys[name]
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
    coarse = [universe.label(key) for key, own in own_grids.items() if own == grid]
    averaged = any(own != grid for own in own_grids.values())
    title = expression.replace(SLOT, universe.label(subject) if subject else SLOT)
    return {
        "plain": plain.lens_sentence(
            title,
            "" if result.unit == RATIO_UNIT else result.unit,
            result.points[0] if result.points else None,
            result.points[-1] if result.points else None,
        ),
        "expression": expression,
        "subject": subject,
        "unit": result.unit,
        "grid": grid,
        "grid_note": plain.grid_sentence(grid, coarse) if averaged else "",
        "terms": terms,
        "dropped": result.dropped,
        "points": [{"day": d.isoformat(), "value": v} for d, v in result.points],
        "note": (
            "Preise gehen in US-Dollar in die Formel ein (Aktien zum Tageskurs der Währung). "
            "Haben die Reihen verschiedene Takte, werden alle auf den gröbsten gemittelt "
            "(Monats- oder Wochenmittel); danach werden zwei Reihen nur an Tagen verrechnet, an "
            "denen beide einen eigenen Wert haben."
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
    ends = [
        (universe.label(x), universe.unit(x), path[0][1], path[-1][1]),
        (universe.label(y), universe.unit(y), path[0][2], path[-1][2]),
    ]
    return {
        "plain": plain.regime_sentence(
            ends[0], ends[1], path[0][0], sum(1 for d in decisions if d["in_window"])
        ),
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
OVERLAPPING_UNIT = "Vorjahresmonat"  # yearly rates of monthly data share eleven months
WEAK_T = 2.0  # below this the slope cannot be told from zero
ESTIMATE = (
    "Schätzung aus vergangenen Änderungen, keine Regel: Steigungen schwanken mit dem Zeitraum, "
    "und ein Zusammenhang ist keine Ursache."
)


def _default_drivers(universe: Universe, key: str) -> tuple[str, ...]:
    if universe.is_share(key):
        return (universe.commodity(key) or "gold",)
    return DRIVERS.get(key, ())


def _drivers(universe: Universe, key: str) -> tuple[str, ...]:
    """The user's own driver set for a series if there is one, else the declared default."""
    stored = tuple(k for k in universe.driver_sets.get(key, ()) if k != key and universe.known(k))
    return stored or _default_drivers(universe, key)


def _relative(universe: Universe, key: str) -> bool:
    return not universe.unit(key).startswith(RATE_UNITS)


def _pair(universe: Universe, first: str, second: str) -> tuple[Points, Points]:
    """Both series on a common grid: months if either is monthly, else their own days."""
    a = universe.in_usd(first) if universe.money(first) else universe.points(first)
    b = universe.in_usd(second) if universe.money(second) else universe.points(second)
    if "monthly" in (universe.frequency(first), universe.frequency(second)):
        return rules.monthly_mean(a), rules.monthly_mean(b)
    return a, b


def _aligned(universe: Universe, keys: list[str]) -> tuple[list[Points], str]:
    """Several series on one grid: the coarsest frequency among them (see ``lens``)."""
    series = [_grid(universe, key) for key in keys]
    grid = rules.coarsest_grid(universe.grid_of(key) for key in keys)
    return [rules.resample(points, grid) for points in series], grid


def _beta_unit(relative_target: bool, relative_driver: bool) -> str:  # noqa: FBT001
    if relative_driver:
        return "% je 1 %" if relative_target else "Punkte je 1 %"
    return "% je Prozentpunkt" if relative_target else "Punkte je Prozentpunkt"


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
    first = halves[0]["beta"] if halves[0] else None
    second = halves[1]["beta"] if halves[1] else None
    flips = first is not None and second is not None and (first > 0) != (second > 0)
    overlapping = any(OVERLAPPING_UNIT in universe.unit(name) for name in (target, driver))
    return {
        **whole,
        "t": whole["t"] if math.isfinite(whole["t"]) else None,
        "first_half": first,
        "second_half": second,
        "weak": abs(whole["t"]) < WEAK_T or flips,
        "overlapping": overlapping,
        "unit": _beta_unit(kind["relative_target"], kind["relative_driver"]),
    }


def _joint(universe: Universe, key: str, keys: list[str], start: date) -> dict[str, Any] | None:
    """All of ``keys`` at once against ``key`` over the window; ``None`` if no fit is possible."""
    series, grid = _aligned(universe, [key, *keys])
    target, *others = ([p for p in points if p[0] >= start] for points in series)
    relative = _relative(universe, key)
    flags = [_relative(universe, name) for name in keys]
    fit = rules.joint_sensitivity(target, others, relative_target=relative, relative_drivers=flags)
    if fit is None:
        return None
    scale = PERCENT if relative else 1.0  # log steps become points, differences stay as they are
    unit = "Punkte" if relative else "Prozentpunkte"
    shares = [value * scale for value in fit.contributions]
    return {
        "drivers": [
            {
                "key": name,
                "label": universe.label(name),
                "beta": beta,
                "unit": _beta_unit(relative, flag),
                "contribution_pct": share,
            }
            for name, flag, beta, share in zip(keys, flags, fit.betas, shares, strict=True)
        ],
        "own_pct": fit.own * scale,
        "total_pct": fit.total * scale,
        "real_change_pct": _pct(fit.total) if relative else fit.total,
        "unit": unit,
        "r_squared": fit.r_squared,
        "observations": fit.observations,
        "grid": grid,
        "plain": plain.joint_sentence(
            universe.label(key),
            [universe.label(name) for name in keys],
            shares,
            fit.own * scale,
            fit.r_squared,
            unit,
        ),
    }


def _requested(universe: Universe, key: str, raw: str) -> list[str]:
    """Drivers asked for as comma-separated keys: known, not the series itself, no duplicates."""
    keys = [part.strip() for part in raw.split(",") if part.strip()]
    if len(keys) > MAX_JOINT_DRIVERS:
        raise ChartError(f"Höchstens {MAX_JOINT_DRIVERS} Treiber")
    if len(set(keys)) != len(keys):
        raise ChartError("Ein Treiber ist doppelt gewählt")
    if any(name == key or not universe.known(name) for name in keys):
        raise ChartError("Unbekannter Treiber")
    return keys


def ladder(
    session: Session, key: str, driver: str, years: float, drivers: str = ""
) -> dict[str, Any]:
    """A series against what stands behind it, and what in turn depends on it.

    ``driver`` picks the one driver drawn and fitted alone (default: the first of the set).
    ``drivers`` (comma-separated, at most three) asks for a joint fit of several at once. Without
    it, the joint fit is made for the series' own set (stored or declared) when that has two or
    more drivers and no single ``driver`` was asked for: asking for one driver means looking at
    exactly that one.
    """
    universe = Universe(session)
    if not universe.known(key):
        raise ChartError("Unbekannte Reihe")
    declared = _drivers(universe, key)
    asked = _requested(universe, key, drivers)
    chosen = driver or (asked[0] if asked else (declared[0] if declared else ""))
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
    joint_keys = asked or (
        [] if driver else [name for name in declared if universe.known(name)][:MAX_JOINT_DRIVERS]
    )
    joint = _joint(universe, key, joint_keys, start) if len(joint_keys) > 1 else None
    names = dict.fromkeys(
        (*(SHARE_PREFIX + s for s in sorted(universe.shares)), *DRIVERS, *universe.driver_sets)
    )
    dependents = [
        name
        for name in names
        if universe.known(name) and key in _drivers(universe, name) and universe.points(name)
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
        return _meta(universe, name)

    return {
        "plain": _ladder_plain(universe, key, chosen, slope),
        "custom": key in universe.driver_sets,
        "max_drivers": MAX_JOINT_DRIVERS,
        "joint": joint,
        "joint_note": (
            "Zu wenige gemeinsame Beobachtungen, oder die Treiber bewegen sich so ähnlich, dass "
            "sich ihre Anteile nicht trennen lassen."
            if len(joint_keys) > 1 and joint is None
            else ""
        ),
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
            f"mindestens {SENSITIVITY_MIN_OBS} Beobachtungen. {POINTS} {ESTIMATE}"
        ),
        "dependents": [row for _, row in rows],
        "note": (
            "Die Treiber sind eine hinterlegte Annahme über die Welt, kein Befund; der Weg zeigt, "
            f"ob die Daten dazu passen. {ESTIMATE}"
        ),
    }


def _meta(universe: Universe, name: str) -> dict[str, Any]:
    return {
        "key": name,
        "label": universe.label(name),
        "unit": USD if universe.is_share(name) else universe.unit(name),
        "has_drivers": bool(_drivers(universe, name)),
    }


def _ladder_plain(universe: Universe, key: str, chosen: str, slope: dict[str, Any] | None) -> str:
    subject = universe.label(key)
    if not chosen:
        return plain.missing_sentence(subject, None)
    if slope is None:
        return plain.missing_sentence(subject, universe.label(chosen))
    return plain.ladder_sentence(
        subject,
        universe.label(chosen),
        beta=slope["beta"],
        r2=slope["r2"],
        weak=slope["weak"],
        relative_target=_relative(universe, key),
        relative_driver=_relative(universe, chosen),
    )


def driver_set(session: Session, key: str) -> dict[str, Any]:
    """The drivers of a series (own or declared) and the declared default."""
    universe = Universe(session)
    if not universe.known(key):
        raise ChartError("Unbekannte Reihe")
    return {
        "key": key,
        "custom": key in universe.driver_sets,
        "drivers": [_meta(universe, name) for name in _drivers(universe, key)],
        "default": [
            _meta(universe, name)
            for name in _default_drivers(universe, key)
            if universe.known(name)
        ],
        "max_drivers": MAX_JOINT_DRIVERS,
    }


def save_driver_set(session: Session, key: str, drivers: list[str]) -> dict[str, Any]:
    """Store the user's own drivers for a series: one to three known keys, none twice."""
    universe = Universe(session)
    if not universe.known(key):
        raise ChartError("Unbekannte Reihe")
    keys = [name.strip() for name in drivers]
    if not 1 <= len(keys) <= MAX_JOINT_DRIVERS:
        raise ChartError(f"Ein bis {MAX_JOINT_DRIVERS} Treiber sind möglich")
    if len(set(keys)) != len(keys):
        raise ChartError("Ein Treiber ist doppelt gewählt")
    if key in keys:
        raise ChartError("Eine Reihe kann nicht ihr eigener Treiber sein")
    unknown = next((name for name in keys if not universe.known(name)), None)
    if unknown is not None:
        raise ChartError(f"Unbekannter Treiber „{unknown}“")
    text = ",".join(keys)
    if len(text) > DRIVER_LIST_CHARS:
        raise ChartError("Die Treiberliste ist zu lang")
    row = session.scalars(select(DriverSet).where(DriverSet.key == key)).first()
    if row is None:
        session.add(DriverSet(key=key, drivers=text))
    else:
        row.drivers = text
    session.flush()
    return driver_set(session, key)


def delete_driver_set(session: Session, key: str) -> None:
    """Back to the declared drivers; nothing to do if the series has no own set."""
    row = session.scalars(select(DriverSet).where(DriverSet.key == key)).first()
    if row is not None:
        session.delete(row)
        session.flush()


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
    rungs: list[dict[str, Any]] = []
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
    rare = [
        (r["label"], r["move"], r["move_unit"])
        for r in rungs
        if r["unusual"] is not None and abs(r["unusual"]) >= UNUSUAL_SCORE
    ]
    return {
        "plain": plain.sheet_sentence(
            len(rungs), rare, measured=sum(1 for r in rungs if r["move"] is not None)
        ),
        "rungs": rungs,
        "years": years,
        "note": (
            "„Ungewöhnlich“ misst die Änderung des letzten Monats in Standardabweichungen aller "
            "Monatsänderungen des gezeigten Zeitraums. Ab etwa ±2 ist die Stufe markiert; bei "
            "Kursen kommen grosse Ausschläge allerdings häufiger vor, als diese Zahl nahelegt. "
            "Welche Reihe hinter welcher steht, ist hinterlegt, nicht gemessen: Ist die "
            "Empfindlichkeit grau, zeigen die Daten des Zeitraums keinen belastbaren Zusammenhang."
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

    earlier = [
        e["change_pct"]
        for e in _episodes(rows, today)
        if e["n"] >= CYCLE_MIN_EPISODE_POINTS
        and e["to"] != rows[-1]["day"]
        and e["change_pct"] is not None
    ]
    return {
        "plain": plain.cycle_sentence(
            universe.label(key), universe.label(chosen), SECTOR_LABELS[today], earlier
        ),
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
