"""Plain-language sentences for charts, built from the numbers of the chart.

Pure: numbers and labels in, German text out. A sentence states only what the numbers support;
a missing or weak result is said so, and nothing here advises to buy or sell.
"""

import math
from collections.abc import Sequence
from datetime import date

from watchstreet.constants import (
    CYCLE_FEW_EPISODES,
    DAYS_PER_YEAR,
    MONTHS_PER_YEAR,
    PERCENT,
    PLAIN_FLAT_PCT,
    PLAIN_SIGNIFICANT,
    PLAIN_WHOLE_FROM,
    SPAN_MONTHS_AS_YEARS,
    WEAK_R2,
)

MINUS = "−"
WEAK = "Der Zusammenhang ist schwach – nicht als Regel verwenden."


def amount(value: float) -> str:
    """A figure rounded for reading, German decimal comma, with a minus sign if negative."""
    size = abs(value)
    if size >= PLAIN_WHOLE_FROM:
        text = f"{size:.0f}"
    elif size >= 1:
        text = f"{size:.1f}"
    elif size == 0:
        text = "0"
    else:
        digits = PLAIN_SIGNIFICANT - 1 - math.floor(math.log10(size))
        text = f"{size:.{digits}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    text = text.replace(".", ",")
    return f"{MINUS}{text}" if value < 0 and text != "0" else text


def signed(value: float) -> str:
    return f"+{amount(value)}" if value > 0 else amount(value)


def when(day: date) -> str:
    return day.strftime("%d.%m.%Y")


def span_text(days: float) -> str:
    """A time span in the dative, as after "in": "einem Jahr", "11 Monaten", "3 Jahren"."""
    months = round(days / (DAYS_PER_YEAR / MONTHS_PER_YEAR))
    if months < 1:
        return f"{max(round(days), 1)} Tagen"
    if months == 1:
        return "einem Monat"
    if months == MONTHS_PER_YEAR:
        return "einem Jahr"
    if months < SPAN_MONTHS_AS_YEARS:
        return f"{months} Monaten"
    return f"{amount(months / MONTHS_PER_YEAR)} Jahren"


def _join(parts: Sequence[str]) -> str:
    return parts[0] if len(parts) == 1 else f"{', '.join(parts[:-1])} und {parts[-1]}"


def _moved(change: float, up: str = "stieg", down: str = "fiel") -> str:
    return up if change >= 0 else down


def currency_name(code: str) -> str:
    return "US-Dollar" if code == "USD" else code


def chain_sentence(
    label: str, currency: str, days: float, total_pct: float, parts: Sequence[tuple[str, float]]
) -> str:
    """Change of a price and what each link of the lever chain contributed (points ~ percent)."""
    where = currency_name(currency)
    if abs(total_pct) < PLAIN_FLAT_PCT:
        first = f"{label} blieb in {span_text(days)} in {where} praktisch unverändert."
    else:
        first = (
            f"{label} {_moved(total_pct)} in {span_text(days)} um {amount(abs(total_pct))} % "
            f"in {where}."
        )
    if not parts:
        return first
    texts = [
        f"{signed(points)} Punkte aus „{name}“" if i == 0 else f"{signed(points)} aus „{name}“"
        for i, (name, points) in enumerate(parts)
    ]
    return f"{first} Davon kamen {_join(texts)} (Punkte entsprechen etwa Prozent)."


def ladder_sentence(  # noqa: PLR0913 - the numbers of one fit
    subject: str,
    driver: str,
    *,
    beta: float,
    r2: float,
    weak: bool,
    relative_target: bool,
    relative_driver: bool,
) -> str:
    """What the fitted sensitivity of a subject to one driver means, in a sentence or two."""
    share = amount(r2 * PERCENT)
    if weak or r2 < WEAK_R2:
        return (
            f"Zwischen {subject} und {driver} zeigt sich in diesem Zeitraum kein verlässlicher "
            f"Zusammenhang: Das erklärt nur {share} % der Bewegung. {WEAK}"
        )
    step = "1 %" if relative_driver else "1 Prozentpunkt"
    size = f"{amount(abs(beta))} {'%' if relative_target else 'Prozentpunkte'}"
    return (
        f"Stieg {driver} um {step}, dann {_moved(beta)} {subject} in diesem Zeitraum im Schnitt "
        f"um {size}. Das erklärt {share} % der Bewegung."
    )


def missing_sentence(subject: str, driver: str | None) -> str:
    if not driver:
        return f"Für {subject} ist kein Treiber hinterlegt – es gibt nichts zum Vergleichen."
    return (
        f"Für {subject} gegen {driver} gibt es in diesem Zeitraum zu wenige gemeinsame Werte "
        "für eine Aussage."
    )


