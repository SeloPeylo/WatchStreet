import httpx
import pytest

from watchstreet.market.base import MarketDataError
from watchstreet.market.yahoo import YahooProvider

CHART = {
    "chart": {
        "result": [
            {
                "meta": {
                    "symbol": "AAPL",
                    "regularMarketPrice": 190.5,
                    "chartPreviousClose": 188.0,
                    "currency": "USD",
                    "longName": "Apple Inc.",
                    "fullExchangeName": "NasdaqGS",
                },
                "timestamp": [1_700_000_000, 1_700_003_600, 1_700_007_200],
                "indicators": {
                    "quote": [
                        {
                            "open": [1.0, None, 3.0],
                            "high": [2.0, 2.0, 4.0],
                            "low": [0.5, 1.0, 2.5],
                            "close": [1.5, 1.8, 3.5],
                            "volume": [100, 200, None],
                        },
                    ],
                },
            },
        ],
    },
}
SEARCH = {
    "quotes": [{"symbol": "AAPL", "longname": "Apple Inc.", "exchDisp": "NASDAQ"}, {"x": 1}],
    "news": [
        {
            "uuid": "u1",
            "title": "Apple beats",
            "link": "http://n/1",
            "publisher": "Wire",
            "providerPublishTime": 1_700_000_000,
        },
        {"title": "no id"},
    ],
}
SUMMARY = {
    "quoteSummary": {
        "result": [
            {
                "summaryDetail": {"trailingPE": {"raw": 28.5}, "dividendYield": {"raw": 0.005}},
                "defaultKeyStatistics": {"priceToBook": {"raw": 40.0}},
                "financialData": {"profitMargins": 0.25, "targetMeanPrice": {"raw": 210.0}},
            },
        ],
    },
}


def handler(request: httpx.Request) -> httpx.Response:
    url = str(request.url)
    if "/v8/finance/chart/BAD" in url:
        return httpx.Response(200, json={"chart": {"result": None}})
    if "/v8/finance/chart/" in url:
        return httpx.Response(200, json=CHART)
    if "/v1/finance/search" in url:
        return httpx.Response(200, json=SEARCH)
    if "getcrumb" in url:
        return httpx.Response(200, text="crumb123")
    if "fc.yahoo.com" in url:
        return httpx.Response(404)
    if "quoteSummary" in url:
        assert request.url.params["crumb"] == "crumb123"
        return httpx.Response(200, json=SUMMARY)
    return httpx.Response(500)


@pytest.fixture
def provider() -> YahooProvider:
    return YahooProvider(httpx.Client(transport=httpx.MockTransport(handler)))


def test_quote(provider):
    quote = provider.quote("AAPL")
    assert (quote.price, quote.currency, quote.name) == (190.5, "USD", "Apple Inc.")
    assert quote.change_pct == pytest.approx(1.33, abs=0.01)


def test_candles_skip_incomplete_rows(provider):
    candles = provider.candles("AAPL", "1h")
    assert [c.close for c in candles] == [1.5, 3.5]
    assert candles[1].volume == 0


def test_search_and_news(provider):
    assert [m.symbol for m in provider.search("apple")] == ["AAPL"]
    news = provider.news("AAPL")
    assert [n.external_id for n in news] == ["u1"]


def test_fundamentals_parse_raw_and_plain_numbers(provider):
    values = provider.fundamentals("AAPL").values
    assert values["trailing_pe"] == 28.5
    assert values["profit_margin"] == 0.25
    assert values["target_mean_price"] == 210.0


def test_errors_become_market_data_error(provider):
    with pytest.raises(MarketDataError):
        provider.quote("BAD")


def test_http_failure_is_wrapped():
    failing = YahooProvider(
        httpx.Client(transport=httpx.MockTransport(lambda _r: httpx.Response(500)))
    )
    with pytest.raises(MarketDataError):
        failing.quote("AAPL")
    assert failing.fundamentals("AAPL").values == {}
