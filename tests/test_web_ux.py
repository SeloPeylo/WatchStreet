"""UX behaviour of the web layer: flash messages, live status API, quick-jump data, a11y hooks."""

from sqlalchemy import select

from watchstreet.models import Stock, Ticket
from watchstreet.web.flash import FLASH_MESSAGES, with_flash


def add_holding(client, symbol="AAPL"):
    return client.post(
        "/holdings",
        data={"symbol": symbol, "quantity": "2", "avg_price": "10"},
        follow_redirects=False,
    )


def test_with_flash_handles_query_and_fragment():
    assert with_flash("/a", None) == "/a"
    assert with_flash("/a", "x") == "/a?flash=x"
    assert with_flash("/a?b=1", "x") == "/a?b=1&flash=x"
    assert with_flash("/a#frag", "x") == "/a?flash=x#frag"


def test_every_mutation_redirects_with_known_flash(client):
    res = add_holding(client)
    assert res.status_code == 303
    assert res.headers["location"] == "/holdings?flash=holding_added"
    page = client.get("/holdings?flash=holding_added").text
    assert FLASH_MESSAGES["holding_added"] in page and "data-flash" in page


def test_unknown_flash_code_is_ignored_and_never_reflected(client):
    page = client.get("/holdings?flash=<script>alert(1)</script>").text
    assert "<script>alert(1)" not in page and "data-flash" not in page


def test_watch_and_delete_flash(client):
    res = client.post("/watchlist", data={"symbol": "MSFT"}, follow_redirects=False)
    assert res.headers["location"] == "/watchlist?flash=watch_added"
    res = client.post("/watchlist/1/delete", follow_redirects=False)
    assert res.headers["location"] == "/watchlist?flash=watch_removed"


def test_error_response_is_announced_as_alert(client):
    add_holding(client)
    res = add_holding(client)
    assert res.status_code == 400
    assert 'role="alert"' in res.text and "bereits" in res.text


def test_ticket_status_api(client, container):
    add_holding(client)
    with container.session_factory() as s:
        ids = [t.id for t in s.scalars(select(Ticket))]
    assert ids
    rows = client.get("/api/tickets/status", params={"ids": ",".join(map(str, ids))}).json()
    assert {r["id"] for r in rows} == set(ids)
    assert all(r["status"] for r in rows)
    assert client.get("/api/tickets/status").json() == []
    assert client.get("/api/tickets/status", params={"ids": "x,,-1"}).json() == []


def test_ticket_pages_carry_live_markers(client, container):
    add_holding(client)
    with container.session_factory() as s:
        ticket = s.scalars(select(Ticket)).first()
        tid = ticket.id
    page = client.get(f"/tickets/{tid}").text
    assert f'data-ticket-id="{tid}"' in page and "data-live-reload" in page
    assert "data-sortable" in client.get("/tickets").text


def test_stock_list_api_for_palette(client, container):
    assert client.get("/api/stocks").json() == []
    add_holding(client, "NEM")
    with container.session_factory() as s:
        stock = s.scalar(select(Stock))
        sid = stock.id
    rows = client.get("/api/stocks").json()
    assert rows[0]["id"] == sid and rows[0]["symbol"] == "NEM"


def test_layout_has_a11y_and_nav_hooks(client):
    page = client.get("/holdings").text
    assert 'class="skip"' in page and 'id="main"' in page
    assert 'aria-current="page"' in page
    assert 'id="palette"' in page and 'id="help"' in page
    for script in ("app.js", "tables.js", "live.js"):
        assert client.get(f"/static/{script}").status_code == 200


def test_destructive_forms_ask_for_confirmation(client):
    add_holding(client)
    page = client.get("/holdings").text
    assert "data-confirm" in page and "onsubmit" not in page


def test_tickets_filter_empty_state_offers_next_step(client):
    page = client.get("/tickets?status=failed").text
    assert "Keine Tickets mit diesem Status" in page
    assert "Position einträgst" in client.get("/tickets").text
