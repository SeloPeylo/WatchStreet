"""Purchasing-power band: a value over time, measured in five yardsticks at once.

The yardsticks are a declarative table. Every one is a US-dollar price, so dividing a US-dollar
price by it cancels the dollar. Each has a known bias, written next to it; none is treated as the
true one. The calculation itself is in ``analysis/purchasing.py``.
"""

from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from watchstreet.analysis import purchasing as pp
from watchstreet.analysis.macro import Points
from watchstreet.errors import WatchStreetError
from watchstreet.models import PricePoint, SharePrice
from watchstreet.services.charts import SHARE_PREFIX, Universe

DOLLAR = "USD"
DOLLAR_LABEL = "US-Dollar (Bargeld)"
DEFAULT, DEFAULT_LABEL = "GOLDWB", "Gold"
SYNTHETIC_SOURCE = "demo"
POINT_DECIMALS = 2  # points are read to a hundredth of a percent at most


@dataclass(frozen=True)
class Spec:
    key: str  # stored series
    label: str  # column and legend name
    phrase: str  # as it reads after "gemessen in"
    note: str  # what the reader must know about its bias


YARDSTICKS: tuple[Spec, ...] = (
    Spec(
        "CPIAUCSL",
        "Warenkorb",
        "Warenkörben",
        "Verbraucherpreise USA (CPI): was ein Haushalt kauft. Umstritten, weil Qualität und Mieten "
        "geschätzt werden; eher zu niedrig als zu hoch, sagen Kritiker.",
    ),
    Spec(
        "AHETPI",
        "Arbeitsstunde",
        "Arbeitsstunden",
        "Stundenlohn von Arbeitern in den USA. Löhne steigen mit der Produktivität schneller als "
        "der Warenkorb, darum wird in Arbeitsstunden fast alles mit der Zeit billiger.",
    ),
    Spec(
        "M2SL",
        "Geldmenge",
        "Geldmenge M2",
        "Anteil an allen Dollar (M2). Wächst auch mit der Wirtschaft und sprang 2020; wer gegen "
        "die Geldmenge misst, fragt, ob ein Wert mit dem Gelddrucken Schritt hielt.",
    ),
    Spec(
        "GOLDWB",
        "Gold",
        "Gold",
        "Unzen Gold (Monatsmittel der Weltbank). Gold hat ein eigenes Regime: es steigt und fällt "
        "mit Realzins, Angst und Käufen der Notenbanken. Wähle Gold als Wert, um es zu sehen.",
    ),
    Spec(
        "DCOILWTICO",
        "Öl",
        "Öl",
        "Barrel Rohöl WTI: Energie als Grundstoff aller Güter, aber der unruhigste Massstab; "
        "kurzfristig misst er vor allem den Ölmarkt.",
    ),
)
# commodities whose stored weekly prices are replaced here by a long real monthly history
LONG_HISTORY = {
    "gold": "GOLDWB",
    "copper": "PCOPPUSDM",
    "uranium": "PURANUSDM",
    "oil": "DCOILWTICO",
    "gas": "DHHNGSP",
}


class PurchasingError(WatchStreetError):
    """The band cannot be drawn from what is stored."""


def _synthetic(session: Session) -> set[str]:
    """Keys whose stored prices come from the demo provider (two queries, not one per key)."""
    keys = {
        c
        for c, s in session.execute(select(PricePoint.commodity, PricePoint.source).distinct())
        if s == SYNTHETIC_SOURCE
    }
    keys |= {
        SHARE_PREFIX + symbol
        for symbol, s in session.execute(select(SharePrice.symbol, SharePrice.source).distinct())
        if s == SYNTHETIC_SOURCE
    }
    return keys


def _objects(universe: Universe, synthetic: set[str]) -> list[dict[str, Any]]:
    out = [{"key": DOLLAR, "label": DOLLAR_LABEL, "share": False, "synthetic": False}]
    for entry in universe.catalog():
        key = entry["key"]
        if not entry["money"] or key in LONG_HISTORY or not universe.points(key):
            continue
        out.append(
            {
                "key": key,
                "label": entry["label"],
                "share": entry["share"],
                "synthetic": key in synthetic,
            }
        )
    # the dollar, then real series, then synthetic ones, shares last
    return sorted(out, key=lambda o: (o["key"] != DOLLAR, o["share"], o["synthetic"]))


