import pytest
from sqlalchemy import select

from watchstreet.domain import WorkflowKey
from watchstreet.harness.executor import execute_ticket
from watchstreet.models import Briefing, Datapoint, Stock, Ticket
from watchstreet.profiles.classify import classify
from watchstreet.profiles.derive import DeriveInput, Point, annuity, derive_mining, derive_oil_gas
from watchstreet.profiles.registry import PANELS, PROFILES
from watchstreet.services import datapoints as dps
from watchstreet.services import portfolio, tickets
from watchstreet.services.profiles import assign_profile
from watchstreet.worker import drain_queue


@pytest.mark.parametrize(
    ("sector", "industry", "expected"),
    [
        ("Basic Materials", "Gold", "mining"),
        ("Basic Materials", "Other Industrial Metals & Mining", "mining"),
        ("Energy", "Oil & Gas E&P", "oil_gas"),
        ("Utilities", "Utilities - Regulated Electric", "utility"),
        ("Real Estate", "REIT - Retail", "reit"),
        ("Financial Services", "Banks - Diversified", "financial"),
        ("Technology", "Software - Application", "tech"),
        ("Healthcare", "Biotechnology", "healthcare"),
        ("Consumer Defensive", "Beverages", None),
    ],
)
def test_classification(sector, industry, expected):
    assert classify(sector, industry) == expected


def test_every_profile_is_consistent():
    for profile in PROFILES.values():
        assert set(profile.lens) <= set(PANELS) and len(set(profile.lens)) == len(profile.lens)
        keys = {d.key for d in profile.datapoints}
        assert set(profile.core_metrics) <= {c.key for c in profile.criteria}
        assert profile.scheme.startswith("valuation")
        assert len(keys) == len(profile.datapoints)


def test_annuity():
    assert annuity(100, 0, 5) == 500
    assert annuity(100, 0.1, 2) == pytest.approx(173.55, abs=0.01)
    assert annuity(100, 0.1, 0) == 0


def mine(name, production, aisc, reserves, own=None):
    pts = [
        Point("mine_production", name, production),
        Point("mine_aisc", name, aisc),
        Point("mine_reserves", name, reserves),
    ]
    return pts + ([Point("mine_ownership", name, own)] if own else [])


def test_mining_nav_math():
    points = [
        *mine("A", 100, 1000, 1000),
        *mine("B", 50, 2500, 500, own=0.5),
        Point("net_debt", value=10_000),
        Point("shares_outstanding", value=1000),
        Point("discount_rate", value=0.0),
    ]
    out = derive_mining(
        DeriveInput({}, points, price=200.0, currency="USD", commodity_price=2000.0)
    )
    rows = {r["mine"]: r for r in out.breakdown["mines"]}
    assert rows["A"]["npv"] == pytest.approx(100 * 1000 * 10)  # margin 1000 x 100 oz x 10 yrs
    assert rows["B"]["npv"] == 0  # AISC above the commodity price -> no value
    assert out.breakdown["gross_nav"] == pytest.approx(1_000_000)
    assert out.breakdown["nav_per_share"] == pytest.approx((1_000_000 - 10_000) / 1000)
    assert out.metrics["p_nav"] == pytest.approx(200 / 990)
    assert out.metrics["reserve_life_years"] == pytest.approx((10 * 100 + 10 * 50) / 150)
    assert 0 < out.metrics["aisc_margin_pct"] < 50


def test_mining_reports_missing_inputs_instead_of_guessing():
    out = derive_mining(DeriveInput({}, [], price=10.0, currency="CAD", commodity_price=None))
    assert any("Rohstoffpreis" in m for m in out.missing)
    assert any("Mine" in m for m in out.missing)
    assert not out.metrics
    partial = [Point("mine_production", "A", 10)]
    out = derive_mining(DeriveInput({}, partial, 10.0, "USD", commodity_price=100.0))
    assert any("Mine 'A'" in m for m in out.missing)


