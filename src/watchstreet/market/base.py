"""Provider-neutral market data types and the provider protocol."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class Candle:
    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class Quote:
    symbol: str
    price: float
    previous_close: float | None
    currency: str
    name: str
    exchange: str

    @property
    def change_pct(self) -> float | None:
        if not self.previous_close:
            return None
        return (self.price / self.previous_close - 1.0) * 100.0


@dataclass(frozen=True)
class NewsItem:
    external_id: str
    title: str
    url: str
    source: str
    published_at: datetime


@dataclass(frozen=True)
class SymbolMatch:
    symbol: str
    name: str
    exchange: str


@dataclass(frozen=True)
class Fundamentals:
    """Optional key figures; any may be missing for a given provider or stock."""

    values: dict[str, float] = field(default_factory=dict)

    def get(self, key: str) -> float | None:
        return self.values.get(key)


class MarketDataError(RuntimeError):
    """Raised when a provider cannot deliver the requested data."""


class MarketDataProvider(Protocol):
    name: str

    def search(self, query: str) -> list[SymbolMatch]: ...

    def quote(self, symbol: str) -> Quote: ...

    def candles(self, symbol: str, interval: str) -> list[Candle]: ...

    def fundamentals(self, symbol: str) -> Fundamentals: ...

    def news(self, symbol: str) -> list[NewsItem]: ...
