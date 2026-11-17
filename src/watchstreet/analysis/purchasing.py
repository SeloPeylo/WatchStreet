"""Purchasing-power band: one value measured against several yardsticks over time.

Pure: series in, numbers and German sentences out. Every line is a ratio of two US-dollar
prices, so the dollar cancels; what is left is "how many baskets, working hours, shares of the
money stock, ounces of gold or barrels of oil" the value was worth. No yardstick is called right:
the band shows where they agree and where the verdict depends on the yardstick. Nothing is fitted,
smoothed or filled in; a month counts only if the value and every yardstick have one.
"""

import math
import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from watchstreet.analysis.plain import signed
from watchstreet.constants import (
    MONTHS_DE,
    MONTHS_PER_YEAR,
    PERCENT,
    PP_FLAT_POINTS,
    PP_INNER_FROM,
    PP_MIN_MONTHS,
    PP_ROLLING_MONTHS,
)

Monthly = dict[date, float]
CUMULATIVE = "since"
ROLLING = "rolling"
MODES = (CUMULATIVE, ROLLING)
ALL_UP, MOST_UP, SPLIT, MOST_DOWN, ALL_DOWN = "all_up", "most_up", "split", "most_down", "all_down"


class BandError(ValueError):
    """Too few shared months to draw a band."""


@dataclass(frozen=True)
class Yardstick:
    key: str
    label: str  # "Warenkorb"
    unit: str  # what one unit of the value is counted in: "Warenkörbe"
    values: Monthly


@dataclass(frozen=True)
class Band:
    mode: str
    months: list[date]
    keys: list[str]  # yardsticks used, in table order
    changes: dict[str, list[float]]  # points (100 × log change) per yardstick and month
    median: list[float]
    low: list[float]
    high: list[float]
    inner_low: list[float]  # without the most extreme yardstick at each end
    inner_high: list[float]
    up: list[int]  # yardsticks that show a gain beyond PP_FLAT_POINTS
    down: list[int]
    first: date  # first month in which the value and every yardstick have a value


def month_of(day: date) -> date:
    return day.replace(day=1)


def monthly_means(points: Sequence[tuple[date, float]]) -> Monthly:
    """Mean of the observations of each calendar month, keyed by its first day."""
    sums: dict[date, list[float]] = {}
    for day, value in points:
        sums.setdefault(month_of(day), []).append(value)
    return {month: sum(values) / len(values) for month, values in sorted(sums.items())}