def joint_sentence(
    subject: str,
    drivers: Sequence[str],
    contributions: Sequence[float],
    own: float,
    r2: float,
    unit: str,
) -> str:
    """What several drivers together explain, and which one carried most of it."""
    share = amount(r2 * PERCENT)
    if r2 < WEAK_R2:
        return (
            f"Alle {len(drivers)} Treiber zusammen erklären nur {share} % der Bewegung von "
            f"{subject}. {WEAK}"
        )
    top = max(range(len(drivers)), key=lambda i: abs(contributions[i]))
    return (
        f"Zusammen erklären {_join(list(drivers))} {share} % der Bewegung von {subject}. "
        f"Den grössten Anteil hatte {drivers[top]} ({signed(contributions[top])} {unit}); "
        f"der Eigenanteil liegt bei {signed(own)} {unit}."
    )


def lens_sentence(
    title: str, unit: str, first: tuple[date, float] | None, last: tuple[date, float] | None
) -> str:
    """Where a formula stands now compared with the start of its series."""
    if first is None or last is None or first[0] == last[0]:
        return (
            f"Die Formel „{title}“ liefert in den gespeicherten Daten zu wenige gemeinsame Werte "
            "für eine Aussage."
        )
    now = f"{amount(last[1])} {unit}".strip()
    text = (
        f"„{title}“ steht zuletzt bei {now} ({when(last[0])}); am Anfang ({when(first[0])}) "
        f"waren es {amount(first[1])}."
    )
    if first[1] > 0 and last[1] > 0:
        change = (last[1] / first[1] - 1) * PERCENT
        text += f" Das entspricht einer Änderung von {signed(change)} %."
    return text


def grid_sentence(grid: str, coarse: Sequence[str]) -> str:
    """Why a formula was computed on weekly or monthly means ('' if nothing was averaged)."""
    word = {"monthly": ("Monatsmitteln", "monatlich"), "weekly": ("Wochenmitteln", "wöchentlich")}
    if grid not in word or not coarse:
        return ""
    names = _join([f"„{name}“" for name in coarse])
    verb = "erscheint" if len(coarse) == 1 else "erscheinen"
    return f"Gerechnet auf {word[grid][0]}, weil {names} nur {word[grid][1]} {verb}."


def matrix_sentence(rows: Sequence[tuple[str, float | None, float | None]]) -> str:
    """Example from the first row with a one-year change in dollars and in gold."""
    head = "Die Zahl in einer Zelle ist die Änderung der letzten 12 Monate in diesem Massstab."
    for label, usd, gold in rows:
        if usd is not None and gold is not None:
            return (
                f"{head} Beispiel: {label} {_moved(usd)} um {amount(abs(usd))} % in US-Dollar "
                f"und {_moved(gold)} um {amount(abs(gold))} % gemessen in Gold."
            )
    return f"{head} Für einen Vergleich in Dollar und Gold fehlen noch genug Kursdaten."


def regime_sentence(
    x: tuple[str, str, float, float],
    y: tuple[str, str, float, float],
    start: date,
    decisions: int,
) -> str:
    """Start and end of both axes, as (label, unit, first, last), and the decisions on the path."""
    parts = [
        f"{label} {_moved(last - first, 'stieg', 'fiel')} von {amount(first)} auf {amount(last)} "
        f"{unit}"
        for label, unit, first, last in (x, y)
    ]
    first = f"Seit {when(start)} {parts[0]}, {parts[1]}."
    if decisions:
        return f"{first} {decisions} Einträge deines Entscheidungsprotokolls liegen auf diesem Weg."
    return f"{first} Auf diesem Weg liegt kein Eintrag deines Entscheidungsprotokolls."


def sheet_sentence(steps: int, rare: Sequence[tuple[str, float, str]], *, measured: int) -> str:
    """Which rung moved unusually in the last month (``rare``: label, move, unit of the move)."""
    if measured == 0:
        return "Für diese Leiter liegen zu wenige Werte vor, um die letzte Bewegung einzuordnen."
    if not rare:
        return (
            f"Keine der {steps} Stufen hat sich im letzten Monat ungewöhnlich stark bewegt; "
            "alles liegt im üblichen Rahmen des Zeitraums."
        )
    texts = [f"{label} ({signed(move)} {unit})" for label, move, unit in rare]
    return (
        f"Ungewöhnlich stark bewegt hat sich im letzten Monat: {_join(texts)}. "
        "Die übrigen Stufen liegen im üblichen Rahmen des Zeitraums."
    )


def cycle_sentence(subject: str, driver: str, phase: str, changes: Sequence[float]) -> str:
    """Today's phase of the driver and what the subject did in earlier stretches in that phase."""
    now = f"{driver} steht heute in der Phase „{phase}“."
    if not changes:
        return f"{now} Es gibt keinen früheren Zeitraum in dieser Phase zum Vergleichen."
    mean = sum(changes) / len(changes)
    text = (
        f"{now} In {len(changes)} früheren Zeiträumen in dieser Phase {_moved(mean)} {subject} "
        f"im Schnitt um {amount(abs(mean))} %."
    )
    if len(changes) < CYCLE_FEW_EPISODES:
        return f"{text} Das sind zu wenige Zeiträume für irgendeine Regel."
    return f"{text} Das ist Rückschau, keine Vorhersage."
