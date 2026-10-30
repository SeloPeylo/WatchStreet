import itertools
import json

import httpx
import pytest
from sqlalchemy import select

from watchstreet.agents.http_runners import OpenAICompatibleRunner
from watchstreet.constants import LAST_SCAN_KEY, SCAN_REQUEST_KEY
from watchstreet.db import session_scope
from watchstreet.domain import TicketStatus, WorkflowKey
from watchstreet.harness.executor import execute_ticket
from watchstreet.harness.ingest import run_ingest
from watchstreet.harness.scheduler import scan_due
from watchstreet.harness.tripwires import commodity_alerts, quake_alerts
from watchstreet.intel.connectors import usgs
from watchstreet.intel.documents import store_document
from watchstreet.intel.fetch import FetchError
from watchstreet.market.base import Quote
from watchstreet.models import (
    Datapoint,
    Document,
    Entity,
    Feed,
    Insight,
    IntelItem,
    Relation,
    Stock,
    Ticket,
)
from watchstreet.services import datapoints as dps
from watchstreet.services import entities, portfolio, scenarios, tickets
from watchstreet.services.entities import GraphError, RelationInput
from watchstreet.services.state import touch
from watchstreet.worker import drain_queue

CARLIN_SENTENCE = (
    "Our Carlin operations in Nevada, United States produced 900,000 ounces of gold in 2025"
)
ORICA_SENTENCE = (
    "Orica Limited supplies substantially all of the explosives used at our Australian operations"
)
_ids = itertools.count()


def mining_stock(container, located=True, financials=True, mines=True):
    """NEM as a located mining stock with NAV inputs."""
    with container.session_factory() as s:
        portfolio.add_holding(s, container.market, portfolio.NewHolding("NEM", 60, 40.0))
        stock = s.scalar(select(Stock))
        rows = [
            ("commodity_price", "", 2400),
            ("net_debt", "", 6e9),
            ("shares_outstanding", "", 55e6),
            ("mine_production", "Carlin", 900_000),
            ("mine_aisc", "Carlin", 1500),
            ("mine_reserves", "Carlin", 12e6),
            ("mine_production", "Cadia", 500_000),
            ("mine_aisc", "Cadia", 1100),
            ("mine_reserves", "Cadia", 9e6),
        ]
        rows = [r for r in rows if financials or r[0] not in ("net_debt", "shares_outstanding")]
        rows = [r for r in rows if mines or not r[1]]
        for key, subject, value in rows:
            dps.add_datapoint(
                s, stock, dps.DatapointInput(key, subject, value, source="test"), origin="user"
            )
        found = {m.name: m for m in entities.sync_mine_entities(s, stock)}
        if located and mines:
            entities.set_location(found["Carlin"], 40.9, -116.2, "United States")
            entities.set_location(found["Cadia"], -33.4, 149.0, "Australia")
        s.commit()
        return stock.id


def scripted(container, monkeypatch, turns, tools=True):
    state = {"turns": list(turns), "requests": []}

    def handler(request):
        state["requests"].append(json.loads(request.content))
        turn = (
            state["turns"].pop(0)
            if state["turns"]
            else {"choices": [{"message": {"role": "assistant", "content": "fertig"}}]}
        )
        return httpx.Response(200, json=turn)

    runner = OpenAICompatibleRunner("http://llm/v1", "m", "", 5, name="llama", tools_enabled=tools)
    monkeypatch.setattr(runner, "_client", httpx.Client(transport=httpx.MockTransport(handler)))
    container.runner = runner
    return state


def call(tool, **args):
    return {
        "id": f"c{next(_ids)}",
        "type": "function",
        "function": {"name": tool, "arguments": json.dumps(args)},
    }


def turn(*calls):
    return {
        "choices": [{"message": {"role": "assistant", "content": None, "tool_calls": list(calls)}}]
    }


def tool_answers(state, request_index=1):
    return [
        m["content"] for m in state["requests"][request_index]["messages"] if m["role"] == "tool"
    ]


