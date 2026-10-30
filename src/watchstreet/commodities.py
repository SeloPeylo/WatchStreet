"""Catalog of commodities and macro series that are tracked (data, not logic)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Commodity:
    key: str
    label: str
    symbol: str  # Yahoo Finance futures symbol
    unit: str


COMMODITIES: tuple[Commodity, ...] = (
    Commodity("gold", "Gold", "GC=F", "USD/oz"),
    Commodity("silver", "Silber", "SI=F", "USD/oz"),
    Commodity("platinum", "Platin", "PL=F", "USD/oz"),
    Commodity("palladium", "Palladium", "PA=F", "USD/oz"),
    Commodity("copper", "Kupfer", "HG=F", "USD/lb"),
    Commodity("aluminium", "Aluminium", "ALI=F", "USD/t"),
    Commodity("wti", "Rohöl WTI", "CL=F", "USD/bbl"),
    Commodity("brent", "Rohöl Brent", "BZ=F", "USD/bbl"),
    Commodity("natgas", "Erdgas", "NG=F", "USD/MMBtu"),
)
MACRO: tuple[Commodity, ...] = (
    Commodity("dxy", "US-Dollar-Index", "DX-Y.NYB", "Punkte"),
    Commodity("us10y", "US-10J-Rendite", "^TNX", "%"),
    Commodity("vix", "VIX", "^VIX", "Punkte"),
    Commodity("spx", "S&P 500", "^GSPC", "Punkte"),
)
BY_SYMBOL = {c.symbol: c for c in COMMODITIES}
BY_KEY = {c.key: c for c in (*COMMODITIES, *MACRO)}
COPPER_GOLD_FACTOR = 1000.0  # conventional scaling of the copper/gold ratio
