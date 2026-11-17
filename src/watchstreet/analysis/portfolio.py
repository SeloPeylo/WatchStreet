"""Exit checks and the monthly depot summary (pure: plain data in, plain data out)."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from watchstreet.constants import MONTHS_DE, PORTFOLIO_REVIEW_DAYS


@dataclass(frozen=True)
class JournalEntry:
    """One line of the decision journal as the summary needs it."""

    id: int
    day: date
    symbol: str
    kind: str
    reason: str


@dataclass(frozen=True)
class PositionCheck:
    """A holding with what is needed to judge it today."""

    id: int
    symbol: str
    name: str
    last_logged: date  # newest journal day of the stock, else the day the position was entered
    breaches: tuple[str, ...]  # exit thresholds crossed today, as texts for the user


@dataclass(frozen=True)
class MonthSummary:
    year: int
    month: int
    review_days: int  # how long a position may go without a logged decision
    sentence: str
    decisions: tuple[JournalEntry, ...]  # this calendar month, newest first
    exits: tuple[PositionCheck, ...]  # positions whose exit threshold is crossed
    unreviewed: tuple[PositionCheck, ...]  # no logged decision for more than the review period


def exit_breaches(
    price: float | None,
    stop_price: float | None,
    runway: float | None,
    min_runway_months: float | None,
) -> list[str]:
    """The exit thresholds the user set that today's data has crossed. Missing data never counts."""
    breaches: list[str] = []
    if stop_price and price is not None and price <= stop_price:
        breaches.append(f"Kurs {price:g} liegt auf oder unter deiner Schwelle {stop_price:g}")
    if min_runway_months and runway is not None and runway < min_runway_months:
        breaches.append(
            f"Reichweite rund {runway:.0f} Monate liegt unter deiner Schwelle {min_runway_months:g}"
        )
    return breaches


def _counted(count: int, zero: str, one: str, many: str) -> str:
    if count == 0:
        return zero
    if count == 1:
        return one
    return many.format(count)


def _sentence(today: date, decisions: int, exits: int, unreviewed: int) -> str:
    parts = (
        _counted(decisions, "keine Entscheidung", "1 Entscheidung", "{} Entscheidungen"),
        _counted(
            exits,
            "keine Position verletzt ihre Ausstiegsbedingung",
            "1 Position verletzt ihre Ausstiegsbedingung",
            "{} Positionen verletzen ihre Ausstiegsbedingung",
        ),
        _counted(
            unreviewed,
            f"keine Position seit über {PORTFOLIO_REVIEW_DAYS} Tagen ungeprüft",
            f"1 Position seit über {PORTFOLIO_REVIEW_DAYS} Tagen ungeprüft",
            f"{{}} Positionen seit über {PORTFOLIO_REVIEW_DAYS} Tagen ungeprüft",
        ),
    )
    return f"Im {MONTHS_DE[today.month - 1]}: {', '.join(parts)}."


def month_summary(
    today: date, journal: Sequence[JournalEntry], positions: Sequence[PositionCheck]
) -> MonthSummary:
    """What happened this calendar month and which positions need a look, from stored data only."""
    this_month = sorted(
        (e for e in journal if (e.day.year, e.day.month) == (today.year, today.month)),
        key=lambda e: (e.day, e.id),
        reverse=True,
    )
    exits = tuple(p for p in positions if p.breaches)
    unreviewed = tuple(p for p in positions if (today - p.last_logged).days > PORTFOLIO_REVIEW_DAYS)
    return MonthSummary(
        year=today.year,
        month=today.month,
        review_days=PORTFOLIO_REVIEW_DAYS,
        sentence=_sentence(today, len(this_month), len(exits), len(unreviewed)),
        decisions=tuple(this_month),
        exits=exits,
        unreviewed=unreviewed,
    )
