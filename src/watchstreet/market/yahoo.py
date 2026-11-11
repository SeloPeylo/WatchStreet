"""Yahoo Finance provider (free, unofficial public endpoints, no API key)."""

import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from watchstreet.constants import HTTP_TIMEOUT_S, INTERVAL_RANGES, MAX_NEWS_PER_STOCK
from watchstreet.market.base import (
    Candle,
    CompanyInfo,
    Fundamentals,
    MarketDataError,
    NewsItem,
    Quote,
    SymbolMatch,
)

logger = logging.getLogger(__name__)

CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
SEARCH_URL = "https://query2.finance.yahoo.com/v1/finance/search"
SUMMARY_URL = "https://query1.finance.yahoo.com/v10/finance/quoteSummary/{symbol}"
COOKIE_URL = "https://fc.yahoo.com"
CRUMB_URL = "https://query1.finance.yahoo.com/v1/test/getcrumb"
USER_AGENT = "Mozilla/5.0 (compatible; WatchStreet/0.1)"
SEARCH_QUOTES_COUNT = 6
SUMMARY_MODULES = "summaryDetail,defaultKeyStatistics,financialData"

# our key -> (module, yahoo field)
FUNDAMENTAL_FIELDS: dict[str, tuple[str, str]] = {
    "trailing_pe": ("summaryDetail", "trailingPE"),
    "forward_pe": ("summaryDetail", "forwardPE"),
    "dividend_yield": ("summaryDetail", "dividendYield"),
    "market_cap": ("summaryDetail", "marketCap"),
    "price_to_book": ("defaultKeyStatistics", "priceToBook"),
    "peg_ratio": ("defaultKeyStatistics", "pegRatio"),
    "beta": ("defaultKeyStatistics", "beta"),
    "profit_margin": ("financialData", "profitMargins"),
    "return_on_equity": ("financialData", "returnOnEquity"),
    "revenue_growth": ("financialData", "revenueGrowth"),
    "debt_to_equity": ("financialData", "debtToEquity"),
    "target_mean_price": ("financialData", "targetMeanPrice"),
}


class YahooProvider:
    """Reads price history, quotes, key figures and news from Yahoo Finance."""

    name = "yahoo"

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(
            timeout=HTTP_TIMEOUT_S,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        )
        self._crumb: str | None = None

    # -- helpers ----------------------------------------------------------
    def _get_json(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            response = self._client.get(url, params=params)
            response.raise_for_status()
            payload: dict[str, Any] = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            msg = f"Yahoo request failed: {exc}"
            raise MarketDataError(msg) from exc
        return payload

    def _chart(self, symbol: str, interval: str) -> dict[str, Any]:
        data = self._get_json(
            CHART_URL.format(symbol=symbol),
            {"interval": interval, "range": INTERVAL_RANGES[interval]},
        )
        results = (data.get("chart") or {}).get("result")
        if not results:
            msg = f"No chart data for {symbol}"
            raise MarketDataError(msg)
        first: dict[str, Any] = results[0]
        return first

    # -- protocol ---------------------------------------------------------
    def search(self, query: str) -> list[SymbolMatch]:
        data = self._get_json(
            SEARCH_URL,
            {"q": query, "quotesCount": SEARCH_QUOTES_COUNT, "newsCount": 0},
        )
        return [
            SymbolMatch(
                symbol=item["symbol"],
                name=item.get("longname") or item.get("shortname") or "",
                exchange=item.get("exchDisp", ""),
            )
            for item in data.get("quotes", [])
            if item.get("symbol")
        ]

    def quote(self, symbol: str) -> Quote:
        meta = self._chart(symbol, "1d").get("meta", {})
        price = meta.get("regularMarketPrice")
        if price is None:
            msg = f"No price for {symbol}"
            raise MarketDataError(msg)
        return Quote(
            symbol=meta.get("symbol", symbol),
            price=float(price),
            previous_close=meta.get("chartPreviousClose") or meta.get("previousClose"),
            currency=meta.get("currency", ""),
            name=meta.get("longName") or meta.get("shortName") or "",
            exchange=meta.get("fullExchangeName") or meta.get("exchangeName") or "",
        )

    def candles(self, symbol: str, interval: str) -> list[Candle]:
        chart = self._chart(symbol, interval)
        stamps = chart.get("timestamp") or []
        quote = ((chart.get("indicators") or {}).get("quote") or [{}])[0]
        candles: list[Candle] = []
        for idx, stamp in enumerate(stamps):
            ohlc = [
                quote.get(k, [None] * len(stamps))[idx] for k in ("open", "high", "low", "close")
            ]
            if any(v is None for v in ohlc):
                continue
            open_, high, low, close = (float(v) for v in ohlc)
            volume = (quote.get("volume") or [0] * len(stamps))[idx] or 0
            candles.append(
                Candle(datetime.fromtimestamp(stamp, UTC), open_, high, low, close, float(volume)),
            )
        return candles

    def fundamentals(self, symbol: str) -> Fundamentals:
        try:
            crumb = self._ensure_crumb()
            data = self._get_json(
                SUMMARY_URL.format(symbol=symbol),
                {"modules": SUMMARY_MODULES, "crumb": crumb},
            )
        except MarketDataError:
            logger.warning("No fundamentals for %s", symbol)
            return Fundamentals()
        result = ((data.get("quoteSummary") or {}).get("result") or [{}])[0]
        values: dict[str, float] = {}
        for key, (module, field_name) in FUNDAMENTAL_FIELDS.items():
            raw = (result.get(module) or {}).get(field_name)
            number = raw.get("raw") if isinstance(raw, dict) else raw
            if isinstance(number, int | float):
                values[key] = float(number)
        return Fundamentals(values)

    def company_info(self, symbol: str) -> CompanyInfo:
        try:
            data = self._get_json(
                SUMMARY_URL.format(symbol=symbol),
                {"modules": "assetProfile", "crumb": self._ensure_crumb()},
            )
        except MarketDataError:
            return CompanyInfo()
        result = ((data.get("quoteSummary") or {}).get("result") or [{}])[0]
        profile = result.get("assetProfile") or {}
        return CompanyInfo(profile.get("sector", ""), profile.get("industry", ""))

    def news(self, symbol: str) -> list[NewsItem]:
        data = self._get_json(
            SEARCH_URL,
            {"q": symbol, "quotesCount": 0, "newsCount": MAX_NEWS_PER_STOCK},
        )
        return [
            NewsItem(
                external_id=str(item.get("uuid") or item["link"]),
                title=item["title"],
                url=item.get("link", ""),
                source=item.get("publisher", ""),
                published_at=datetime.fromtimestamp(item.get("providerPublishTime", 0), UTC),
            )
            for item in data.get("news", [])
            if item.get("title") and (item.get("uuid") or item.get("link"))
        ]

    def _ensure_crumb(self) -> str:
        if self._crumb:
            return self._crumb
        try:
            self._client.get(COOKIE_URL)
            response = self._client.get(CRUMB_URL)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            msg = f"Yahoo crumb failed: {exc}"
            raise MarketDataError(msg) from exc
        self._crumb = response.text.strip()
        return self._crumb