def test_mining_currency_mismatch_needs_fx():
    points = [
        *mine("A", 100, 1000, 1000),
        Point("net_debt", value=0),
        Point("shares_outstanding", value=10),
    ]
    out = derive_mining(DeriveInput({}, points, 50.0, "CAD", commodity_price=2000.0))
    assert any("Wechselkurs" in m for m in out.missing) and "p_nav" not in out.metrics
    points.append(Point("fx_rate", value=1.3))
    out = derive_mining(DeriveInput({}, points, 50.0, "CAD", commodity_price=2000.0))
    assert "p_nav" in out.metrics


def test_oil_gas_margin_and_fcf():
    points = [
        Point("breakeven_price", value=50),
        Point("reserves", value=1000),
        Point("production", value=100),
        Point("free_cash_flow", value=500),
    ]
    out = derive_oil_gas(DeriveInput({"market_cap": 10_000}, points, 10.0, "USD", 80.0))
    assert out.metrics == {
        "commodity_margin_pct": pytest.approx(37.5),
        "reserve_life_years": 10,
        "fcf_yield": 5,
    }


def test_profile_precedence():
    stock = Stock(symbol="X")
    assert assign_profile(stock, "tech", "auto")
    assert assign_profile(stock, "mining", "agent")
    assert not assign_profile(stock, "tech", "auto")  # lower rank cannot override
    assert assign_profile(stock, "utility", "user")
    assert not assign_profile(stock, "mining", "agent")
    assert not assign_profile(stock, "nonsense", "user")
    assert stock.profile == "utility"


def add_stock(container, symbol, profile=None):
    with container.session_factory() as s:
        portfolio.add_holding(s, container.market, portfolio.NewHolding(symbol, 10, 50.0))
        if profile:
            stock = s.scalar(select(Stock).where(Stock.symbol == symbol))
            assign_profile(stock, profile, "user")
        s.commit()


def test_intake_classifies_from_company_info(container):
    for symbol, profile in (
        ("NEM", "mining"),
        ("XOM", "oil_gas"),
        ("KO", "generic"),
        ("AAPL", "tech"),
    ):
        add_stock(container, symbol)
        with container.session_factory() as s:
            assert s.scalar(select(Stock).where(Stock.symbol == symbol)).profile == profile


def test_datapoint_validation_and_user_protection(container):
    add_stock(container, "NEM")
    with container.session_factory() as s:
        stock = s.scalar(select(Stock))
        for bad in (
            dps.DatapointInput("nope", value=1),
            dps.DatapointInput("mine_aisc", value=1),
            dps.DatapointInput("net_debt", subject="A", value=1),
            dps.DatapointInput("net_debt"),
            dps.DatapointInput("commodity_symbol"),
            dps.DatapointInput("net_debt", value=1, confidence="sure"),
        ):
            with pytest.raises(dps.DatapointError):
                dps.add_datapoint(s, stock, bad, origin="user")
        dps.add_datapoint(s, stock, dps.DatapointInput("net_debt", value=5), origin="user")
        with pytest.raises(dps.DatapointError, match="geschützt"):
            dps.add_datapoint(s, stock, dps.DatapointInput("net_debt", value=9), origin="agent")
        dps.add_datapoint(s, stock, dps.DatapointInput("net_debt", value=6), origin="user")
        assert [p.value for p in dps.latest(stock) if p.key == "net_debt"] == [6]