# ------------------------------------------------------------------ graph
def test_relations_need_verified_quotes_and_protect_user_entries(session):
    doc, _ = store_document(
        session, url="https://x/10k", text=f"{ORICA_SENTENCE}. More text.", kind="filing"
    )
    orica = entities.get_or_create_entity(session, "Orica Limited", "supplier", country="australia")
    nem = entities.get_or_create_entity(session, "Demo Gold", "company")
    assert orica.country == "Australia"
    good = entities.add_relation(
        session,
        orica,
        nem,
        RelationInput(
            "supplies",
            0.3,
            document_id=doc.id,
            quote=ORICA_SENTENCE,
            confidence="high",
            origin="agent",
        ),
    )
    assert good.confidence == "high" and good.quote == ORICA_SENTENCE
    for bad in (
        RelationInput("supplies", document_id=doc.id, quote="Orica supplies the moon and stars"),
        RelationInput("supplies", 1.5),
        RelationInput("nonsense"),
    ):
        with pytest.raises(GraphError):
            entities.add_relation(session, orica, nem, bad)
    unsourced = entities.add_relation(
        session, nem, orica, RelationInput("depends_on", confidence="high", origin="agent")
    )
    assert unsourced.confidence == "low"  # no document, no trust
    entities.add_relation(session, nem, orica, RelationInput("depends_on", 0.5, origin="user"))
    with pytest.raises(GraphError, match="geschützt"):
        entities.add_relation(session, nem, orica, RelationInput("depends_on", 0.9, origin="agent"))
    with pytest.raises(GraphError):
        entities.get_or_create_entity(session, " ", "company")
    with pytest.raises(GraphError):
        entities.get_or_create_entity(session, "X", "alien")
    with pytest.raises(GraphError):
        entities.set_location(nem, 123, 0)


def test_graph_neighbourhood_and_country_exposure(container):
    stock_id = mining_stock(container)
    with container.session_factory() as s:
        company = s.scalar(select(Entity).where(Entity.kind == "company"))
        supplier = entities.get_or_create_entity(
            s, "Orica Limited", "supplier", country="Australia"
        )
        entities.add_relation(s, supplier, company, RelationInput("supplies", 0.2, origin="user"))
        other = entities.get_or_create_entity(s, "Far Away Ltd", "supplier")
        entities.add_relation(s, other, supplier, RelationInput("supplies", origin="user"))
        s.commit()
        whole = entities.graph(s)
        near = entities.graph(s, stock_id, depth=1)
        far = entities.graph(s, stock_id, depth=2)
        assert {n["name"] for n in near["nodes"]} >= {"Carlin", "Cadia", "Orica Limited"}
        assert "Far Away Ltd" not in {n["name"] for n in near["nodes"]} and "Far Away Ltd" in {
            n["name"] for n in far["nodes"]
        }
        assert len(whole["edges"]) == 4
        exposure = entities.country_exposure(s, {stock_id: 1000.0})
        # assets weighted by production: Carlin 900k vs Cadia 500k; supplier adds 20 % to Australia
        assert exposure["United States of America"].share == pytest.approx(900 / 1400)
        assert exposure["Australia"].share == pytest.approx(500 / 1400 + 0.2)
        assert {c["via"].split(":")[0] for c in exposure["Australia"].contributions} == {
            "Asset Cadia",
            "supplies",
        }
        assert entities.country_exposure(s, {}) == {}
        assert {a.name for a in entities.assets(s)} == {"Carlin", "Cadia"}


def test_sync_mine_entities_is_idempotent(container):
    mining_stock(container, located=False)
    with container.session_factory() as s:
        stock = s.scalar(select(Stock))
        before = len(list(s.scalars(select(Relation))))
        entities.sync_mine_entities(s, stock)
        assert len(list(s.scalars(select(Relation)))) == before == 2


# ------------------------------------------------------------------ tripwires
def test_quake_tripwire_only_near_assets_and_only_once(container):
    mining_stock(container)
    quakes = usgs.recent_quakes(container.fetcher)
    with container.session_factory() as s:
        assert quake_alerts(s, quakes) == 1  # demo-q1 is near Carlin, demo-q2 is mid-Pacific
        assert quake_alerts(s, quakes) == 0
        item = s.scalar(select(IntelItem))
        assert item.category == "hazard" and item.severity >= 3 and "Carlin" in item.headline
        assert item.document.kind == "gov" and item.document.publisher == "USGS"
        assert item.source_url.startswith("https://quake.demo.example/") and item.author == "rules"
        assert [(i.stock.symbol, i.direction) for i in item.impacts] == [("NEM", "bearish")]
        assert quake_alerts(s, [q for q in quakes if q.magnitude < 5.0]) == 0


