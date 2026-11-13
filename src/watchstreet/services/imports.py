"""Importing an analysis: everything it says becomes visible at once, marked as unverified.

An imported figure never replaces a figure from a primary source or a user entry; it only fills
gaps or updates an earlier import. Verification later replaces it with a sourced value.
"""

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from watchstreet.analysis.imports import ImportRow, number, status_of
from watchstreet.commodities import BY_KEY, COMMODITIES
from watchstreet.constants import (
    IMPORT_TOLERANCE,
    MAX_LAT,
    MAX_LON,
    MIN_REASON_CHARS,
    PERCENT,
    USER_CONFIRMED,
)
from watchstreet.domain import (
    AssetKind,
    DataOrigin,
    Epistemic,
    FindingKind,
    StakeRole,
    SubjectType,
)
from watchstreet.intel.documents import content_hash, store_document, verify_quote
from watchstreet.metrics import METRICS
from watchstreet.models import (
    Asset,
    AssetCommodity,
    Company,
    Document,
    DocumentLink,
    Fact,
    Finding,
    Stake,
    StatusPeriod,
)
from watchstreet.services.changes import log_change
from watchstreet.services.facts import FactError, FactInput, display_value, record_fact
from watchstreet.services.registry import company_by_name, slug
from watchstreet.services.world import metric_unit
from watchstreet.timeutil import utcnow

ANALYSIS_KIND = "analysis"
HASH_CHARS = 16
COMMODITY_BY_LABEL = {c.label.lower(): c.key for c in COMMODITIES}
IMPORT_BASIS = "laut importierter Analyse, Definition ungeprüft"


@dataclass
class ImportOutcome:
    rows: int = 0
    created: int = 0
    matched: int = 0
    facts: int = 0
    unchanged: int = 0
    conflicts: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    asset_ids: list[int] = field(default_factory=list)
    fact_ids: list[int] = field(default_factory=list)


def store_analysis(session: Session, title: str, publisher: str, text: str) -> Document:
    document, _created = store_document(
        session,
        url=f"import:{content_hash(text)[:HASH_CHARS]}",
        text=text,
        kind=ANALYSIS_KIND,
        publisher=publisher.strip() or "eigene Analyse",
        title=title.strip() or "Importierte Analyse",
    )
    return document


def _commodity(raw: str) -> str | None:
    key = raw.strip().lower()
    return key if key in BY_KEY else COMMODITY_BY_LABEL.get(key)


def _create_asset(session: Session, row: ImportRow, document: Document) -> Asset | str:
    """A new asset needs a place and a commodity; otherwise the reason it was skipped."""
    fields = row.fields
    lat, lon = number(fields.get("lat", "")), number(fields.get("lon", ""))
    commodity = _commodity(fields.get("commodity", ""))
    if lat is None or lon is None or abs(lat) > MAX_LAT or abs(lon) > MAX_LON:
        return "unbekanntes Objekt ohne gültige Koordinaten (lat, lon)"
    if commodity is None:
        return "unbekanntes Objekt ohne erfassten Rohstoff (gold, silver, copper, uranium)"
    asset = Asset(
        slug=f"{slug(fields['name'])}-import-{document.id}",
        name=fields["name"],
        kind=AssetKind.DEPOSIT,
        lat=lat,
        lon=lon,
        country=fields.get("country", ""),
        region=fields.get("region", ""),
        summary="Aus einer importierten Analyse übernommen; Angaben sind ungeprüft.",
    )
    session.add(asset)
    session.flush()
    session.add(AssetCommodity(asset_id=asset.id, commodity=commodity, role="primary"))
    status = status_of(fields.get("status", ""))
    if status is not None:
        session.add(
            StatusPeriod(
                asset_id=asset.id, status=status, valid_from=utcnow().date(),
                document_id=document.id, quote=row.line,
            )
        )  # fmt: skip
    session.flush()
    session.refresh(asset)
    log_change(
        session, SubjectType.ASSET, asset.id, "import", f"Aus Analyse übernommen: {asset.name}"
    )
    return asset


def _link(session: Session, document: Document, asset: Asset) -> None:
    exists = session.scalars(
        select(DocumentLink.id).where(
            DocumentLink.document_id == document.id,
            DocumentLink.subject_type == SubjectType.ASSET,
            DocumentLink.subject_id == asset.id,
        )
    ).first()
    if not exists:
        session.add(
            DocumentLink(
                document_id=document.id, subject_type=SubjectType.ASSET, subject_id=asset.id
            )
        )


