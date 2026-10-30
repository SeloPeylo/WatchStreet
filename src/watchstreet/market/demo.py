"""Deterministic synthetic market data for offline use, tests and documentation."""

import hashlib
import math
import random
from datetime import UTC, datetime, timedelta

from watchstreet.constants import (
    DEMO_BASE_PRICE_MIN,
    DEMO_BASE_PRICE_SPAN,
    DEMO_CANDLE_COUNT,
    DEMO_DRIFT,
    DEMO_VOLATILITY,
    DEMO_VOLUME_BASE,
    INTERVAL_SECONDS,
    SECONDS_PER_HOUR,
)
from watchstreet.market.base import (
    Candle,
    CompanyInfo,
    Fundamentals,
    NewsItem,
    Quote,
    SymbolMatch,
)

DEMO_CURRENCY = "USD"
DEMO_EXCHANGE = "DEMO"
DEMO_HEADLINES = (
    "{name} meldet Quartalszahlen über den Erwartungen",
    "Analysten passen Kursziel für {name} an",
    "{name}: Management kündigt neues Aktienrückkaufprogramm an",
)
HASH_BYTES = 8
# Demo only: fixed sectors for well-known symbols so every profile can be shown offline.
DEMO_COMPANIES: dict[str, CompanyInfo] = {
    "AAPL": CompanyInfo("Technology", "Consumer Electronics"),
    "MSFT": CompanyInfo("Technology", "Software - Infrastructure"),
    "NVDA": CompanyInfo("Technology", "Semiconductors"),
    "SAP.DE": CompanyInfo("Technology", "Software - Application"),
    "NEM": CompanyInfo("Basic Materials", "Gold"),
    "GOLD": CompanyInfo("Basic Materials", "Gold"),
    "XOM": CompanyInfo("Energy", "Oil & Gas Integrated"),
    "NEE": CompanyInfo("Utilities", "Utilities - Regulated Electric"),
    "JPM": CompanyInfo("Financial Services", "Banks - Diversified"),
    "O": CompanyInfo("Real Estate", "REIT - Retail"),
    "PFE": CompanyInfo("Healthcare", "Drug Manufacturers - General"),
}


def _rng(symbol: str, salt: str = "") -> random.Random:
    digest = hashlib.sha256(f"{symbol.upper()}:{salt}".encode()).digest()
    return random.Random(int.from_bytes(digest[:HASH_BYTES], "big"))  # noqa: S311  # nosec B311 - reproducible fake data, not security


class DemoProvider:
    """Reproducible fake data. Never use it for real investment decisions."""

    name = "demo"

    def search(self, query: str) -> list[SymbolMatch]:
        symbol = query.strip().upper()
        return [SymbolMatch(symbol, f"Demo {symbol}", DEMO_EXCHANGE)] if symbol else []

    def quote(self, symbol: str) -> Quote:
        candles = self.candles(symbol, "1d")
        return Quote(
            symbol=symbol.upper(),
            price=candles[-1].close,
            previous_close=candles[-2].close,
            currency=DEMO_CURRENCY,
            name=f"Demo {symbol.upper()}",
            exchange=DEMO_EXCHANGE,
        )

    def candles(self, symbol: str, interval: str) -> list[Candle]:
        step = INTERVAL_SECONDS[interval]
        rng = _rng(symbol, "candles")
        price = DEMO_BASE_PRICE_MIN + rng.random() * DEMO_BASE_PRICE_SPAN
        drift = DEMO_DRIFT * (rng.random() * 2 - 1) * 2
        now = datetime.now(UTC)
        end = now - timedelta(seconds=now.timestamp() % step)
        out: list[Candle] = []
        for idx in range(DEMO_CANDLE_COUNT):
            opened = price
            closed = opened * math.exp(drift + rng.gauss(0, DEMO_VOLATILITY))
            wick = abs(rng.gauss(0, DEMO_VOLATILITY)) * opened
            out.append(
                Candle(
                    time=end - timedelta(seconds=step * (DEMO_CANDLE_COUNT - idx)),
                    open=opened,
                    high=max(opened, closed) + wick,
                    low=min(opened, closed) - wick,
                    close=closed,
                    volume=DEMO_VOLUME_BASE * (0.5 + rng.random()),
                ),
            )
            price = closed
        return out

    def fundamentals(self, symbol: str) -> Fundamentals:
        rng = _rng(symbol, "fundamentals")
        price = self.candles(symbol, "1d")[-1].close
        return Fundamentals(
            {
                "trailing_pe": 8 + rng.random() * 30,
                "forward_pe": 8 + rng.random() * 25,
                "price_to_book": 0.8 + rng.random() * 8,
                "peg_ratio": 0.5 + rng.random() * 3,
                "dividend_yield": rng.random() * 0.04,
                "profit_margin": rng.random() * 0.3,
                "return_on_equity": rng.random() * 0.35,
                "revenue_growth": -0.05 + rng.random() * 0.3,
                "debt_to_equity": 10 + rng.random() * 200,
                "target_mean_price": price * (0.85 + rng.random() * 0.4),
                "beta": 0.6 + rng.random() * 1.2,
            },
        )

    def company_info(self, symbol: str) -> CompanyInfo:
        return DEMO_COMPANIES.get(symbol.upper(), CompanyInfo("Consumer Defensive", "Beverages"))

    def news(self, symbol: str) -> list[NewsItem]:
        name = f"Demo {symbol.upper()}"
        today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        return [
            NewsItem(
                external_id=f"demo-{symbol.upper()}-{today:%Y%m%d}-{idx}",
                title=headline.format(name=name),
                url="",
                source="Demo Wire",
                published_at=today + timedelta(seconds=SECONDS_PER_HOUR * (idx + 1)),
            )
            for idx, headline in enumerate(DEMO_HEADLINES)
        ]