def test_commodity_tripwire_uses_exposure_and_dedupes(container, monkeypatch):
    mining_stock(container)
    with container.session_factory() as s:
        stock = s.scalar(select(Stock))
        dps.add_datapoint(
            s, stock, dps.DatapointInput("commodity_symbol", text="GC=F", source="x"), origin="user"
        )
        s.commit()
    quote = Quote("GC=F", 2500.0, 2400.0, "USD", "Gold", "")
    monkeypatch.setattr(container.market, "try_quote", lambda _s: quote)
    with container.session_factory() as s:
        assert commodity_alerts(s, container.market) == 1
        assert commodity_alerts(s, container.market) == 0
        item = s.scalar(select(IntelItem))
        assert (
            item.category == "commodity"
            and item.commodities == ["gold"]
            and "Yahoo" not in item.headline
        )
        assert item.impacts[0].direction == "bullish"  # a gold rally helps a gold miner
    quote2 = Quote("GC=F", 2410.0, 2400.0, "USD", "Gold", "")
    monkeypatch.setattr(container.market, "try_quote", lambda _s: quote2)
    with container.session_factory() as s:
        assert commodity_alerts(s, container.market) == 0  # +0.4 % is noise


# ------------------------------------------------------------------ ingest + triage
def test_ingest_triage_pipeline_end_to_end_offline(container):
    mining_stock(container)
    report = run_ingest(container)
    assert (
        report.errors == [] and report.alerts >= 1 and report.tickets == 1 and report.documents >= 4
    )
    with container.session_factory() as s:
        ticket = s.scalar(select(Ticket).where(Ticket.workflow == WorkflowKey.INTEL_TRIAGE))
        assert ticket.params["document_ids"] and ticket.priority < 50
        assert {f.last_error for f in s.scalars(select(Feed))} == {""}
    assert run_ingest(container).documents == 0  # same URLs and content: nothing new
    drain_queue(container)
    with container.session_factory() as s:
        done = s.scalar(select(Ticket).where(Ticket.workflow == WorkflowKey.INTEL_TRIAGE))
        assert done.status == TicketStatus.DONE, done.error
        news = [i for i in s.scalars(select(IntelItem)) if i.document and i.document.kind == "news"]
        assert len(news) >= 2
        strike = next(i for i in news if "Streik" in i.headline)
        assert (
            strike.category == "geopolitics" and strike.severity == 3 and strike.author == "rules"
        )
        assert (
            strike.impacts[0].direction == "bearish"
            and strike.quote
            and strike.source_url.startswith("https://news.demo.example/")
        )


def test_scan_due_honours_manual_requests(container):
    with session_scope(container.session_factory) as s:
        touch(s, LAST_SCAN_KEY)
    assert not scan_due(container)
    with session_scope(container.session_factory) as s:
        touch(s, SCAN_REQUEST_KEY)
    assert scan_due(container)


def test_feed_failures_are_recorded_and_disable_the_feed(container, monkeypatch):
    mining_stock(container)

    def broken(_url):
        raise FetchError("boom")

    monkeypatch.setattr(container.fetcher, "fetch", broken)
    for _ in range(5):
        report = run_ingest(container)
    assert any("boom" in e for e in report.errors)
    with container.session_factory() as s:
        feeds = list(s.scalars(select(Feed)))
        assert all(
            not f.enabled and f.last_error == "boom" for f in feeds if f.kind in ("rss", "usgs")
        )