def _subject_points(universe: Universe, key: str) -> Points:
    key = LONG_HISTORY.get(key, key)
    return universe.in_usd(key) if universe.is_share(key) else universe.points(key)


def _start(text: str) -> date | None:
    if not text:
        return None
    try:
        return date.fromisoformat(f"{text[:7]}-01")
    except ValueError as exc:
        raise PurchasingError("Startmonat nicht lesbar (erwartet JJJJ-MM)") from exc


def band(session: Session, key: str, mode: str = pp.CUMULATIVE, start: str = "") -> dict[str, Any]:
    if mode not in pp.MODES:
        raise PurchasingError("Unbekannte Ansicht")
    universe = Universe(session)
    synthetic = _synthetic(session)
    objects = _objects(universe, synthetic)
    key = LONG_HISTORY.get(key, key)
    notice = ""
    if key not in {o["key"] for o in objects}:
        if key:
            known = universe.label(key) if universe.known(key) else key
            notice = f"„{known}“ ist kein Preis in Dollar; gezeigt wird {DEFAULT_LABEL}."
        key = DEFAULT
    subject = None if key == DOLLAR else pp.monthly_means(_subject_points(universe, key))
    used: list[pp.Yardstick] = []
    skipped: list[dict[str, str]] = []
    for spec in YARDSTICKS:
        values = pp.monthly_means(universe.points(spec.key))
        if spec.key == key:
            skipped.append({"label": spec.label, "reason": "ist der Wert selbst (immer 1)"})
        elif not values:
            skipped.append({"label": spec.label, "reason": "keine Werte gespeichert"})
        else:
            used.append(pp.Yardstick(spec.key, spec.label, spec.phrase, values))
    try:
        result = pp.band(subject, used, mode, _start(start))
    except pp.BandError as exc:
        raise PurchasingError(f"Zu wenige gemeinsame Monate für ein Band ({exc})") from exc
    label = DOLLAR_LABEL if key == DOLLAR else universe.label(key)
    subject_info = {"key": key, "label": label, "synthetic": key in synthetic}
    return {**_payload(subject_info, result, used, skipped, objects), "notice": notice}


def _rounded(values: list[float]) -> list[float]:
    return [round(v, POINT_DECIMALS) for v in values]


def _payload(
    subject: dict[str, Any],
    result: pp.Band,
    used: list[pp.Yardstick],
    skipped: list[dict[str, str]],
    objects: list[dict[str, Any]],
) -> dict[str, Any]:
    label = subject["label"]
    info = pp.summarize(result)
    specs = {s.key: s for s in YARDSTICKS}
    plain = pp.sentence(label.split(" (")[0], result, {y.key: y.unit for y in used})
    if subject["synthetic"]:
        plain = (
            f"Achtung: Die Kurse von {label} sind synthetische Demo-Daten; das Band sagt nichts "
            f"über die Wirklichkeit. {plain}"
        )
    return {
        "subject": subject,
        "mode": result.mode,
        "start": result.months[0].isoformat(),
        "end": result.months[-1].isoformat(),
        "first": result.first.isoformat(),
        "months": [m.isoformat() for m in result.months],
        "yardsticks": [
            {
                "key": y.key,
                "label": y.label,
                "phrase": y.unit,
                "note": specs[y.key].note,
                "slot": list(specs).index(y.key),  # colour follows the yardstick, not its rank
            }
            for y in used
        ],
        "skipped": skipped,
        "lines": {k: _rounded(values) for k, values in result.changes.items()},
        "median": _rounded(result.median),
        "low": _rounded(result.low),
        "high": _rounded(result.high),
        "inner_low": _rounded(result.inner_low),
        "inner_high": _rounded(result.inner_high),
        "up": result.up,
        "down": result.down,
        "summary": {
            "verdict": info.verdict,
            "unanimous_share": info.unanimous_share,
            "alone": info.alone,
            "widest_month": info.widest_month.isoformat(),
            "widest_points": info.widest_points,
        },
        "plain": plain,
        "objects": objects,
    }