def test_mining_valuation_end_to_end_via_web(client, container):
    add_stock(container, "NEM")
    drain_queue(container)
    with container.session_factory() as s:
        stock = s.scalar(select(Stock))
        sid = stock.id
        provisional = next(x for x in stock.scores if x.scheme == "valuation_mining_v1")
        assert provisional.details["provisional"] is True and provisional.details["missing"]
    entries = [
        {"key": "commodity_price", "value": "2000", "unit": "USD/oz", "source": "test"},
        {"key": "net_debt", "value": "100", "source": "test"},
        {"key": "shares_outstanding", "value": "10", "source": "test"},
        {"key": "mine_production", "subject": "Carlin", "value": "100", "source": "10-K"},
        {"key": "mine_aisc", "subject": "Carlin", "value": "1200", "source": "10-K"},
        {"key": "mine_reserves", "subject": "Carlin", "value": "1500", "source": "10-K"},
    ]
    for entry in entries:
        assert (
            client.post(f"/stocks/{sid}/datapoints", data=entry, follow_redirects=False).status_code
            == 303
        )
    drain_queue(container)
    with container.session_factory() as s:
        newest = s.scalars(select(Stock)).one().scores[0]
        assert newest.scheme == "valuation_mining_v1" and newest.details["provisional"] is False
        assert newest.details["breakdown"]["mines"][0]["mine"] == "Carlin"
        assert "p_nav" in {c["key"] for c in newest.details["criteria"]}
    page = client.get(f"/stocks/{sid}").text
    assert "Net Asset Value" in page and "Carlin" in page and "Worauf es jetzt ankommt" in page
    bad = client.post(
        f"/stocks/{sid}/datapoints", data={"key": "mine_aisc", "value": "1", "source": "x"}
    )
    assert bad.status_code == 400 and "braucht einen Bezug" in bad.text
    point_id = None
    with container.session_factory() as s:
        point_id = s.scalar(select(Datapoint.id).where(Datapoint.key == "net_debt"))
    assert client.post(f"/datapoints/{point_id}/delete", follow_redirects=False).status_code == 303


def test_profile_change_via_web_requeues_valuation(client, container):
    add_stock(container, "AAPL")
    drain_queue(container)
    with container.session_factory() as s:
        sid = s.scalar(select(Stock.id))
    assert client.post(f"/stocks/{sid}/profile", data={"profile": "utility"}).status_code == 200
    assert client.post(f"/stocks/{sid}/profile", data={"profile": "bogus"}).status_code == 400
    drain_queue(container)
    with container.session_factory() as s:
        stock = s.scalar(select(Stock))
        assert (stock.profile, stock.profile_source) == ("utility", "user")
        assert stock.scores[0].scheme == "valuation_utility_v1"


def test_lens_order_differs_per_profile(client, container):
    add_stock(container, "NEM")
    add_stock(container, "AAPL")
    drain_queue(container)
    with container.session_factory() as s:
        ids = {st.symbol: st.id for st in s.scalars(select(Stock))}
    mining, tech = (client.get(f"/stocks/{ids[x]}").text for x in ("NEM", "AAPL"))
    assert mining.index('id="valuation"') < mining.index('id="chart-panel"')
    assert tech.index('id="chart-panel"') < tech.index('id="valuation"')


def test_briefing_follows_every_finished_ticket_and_is_deduplicated(container):
    add_stock(container, "NEM")
    drain_queue(container)
    with container.session_factory() as s:
        briefings = s.scalars(select(Ticket).where(Ticket.workflow == WorkflowKey.BRIEFING)).all()
        assert len(briefings) == 1  # one after the whole chain, not one per ticket
        stock = s.scalar(select(Stock))
        latest = list(s.scalars(select(Briefing)))[-1]
        assert "Minen" in latest.headline and "vorläufig" in latest.headline
        assert latest.focus == "evidence" and any("Datenlücken" in b for b in latest.bullets)
        assert latest.author == "rules"
        tickets.ensure_open(s, stock, WorkflowKey.BRIEFING, origin="user")
        s.commit()
    assert execute_ticket(container, 1)


def test_offline_research_lists_gaps_and_classify_workflow(container):
    add_stock(container, "NEM")
    drain_queue(container)
    with container.session_factory() as s:
        stock = s.scalar(select(Stock))
        research = tickets.create_ticket(s, stock, WorkflowKey.RESEARCH_DATAPOINTS)
        classify_t = tickets.create_ticket(s, stock, WorkflowKey.CLASSIFY_STOCK)
        s.commit()
    drain_queue(container)
    with container.session_factory() as s:
        assert "nicht recherchieren" in s.get(Ticket, research.id).summary
        assert "mining" in s.get(Ticket, classify_t.id).summary
        assert s.scalar(select(Stock)).profile == "mining"