def _stake(session: Session, row: ImportRow, document: Document, asset: Asset) -> None:
    name = row.fields.get("company", "")
    if not name:
        return
    company = company_by_name(session, name)
    held = session.scalars(
        select(Stake.id).where(Stake.asset_id == asset.id, Stake.company_id == company.id)
    ).first()
    if held:
        return
    share = number(row.fields.get("share", ""))
    session.add(
        Stake(
            asset_id=asset.id, company_id=company.id,
            role=StakeRole.OWNER if share is not None else StakeRole.OPERATOR,
            share_pct=share if share is not None and 0 < share <= PERCENT else None,
            document_id=document.id, quote=row.line,
        )
    )  # fmt: skip


def current_any(session: Session, subject_type: str, subject_id: int, metric: str) -> Fact | None:
    """The newest fact that still stands for a metric, whatever period it reports."""
    return session.scalars(
        select(Fact)
        .where(
            Fact.subject_type == subject_type,
            Fact.subject_id == subject_id,
            Fact.metric_key == metric,
            Fact.superseded_by.is_(None),
        )
        .order_by(Fact.id.desc())
    ).first()


def agrees(old: Fact, value: float | None, text: str) -> bool:
    if value is None or old.value is None:
        return old.text.strip().lower() == text.strip().lower()
    return abs(old.value - value) <= IMPORT_TOLERANCE * max(abs(old.value), abs(value))


def _fact(  # noqa: PLR0913, PLR0917
    session: Session,
    row: ImportRow,
    document: Document,
    asset: Asset | Company,
    metric_key: str,
    outcome: ImportOutcome,
    ticket_id: int | None,
) -> None:
    metric = METRICS[metric_key]
    kind = SubjectType.COMPANY if isinstance(asset, Company) else SubjectType.ASSET
    raw = row.fields[metric_key]
    value = None if metric.is_text else number(raw)
    label = f"{asset.name}, {metric.label}"
    if not metric.is_text and value is None:
        outcome.skipped.append(f"{label}: „{raw}“ ist keine Zahl")
        return
    if value is not None and (value <= 0 or (metric.unit == "%" and value > PERCENT)):
        outcome.skipped.append(f"{label}: {raw} ist nicht plausibel (muss positiv sein, % ≤ 100)")
        return
    current = current_any(session, kind, asset.id, metric_key)
    if current is not None and agrees(current, value, raw):
        outcome.unchanged += 1
        return
    if current is not None and current.origin != DataOrigin.IMPORT:
        outcome.conflicts.append(
            f"{label}: Analyse nennt {raw}, vorhanden ist {display_value(current)} – "
            "nicht überschrieben"
        )
        # the disagreement stays at the asset: how often a source is wrong is what matters about it
        session.add(
            Finding(
                subject_type=kind, subject_id=asset.id, kind=FindingKind.ANOMALY,
                epistemic=Epistemic.UNRESOLVED,
                text=f"„{document.title}“ ({document.publisher}) nennt für {metric.label} {raw}; "
                f"vorhanden ist {display_value(current)}.",
                uncertainty="Die importierte Angabe wurde nicht übernommen.",
            )
        )  # fmt: skip
        return
    try:
        fact = record_fact(
            session,
            FactInput(
                kind, asset.id, metric_key,
                value=value, text=raw if metric.is_text else "",
                unit=metric_unit(asset, metric_key),
                basis=IMPORT_BASIS if metric.is_cost else "",
                document_id=document.id, quote=row.line, confidence="low",
                origin=DataOrigin.IMPORT, ticket_id=ticket_id,
            ),
        )  # fmt: skip
    except FactError as exc:
        outcome.skipped.append(f"{label}: {exc}")
        return
    outcome.facts += 1
    outcome.fact_ids.append(fact.id)


def _company_figures(
    session: Session,
    row: ImportRow,
    document: Document,
    outcome: ImportOutcome,
    ticket_id: int | None,
) -> None:
    """Cash, debt, share count and the like belong to the company named in the row."""
    keys = [k for k in row.fields if k in METRICS and METRICS[k].scope == SubjectType.COMPANY]
    if not keys:
        return
    if not row.fields.get("company"):
        outcome.skipped.append("Unternehmenszahlen ohne Spalte „company“")
        return
    company = company_by_name(session, row.fields["company"])
    linked = session.scalars(
        select(DocumentLink.id).where(
            DocumentLink.document_id == document.id,
            DocumentLink.subject_type == SubjectType.COMPANY,
            DocumentLink.subject_id == company.id,
        )
    ).first()
    if not linked:
        session.add(
            DocumentLink(
                document_id=document.id, subject_type=SubjectType.COMPANY, subject_id=company.id
            )
        )
    for key in keys:
        _fact(session, row, document, company, key, outcome, ticket_id)


