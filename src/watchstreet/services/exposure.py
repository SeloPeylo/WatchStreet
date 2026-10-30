"""Country exposure of the portfolio, derived from owned assets and business partners.

Data flow: ``_load_exposure_inputs`` reads everything in a fixed number of queries, the
``_*_shares`` functions turn it into (country, share, reason) rows per stock, and
``country_exposure`` adds the rows up weighted by position value.
"""

from dataclasses import dataclass, field
from typing import Any, NamedTuple

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from watchstreet.constants import ASSET_KINDS, DEFAULT_RELATION_STRENGTH
from watchstreet.geo import normalize_country
from watchstreet.models import Entity, Relation, Stock

PARTNER_KINDS = ("supplier", "customer")
OWNS = "owns"
COUNTRY = "country"

Connected = list[tuple[Relation, Entity]]  # (relation, entity on the other end)


@dataclass
class CountryExposure:
    share: float = 0.0
    contributions: list[dict[str, Any]] = field(default_factory=list)


class CountryShare(NamedTuple):
    """One reason a stock is tied to a country: its country, share of the stock, explanation."""

    country: str
    share: float
    via: str


def _asset_weights(stock: Stock, owned: Connected) -> list[tuple[Entity, float]]:
    """Owned assets with their weight inside the company (production x ownership if known)."""
    production = {
        d.subject: d.value for d in stock.datapoints if d.key == "mine_production" and d.value
    }
    weighted = [
        (asset, (production.get(asset.name) or 1.0) * (edge.strength or 1.0))
        for edge, asset in owned
        if asset.kind in ASSET_KINDS
    ]
    total = sum(weight for _asset, weight in weighted)
    return [(asset, weight / total) for asset, weight in weighted] if total else []


def _asset_country_shares(stock: Stock, company: Entity, edges: Connected) -> list[CountryShare]:
    """Where the company's own assets sit, as shares of the whole company."""
    owned = [
        (rel, other) for rel, other in edges if rel.source_id == company.id and rel.kind == OWNS
    ]
    return [
        CountryShare(asset.country, share, f"Asset {asset.name}")
        for asset, share in _asset_weights(stock, owned)
    ]


def _partner_country_shares(edges: Connected) -> list[CountryShare]:
    """Countries reached through suppliers, customers and direct country relations."""
    shares: list[CountryShare] = []
    for rel, other in edges:
        if rel.kind == OWNS:
            continue
        if other.kind != COUNTRY and other.kind not in PARTNER_KINDS:
            continue
        strength = rel.strength if rel.strength is not None else DEFAULT_RELATION_STRENGTH
        country = other.name if other.kind == COUNTRY else other.country
        shares.append(CountryShare(country, strength, f"{rel.kind}: {other.name}"))
    return shares


def _load_exposure_inputs(
    session: Session, stock_ids: list[int]
) -> tuple[dict[int, Stock], dict[int, Entity], dict[int, Connected]]:
    """Load stocks, company entities and connected relations in a fixed number of queries."""
    stocks = {
        s.id: s
        for s in session.scalars(
            select(Stock).where(Stock.id.in_(stock_ids)).options(selectinload(Stock.datapoints)),
        )
    }
    companies: dict[int, Entity] = {}
    for company in session.scalars(
        select(Entity)
        .where(Entity.stock_id.in_(stock_ids), Entity.kind == "company")
        .order_by(Entity.id),
    ):
        if company.stock_id is not None:
            companies.setdefault(company.stock_id, company)
    company_ids = {c.id for c in companies.values()}
    relations = list(
        session.scalars(
            select(Relation)
            .where(Relation.source_id.in_(company_ids) | Relation.target_id.in_(company_ids))
            .order_by(Relation.id),
        ),
    )
    other_ids = {r.target_id for r in relations} | {r.source_id for r in relations}
    others = {e.id: e for e in session.scalars(select(Entity).where(Entity.id.in_(other_ids)))}
    connected: dict[int, Connected] = {}
    for rel in relations:
        for company_id, other_id in (
            (rel.source_id, rel.target_id),
            (rel.target_id, rel.source_id),
        ):
            other = others.get(other_id)
            if company_id in company_ids and other is not None:
                connected.setdefault(company_id, []).append((rel, other))
    return stocks, companies, connected


def country_exposure(session: Session, values: dict[int, float]) -> dict[str, CountryExposure]:
    """Share of the portfolio (by position value) tied to each country, with the reasons."""
    total = sum(values.values())
    if not total:
        return {}
    stocks, companies, connected = _load_exposure_inputs(session, list(values))
    exposure: dict[str, CountryExposure] = {}
    for stock_id, value in values.items():
        stock, company = stocks.get(stock_id), companies.get(stock_id)
        if stock is None or company is None:
            continue
        weight = value / total
        edges = connected.get(company.id, [])
        reasons = [*_asset_country_shares(stock, company, edges), *_partner_country_shares(edges)]
        for reason in reasons:
            name = normalize_country(reason.country)
            share = weight * reason.share
            if name and share > 0:
                entry = exposure.setdefault(name, CountryExposure())
                entry.share += share
                entry.contributions.append(
                    {"stock": stock.symbol, "via": reason.via, "share": share}
                )
    return exposure
