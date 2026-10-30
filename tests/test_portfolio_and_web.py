import pytest
from sqlalchemy import select

from watchstreet.models import Holding, Stock, Ticket, WatchEntry
from watchstreet.services import portfolio
from watchstreet.services.portfolio import PortfolioError
from watchstreet.worker import drain_queue


def test_validation(container):
    with container.session_factory() as s:
        for bad in ("", "A B", "X" * 40):
            with pytest.raises(PortfolioError):
                portfolio.normalize_symbol(bad)
        with pytest.raises(PortfolioError):
            portfolio.add_holding(s, container.market, portfolio.NewHolding("AAPL", 0, 10))
        portfolio.add_holding(s, container.market, portfolio.NewHolding("AAPL", 1, 10))
        with pytest.raises(PortfolioError):
            portfolio.add_holding(s, container.market, portfolio.NewHolding("aapl", 1, 10))


def test_totals_never_mix_currencies(container):
    with container.session_factory() as s:
        portfolio.add_holding(s, container.market, portfolio.NewHolding("AAA", 2, 10))
        portfolio.add_holding(s, container.market, portfolio.NewHolding("BBB", 1, 10))
        rows = portfolio.holding_rows(s, container.market)
        totals = portfolio.totals_by_currency(rows)
        assert list(totals) == ["USD"]
        assert totals["USD"]["cost"] == 30
        assert totals["USD"]["pnl"] == pytest.approx(totals["USD"]["value"] - 30)


def test_pages_render_empty(client):
    for path in ("/", "/holdings", "/watchlist", "/tickets", "/system", "/healthz"):
        assert client.get(path).status_code == 200, path
    assert client.get("/stocks/999").status_code == 404
    assert client.get("/tickets/999").status_code == 404
    assert client.get("/manual").status_code == 404


def test_full_user_flow(client, container):
    resp = client.post(
        "/holdings",
        data={"symbol": "aapl", "quantity": "12,5", "avg_price": "150,25", "intent": "halten"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    client.post("/watchlist", data={"symbol": "msft", "note": "cloud"})
    drain_queue(container)

    page = client.get("/holdings").text
    assert "AAPL" in page and "12,5" not in page  # rendered via number filter
    with container.session_factory() as s:
        stock = s.scalar(select(Stock).where(Stock.symbol == "AAPL"))
        holding = s.scalar(select(Holding))
        assert holding.quantity == 12.5 and holding.avg_price == 150.25
        stock_id, holding_id = stock.id, holding.id
        entry_id = s.scalar(select(WatchEntry.id))

    detail = client.get(f"/stocks/{stock_id}")
    assert detail.status_code == 200
    for needle in ("Investmentthese", "valuation_v1", "technical_v1", "Zeitleiste", "halten"):
        assert needle in detail.text

    candles = client.get(f"/api/stocks/{stock_id}/candles?interval=1d").json()
    assert len(candles) > 50 and set(candles[0]) == {"t", "o", "h", "l", "c", "v"}
    assert client.get(f"/api/stocks/{stock_id}/candles?interval=5m").status_code == 400

    created = client.post(
        f"/stocks/{stock_id}/tickets",
        data={"workflow": "topic_analysis", "topic": "Wettbewerb"},
        follow_redirects=False,
    )
    assert created.status_code == 303
    assert (
        client.post(f"/stocks/{stock_id}/tickets", data={"workflow": "topic_analysis"}).status_code
        == 400
    )
    assert (
        client.post(f"/stocks/{stock_id}/tickets", data={"workflow": "initial_holding"}).status_code
        == 404
    )

    with container.session_factory() as s:
        ticket_id = s.scalars(select(Ticket).order_by(Ticket.id.desc())).first().id
    assert "Wettbewerb" in client.get(f"/tickets/{ticket_id}").text
    assert client.get("/tickets?status=queued").status_code == 200
    assert client.post(f"/tickets/{ticket_id}/cancel", follow_redirects=False).status_code == 303
    assert "abgebrochen" in client.get(f"/tickets/{ticket_id}").text
    assert client.post(f"/tickets/{ticket_id}/retry", follow_redirects=False).status_code == 303

    upd = client.post(
        f"/holdings/{holding_id}/update",
        data={"quantity": "20", "avg_price": "140", "intent": "aufstocken"},
        follow_redirects=False,
    )
    assert upd.status_code == 303
    assert (
        client.post(
            f"/holdings/{holding_id}/update",
            data={"quantity": "x", "avg_price": "1"},
        ).status_code
        == 400
    )

    assert client.get("/api/search?q=abc").json()[0]["symbol"] == "ABC"
    assert "System" in client.get("/system").text

    client.post(f"/holdings/{holding_id}/delete")
    client.post(f"/watchlist/{entry_id}/delete")
    with container.session_factory() as s:
        assert s.scalar(select(Holding)) is None and s.scalar(select(WatchEntry)) is None
        assert s.scalar(select(Stock).where(Stock.symbol == "AAPL")) is not None  # knowledge kept


def test_form_errors_show_message_and_keep_input(client):
    bad = client.post("/holdings", data={"symbol": "AAPL", "quantity": "abc", "avg_price": "1"})
    assert bad.status_code == 400 and "keine Zahl" in bad.text and 'value="AAPL"' in bad.text
    assert (
        client.post(
            "/holdings",
            data={"symbol": "AAPL", "quantity": "1", "avg_price": "1", "bought_at": "gestern"},
        ).status_code
        == 400
    )
    assert client.post("/watchlist", data={"symbol": "A B"}).status_code == 400


def test_manual_is_rendered_with_images(client, container, tmp_path):
    docs = tmp_path / "docs"
    (docs / "screenshots").mkdir(parents=True)
    (docs / "user-manual.md").write_text("# Handbuch\n\n![x](screenshots/a.png)\n")
    page = client.get("/manual")
    assert page.status_code == 200 and "/manual-assets/a.png" in page.text
