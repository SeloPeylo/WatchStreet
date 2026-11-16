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
    Commodity("oil", "Rohöl", "CL=F", "bbl", "#7a5c9e"),
    # Gas is priced per energy unit and stays its own commodity; it is never converted to barrels.
    Commodity("gas", "Erdgas", "NG=F", "MMBtu", "#3b82c4"),
    Commodity("lumber", "Holz", "LBR=F", "mbf", "#8a6d3b"),  # mbf: thousand board feet
)
BY_KEY = {c.key: c for c in COMMODITIES}