# ------------------------------------------------------------------ SEC sync + filing reading
def test_sec_sync_stores_filings_and_deterministic_xbrl_datapoints(container):
    mining_stock(container, financials=False)
    with container.session_factory() as s:
        stock = s.scalar(select(Stock))
        t = tickets.create_ticket(s, stock, WorkflowKey.SEC_SYNC)
        s.commit()
        tid = t.id
    assert execute_ticket(container, tid) == TicketStatus.DONE
    with container.session_factory() as s:
        ticket = s.get(Ticket, tid)
        assert "2 neue Einreichung" in ticket.summary and "XBRL" in ticket.summary
        docs = {
            d.meta["form"]: d for d in s.scalars(select(Document).where(Document.kind == "filing"))
        }
        assert (
            "Item 2. Properties" in docs["10-K"].text
            and docs["8-K"].text == "Current report (demo)"
        )
        sec = [d for d in s.scalars(select(Datapoint)) if d.origin == "api"]
        assert {(d.key, d.confidence) for d in sec} == {
            ("shares_outstanding", "high"),
            ("net_debt", "high"),
        }
        assert all("companyfacts" in d.source for d in sec)
        assert {i.dedupe_key.split(":")[0] for i in s.scalars(select(IntelItem))} == {"filing"}
        assert not ticket.children  # offline runner cannot read filings: no follow-up
    with container.session_factory() as s:
        t2 = tickets.create_ticket(s, s.scalar(select(Stock)), WorkflowKey.SEC_SYNC)
        s.commit()
        tid2 = t2.id
    execute_ticket(container, tid2)
    with container.session_factory() as s:
        assert "0 neue Einreichung" in s.get(Ticket, tid2).summary


def test_sec_sync_never_overwrites_user_values(container):
    mining_stock(container)  # user already entered net debt and shares
    with container.session_factory() as s:
        t = tickets.create_ticket(s, s.scalar(select(Stock)), WorkflowKey.SEC_SYNC)
        s.commit()
        tid = t.id
    assert execute_ticket(container, tid) == TicketStatus.DONE
    with container.session_factory() as s:
        assert not [d for d in s.scalars(select(Datapoint)) if d.origin == "api"]
        assert {d.value for d in s.scalars(select(Datapoint)) if d.key == "net_debt"} == {6e9}


def test_sec_sync_proposes_reading_only_with_a_tool_capable_agent(container, monkeypatch):
    mining_stock(container)
    scripted(container, monkeypatch, [])
    with container.session_factory() as s:
        t = tickets.create_ticket(s, s.scalar(select(Stock)), WorkflowKey.SEC_SYNC)
        s.commit()
        tid = t.id
    execute_ticket(container, tid)
    with container.session_factory() as s:
        child = s.scalar(select(Ticket).where(Ticket.parent_id == tid))
        assert child.workflow == WorkflowKey.READ_FILING and child.params["topic"].startswith(
            "doc:"
        )


def test_sec_sync_without_cik_and_without_edgar(container):
    with container.session_factory() as s:
        portfolio.add_holding(s, container.market, portfolio.NewHolding("KO", 1, 10.0))
        s.commit()
        t = tickets.create_ticket(s, s.scalar(select(Stock)), WorkflowKey.SEC_SYNC)
        s.commit()
        tid = t.id
    execute_ticket(container, tid)
    with container.session_factory() as s:
        assert "Kein SEC-Eintrag" in s.get(Ticket, tid).summary


def read_filing_ticket(container):
    with container.session_factory() as s:
        stock = s.scalar(select(Stock))
        sync = tickets.create_ticket(s, stock, WorkflowKey.SEC_SYNC)
        s.commit()
        execute_ticket(container, sync.id)
        doc = s.scalar(select(Document).where(Document.url.like("%demo-10k.htm")))
        ticket = tickets.create_ticket(s, stock, WorkflowKey.READ_FILING, topic=f"doc:{doc.id}")
        s.commit()
        return ticket.id, doc.id


