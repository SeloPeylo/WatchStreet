"""Seeding the map from public registers ("lazy research", step one).

A registry entry becomes an asset with a location, a name and – if the register names one – an
operator, each backed by a stored registry document. It carries no status, production or cost:
those stay unknown until research documents them.
"""

import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from watchstreet.constants import DUPLICATE_RADIUS_KM
from watchstreet.domain import AssetKind, StakeRole, SubjectType
from watchstreet.geo import haversine_km
from watchstreet.intel.connectors.registry import RegistryMine
from watchstreet.intel.documents import store_document
from watchstreet.models import Asset, AssetCommodity, Company, DocumentLink, Stake
from watchstreet.services.changes import log_change

SOURCE_LABEL = {"wikidata": "Wikidata", "mrds": "USGS MRDS"}
SLUG_CHARS = re.compile(r"[^a-z0-9]+")


@dataclass
class ImportReport:
    created: int = 0
    known: int = 0
    other_commodity: int = 0
    asset_ids: list[int] | None = None


def slug(text: str) -> str:
    return SLUG_CHARS.sub("-", text.lower()).strip("-")


_slug = slug


def _is_known(existing: list[Asset], mine: RegistryMine) -> bool:
    """Already imported, or the same name at practically the same place."""
    for asset in existing:
        if asset.registry_source == mine.source and asset.registry_id == mine.external_id:
            return True
        near = haversine_km(asset.lat, asset.lon, mine.lat, mine.lon) <= DUPLICATE_RADIUS_KM
        if near and _slug(asset.name) == _slug(mine.name):
            return True
    return False


def company_by_name(session: Session, name: str) -> Company:
    slug = _slug(name)
    company = session.scalars(select(Company).where(Company.slug == slug)).first()
    if company is None:
        company = Company(slug=slug, name=name)
        session.add(company)
        session.flush()
    return company


def _record_text(mine: RegistryMine) -> str:
    """The registry entry as stored text; stakes quote their line of it verbatim."""
    lines = [
        f"Registry record from {SOURCE_LABEL[mine.source]} for {mine.name} ({mine.external_id}).",
        f"Location: latitude {mine.lat}, longitude {mine.lon}. Country: {mine.country or 'unknown'}.",
        f"Commodities: {', '.join(mine.commodities)}.",
    ]
    lines += [f"Operator according to the register: {name}." for name in mine.operators]
    lines += [f"Owner according to the register: {name}." for name in mine.owners]
    if mine.status_hint:
        lines.append(f"Development status in the register (may be outdated): {mine.status_hint}.")
    return "\n".join(lines)


def _create(session: Session, mine: RegistryMine) -> Asset:
    asset = Asset(
        slug=f"{_slug(mine.name)}-{mine.source}-{_slug(mine.external_id)}",
        name=mine.name,
        kind=AssetKind.DEPOSIT,
        lat=mine.lat,
        lon=mine.lon,
        country=mine.country,
        registry_source=mine.source,
        registry_id=mine.external_id,
        summary=f"Aus dem Register {SOURCE_LABEL[mine.source]} übernommen; Status und Kennzahlen "
        "sind noch nicht recherchiert.",
    )
    session.add(asset)
    session.flush()
    for index, commodity in enumerate(mine.commodities):
        role = "primary" if index == 0 else "co_product"
        session.add(AssetCommodity(asset_id=asset.id, commodity=commodity, role=role))
    text = _record_text(mine)
    document, _ = store_document(
        session, url=mine.url, text=text, kind="dataset", publisher=SOURCE_LABEL[mine.source],
        title=f"Registereintrag {mine.name}",
    )  # fmt: skip
    session.add(
        DocumentLink(document_id=document.id, subject_type=SubjectType.ASSET, subject_id=asset.id)
    )
    for role, names, word in (
        (StakeRole.OPERATOR, mine.operators, "Operator"),
        (StakeRole.OWNER, mine.owners, "Owner"),
    ):
        for name in names:
            session.add(
                Stake(
                    asset_id=asset.id, company_id=company_by_name(session, name).id, role=role,
                    document_id=document.id, quote=f"{word} according to the register: {name}.",
                )
            )  # fmt: skip
    log_change(
        session, SubjectType.ASSET, asset.id, "registry",
        f"Aus Register übernommen ({SOURCE_LABEL[mine.source]}): {mine.name}",
    )  # fmt: skip
    return asset


def import_mines(session: Session, mines: list[RegistryMine]) -> ImportReport:
    """Create assets for registry entries we do not have yet; never touches existing ones."""
    existing = list(session.scalars(select(Asset)))
    report = ImportReport(asset_ids=[])
    for mine in mines:
        if not mine.commodities:
            report.other_commodity += 1
        elif _is_known(existing, mine):
            report.known += 1
        else:
            asset = _create(session, mine)
            existing.append(asset)
            report.created += 1
            report.asset_ids.append(asset.id)  # type: ignore[union-attr]
    session.flush()
    return report
