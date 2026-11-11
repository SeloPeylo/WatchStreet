"""Synthetic demo data set. Every row is flagged ``is_demo`` and every name starts with 'Demo'.

Used only with the ``demo`` market provider; it is never mixed into a real database.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from watchstreet.commodities import BY_KEY
from watchstreet.domain import AssetKind, AssetStatus, ClaimKind, DataOrigin, StakeRole, SubjectType
from watchstreet.intel.documents import store_document
from watchstreet.market.service import MarketService
from watchstreet.models import (
    Asset,
    AssetCommodity,
    Company,
    DocumentLink,
    Milestone,
    Stake,
    StatusPeriod,
)
from watchstreet.services import theses
from watchstreet.services.facts import FactInput, record_fact
from watchstreet.services.prices import sync_history

REPORT_DAY = date(2026, 2, 20)
PERIOD_END = date(2025, 12, 31)
PRIOR_REPORT_DAY = date(2025, 2, 20)
PRIOR_PERIOD_END = date(2024, 12, 31)
PRIOR_COST_FACTOR = 0.93  # last year's unit cost relative to this year's
FULL_SHARE = 100.0


@dataclass(frozen=True)
class DemoAsset:
    name: str
    commodity: str
    status: str
    lat: float
    lon: float
    country: str
    region: str
    company: str
    method: str
    production: float | None = None  # units per year
    aisc: float | None = None
    reserves: float | None = None
    hide_cost: bool = False  # cost stays in the document only, so research can find it
    start_year: int = 2008
    by_product: str = ""


PROD, DEV, EXPL = AssetStatus.PRODUCTION, AssetStatus.DEVELOPMENT, AssetStatus.EXPLORATION
ANDES, PACIFIC, JUNIOR = (
    "Demo Andes Copper Corp",
    "Demo Pacific Metals",
    "Demo Junior Explorers Ltd",
)
AURUM, PLATA, URAN = "Demo Aurum Mining", "Demo Plata Resources", "Demo Uranium One"
DEMO_ASSETS: tuple[DemoAsset, ...] = (
    DemoAsset(
        "Demo Mina Altiplano",
        "copper",
        PROD,
        -22.30,
        -68.90,
        "Chile",
        "Antofagasta",
        ANDES,
        "open_pit",
        420e6,
        2.05,
        9.8e9,
        by_product="gold",
    ),
    DemoAsset(
        "Demo Mina Río Seco",
        "copper",
        PROD,
        -27.40,
        -70.30,
        "Chile",
        "Atacama",
        ANDES,
        "open_pit",
        260e6,
        1.85,
        5.1e9,
    ),
    DemoAsset(
        "Demo Mina Quebrada Sur",
        "copper",
        PROD,
        -16.50,
        -71.60,
        "Peru",
        "Arequipa",
        PACIFIC,
        "open_pit",
        310e6,
        2.60,
        6.4e9,
    ),
    DemoAsset(
        "Demo Mina Kupferberg",
        "copper",
        PROD,
        -12.20,
        26.40,
        "Zambia",
        "Copperbelt",
        PACIFIC,
        "underground",
        150e6,
        4.40,
        2.2e9,
    ),
    DemoAsset(
        "Demo Mina Laguna Clara",
        "copper",
        PROD,
        -23.00,
        -68.50,
        "Chile",
        "Antofagasta",
        PACIFIC,
        "open_pit",
        180e6,
        2.31,
        3.0e9,
        hide_cost=True,
    ),
    DemoAsset(
        "Demo Projekt Vecino",
        "copper",
        EXPL,
        -22.52,
        -68.72,
        "Chile",
        "Antofagasta",
        JUNIOR,
        "open_pit",
        start_year=2019,
    ),
    DemoAsset(
        "Demo Projekt Cobre Alto",
        "copper",
        DEV,
        -14.10,
        -72.30,
        "Peru",
        "Apurímac",
        JUNIOR,
        "open_pit",
        190e6,
        2.20,
        4.0e9,
        start_year=2015,
    ),
    DemoAsset(
        "Demo Mine Silver Peak",
        "gold",
        PROD,
        40.80,
        -116.30,
        "United States of America",
        "Nevada",
        AURUM,
        "open_pit",
        610e3,
        1180.0,
        9.5e6,
    ),
    DemoAsset(
        "Demo Mine Kalgoorlie East",
        "gold",
        PROD,
        -30.80,
        121.60,
        "Australia",
        "Western Australia",
        AURUM,
        "underground",
        320e3,
        1420.0,
        4.1e6,
    ),
    DemoAsset(
        "Demo Mine Ashanti Ridge",
        "gold",
        PROD,
        6.20,
        -1.90,
        "Ghana",
        "Ashanti",
        AURUM,
        "open_pit",
        240e3,
        1560.0,
        3.0e6,
    ),
    DemoAsset(
        "Demo Projekt Golden Shield",
        "gold",
        DEV,
        48.50,
        -81.30,
        "Canada",
        "Ontario",
        JUNIOR,
        "underground",
        180e3,
        1250.0,
        2.6e6,
        start_year=2016,
    ),
    DemoAsset(
        "Demo Mina Sierra Plata",
        "silver",
        PROD,
        24.00,
        -104.70,
        "Mexico",
        "Durango",
        PLATA,
        "underground",
        9.5e6,
        17.4,
        110e6,
    ),
    DemoAsset(
        "Demo Mina Zacatecas Norte",
        "silver",
        PROD,
        22.90,
        -102.60,
        "Mexico",
        "Zacatecas",
        PLATA,
        "underground",
        14.0e6,
        14.9,
        190e6,
    ),
    DemoAsset(
        "Demo Mina Cordillera",
        "silver",
        PROD,
        -10.70,
        -76.30,
        "Peru",
        "Pasco",
        PLATA,
        "underground",
        6.2e6,
        21.8,
        60e6,
    ),
    DemoAsset(
        "Demo Projekt Plata Nueva",
        "silver",
        EXPL,
        25.40,
        -105.90,
        "Mexico",
        "Durango",
        JUNIOR,
        "underground",
        start_year=2021,
    ),
    DemoAsset(
        "Demo Mine Steppe ISR",
        "uranium",
        PROD,
        44.80,
        67.90,
        "Kazakhstan",
        "Turkistan",
        URAN,
        "isr",
        6.8e6,
        24.0,
        95e6,
    ),
    DemoAsset(
        "Demo Mine Athabasca Deep",
        "uranium",
        PROD,
        57.80,
        -105.00,
        "Canada",
        "Saskatchewan",
        URAN,
        "underground",
        15.0e6,
        33.0,
        210e6,
    ),
    DemoAsset(
        "Demo Mine Namib Sands",
        "uranium",
        PROD,
        -22.50,
        15.00,
        "Namibia",
        "Erongo",
        URAN,
        "open_pit",
        5.1e6,
        47.0,
        70e6,
    ),
    DemoAsset(
        "Demo Projekt Powder Basin",
        "uranium",
        DEV,
        43.50,
        -105.80,
        "United States of America",
        "Wyoming",
        JUNIOR,
        "isr",
        1.8e6,
        39.0,
        22e6,
        start_year=2017,
    ),
)


def _slug(name: str) -> str:
    table = str.maketrans({"í": "i", "ó": "o", "á": "a", "é": "e", " ": "-"})
    return name.lower().translate(table)


def _report_text(item: DemoAsset) -> str:
    """A synthetic report whose sentences back every seeded figure verbatim."""
    unit = BY_KEY[item.commodity].unit
    parts = [f"Synthetischer Demo-Bericht für {item.name}. Alle Angaben sind erfunden."]
    if item.production:
        parts.append(f"Annual production of {item.production:,.0f} {unit} in fiscal 2025.")
    if item.aisc:
        parts.append(
            f"All-in sustaining costs (AISC) averaged US${item.aisc:,.2f} per {unit} in 2025."
        )
    if item.reserves and item.status == PROD:
        parts.append(
            f"Proven and probable mineral reserves of {item.reserves:,.0f} {unit} at year end."
        )
    elif item.reserves:
        parts.append(f"Measured and indicated mineral resources of {item.reserves:,.0f} {unit}.")
    return "\n".join(parts)


def _prior_report_text(item: DemoAsset) -> str:
    """Last year's figure belongs to last year's report, published a year earlier."""
    unit = BY_KEY[item.commodity].unit
    cost = (item.aisc or 0.0) * PRIOR_COST_FACTOR
    return (
        f"Synthetischer Demo-Bericht 2024 für {item.name}. Alle Angaben sind erfunden.\n"
        f"All-in sustaining costs (AISC) averaged US${cost:,.2f} per {unit} in 2024."
    )


def _company(session: Session, cache: dict[str, Company], name: str) -> Company:
    if name not in cache:
        cache[name] = Company(slug=_slug(name), name=name, is_demo=True)
        session.add(cache[name])
        session.flush()
    return cache[name]


def _history(session: Session, asset: Asset, item: DemoAsset) -> None:
    start = date(item.start_year, 6, 1)
    stages = [(EXPL, start)]
    if item.status in (DEV, PROD):
        stages.append((DEV, date(item.start_year + 5, 3, 1)))
    if item.status == PROD:
        stages.append((PROD, date(item.start_year + 8, 9, 1)))
    for index, (status, begin) in enumerate(stages):
        end = stages[index + 1][1] if index + 1 < len(stages) else None
        session.add(StatusPeriod(asset_id=asset.id, status=status, valid_from=begin, valid_to=end))
    titles = {
        EXPL: ("discovery", "Entdeckung"),
        DEV: ("construction", "Baubeginn"),
        PROD: ("first_production", "Erste Produktion"),
    }
    for status, begin in stages:
        kind, title = titles[status]
        session.add(Milestone(asset_id=asset.id, kind=kind, day=begin, title=title))
    if len(stages) > 1:
        session.add(
            Milestone(
                asset_id=asset.id,
                kind="feasibility",
                day=date(item.start_year + 4, 5, 1),
                title="Machbarkeitsstudie",
            )
        )


def _facts(
    session: Session, asset: Asset, item: DemoAsset, document_id: int, text: str, prior_id: int
) -> None:
    unit = BY_KEY[item.commodity].unit
    lines = text.split("\n")
    producing = item.status == PROD

    def sentence(needle: str) -> str:
        return next(line for line in lines if needle in line)

    def add(metric: str, value: float, quote: str, fact_unit: str, *, prior: bool = False) -> None:
        record_fact(
            session,
            FactInput(
                SubjectType.ASSET,
                asset.id,
                metric,
                value=value,
                unit=fact_unit,
                basis="AISC, Nebenprodukte als Gutschrift, USD" if "aisc" in metric else "",
                period_end=PRIOR_PERIOD_END if prior else PERIOD_END,
                published_at=PRIOR_REPORT_DAY if prior else REPORT_DAY,
                claim_kind=ClaimKind.ACTUAL if producing else ClaimKind.GUIDANCE,
                document_id=prior_id if prior else document_id,
                quote=quote,
                confidence="high",
                origin=DataOrigin.API,
                is_demo=True,
            ),
        )

    if item.production:
        add(
            "production" if producing else "expected_production",
            item.production,
            sentence("Annual production"),
            f"{unit}/Jahr",
        )
    if item.aisc and not item.hide_cost:
        key = "aisc" if producing else "expected_aisc"
        add(
            key,
            round(item.aisc * PRIOR_COST_FACTOR, 2),
            _prior_report_text(item).split("\n")[1],
            f"USD/{unit}",
            prior=True,
        )
        add(key, item.aisc, sentence("All-in sustaining"), f"USD/{unit}")
    if item.reserves:
        add("reserves" if producing else "resources", item.reserves, sentence("mineral res"), unit)


def seed_demo(session: Session, market: MarketService) -> int:
    """Create the demo world once; returns the number of assets created."""
    if session.scalars(select(Asset.id).limit(1)).first() is not None:
        return 0
    companies: dict[str, Company] = {}
    copper_assets: list[Asset] = []
    for item in DEMO_ASSETS:
        asset = Asset(
            slug=_slug(item.name),
            name=item.name,
            lat=item.lat,
            lon=item.lon,
            kind=AssetKind.MINE if item.status == PROD else AssetKind.PROJECT,
            country=item.country,
            region=item.region,
            mining_method=item.method,
            is_demo=True,
            summary="Synthetisches Demo-Objekt – keine reale Mine.",
        )
        session.add(asset)
        session.flush()
        session.add(AssetCommodity(asset_id=asset.id, commodity=item.commodity, role="primary"))
        if item.by_product:
            session.add(
                AssetCommodity(asset_id=asset.id, commodity=item.by_product, role="by_product")
            )
        company = _company(session, companies, item.company)
        for role in (StakeRole.OPERATOR, StakeRole.OWNER):
            session.add(
                Stake(
                    asset_id=asset.id,
                    company_id=company.id,
                    role=role,
                    share_pct=FULL_SHARE,
                    valid_from=date(item.start_year, 6, 1),
                )
            )
        _history(session, asset, item)
        text = _report_text(item)
        document, _ = store_document(
            session,
            url=f"https://demo.invalid/reports/{asset.slug}",
            text=text,
            kind="filing",
            publisher=item.company,
            title=f"Demo-Jahresbericht 2025 – {item.name}",
            published_at=datetime(REPORT_DAY.year, REPORT_DAY.month, REPORT_DAY.day, tzinfo=UTC),
            meta={"is_demo": True},
        )
        session.add(
            DocumentLink(
                document_id=document.id, subject_type=SubjectType.ASSET, subject_id=asset.id
            )
        )
        prior, _ = store_document(
            session,
            url=f"https://demo.invalid/reports/{asset.slug}-2024",
            text=_prior_report_text(item),
            kind="filing",
            publisher=item.company,
            title=f"Demo-Jahresbericht 2024 – {item.name}",
            published_at=datetime(
                PRIOR_REPORT_DAY.year, PRIOR_REPORT_DAY.month, PRIOR_REPORT_DAY.day, tzinfo=UTC
            ),
            meta={"is_demo": True},
        )
        session.add(
            DocumentLink(document_id=prior.id, subject_type=SubjectType.ASSET, subject_id=asset.id)
        )
        _facts(session, asset, item, document.id, text, prior.id)
        if item.commodity == "copper":
            copper_assets.append(asset)
    thesis = theses.create_thesis(
        session,
        "Kupfernachfrage wächst langfristig",
        "Elektrifizierung und Netzausbau erhöhen den Kupferbedarf schneller, als neue Minen in "
        "Produktion gehen. (Demo-These)",
        "10 Jahre",
        "copper",
    )
    thesis.is_demo = True
    for text in (
        "Neue Minen brauchen über zehn Jahre bis zur Produktion.",
        "Erzgehalte bestehender Minen sinken.",
        "Substitution durch Aluminium bleibt begrenzt.",
    ):
        theses.add_assumption(session, thesis, text)
    for asset in copper_assets:
        theses.link(session, thesis, "asset", asset.id)
    sync_history(session, market)
    session.flush()
    return len(DEMO_ASSETS)