def test_read_filing_extracts_only_what_it_can_quote(container, monkeypatch):
    mining_stock(container, located=False, mines=False)
    tid, doc_id = read_filing_ticket(container)
    state = scripted(
        container,
        monkeypatch,
        [
            turn(
                call("list_sections"),
                call("search_document", query="carlin ounces"),
                call(
                    "record_datapoint",
                    key="mine_production",
                    subject="Carlin",
                    value=900000,
                    unit="oz",
                    source="10-K",
                    confidence="high",
                    quote=CARLIN_SENTENCE,
                ),
                call(
                    "record_datapoint",
                    key="mine_aisc",
                    subject="Carlin",
                    value=999,
                    source="10-K",
                    confidence="high",
                    quote="Carlin AISC was famously only 999 dollars per ounce",
                ),
                call(
                    "record_relation",
                    **{
                        "from": "Orica Limited",
                        "from_kind": "supplier",
                        "to": "SELF",
                        "to_kind": "company",
                        "relation": "supplies",
                        "country": "Australia",
                        "quote": ORICA_SENTENCE,
                    },
                ),
                call(
                    "record_relation",
                    **{
                        "from": "Caterpillar Inc.",
                        "to": "SELF",
                        "relation": "supplies",
                        "quote": "Caterpillar delivers every truck we have ever owned",
                    },
                ),
                call(
                    "record_asset",
                    name="Carlin",
                    kind="mine",
                    country="United States",
                    lat=40.9,
                    lon=-116.2,
                    ownership=1.0,
                    quote=CARLIN_SENTENCE,
                ),
                call(
                    "add_insight",
                    category="risk",
                    text="Abhängig von wenigen Zulieferern",
                    quote="We rely on a limited number of suppliers, which exposes us to supply interruptions.",
                ),
                call(
                    "add_insight",
                    category="risk",
                    text="Erfunden",
                    quote="Es gibt keine Risiken irgendwo.",
                ),
            ),
        ],
    )
    assert execute_ticket(container, tid) == TicketStatus.DONE
    answers = tool_answers(state)
    assert json.loads(answers[0])[0]["heading"].startswith("Item 1")
    assert "900,000" in answers[1] and answers[2] == "recorded"
    assert (
        "quote not found" in answers[3]
        and answers[4] == "recorded"
        and "quote not found" in answers[5]
    )
    assert answers[6] == "recorded" and answers[7] == "recorded" and "quote not found" in answers[8]
    with container.session_factory() as s:
        point = s.scalar(
            select(Datapoint).where(Datapoint.key == "mine_production", Datapoint.origin == "agent")
        )
        assert (point.document_id, point.confidence, point.quote) == (
            doc_id,
            "high",
            CARLIN_SENTENCE,
        )
        assert (
            s.scalar(
                select(Datapoint).where(Datapoint.key == "mine_aisc", Datapoint.origin == "agent")
            )
            is None
        )
        rel = s.scalar(select(Relation).where(Relation.kind == "supplies"))
        assert (
            s.get(Entity, rel.source_id).name == "Orica Limited"
            and s.get(Entity, rel.source_id).country == "Australia"
        )
        assert rel.document_id == doc_id and rel.confidence == "medium" and rel.origin == "agent"
        assert s.get(Entity, rel.target_id).kind == "company"
        carlin = s.scalar(select(Entity).where(Entity.name == "Carlin"))
        assert (carlin.lat, carlin.lon, carlin.country) == (
            40.9,
            -116.2,
            "United States of America",
        )
        cited = s.scalar(select(Insight).where(Insight.text.like("Abhängig%")))
        assert cited.document_id == doc_id
        assert s.scalar(select(Insight).where(Insight.text == "Erfunden")) is None
        assert s.get(Ticket, tid).result["data"]["document_id"] == doc_id


def test_read_filing_needs_a_tool_capable_agent(container):
    mining_stock(container)
    tid, _doc = read_filing_ticket(container)
    assert execute_ticket(container, tid) == TicketStatus.FAILED
    with container.session_factory() as s:
        assert "Tool-Unterstützung" in s.get(Ticket, tid).error


# ------------------------------------------------------------------ intel triage with agents
def triage_ticket(container):
    mining_stock(container)
    with container.session_factory() as s:
        stock = s.scalar(select(Stock))
        docs = [
            store_document(
                s,
                url=f"https://news.example/{i}",
                kind="news",
                publisher="Wire",
                title=title,
                text=f"{title}\n{body}",
            )[0]
            for i, (title, body) in enumerate(
                [
                    (
                        "Gewerkschaft ruft Streik in Carlin aus",
                        "Die Gewerkschaft kündigte unbefristete Arbeitsniederlegung an.",
                    ),
                    ("Irrelevante Meldung über Fußball", "Ergebnisse vom Wochenende."),
                ]
            )
        ]
        ticket = tickets.create_ticket(
            s, stock, WorkflowKey.INTEL_TRIAGE, params={"document_ids": [d.id for d in docs]}
        )
        s.commit()
        return ticket.id, [d.id for d in docs]


