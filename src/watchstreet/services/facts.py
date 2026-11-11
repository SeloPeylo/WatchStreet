"""Recording facts under the evidence rules ("no source, no fact")."""

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from watchstreet.domain import ClaimKind, DataOrigin, Provenance
from watchstreet.errors import WatchStreetError
from watchstreet.intel.documents import verify_quote
from watchstreet.metrics import METRICS
from watchstreet.models import Document, Fact
from watchstreet.services.changes import log_change

CONFIDENCES = ("high", "medium", "low")


class FactError(WatchStreetError, ValueError):
    """A fact that violates the evidence rules; it is rejected, never stored."""


@dataclass(frozen=True)
class FactInput:
    subject_type: str
    subject_id: int
    metric_key: str
    value: float | None = None
    low: float | None = None
    high: float | None = None
    text: str = ""
    unit: str = ""
    basis: str = ""
    period_start: date | None = None
    period_end: date | None = None
    published_at: date | None = None
    provenance: str = Provenance.REPORTED
    claim_kind: str = ClaimKind.ACTUAL
    formula_key: str = ""
    inputs: dict[str, Any] = field(default_factory=dict)
    document_id: int | None = None
    quote: str = ""
    confidence: str = "medium"
    origin: str = DataOrigin.USER
    ticket_id: int | None = None
    is_demo: bool = False


def _fail(message: str) -> None:
    raise FactError(message)


def _check_vocabulary(data: FactInput) -> None:
    if data.provenance not in (Provenance.REPORTED, Provenance.DERIVED, Provenance.ESTIMATED):
        _fail("Herkunft muss berichtet, berechnet oder geschätzt sein")
    if data.claim_kind not in tuple(ClaimKind):
        _fail("Unbekannte Aussageart")
    if data.confidence not in CONFIDENCES:
        _fail("Vertrauen muss high, medium oder low sein")


def _check_shape(data: FactInput) -> None:
    metric = METRICS.get(data.metric_key)
    if metric is None:
        _fail(f"Unbekannte Kennzahl: {data.metric_key}")
        return
    if metric.scope != data.subject_type:
        _fail(f"{metric.label} ist keine Kennzahl für dieses Objekt")
    _check_vocabulary(data)
    has_range = data.low is not None and data.high is not None
    if metric.is_text:
        if not data.text.strip():
            _fail("Textkennzahl ohne Text")
    elif data.value is None and not has_range:
        _fail("Weder Wert noch Bandbreite angegeben")
    if has_range and data.low > data.high:  # type: ignore[operator]
        _fail("Bandbreite: Untergrenze liegt über der Obergrenze")
    if metric.is_cost and not data.basis.strip():
        _fail("Kostenkennzahlen brauchen eine Definition (Kostenbegriff, Währung, Zeitraum)")


def _check_provenance(session: Session, data: FactInput) -> str:
    """Returns the confidence to store; raises if the evidence rules are violated."""
    has_range = data.low is not None and data.high is not None
    if data.provenance == Provenance.DERIVED and not data.formula_key:
        _fail("Berechnete Werte brauchen eine Formel")
    if data.provenance == Provenance.ESTIMATED and not (has_range and data.basis.strip()):
        _fail("Schätzungen brauchen eine Bandbreite und eine benannte Methode")
    if data.quote or data.document_id is not None:
        document = session.get(Document, data.document_id) if data.document_id else None
        if document is None:
            _fail("Zitat ohne gespeichertes Dokument")
        elif not verify_quote(document, data.quote):
            _fail("Das Zitat steht nicht wörtlich im Dokument")
        return data.confidence
    if data.provenance == Provenance.REPORTED and data.origin != DataOrigin.USER:
        _fail("Berichtete Werte brauchen Dokument und wörtliches Zitat")
    if data.origin == DataOrigin.AGENT:
        return "low"  # an agent claim without document never ranks above low
    return data.confidence


def current_fact(
    session: Session, subject_type: str, subject_id: int, metric_key: str, period_end: date | None
) -> Fact | None:
    query = select(Fact).where(
        Fact.subject_type == subject_type,
        Fact.subject_id == subject_id,
        Fact.metric_key == metric_key,
        Fact.superseded_by.is_(None),
    )
    query = (
        query.where(Fact.period_end.is_(None))
        if period_end is None
        else query.where(Fact.period_end == period_end)
    )
    return session.scalars(query.order_by(Fact.id.desc())).first()


GERMAN_NUMBER = str.maketrans({",": ".", ".": ","})


def _number(value: float) -> str:
    """1234567.5 -> '1.234.567,5' (German grouping, no exponent)."""
    return f"{value:,.10g}".translate(GERMAN_NUMBER)


def display_value(fact: Fact) -> str:
    if fact.value is not None:
        return f"{_number(fact.value)} {fact.unit}".strip()
    if fact.value_low is not None and fact.value_high is not None:
        return f"{_number(fact.value_low)}–{_number(fact.value_high)} {fact.unit}".strip()
    return fact.text


def record_fact(session: Session, data: FactInput) -> Fact:
    """Validate and append a fact; the previous value for the same period is superseded."""
    _check_shape(data)
    confidence = _check_provenance(session, data)
    previous = current_fact(
        session, data.subject_type, data.subject_id, data.metric_key, data.period_end
    )
    if previous and previous.origin == DataOrigin.USER and data.origin != DataOrigin.USER:
        _fail("Ein Nutzereintrag wird nicht überschrieben")
    fact = Fact(
        subject_type=data.subject_type,
        subject_id=data.subject_id,
        metric_key=data.metric_key,
        value=data.value,
        value_low=data.low,
        value_high=data.high,
        text=data.text.strip(),
        unit=data.unit,
        basis=data.basis.strip(),
        period_start=data.period_start,
        period_end=data.period_end,
        published_at=data.published_at,
        provenance=data.provenance,
        claim_kind=data.claim_kind,
        formula_key=data.formula_key,
        inputs=data.inputs,
        document_id=data.document_id,
        quote=data.quote,
        confidence=confidence,
        origin=data.origin,
        ticket_id=data.ticket_id,
        is_demo=data.is_demo,
    )
    session.add(fact)
    session.flush()
    if previous:
        previous.superseded_by = fact.id
    log_change(
        session,
        data.subject_type,
        data.subject_id,
        "fact",
        f"{METRICS[data.metric_key].label}: {display_value(fact)}",
        old=display_value(previous) if previous else "",
        new=display_value(fact),
    )
    return fact


def fact_history(
    session: Session, subject_type: str, subject_id: int, metric_key: str
) -> list[Fact]:
    return list(
        session.scalars(
            select(Fact)
            .where(
                Fact.subject_type == subject_type,
                Fact.subject_id == subject_id,
                Fact.metric_key == metric_key,
            )
            .order_by(Fact.id.desc())
        )
    )
