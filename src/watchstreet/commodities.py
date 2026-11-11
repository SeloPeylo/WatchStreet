"""Catalog of tracked commodities (data, not logic)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Commodity:
    key: str
    label: str
    symbol: str  # Yahoo Finance futures symbol
    unit: str  # unit of production and of the price denominator
    color: str

    @property
    def price_unit(self) -> str:
        return f"USD/{self.unit}"


COMMODITIES: tuple[Commodity, ...] = (
    Commodity("gold", "Gold", "GC=F", "oz", "#c9a227"),
    Commodity("silver", "Silber", "SI=F", "oz", "#8d99ae"),
    Commodity("copper", "Kupfer", "HG=F", "lb", "#b5651d"),
    Commodity("uranium", "Uran", "UX=F", "lb", "#5a9367"),
)
BY_KEY = {c.key: c for c in COMMODITIES}
