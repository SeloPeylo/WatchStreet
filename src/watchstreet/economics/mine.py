"""Mine-level economics (pure). Every result is an interval; a point is an interval of width 0."""

from dataclasses import dataclass

from watchstreet.constants import DEFAULT_DISCOUNT_RATE, MAX_MINE_LIFE_YEARS


@dataclass(frozen=True)
class Interval:
    low: float
    high: float

    @classmethod
    def point(cls, value: float) -> "Interval":
        return cls(value, value)

    @property
    def is_point(self) -> bool:
        return self.low == self.high

    @property
    def mid(self) -> float:
        return (self.low + self.high) / 2

    def minus(self, other: "Interval") -> "Interval":
        return Interval(self.low - other.high, self.high - other.low)

    def times(self, other: "Interval") -> "Interval":
        products = (
            self.low * other.low,
            self.low * other.high,
            self.high * other.low,
            self.high * other.high,
        )
        return Interval(min(products), max(products))

    def scaled(self, factor: float) -> "Interval":
        return self.times(Interval.point(factor))


@dataclass(frozen=True)
class ByProduct:
    """A by-product whose revenue is credited against unit cost."""

    volume: float  # per year, in the by-product's unit
    reference_price: float  # price the reported cost was calculated with
    price: float  # price in the view being evaluated


@dataclass(frozen=True)
class MineInputs:
    cost: Interval | None = None  # per unit of the main commodity
    production: Interval | None = None  # units per year (100 % basis)
    reserves: float | None = None  # units
    share: float = 1.0  # attributable share 0..1
    by_products: tuple[ByProduct, ...] = ()


@dataclass(frozen=True)
class MineEconomics:
    price: float
    cost: Interval | None
    margin: Interval | None  # per unit
    margin_pct: Interval | None  # 0..1; also the distance to break-even
    cash_flow: Interval | None  # per year, 100 % basis
    attributable_cash_flow: Interval | None
    leverage: float | None  # % change of margin per % change of price
    mine_life: float | None  # years, capped
    nav: Interval | None
    by_product_adjusted: bool


def annuity(cash_flow: float, rate: float, years: float) -> float:
    """Present value of a constant yearly cash flow."""
    if years <= 0:
        return 0.0
    if rate == 0:
        return cash_flow * years
    return float(cash_flow * (1 - (1 + rate) ** -years) / rate)


def adjusted_cost(inputs: MineInputs) -> tuple[Interval | None, bool]:
    """Re-price the by-product credit: C' = C + sum(Q_by * (P_ref - P_by)) / Q."""
    cost, production = inputs.cost, inputs.production
    if cost is None or production is None or not inputs.by_products or production.mid <= 0:
        return cost, False
    delta = sum(b.volume * (b.reference_price - b.price) for b in inputs.by_products)
    shift = delta / production.mid
    return Interval(cost.low + shift, cost.high + shift), True


def mine_life(inputs: MineInputs) -> float | None:
    if inputs.reserves is None or inputs.production is None or inputs.production.mid <= 0:
        return None
    return min(inputs.reserves / inputs.production.mid, MAX_MINE_LIFE_YEARS)


def evaluate(
    inputs: MineInputs, price: float, discount_rate: float = DEFAULT_DISCOUNT_RATE
) -> MineEconomics:
    """All mine figures for one price. Missing inputs yield ``None``, never a guess."""
    cost, adjusted = adjusted_cost(inputs)
    life = mine_life(inputs)
    if cost is None or price <= 0:
        return MineEconomics(price, cost, None, None, None, None, None, life, None, adjusted)
    margin = Interval.point(price).minus(cost)
    margin_pct = margin.scaled(1 / price)
    leverage = price / margin.mid if margin.mid > 0 else None
    cash_flow = margin.times(inputs.production) if inputs.production else None
    attributable = cash_flow.scaled(inputs.share) if cash_flow else None
    nav = None
    if attributable is not None and life is not None:
        nav = Interval(
            annuity(attributable.low, discount_rate, life),
            annuity(attributable.high, discount_rate, life),
        )
    return MineEconomics(
        price, cost, margin, margin_pct, cash_flow, attributable, leverage, life, nav, adjusted
    )