def apply_rows(
    session: Session, document: Document, rows: list[ImportRow], ticket_id: int | None = None
) -> ImportOutcome:
    """Create or match the assets of an analysis and record its figures as unverified facts."""
    outcome = ImportOutcome(rows=len(rows))
    by_slug = {slug(a.name): a for a in session.scalars(select(Asset))}
    for row in rows:
        name = row.fields.get("name") or row.fields["company"]
        if not verify_quote(document, row.line):
            outcome.skipped.append(
                f"{name}: Zeile ist kürzer als 20 Zeichen (zu kurz als Beleg) oder steht "
                "nicht wörtlich im Dokument"
            )
            continue
        _company_figures(session, row, document, outcome, ticket_id)
        if "name" not in row.fields:
            continue  # a row about the company only
        asset = by_slug.get(slug(name))
        if asset is None:
            made = _create_asset(session, row, document)
            if isinstance(made, str):
                outcome.skipped.append(f"{name}: {made}")
                continue
            asset = by_slug[slug(name)] = made
            outcome.created += 1
        else:
            outcome.matched += 1
        outcome.asset_ids.append(asset.id)
        _link(session, document, asset)
        _stake(session, row, document, asset)
        for metric_key in row.fields:
            if metric_key in METRICS and METRICS[metric_key].scope == SubjectType.ASSET:
                _fact(session, row, document, asset, metric_key, outcome, ticket_id)
    session.flush()
    return outcome


def unverified_facts(session: Session) -> list[dict[str, Any]]:
    """Every imported figure that still stands, i.e. that nothing has confirmed or replaced."""
    facts = session.scalars(
        select(Fact)
        .where(Fact.origin == DataOrigin.IMPORT, Fact.superseded_by.is_(None))
        .order_by(Fact.subject_id, Fact.id)
    )
    rows = []
    for fact in facts:
        subject: Asset | Company | None = (
            session.get(Company, fact.subject_id)
            if fact.subject_type == SubjectType.COMPANY
            else session.get(Asset, fact.subject_id)
        )
        rows.append(
            {
                "fact_id": fact.id,
                "subject_type": fact.subject_type,
                "subject_id": fact.subject_id,
                "name": subject.name if subject else "",
                "metric": fact.metric_key,
                "label": METRICS[fact.metric_key].label,
                "display": display_value(fact),
                "document_id": fact.document_id,
                "document": fact.document.title if fact.document else "",
            }
        )
    return rows


def confirm(session: Session, fact: Fact, reason: str) -> Fact:
    """The user vouches for an imported figure and says why.

    It becomes the user's entry but keeps its mark: vouching is not a primary source, so the
    confidence stays low and everything derived from it stays flagged.
    """
    if fact.origin != DataOrigin.IMPORT or fact.superseded_by is not None:
        msg = "Nur eine noch ungeprüfte importierte Angabe lässt sich bestätigen"
        raise FactError(msg)
    if len(reason.strip()) < MIN_REASON_CHARS:
        msg = "Bitte begründen, woher du weisst, dass die Angabe stimmt"
        raise FactError(msg)
    return record_fact(
        session,
        FactInput(
            fact.subject_type, fact.subject_id, fact.metric_key,
            value=fact.value, low=fact.value_low, high=fact.value_high, text=fact.text,
            unit=fact.unit, basis=fact.basis, period_end=fact.period_end,
            published_at=fact.published_at, document_id=fact.document_id, quote=fact.quote,
            confidence="low", origin=DataOrigin.USER,
            formula_key=USER_CONFIRMED, inputs={"reason": reason.strip()},
        ),
    )  # fmt: skip


def retract(session: Session, fact: Fact) -> None:
    """Withdraw an own or imported entry. Nothing is deleted: the fact points at itself."""
    if fact.origin not in (DataOrigin.USER, DataOrigin.IMPORT) or fact.superseded_by is not None:
        msg = "Nur eigene oder importierte, noch gültige Angaben lassen sich stornieren"
        raise FactError(msg)
    fact.superseded_by = fact.id
    for earlier in session.scalars(
        select(Fact).where(Fact.superseded_by == fact.id, Fact.id != fact.id)
    ):
        earlier.superseded_by = None  # the value it had replaced stands again
    log_change(
        session, fact.subject_type, fact.subject_id, "fact",
        f"{METRICS[fact.metric_key].label} storniert", old=display_value(fact),
    )  # fmt: skip