def shift_months(month: date, months: int) -> date:
    index = month.year * MONTHS_PER_YEAR + month.month - 1 + months
    return date(index // MONTHS_PER_YEAR, index % MONTHS_PER_YEAR + 1, 1)


def to_pct(points: float) -> float:
    """Points (100 × log change) as an ordinary percentage change."""
    return (math.exp(points / PERCENT) - 1) * PERCENT


def verdict(up: int, down: int, count: int) -> str:
    if up == count:
        return ALL_UP
    if down == count:
        return ALL_DOWN
    if up * 2 > count:
        return MOST_UP
    if down * 2 > count:
        return MOST_DOWN
    return SPLIT


def _measured(subject: Monthly | None, yardstick: Yardstick, month: date) -> float:
    """Log of the value in units of the yardstick; ``None`` as subject is one US dollar."""
    top = 1.0 if subject is None else subject[month]
    return math.log(top / yardstick.values[month])


def _months(subject: Monthly | None, yardsticks: Sequence[Yardstick]) -> list[date]:
    shared = set.intersection(*(set(y.values) for y in yardsticks))
    if subject is not None:
        shared &= set(subject)
    usable = {m for m in shared if all(y.values[m] > 0 for y in yardsticks)}
    if subject is not None:
        usable = {m for m in usable if subject[m] > 0}
    return sorted(usable)


def band(
    subject: Monthly | None,
    yardsticks: Sequence[Yardstick],
    mode: str = CUMULATIVE,
    start: date | None = None,
) -> Band:
    """Change of ``subject`` in every yardstick, since ``start`` or over the previous 12 months."""
    if not yardsticks:
        raise BandError("Kein Massstab")
    common = _months(subject, yardsticks)
    pairs: list[tuple[date, date]]
    if mode == CUMULATIVE:
        begin = next((m for m in common if start is None or m >= month_of(start)), None)
        pairs = [(begin, m) for m in common if begin is not None and m >= begin]
    else:
        present = set(common)
        before = {m: shift_months(m, -PP_ROLLING_MONTHS) for m in common}
        first = month_of(start) if start else date.min
        pairs = [(before[m], m) for m in common if before[m] in present and m >= first]
    if len(pairs) < PP_MIN_MONTHS:
        raise BandError(f"Nur {len(pairs)} gemeinsame Monate")
    changes = {
        y.key: [
            PERCENT * (_measured(subject, y, end) - _measured(subject, y, base))
            for base, end in pairs
        ]
        for y in yardsticks
    }
    columns = [sorted(changes[y.key][i] for y in yardsticks) for i in range(len(pairs))]
    trim = 1 if len(yardsticks) >= PP_INNER_FROM else 0
    return Band(
        mode=mode,
        months=[end for _, end in pairs],
        keys=[y.key for y in yardsticks],
        changes=changes,
        median=[statistics.median(c) for c in columns],
        low=[c[0] for c in columns],
        high=[c[-1] for c in columns],
        inner_low=[c[trim] for c in columns],
        inner_high=[c[-1 - trim] for c in columns],
        up=[sum(v > PP_FLAT_POINTS for v in c) for c in columns],
        down=[sum(v < -PP_FLAT_POINTS for v in c) for c in columns],
        first=common[0],
    )


@dataclass(frozen=True)
class Summary:
    verdict: str  # of the last month
    last: dict[str, float]  # points per yardstick, last month
    unanimous_share: float  # share of months in which every yardstick gave the same direction
    alone: dict[str, int]  # months in which this yardstick alone disagreed with all others
    widest_month: date
    widest_points: float  # distance between the highest and lowest yardstick that month


def _alone(result: Band, key: str, i: int) -> bool:
    """Every other yardstick moved the same way beyond the flat zone, this one did not."""
    others = [result.changes[k][i] for k in result.keys if k != key]
    own = result.changes[key][i]
    if all(v > PP_FLAT_POINTS for v in others):
        return own <= PP_FLAT_POINTS
    return all(v < -PP_FLAT_POINTS for v in others) and own >= -PP_FLAT_POINTS


def summarize(result: Band) -> Summary:
    count = len(result.keys)
    measured = range(1 if result.mode == CUMULATIVE else 0, len(result.months))
    verdicts = [verdict(result.up[i], result.down[i], count) for i in measured]
    alone = dict.fromkeys(result.keys, 0)
    for i in measured:
        for key in result.keys:
            if _alone(result, key, i):
                alone[key] += 1
    widths = [result.high[i] - result.low[i] for i in range(len(result.months))]
    widest = max(range(len(widths)), key=widths.__getitem__)
    return Summary(
        verdict=verdict(result.up[-1], result.down[-1], count),
        last={key: result.changes[key][-1] for key in result.keys},
        unanimous_share=sum(v in (ALL_UP, ALL_DOWN) for v in verdicts) / max(len(verdicts), 1),
        alone=alone,
        widest_month=result.months[widest],
        widest_points=widths[widest],
    )


def month_text(month: date) -> str:
    return f"{MONTHS_DE[month.month - 1]} {month.year}"


def _pct(points: float) -> str:
    return f"{signed(to_pct(points))} %"


def _names(keys: Sequence[str], labels: dict[str, str]) -> str:
    names = [labels[k] for k in keys]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " und " + names[-1]


def _first(subject: str, head: str, result: Band, info: Summary, labels: dict[str, str]) -> str:
    count = len(result.keys)
    gained = [k for k in result.keys if info.last[k] > PP_FLAT_POINTS]
    lost = [k for k in result.keys if info.last[k] < -PP_FLAT_POINTS]
    flat = [k for k in result.keys if k not in gained and k not in lost]
    if info.verdict in (ALL_UP, ALL_DOWN):
        verb = "gewann" if info.verdict == ALL_UP else "verlor"
        span = f"{_pct(result.low[-1])} bis {_pct(result.high[-1])}"
        return f"{head} {verb} {subject} nach allen {count} Massstäben an Kaufkraft ({span})."
    if info.verdict == SPLIT:
        return (
            f"{head} hängt das Urteil über {subject} am Massstab: gewonnen in "
            f"{_names(gained, labels) if gained else 'keinem'}, verloren in "
            f"{_names(lost, labels) if lost else 'keinem'}."
        )
    up = info.verdict == MOST_UP
    majority, minority = (gained, lost) if up else (lost, gained)
    text = (
        f"{head} {'gewann' if up else 'verlor'} {subject} nach {len(majority)} von {count} "
        f"Massstäben an Kaufkraft (Mitte {_pct(result.median[-1])})"
    )
    if minority:
        other = ", ".join(f"in {labels[k]} {_pct(info.last[k])}" for k in minority)
        text += f"; dagegen gemessen {other}"
    if flat:
        text += f"; kaum verändert gemessen in {_names(flat, labels)}"
    return text + "."


def sentence(subject: str, result: Band, labels: dict[str, str]) -> str:
    """What the band says in two sentences, from its own numbers.

    ``labels`` name each yardstick as it reads after "gemessen in" ("Warenkörben", "Gold").
    """
    info = summarize(result)
    if result.mode == CUMULATIVE:
        head = f"Seit {month_text(result.months[0])}"
    else:
        head = f"In den {PP_ROLLING_MONTHS} Monaten bis {month_text(result.months[-1])}"
    share = round(info.unanimous_share * PERCENT)
    second = f" In {share} % der Monate waren sich alle Massstäbe in der Richtung einig"
    loner = max(result.keys, key=lambda k: info.alone[k])
    if info.alone[loner] > 0:
        second += (
            f"; sonst wich am häufigsten allein die Messung in {labels[loner]} ab "
            f"({info.alone[loner]} Monate)"
        )
    return _first(subject, head, result, info, labels) + second + "."