def test_intel_triage_tool_mode_publishes_grounded_items(container, monkeypatch):
    tid, (relevant, _other) = triage_ticket(container)
    state = scripted(
        container,
        monkeypatch,
        [
            turn(
                call("get_document", document_id=relevant),
                call(
                    "publish_intel",
                    document_id=relevant,
                    headline="Streik im Carlin-Revier",
                    summary="Gewerkschaft droht.",
                    why_it_matters="Carlin liefert den größten Teil der Produktion.",
                    category="geopolitics",
                    severity=4,
                    direction="bearish",
                    country="USA",
                    commodities=["gold"],
                    quote="Die Gewerkschaft kündigte unbefristete Arbeitsniederlegung an.",
                ),
                call(
                    "publish_intel",
                    document_id=relevant,
                    headline="Erfunden",
                    why_it_matters="x",
                    category="company",
                    severity=2,
                    direction="bullish",
                    quote="Newmont verdoppelt die Dividende morgen früh",
                ),
                call(
                    "publish_intel",
                    document_id=99999,
                    headline="Fremd",
                    why_it_matters="x",
                    quote="irrelevant genug zum Zitieren hier",
                    category="company",
                    severity=2,
                    direction="unknown",
                ),
                call(
                    "publish_intel",
                    document_id=relevant,
                    headline="Schlecht",
                    why_it_matters="x",
                    category="bogus",
                    severity=9,
                    direction="bearish",
                    quote="Die Gewerkschaft kündigte unbefristete Arbeitsniederlegung an.",
                ),
            )
        ],
    )
    assert execute_ticket(container, tid) == TicketStatus.DONE
    answers = tool_answers(state)
    assert "Carlin" in answers[0] and answers[1] == "published" and "quote not found" in answers[2]
    assert "document_id must be one of" in answers[3] and answers[4].startswith("ERROR")
    assert [t["function"]["name"] for t in state["requests"][0]["tools"]] == [
        "get_document",
        "get_knowledge",
        "publish_intel",
    ]
    with container.session_factory() as s:
        item = s.scalar(select(IntelItem))
        assert (item.headline, item.severity, item.author, item.country) == (
            "Streik im Carlin-Revier",
            4,
            "agent",
            "United States of America",
        )
        assert (
            item.lat is not None and item.document_id == relevant and item.commodities == ["gold"]
        )
        assert [(i.stock.symbol, i.direction) for i in item.impacts] == [("NEM", "bearish")]


def test_intel_triage_json_mode_drops_items_with_unverifiable_quotes(container, monkeypatch):
    tid, (relevant, other) = triage_ticket(container)
    answer = {
        "summary": "zwei Quellen geprüft",
        "intel": [
            {
                "document_id": relevant,
                "headline": "Streik",
                "why_it_matters": "Produktion",
                "category": "geopolitics",
                "severity": 4,
                "direction": "bearish",
                "quote": "Die Gewerkschaft kündigte unbefristete Arbeitsniederlegung an.",
            },
            {
                "document_id": other,
                "headline": "Fußball",
                "why_it_matters": "nichts",
                "quote": "Das Spiel endete drei zu zwei nach Verlängerung.",
            },
            {
                "document_id": 424242,
                "headline": "Phantom",
                "quote": "Ein Zitat aus einem Dokument, das es nicht gibt.",
            },
        ],
    }
    scripted(
        container,
        monkeypatch,
        [{"choices": [{"message": {"content": json.dumps(answer)}}]}],
        tools=False,
    )
    assert execute_ticket(container, tid) == TicketStatus.DONE
    with container.session_factory() as s:
        assert [i.headline for i in s.scalars(select(IntelItem))] == ["Streik"]


# ------------------------------------------------------------------ scenarios
def test_nav_scenarios_move_with_the_commodity_price(container):
    mining_stock(container)
    with container.session_factory() as s:
        stock = s.scalar(select(Stock))
        rows = scenarios.mining_scenarios(container.market, stock, (-0.2, -0.1, 0.0, 0.1, 0.2))
        navs = [r.nav_per_share for r in rows]
        assert navs == sorted(navs) and len(set(navs)) == 5
        assert (
            rows[2].nav_change_pct == 0 and rows[4].nav_change_pct > 20 > 0 > rows[0].nav_change_pct
        )
        assert (
            all(r.p_nav for r in rows) and rows[0].p_nav > rows[4].p_nav
        )  # cheaper NAV, higher multiple
        plain = Stock(symbol="ZZZ", name="n", profile="generic")
        assert scenarios.mining_scenarios(container.market, plain, (0.0,)) == []
