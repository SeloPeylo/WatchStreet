"""Caching facade around a provider so pages and workflows do not hammer free APIs."""

import threading
import time
from collections.abc import Callable
from typing import TypeVar

from watchstreet.config import Settings
from watchstreet.constants import CANDLE_CACHE_TTL_S, QUOTE_CACHE_TTL_S
from watchstreet.market.base import (
    Candle,
    Fundamentals,
    MarketDataError,
    MarketDataProvider,
    NewsItem,
    Quote,
    SymbolMatch,
)
from watchstreet.market.demo import DemoProvider
from watchstreet.market.yahoo import YahooProvider

T = TypeVar("T")


def build_provider(settings: Settings) -> MarketDataProvider:
    if settings.market_provider == "demo":
        return DemoProvider()
    if settings.market_provider == "yahoo":
        return YahooProvider()
    msg = f"Unknown market provider: {settings.market_provider}"
    raise ValueError(msg)


class MarketService:
    """TTL cache in front of a provider. Errors are not cached."""

    def __init__(self, provider: MarketDataProvider) -> None:
        self.provider = provider
        self._cache: dict[tuple[str, ...], tuple[float, object]] = {}
        self._lock = threading.Lock()

    @property
    def name(self) -> str:
        return self.provider.name

    def _cached(self, key: tuple[str, ...], ttl: float, loader: Callable[[], T]) -> T:
        now = time.monotonic()
        with self._lock:
            hit = self._cache.get(key)
            if hit and now - hit[0] < ttl:
                return hit[1]  # type: ignore[return-value]
        value = loader()
        with self._lock:
            self._cache[key] = (now, value)
        return value

    def search(self, query: str) -> list[SymbolMatch]:
        return self.provider.search(query)

    def quote(self, symbol: str) -> Quote:
        return self._cached(("q", symbol), QUOTE_CACHE_TTL_S, lambda: self.provider.quote(symbol))

    def try_quote(self, symbol: str) -> Quote | None:
        try:
            return self.quote(symbol)
        except MarketDataError:
            return None

    def candles(self, symbol: str, interval: str) -> list[Candle]:
        return self._cached(
            ("c", symbol, interval),
            CANDLE_CACHE_TTL_S,
            lambda: self.provider.candles(symbol, interval),
        )

    def fundamentals(self, symbol: str) -> Fundamentals:
        return self._cached(
            ("f", symbol),
            CANDLE_CACHE_TTL_S,
            lambda: self.provider.fundamentals(symbol),
        )

    def news(self, symbol: str) -> list[NewsItem]:
        return self.provider.news(symbol)
