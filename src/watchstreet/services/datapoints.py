"""Datapoints: sourced inputs for the profile schemes."""

from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from watchstreet.models import Datapoint, Stock
from watchstreet.profiles.derive import Point
from watchstreet.profiles.registry import DatapointSpec, get_profile

CONFIDENCE = ("high", "medium", "low")
AGENT_SOURCE_FALLBACK = "agent_knowledge"


class DatapointError(ValueError):
    """Invalid datapoint input."""


@dataclass(frozen=True)
class DatapointInput:
    key: str
    subject: str = ""
    value: float | None = None
    text: str = ""
    unit: str = ""
    source: str = ""
    confidence: str = "medium"
    as_of: date | None = None


def latest(stock: Stock) -> list[Datapoint]:
    """Newest datapoint per (key, subject)."""
    seen: set[tuple[str, str]] = set()
    out: list[Datapoint] = []
    for point in stock.datapoints:  # newest first
        marker = (point.key, point.subject)
        if marker not in seen:
            seen.add(marker)
            out.append(point)
    return out


def as_points(points: list[Datapoint]) -> list[Point]:
    return [Point(p.key, p.subject, p.value, p.text) for p in points]


def validate(stock: Stock, data: DatapointInput) -> DatapointSpec:
    spec = get_profile(stock.profile).spec(data.key)
    if spec is None:
        msg = f"'{data.key}' gehört nicht zum Profil '{stock.profile}'"
        raise DatapointError(msg)
    if spec.per_subject and not data.subject.strip():
        msg = f"'{spec.label}' braucht einen Bezug (z. B. Name der Mine)"
        raise DatapointError(msg)
    if not spec.per_subject and data.subject.strip():
        msg = f"'{spec.label}' gilt für das ganze Unternehmen (kein Bezug)"
        raise DatapointError(msg)
    if spec.textual and not data.text.strip():
        msg = f"'{spec.label}' braucht einen Text"
        raise DatapointError(msg)
    if not spec.textual and data.value is None:
        msg = f"'{spec.label}' braucht eine Zahl"
        raise DatapointError(msg)
    if data.confidence not in CONFIDENCE:
        msg = f"Konfidenz muss eine von {', '.join(CONFIDENCE)} sein"
        raise DatapointError(msg)
    return spec


def is_user_protected(stock: Stock, key: str, subject: str) -> bool:
    current = next((p for p in latest(stock) if (p.key, p.subject) == (key, subject)), None)
    return current is not None and current.origin == "user"


def add_datapoint(
    session: Session,
    stock: Stock,
    data: DatapointInput,
    *,
    origin: str,
    ticket_id: int | None = None,
) -> Datapoint:
    validate(stock, data)
    subject = data.subject.strip()
    if origin == "agent" and is_user_protected(stock, data.key, subject):
        msg = "durch einen Nutzer-Eintrag geschützt"
        raise DatapointError(msg)
    point = Datapoint(
        stock_id=stock.id,
        ticket_id=ticket_id,
        key=data.key,
        subject=subject,
        value=data.value,
        text=data.text.strip(),
        unit=data.unit.strip(),
        source=data.source.strip() or (AGENT_SOURCE_FALLBACK if origin == "agent" else "manuell"),
        confidence=data.confidence,
        origin=origin,
        as_of=data.as_of,
    )
    session.add(point)
    session.flush()
    session.refresh(stock)
    return point
