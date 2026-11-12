"""The explorer end to end on the synthetic demo world: API, research loop, engine, portfolio."""

import json
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import select

from watchstreet.agents.tools import ToolRun
from watchstreet.domain import DataOrigin, Provenance, SubjectType, TicketStatus
from watchstreet.harness.executor import execute_ticket
from watchstreet.harness.scan import run_scan, scan_due
from watchstreet.intel.connectors.usgs import Quake
from watchstreet.intel.fetch import Fetcher
from watchstreet.models import Asset, Company, Document, Event, Fact, Finding, Proposal, Ticket
from watchstreet.services import proposals
from watchstreet.services.events import record_quakes
from watchstreet.services.facts import FactError, FactInput, record_fact
from watchstreet.worker import drain_queue, tick

API = "/api/v1"


def _asset(session, name: str) -> Asset:
    return session.scalars(select(Asset).where(Asset.name == name)).one()


def _metric(card: dict, key: str) -> dict:
    return next(m for m in (*card["metrics"], *card["economics"]) if m["metric"] == key)


# --- map, cards, time and scenario --------------------------------------------------


def test_commodities_and_map(client):
    bar = client.get(f"{API}/commodities").json()
    assert [c["key"] for c in bar] == ["gold", "silver", "copper", "uranium"] and bar[0]["price"]
    world = client.get(f"{API}/map").json()
    assert len(world["features"]) == 19 and all(
        f["properties"]["is_demo"] for f in world["features"]
    )
    copper = client.get(f"{API}/map", params={"commodity": "copper", "color": "margin"}).json()
    names = {f["properties"]["name"]: f["properties"] for f in copper["features"]}
    assert len(names) == 7 and names["Demo Mina Altiplano"]["color_known"]
    # unknown must not look like the middle of the scale
    assert not names["Demo Mina Laguna Clara"]["color_known"]
    assert not names["Demo Projekt Cobre Alto"]["color_known"]  # forecasts are not coloured
    assert client.get(f"{API}/map", params={"color": "nope"}).status_code == 422
    assert client.get(f"{API}/commodities/copper/prices").json()[0]["close"] > 0
    assert client.get(f"{API}/commodities/zinc/prices").status_code == 404


def test_card_shows_provenance_and_derived_economics(client, session):
    asset = _asset(session, "Demo Mina Altiplano")
    detail = client.get(f"{API}/assets/{asset.id}").json()
    card = detail["card"]
    assert card["status"] == "production" and card["operator"] == "Demo Andes Copper Corp"
    aisc = _metric(card, "aisc")
    assert aisc["value"] == 2.05 and aisc["provenance"] == "reported" and aisc["basis"]
    assert _metric(card, "grade")["provenance"] == "unknown"
    margin = _metric(card, "margin")
    assert margin["provenance"] == "derived" and margin["input_fact_ids"]
    assert detail["milestones"][0]["kind"] == "discovery" and detail["documents"]
    derivation = client.get(f"{API}/assets/{asset.id}/facts/aisc").json()
    assert len(derivation["history"]) == 2 and derivation["history"][0]["quote"].startswith(
        "All-in"
    )
    assert derivation["history"][0]["document"]["is_demo"]
    assert client.get(f"{API}/assets/{asset.id}/facts/nope").status_code == 404
    assert client.get(f"{API}/assets/99999").status_code == 404


def test_reference_date_separates_known_then_from_hindsight(client, session):
    asset = _asset(session, "Demo Mina Altiplano")
    at = {"asof": "2025-12-31"}
    then = client.get(f"{API}/assets/{asset.id}", params=at).json()["card"]
    assert _metric(then, "aisc")["value"] == 1.91 and then["mode"] == "as_of"
    hindsight = client.get(f"{API}/assets/{asset.id}", params={**at, "view": "hindsight"}).json()
    assert _metric(hindsight["card"], "aisc")["value"] == 2.05
    early = client.get(f"{API}/assets/{asset.id}", params={"asof": "2015-01-01"}).json()["card"]
    assert (
        early["status"] == "development"
        and _metric(early, "study_stage")["provenance"] == "unknown"
    )
    before = client.get(f"{API}/map", params={"asof": "2000-01-01"}).json()
    assert before["features"] == []


def test_scenario_recolours_the_map_and_marks_the_mode(client, session):
    asset = _asset(session, "Demo Mina Kupferberg")
    scenario = {"scenario": "copper:3.0", "color": "delta"}
    card = client.get(f"{API}/cards", params={"ids": str(asset.id), **scenario}).json()[0]
    assert card["mode"] == "scenario" and card["price"] == 3.0
    assert _metric(card, "margin")["value"] == pytest.approx(-1.4)
    world = client.get(f"{API}/map", params=scenario).json()
    kupferberg = next(f for f in world["features"] if f["id"] == asset.id)["properties"]
    assert kupferberg["color_value"] < 0
    assert client.get(f"{API}/map", params={"scenario": "zinc:1"}).status_code == 422
    assert client.get(f"{API}/map", params={"scenario": "copper:x"}).status_code == 422


def test_compare_company_and_search(client, session):
    a, b = _asset(session, "Demo Mina Altiplano"), _asset(session, "Demo Projekt Vecino")
    compared = client.get(f"{API}/compare", params={"ids": f"{a.id},{b.id}"}).json()
    assert len(compared["cards"]) == 2
    lane = next(lane for lane in compared["lanes"] if lane["asset_id"] == a.id)
    assert lane["milestones"][0]["years"] == 0.0 and lane["milestones"][-1]["years"] > 8
    company = client.get(f"{API}/companies/{a.stakes[0].company_id}").json()
    assert {c["name"] for c in company["assets"]} == {"Demo Mina Altiplano", "Demo Mina Río Seco"}
    hits = client.get(f"{API}/search", params={"q": "vecino"}).json()
    assert (
        hits[0]["type"] == "asset" and client.get(f"{API}/search", params={"q": "x"}).json() == []
    )
    assert {h["type"] for h in client.get(f"{API}/search", params={"q": "kupfer"}).json()} == {
        "asset",
        "thesis",
    }


# --- evidence rules -------------------------------------------------------------------


def test_fact_rules(session):
    asset = _asset(session, "Demo Mina Altiplano")
    document = session.scalars(select(Document)).first()

    def attempt(**kwargs):
        return record_fact(session, FactInput(SubjectType.ASSET, asset.id, **kwargs))

    for bad in (
        {"metric_key": "nope", "value": 1.0},
        {"metric_key": "grade"},
        {"metric_key": "aisc", "value": 2.0},  # cost without definition
        {"metric_key": "grade", "value": 1.0, "provenance": "unknown"},
        {"metric_key": "grade", "value": 1.0, "claim_kind": "x"},
        {"metric_key": "grade", "value": 1.0, "confidence": "x"},
        {"metric_key": "grade", "low": 3.0, "high": 1.0},
        {"metric_key": "study_stage"},
        {"metric_key": "grade", "value": 1.0, "provenance": Provenance.DERIVED},
        {"metric_key": "grade", "value": 1.0, "provenance": Provenance.ESTIMATED},
        {"metric_key": "grade", "value": 1.0, "origin": DataOrigin.AGENT},  # reported, no source
        {"metric_key": "grade", "value": 1.0, "quote": "x" * 30},
        {
            "metric_key": "grade",
            "value": 1.0,
            "document_id": document.id,
            "quote": "not in there " * 3,
        },
    ):
        with pytest.raises(FactError):
            attempt(**bad)
    estimate = attempt(
        metric_key="grade",
        low=0.4,
        high=0.6,
        basis="Vergleich",
        provenance=Provenance.ESTIMATED,
        origin=DataOrigin.AGENT,
        confidence="high",
    )
    assert estimate.confidence == "low"  # an unsourced agent claim never ranks above low
    mine = attempt(metric_key="grade", value=0.55, unit="%")
    assert session.get(Fact, estimate.id).superseded_by == mine.id
    with pytest.raises(FactError):  # a user entry is never overwritten
        attempt(
            metric_key="grade",
            low=0.1,
            high=0.2,
            basis="x",
            provenance=Provenance.ESTIMATED,
            origin=DataOrigin.AGENT,
        )


def test_user_fact_via_api(client, session):
    asset = _asset(session, "Demo Mina Altiplano")
    body = {"subject_id": asset.id, "metric": "grade", "value": 0.61, "unit": "% Cu"}
    assert client.post(f"{API}/facts", json=body).json()["origin"] == "user"
    rejected = client.post(f"{API}/facts", json={**body, "metric": "aisc"})
    assert rejected.status_code == 400 and "Definition" in rejected.json()["detail"]


# --- research loop -----------------------------------------------------------------------


def test_missing_cost_is_proposed_started_and_found_with_quote(client, container, session):
    asset = _asset(session, "Demo Mina Laguna Clara")
    card = client.get(f"{API}/assets/{asset.id}").json()["card"]
    assert _metric(card, "aisc")["provenance"] == "unknown" and card["knowledge"]["missing"] == [
        "aisc"
    ]
    body = {"subject_id": asset.id, "template": "fill_metric", "metric": "aisc"}
    proposal = client.post(f"{API}/proposals", json=body).json()
    assert proposal["state"] == "draft" and proposal["value_parts"]["insight"] == 1.0
    assert client.get(f"{API}/tickets").json() == []  # nothing runs before the user starts it
    backlog = client.get(f"{API}/proposals").json()
    assert backlog[0]["subject_name"] == "Demo Mina Laguna Clara"
    edited = client.patch(f"{API}/proposals/{proposal['id']}", json={"question": "AISC 2025?"})
    assert edited.json()["question"] == "AISC 2025?"
    started = client.post(f"{API}/proposals/start", json={"ids": [proposal["id"]]}).json()
    assert started[0]["status"] == "queued"
    assert client.post(f"{API}/proposals/start", json={"ids": [proposal["id"]]}).status_code == 400
    running = client.get(f"{API}/map").json()["features"]
    assert next(f for f in running if f["id"] == asset.id)["properties"]["running"]
    assert drain_queue(container) == 1
    ticket = client.get(f"{API}/tickets/{started[0]['id']}").json()
    assert (
        ticket["status"] == "done" and ticket["result"]["sources"] and ticket["runner"] == "offline"
    )
    after = client.get(f"{API}/assets/{asset.id}").json()
    aisc = _metric(after["card"], "aisc")
    assert aisc["value"] == 2.31 and aisc["provenance"] == "reported" and aisc["origin"] == "api"
    assert _metric(after["card"], "margin")["provenance"] == "derived"
    assert (
        after["card"]["knowledge"]["new_result"]
        and after["findings"][0]["epistemic"] == "evidenced"
    )
    history = client.get(f"{API}/assets/{asset.id}/facts/aisc").json()["history"]
    assert "US$2.31 per lb" in history[0]["quote"]
    bell = client.get(f"{API}/notifications").json()
    assert bell["running"] == 0 and bell["unseen"][0]["id"] == ticket["id"]
    client.post(f"{API}/tickets/{ticket['id']}/seen")
    assert client.get(f"{API}/notifications").json()["unseen"] == []


def test_estimate_is_a_band_and_strategic_question_without_agent_is_honest(
    client, container, session
):
    asset = _asset(session, "Demo Mina Laguna Clara")
    for template in ("estimate_cost", "takeover"):
        client.post(
            f"{API}/proposals", json={"subject_id": asset.id, "template": template, "start": True}
        )
    assert drain_queue(container) == 2
    aisc = _metric(client.get(f"{API}/assets/{asset.id}").json()["card"], "aisc")
    assert (
        aisc["provenance"] == "estimated" and aisc["value"] is None and aisc["low"] < aisc["high"]
    )
    margin = _metric(client.get(f"{API}/assets/{asset.id}").json()["card"], "margin")
    assert margin["provenance"] == "estimated" and margin["low"] < margin["high"]
    derivation = client.get(f"{API}/assets/{asset.id}/facts/aisc").json()
    assert derivation["history"][0]["formula_key"] == "peer_iqr" and len(derivation["inputs"]) == 4
    question = next(t for t in client.get(f"{API}/tickets").json() if "Übernahmeziel" in t["title"])
    result = client.get(f"{API}/tickets/{question['id']}").json()["result"]
    assert not result["agent_used"] and "Kein Agent konfiguriert" in result["uncertainties"][0]
    gold = _asset(session, "Demo Mine Silver Peak")
    lonely = proposals.create_proposal(session, SubjectType.ASSET, gold.id, "estimate_cost")
    proposals.start(session, lonely)
    session.commit()
    drain_queue(container)
    assert "zu wenige" in session.get(Ticket, lonely.ticket_id).summary


class JsonAgent:
    name = "fake"

    def __init__(self, answer: dict):
        self.answer, self.prompts = answer, []

    def complete(self, request):
        self.prompts.append(request.prompt)
        return "```json\n" + json.dumps(self.answer) + "\n```"


def test_agent_answer_is_validated_and_followups_become_proposals(client, container, session):
    asset = _asset(session, "Demo Mina Altiplano")
    document = session.scalars(
        select(Document).where(Document.title.contains("2025 – Demo Mina Altiplano"))
    ).one()
    quote = "Annual production of 420,000,000 lb in fiscal 2025."
    container.runner = JsonAgent(
        {
            "answer": "Bedeutend.",
            "uncertainties": ["Nur ein Bericht."],
            "facts": [
                {
                    "metric": "grade",
                    "value": 0.6,
                    "unit": "%",
                    "document_id": document.id,
                    "quote": quote,
                },
                {
                    "metric": "grade",
                    "value": 9.9,
                    "document_id": document.id,
                    "quote": "erfunden " * 4,
                },
                {"metric": "bogus", "value": 1},
            ],
            "followups": ["Wie hoch ist der Wasserbedarf?"],
        }
    )
    thesis = client.get(f"{API}/theses").json()[0]
    body = {
        "subject_id": asset.id,
        "template": "strategic",
        "thesis_id": thesis["id"],
        "start": True,
    }
    client.post(f"{API}/proposals", json=body)
    drain_queue(container)
    ticket = client.get(f"{API}/tickets").json()[0]
    result = client.get(f"{API}/tickets/{ticket['id']}").json()["result"]
    assert result["agent_used"] and len(result["fact_ids"]) == 1 and len(result["rejected"]) == 2
    assert "Dokument" in container.runner.prompts[0]
    follow = client.get(f"{API}/proposals").json()
    assert [p["origin"] for p in follow] == ["agent"] and follow[0]["state"] == "draft"
    links = client.get(f"{API}/theses").json()[0]["links"]
    assert any(link["target_type"] == "finding" for link in links)
    container.runner = JsonAgent({})
    container.runner.complete = lambda _request: "kein JSON"
    client.post(
        f"{API}/proposals", json={"subject_id": asset.id, "template": "strategic", "start": True}
    )
    drain_queue(container)
    assert client.get(f"{API}/tickets").json()[0]["summary"] == "kein JSON"


class ToolAgent:
    name, supports_tools = "tooler", True

    def __init__(self, document_id: int):
        self.document_id, self.outputs = document_id, []

    def run_with_tools(self, _system, _prompt, tools):
        by_name = {t.name: t.handler for t in tools}
        doc = {"document_id": self.document_id}
        self.outputs.append(by_name["search_document"]({**doc, "query": "reserves"}))
        self.outputs.append(by_name["read_document"](doc))
        quote = "Proven and probable mineral reserves of 9,800,000,000 lb at year end."
        self.outputs.append(
            by_name["record_fact"]({**doc, "metric": "resources", "value": 9.8e9, "quote": quote})
        )
        self.outputs.append(
            by_name["record_fact"]({"metric": "grade", "value": 1.0, "quote": "x" * 25})
        )
        self.outputs.append(
            by_name["propose_followup"]({"question": "Wie lange reicht das Wasser?"})
        )
        for broken in ({"document_id": 0, "query": "x"}, {"metric": 5}):
            try:
                by_name["search_document" if "query" in broken else "record_fact"](broken)
            except ValueError as exc:
                self.outputs.append(f"error: {exc}")
        return ToolRun('{"answer": "fertig"}', steps=2, tool_calls=5)


def test_tool_capable_agent_reads_documents_and_records_sourced_facts(client, container, session):
    asset = _asset(session, "Demo Mina Altiplano")
    document = session.scalars(
        select(Document).where(Document.title.contains("2025 – Demo Mina Altiplano"))
    ).one()
    container.runner = ToolAgent(document.id)
    client.post(
        f"{API}/proposals", json={"subject_id": asset.id, "template": "strategic", "start": True}
    )
    drain_queue(container)
    outputs = container.runner.outputs
    assert "reserves" in outputs[0] and "Demo-Bericht" in outputs[1] and outputs[2] == "gespeichert"
    assert "Zitat" in outputs[3] and outputs[4].startswith("als Vorschlag")
    assert sum(o.startswith("error") for o in outputs) == 2
    assert client.get(f"{API}/tickets").json()[0]["summary"] == "fertig"


def test_document_by_url_is_fetched_safely_and_read(client, container, session):
    asset = _asset(session, "Demo Projekt Vecino")
    html = "<html><body><p>Technical report. AISC of US$1.95 per lb expected.</p></body></html>"
    transport = httpx.MockTransport(lambda _r: httpx.Response(200, html=html))
    container.fetcher = Fetcher(
        httpx.Client(transport=transport), lambda _h: ["93.184.216.34"], min_interval_s=0
    )
    body = {"asset_id": asset.id, "url": "https://example.com/report", "title": "PEA"}
    assert (
        client.post(f"{API}/documents", json={**body, "url": "file:///etc/passwd"}).status_code
        == 422
    )
    assert client.post(f"{API}/documents", json=body).json()["status"] == "queued"
    drain_queue(container)
    ticket = client.get(f"{API}/tickets").json()[0]
    result = client.get(f"{API}/tickets/{ticket['id']}").json()["result"]
    assert ticket["status"] == "done" and len(result["fact_ids"]) == 1
    assert "Veröffentlichungsdatum unbekannt" in result["uncertainties"][-1]
    stored = client.get(f"{API}/documents").json()[0]
    assert (
        stored["title"] == "PEA"
        and "AISC" in client.get(f"{API}/documents/{stored['id']}").json()["text"]
    )
    container.fetcher = Fetcher(
        httpx.Client(transport=transport), lambda _h: ["10.0.0.1"], min_interval_s=0
    )
    client.post(f"{API}/documents", json=body)
    drain_queue(container)
    failed = client.get(f"{API}/tickets").json()[0]
    assert failed["status"] == "failed" and failed["error"]
    assert client.post(f"{API}/tickets/{failed['id']}/retry").json()["status"] == "queued"
    assert client.post(f"{API}/tickets/{failed['id']}/cancel").json()["status"] == "cancelled"


def test_proposal_guards(client, session):
    asset = _asset(session, "Demo Mina Altiplano")
    assert (
        client.post(f"{API}/proposals", json={"subject_id": asset.id, "template": "x"}).status_code
        == 400
    )
    assert (
        client.post(f"{API}/proposals", json={"subject_id": 9999, "template": "free"}).status_code
        == 400
    )
    free = {"subject_id": asset.id, "template": "free"}
    assert client.post(f"{API}/proposals", json=free).status_code == 400  # empty question
    made = client.post(f"{API}/proposals", json={**free, "question": "Warum?"}).json()
    assert client.post(f"{API}/proposals/{made['id']}/dismiss").json()["state"] == "dismissed"
    assert client.patch(f"{API}/proposals/{made['id']}", json={"question": "x"}).status_code == 400
    assert len(client.get(f"{API}/templates").json()) >= 9


# --- engine, events, situation report ------------------------------------------------------


def test_scan_runs_engine_without_starting_research(client, container, session):
    assert scan_due(container)
    report = run_scan(container)
    assert report.findings >= 3 and report.proposals >= 5 and not scan_due(container)
    assert session.scalars(select(Ticket)).all() == []  # the engine proposes, it never starts
    findings = {f.rule_key: f for f in session.scalars(select(Finding))}
    assert (
        findings["cost_outlier"].epistemic == "correlation"
        and "Kupferberg" in findings["cost_outlier"].text
    )
    assert any(key.startswith("neighbour_") for key in findings)
    laguna = _asset(session, "Demo Mina Laguna Clara")
    templates = {
        p.template_key
        for p in session.scalars(select(Proposal).where(Proposal.subject_id == laguna.id))
    }
    assert {"fill_metric", "estimate_cost"} <= templates
    again = run_scan(container)
    assert again.findings == 0 and again.proposals == 0  # idempotent
    client.post(f"{API}/system/scan")
    assert scan_due(container) and tick(container) == 0


def test_quakes_are_linked_to_nearby_assets(client, session):
    asset = _asset(session, "Demo Mina Altiplano")
    now = datetime.now(UTC)
    quakes = [
        Quake("a", 6.8, "Calama", asset.lat + 0.5, asset.lon, now, "https://example.org/a"),
        Quake("b", 4.9, "weak", asset.lat, asset.lon, now, ""),
    ]
    assert record_quakes(session, quakes, is_demo=True) == 1
    assert record_quakes(session, quakes, is_demo=True) == 0
    session.commit()
    event = session.scalars(select(Event)).one()
    assert event.severity == 4 and asset.id in {link.asset_id for link in event.links}
    assert client.get(f"{API}/map").json()["events"][0]["title"].startswith("Erdbeben M6.8")


def test_situation_report_since_last_visit(client, session):
    first = client.get(f"{API}/changes").json()
    assert first["last_visit"] is None and len(first["changes"]) > 10
    client.post(f"{API}/visits")
    assert client.get(f"{API}/changes").json()["changes"] == []
    asset = _asset(session, "Demo Mina Altiplano")
    client.post(f"{API}/facts", json={"subject_id": asset.id, "metric": "grade", "value": 0.7})
    report = client.get(f"{API}/changes").json()
    assert (
        report["changes"][0]["subject_name"] == "Demo Mina Altiplano"
        and report["changes"][0]["new"]
    )
    card = client.get(f"{API}/assets/{asset.id}").json()["card"]
    assert card["knowledge"]["status"] == "new"
    assert (
        len(
            client.get(f"{API}/changes", params={"since": "2000-01-01T00:00:00Z"}).json()["changes"]
        )
        > 10
    )


# --- theses, portfolio, system ----------------------------------------------------------------


def test_thesis_board(client, session):
    demo = client.get(f"{API}/theses").json()[0]
    assert demo["title"].startswith("Kupfernachfrage") and len(demo["asset_ids"]) == 7
    assert client.post(f"{API}/theses", json={"title": " "}).status_code == 400
    made = client.post(
        f"{API}/theses", json={"title": "Uran-Renaissance", "commodity": "uranium"}
    ).json()
    asset = _asset(session, "Demo Mine Steppe ISR")
    link = {"target_type": "asset", "target_id": asset.id, "stance": "supports"}
    assert client.post(f"{API}/theses/{made['id']}/links", json=link).json()["asset_ids"] == [
        asset.id
    ]
    updated = client.post(
        f"{API}/theses/{made['id']}/links", json={**link, "stance": "contradicts"}
    ).json()
    assert len(updated["links"]) == 1 and updated["links"][0]["stance"] == "contradicts"
    assert (
        client.post(
            f"{API}/theses/{made['id']}/links", json={**link, "target_type": "x"}
        ).status_code
        == 400
    )
    assert (
        client.post(f"{API}/theses/{made['id']}/assumptions", json={"text": ""}).status_code == 400
    )
    added = client.post(
        f"{API}/theses/{made['id']}/assumptions", json={"text": "Angebot bleibt knapp"}
    ).json()
    assumption = added["assumptions"][0]["id"]
    assert (
        client.patch(
            f"{API}/assumptions/{assumption}",
            json={"status": "supported", "reason": "Bericht 2025"},
        ).json()["status"]
        == "supported"
    )
    assert client.patch(f"{API}/assumptions/{assumption}", json={"status": "x"}).status_code == 400


def test_portfolio(client):
    holding = {
        "symbol": "nem",
        "quantity": 10,
        "avg_price": 40.0,
        "intent": "Goldhebel im Aufschwung",
        "exit_condition": "Verkauf bei AISC über 1500",
    }
    made = client.post(f"{API}/portfolio/holdings", json=holding).json()
    assert client.post(f"{API}/portfolio/holdings", json=holding).status_code == 400
    assert (
        client.post(f"{API}/portfolio/holdings", json={**holding, "quantity": 0}).status_code == 400
    )
    assert client.post(f"{API}/portfolio/watch", json={"symbol": "bad symbol"}).status_code == 400
    watch = client.post(
        f"{API}/portfolio/watch", json={"symbol": "GOLD", "note": "beobachten"}
    ).json()
    assert client.post(f"{API}/portfolio/watch", json={"symbol": "GOLD"}).status_code == 400
    view = client.get(f"{API}/portfolio").json()
    assert view["holdings"][0]["symbol"] == "NEM" and view["holdings"][0]["pnl_pct"] is not None
    assert view["watchlist"][0]["price"] > 0
    client.delete(f"{API}/portfolio/holdings/{made['id']}")
    client.delete(f"{API}/portfolio/watch/{watch['id']}")
    assert client.get(f"{API}/portfolio").json() == {"holdings": [], "watchlist": []}


def test_system_manual_security_and_spa(client, container, tmp_path):
    assert client.get("/healthz").json() == {"status": "ok"}
    system = client.get(f"{API}/system").json()
    assert system["is_demo"] and not system["agent_available"] and system["assets"] == 19
    assert not system["worker_alive"]
    tick(container, force_scan=True)
    assert client.get(f"{API}/system").json()["worker_alive"]
    assert client.get(f"{API}/manual").status_code == 404
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "user-manual.md").write_text("# Handbuch\n![x](screenshots/a.png)", encoding="utf-8")
    assert "/manual-assets/a.png" in client.get(f"{API}/manual").json()["html"]
    page = client.get("/research")
    assert page.status_code == 200 and "Content-Security-Policy" in page.headers
    assert client.get("/api/nope").status_code == 404
    evil = client.post(f"{API}/visits", headers={"Origin": "https://evil.example"})
    assert evil.status_code == 403
    assert client.post(f"{API}/visits", headers={"Origin": "http://testserver"}).status_code == 200


def test_ticket_states(container, session):
    assert container.is_demo
    asset = _asset(session, "Demo Mina Altiplano")
    proposal = proposals.create_proposal(
        session, SubjectType.ASSET, asset.id, "fill_metric", params={"metric": "nope"}
    )
    ticket = proposals.start(session, proposal)
    session.commit()
    drain_queue(container)
    session.refresh(ticket)
    assert ticket.status == TicketStatus.FAILED and "Kennzahl" in ticket.error


# --- corrections after the requirements review -------------------------------------------


def test_prior_year_figure_comes_from_its_own_earlier_report(client, session):
    asset = _asset(session, "Demo Mina Altiplano")
    history = client.get(f"{API}/assets/{asset.id}/facts/aisc").json()["history"]
    assert history[1]["document"]["published_at"] == "2025-02-20"
    assert client.get(f"{API}/system").json()["documents"] == 44
    project = _asset(session, "Demo Projekt Cobre Alto")
    resources = client.get(f"{API}/assets/{project.id}/facts/resources").json()["history"][0]
    assert "resources" in resources["quote"] and "reserves" not in resources["quote"]


def test_unsuccessful_research_is_neither_hypothesis_nor_deep_nor_visible_in_the_past(
    client, container, session
):
    asset = _asset(session, "Demo Projekt Vecino")
    body = {"subject_id": asset.id, "template": "fill_metric", "metric": "capex", "start": True}
    client.post(f"{API}/proposals", json=body)
    drain_queue(container)
    detail = client.get(f"{API}/assets/{asset.id}").json()
    assert detail["findings"][0]["epistemic"] == "unresolved"
    assert detail["card"]["knowledge"]["status"] != "deep"
    past = client.get(f"{API}/assets/{asset.id}", params={"asof": "2025-06-30"}).json()
    assert past["findings"] == [] and past["tickets"] == []


def test_scenario_summary_and_cost_figures(client):
    params = {"commodity": "copper", "scenario": "copper:3.0"}
    world = client.get(f"{API}/map", params=params).json()
    summary = world["summary"]
    assert summary["producing"] == 5 and summary["unknown"] == 1 and summary["under_water"] == 1
    assert 0 < summary["production_share_under_water"] < 0.2
    costs = {f["properties"]["name"]: f["properties"]["unit_cost"] for f in world["features"]}
    assert costs["Demo Mina Kupferberg"] == 4.4 and costs["Demo Projekt Cobre Alto"] is None


def test_thesis_changes_are_logged_and_evidence_is_readable(client, session):
    client.post(f"{API}/visits")
    made = client.post(
        f"{API}/theses", json={"title": "Realzinsen und Gold", "horizon": "5 Jahre"}
    ).json()
    added = client.post(
        f"{API}/theses/{made['id']}/assumptions", json={"text": "Realzins fällt"}
    ).json()
    client.patch(
        f"{API}/assumptions/{added['assumptions'][0]['id']}",
        json={"status": "supported", "reason": "Bericht 2025"},
    )
    report = client.get(f"{API}/changes").json()["changes"]
    assert [c["kind"] for c in report] == ["thesis", "thesis", "thesis"]
    assert report[0]["new"] == "gestützt" and "Bericht 2025" in report[0]["summary"]
    assert len(client.get(f"{API}/changes", params={"since": "2000-01-01"}).json()["changes"]) > 10
    assert client.get(f"{API}/changes", params={"since": "gestern"}).status_code == 422


def test_compare_keeps_selection_order(client, session):
    a, b = _asset(session, "Demo Projekt Vecino"), _asset(session, "Demo Mina Altiplano")
    cards = client.get(f"{API}/compare", params={"ids": f"{a.id},{b.id}"}).json()["cards"]
    assert [c["id"] for c in cards] == [a.id, b.id]


# --- company view: balance sheet, dilution, people, royalties, checklist ---------------------


def _company_id(session, name: str) -> int:
    return session.scalars(select(Company.id).where(Company.name == name)).one()


def test_company_view_shows_runway_dilution_people_and_checklist(client, session):
    junior = client.get(
        f"{API}/companies/{_company_id(session, 'Demo Junior Explorers Ltd')}"
    ).json()
    derived = {m["metric"]: m for m in junior["derived"]}
    # nine million at year end 2025, burning 3.5 a quarter: used up before today
    assert derived["cash_today"]["value"] == 0.0 and derived["runway_months"]["value"] == 0.0
    assert (
        derived["runway_months"]["provenance"] == "derived" and derived["runway_months"]["formula"]
    )
    assert round(derived["dilution_overhang"]["value"], 2) == 0.34
    assert derived["net_cash"]["provenance"] == "unknown"  # debt is not on file yet
    assert derived["market_cap"]["value"] > 0 and junior["symbol"] == "DJEX"
    assert junior["people"][0]["sourced"] and len(junior["financings"]) == 2
    checklist = {q["key"]: q for q in junior["checklist"]}
    assert checklist["people"]["answered"] and checklist["financing"]["answered"]
    assert not checklist["debt"]["answered"] and checklist["debt"]["missing"] == ["debt"]
    assert not checklist["catalyst"]["answered"]
    assert {a["name"] for a in junior["assets"]} >= {"Demo Projekt Vecino"}
    major = client.get(f"{API}/companies/{_company_id(session, 'Demo Andes Copper Corp')}").json()
    derived = {m["metric"]: m for m in major["derived"]}
    assert derived["runway_months"]["provenance"] == "unknown"  # generates cash, burns none
    assert derived["nav_sum"]["value"] > 0 and derived["p_nav"]["value"] > 0
    flows = [row["cash_flow"] for row in major["sensitivity"]]
    assert flows == sorted(flows) and flows[0] < flows[2] < flows[4]
    assert major["burdens"][0]["holder"] == "Demo Royalty Partners"
    assert {q["key"] for q in major["checklist"] if q["answered"]} >= {"costs", "royalties", "cash"}
    history = client.get(f"{API}/companies/{major['id']}/facts/cash").json()["history"]
    assert "Cash and cash equivalents" in history[0]["quote"]
    assert client.get(f"{API}/companies/{major['id']}/facts/nope").status_code == 404


def test_royalty_reduces_the_margin(client, session):
    seco = _asset(session, "Demo Mina Río Seco")
    card = client.get(
        f"{API}/cards", params={"ids": str(seco.id), "scenario": "copper:4.0"}
    ).json()[0]
    assert card["royalty_pct"] == 2.0
    assert _metric(card, "margin")["value"] == pytest.approx(4.0 * 0.98 - 1.85)


def test_company_research_finds_debt_with_scale_and_engine_flags_short_runway(
    client, container, session
):
    junior = _company_id(session, "Demo Junior Explorers Ltd")
    report = run_scan(container)
    assert report.findings >= 4
    detail = client.get(f"{API}/companies/{junior}").json()
    assert "rund 8 Monate" in detail["findings"][0]["text"]
    assert [p["template"] for p in detail["proposals"]] == ["financing"]
    body = {
        "subject_type": "company",
        "subject_id": junior,
        "template": "fill_metric",
        "metric": "debt",
    }
    client.post(f"{API}/proposals", json={**body, "start": True})
    drain_queue(container)
    after = client.get(f"{API}/companies/{junior}").json()
    debt = next(m for m in after["metrics"] if m["metric"] == "debt")
    assert debt["value"] == 500_000 and debt["provenance"] == "reported"  # 'US$0.5 million'
    assert {m["metric"]: m for m in after["derived"]}["net_cash"][
        "value"
    ] == -500_000  # cash is used up by today, the debt remains
    question = {
        "subject_type": "company",
        "subject_id": junior,
        "template": "management",
        "start": True,
    }
    client.post(f"{API}/proposals", json=question)
    drain_queue(container)
    ticket = client.get(f"{API}/tickets").json()[0]
    result = client.get(f"{API}/tickets/{ticket['id']}").json()["result"]
    assert "Unternehmen: Demo Junior Explorers Ltd" in result["answer"]


def test_company_facts_by_user_and_scope_guard(client, session):
    junior = _company_id(session, "Demo Junior Explorers Ltd")
    body = {
        "subject_type": "company",
        "subject_id": junior,
        "metric": "next_catalyst",
        "text": "PEA im Q2",
    }
    assert client.post(f"{API}/facts", json=body).json()["origin"] == "user"
    wrong = client.post(f"{API}/facts", json={**body, "metric": "grade", "value": 1.0})
    assert wrong.status_code == 400 and "keine Kennzahl" in wrong.json()["detail"]
    asset = _asset(session, "Demo Mina Altiplano")
    cash_on_mine = {"subject_id": asset.id, "metric": "cash", "value": 1.0}
    assert client.post(f"{API}/facts", json=cash_on_mine).status_code == 400


def test_fact_as_thesis_evidence(client, session):
    asset = _asset(session, "Demo Mina Altiplano")
    fact_id = client.get(f"{API}/assets/{asset.id}/facts/aisc").json()["history"][0]["id"]
    thesis = client.get(f"{API}/theses").json()[0]
    link = {"target_type": "fact", "target_id": fact_id, "stance": "supports"}
    client.post(f"{API}/theses/{thesis['id']}/links", json=link)
    evidence = [
        x for x in client.get(f"{API}/theses").json()[0]["links"] if x["target_type"] == "fact"
    ]
    assert evidence[0]["fact"]["display"].startswith("2,05") and evidence[0]["stance"] == "supports"


# --- login ----------------------------------------------------------------------------------


def test_password_protects_the_api_but_not_the_page(container, tmp_path):
    from dataclasses import replace

    from fastapi.testclient import TestClient

    from watchstreet.web.app import create_app

    container.settings = replace(container.settings, password="geheim", secret_key="k")
    with TestClient(create_app(container)) as locked:
        assert locked.get("/").status_code == 200 and locked.get("/healthz").status_code == 200
        assert locked.get(f"{API}/session").json() == {"auth_required": True, "logged_in": False}
        assert locked.get(f"{API}/map").status_code == 401
        assert locked.post(f"{API}/login", json={"password": "falsch"}).status_code == 401
        assert locked.post(f"{API}/login", json={"password": "geheim"}).json() == {
            "logged_in": True
        }
        assert locked.get(f"{API}/map").status_code == 200
        assert locked.get(f"{API}/session").json()["logged_in"]
        locked.cookies.set("ws_session", "9999999999.gefaelscht")
        assert locked.get(f"{API}/map").status_code == 401
        locked.post(f"{API}/logout")
    with TestClient(create_app(container)) as brute:
        for _ in range(5):
            brute.post(f"{API}/login", json={"password": "x"})
        assert brute.post(f"{API}/login", json={"password": "geheim"}).status_code == 401  # locked


# --- testable assumptions and portfolio exposure ------------------------------------------------


def test_assumptions_need_a_reason_and_carry_criterion_and_evidence(client, session):
    thesis = client.get(f"{API}/theses").json()[0]
    body = {"text": "Realzins fällt", "criterion": "10J-TIPS über 2,5 %", "review_by": "2020-01-01"}
    made = client.post(f"{API}/theses/{thesis['id']}/assumptions", json=body).json()["assumptions"][
        -1
    ]
    assert made["criterion"] == "10J-TIPS über 2,5 %" and made["review_due"]
    no_reason = client.patch(f"{API}/assumptions/{made['id']}", json={"status": "contradicted"})
    assert no_reason.status_code == 400 and "begründen" in no_reason.json()["detail"]
    edit = {"criterion": "10J-TIPS über 3 %", "review_by": "2099-01-01"}
    client.patch(f"{API}/assumptions/{made['id']}", json=edit)
    asset = _asset(session, "Demo Mina Altiplano")
    fact_id = client.get(f"{API}/assets/{asset.id}/facts/aisc").json()["history"][0]["id"]
    link = {
        "target_type": "fact",
        "target_id": fact_id,
        "stance": "contradicts",
        "assumption_id": made["id"],
    }
    client.post(f"{API}/theses/{thesis['id']}/links", json=link)
    judged = {"status": "contradicted", "reason": "Kosten steigen"}
    client.patch(f"{API}/assumptions/{made['id']}", json=judged)
    after = client.get(f"{API}/theses").json()[0]["assumptions"][-1]
    assert after["contradicts"] == 1 and after["supports"] == 0 and not after["review_due"]
    assert after["status_reason"] == "Kosten steigen" and after["criterion"] == "10J-TIPS über 3 %"


def test_position_shows_company_assets_and_theses(client):
    why = {"intent": "Goldhebel im Aufschwung", "exit_condition": "Verkauf bei AISC über 1500"}
    assert (
        client.post(
            f"{API}/portfolio/holdings", json={"symbol": "DACC", "quantity": 10, "avg_price": 30}
        ).status_code
        == 400  # no purchase without intent and exit condition
    )
    client.post(
        f"{API}/portfolio/holdings", json={"symbol": "DACC", "quantity": 10, "avg_price": 30, **why}
    )
    client.post(
        f"{API}/portfolio/holdings", json={"symbol": "NEM", "quantity": 1, "avg_price": 30, **why}
    )
    known, unknown = client.get(f"{API}/portfolio").json()["holdings"]
    assert known["company"]["name"] == "Demo Andes Copper Corp"
    assert {a["name"] for a in known["assets"]} == {"Demo Mina Altiplano", "Demo Mina Río Seco"}
    assert known["theses"][0]["title"].startswith("Kupfernachfrage")
    assert unknown["company"] is None and unknown["theses"] == []


def test_funding_gap_ev_and_user_entries_for_people_and_financings(client, session):
    junior = _company_id(session, "Demo Junior Explorers Ltd")
    derived = {m["metric"]: m for m in client.get(f"{API}/companies/{junior}").json()["derived"]}
    assert derived["open_capex"]["value"] > 0
    assert derived["funding_gap"]["value"] == (
        derived["open_capex"]["value"] - derived["cash_today"]["value"]
    )
    assert _cash(client, junior) == 9e6  # the reported figure itself is untouched
    assert "enterprise_value" in derived
    before = client.get(f"{API}/companies/{junior}").json()
    person = {"name": "Erika Muster", "role": "CFO", "track_record": "Zwei Minen finanziert"}
    assert client.post(f"{API}/companies/{junior}/people", json=person).status_code == 201
    raise_ = {"day": "2026-03-01", "amount": 5e6, "price": 0.4, "note": "mit Warrants"}
    assert client.post(f"{API}/companies/{junior}/financings", json=raise_).status_code == 201
    assert client.post(f"{API}/companies/{junior}/financings", json={"day": "x"}).status_code == 422
    after = client.get(f"{API}/companies/{junior}").json()
    assert len(after["people"]) == len(before["people"]) + 1
    assert len(after["financings"]) == len(before["financings"]) + 1
    assert after["financings"][0]["note"] == "mit Warrants"


def _cash(client, company_id):
    metrics = client.get(f"{API}/companies/{company_id}").json()["metrics"]
    return next(m["value"] for m in metrics if m["metric"] == "cash")


def test_company_view_is_honest_about_dates_duplicates_and_coverage(client, session):
    junior = _company_id(session, "Demo Junior Explorers Ltd")
    view = client.get(f"{API}/companies/{junior}").json()
    derived = {m["metric"]: m for m in view["derived"]}
    assert derived["cash_empty"]["text"].startswith("seit ") and derived["cash_empty"]["stale"]
    assert derived["gap_to_market_cap"]["value"] > 1
    assert derived["market_cap_diluted"]["value"] > derived["market_cap"]["value"]
    assert view["sensitivity"] == []  # nothing producing: not applicable instead of zeros
    future = {"day": "2099-01-01", "amount": 1e6}
    assert client.post(f"{API}/companies/{junior}/financings", json=future).status_code == 422
    assert (
        client.post(f"{API}/companies/{junior}/financings", json={"day": "2026-01-01"}).status_code
        == 422
    )
    past = client.get(f"{API}/companies/{junior}", params={"asof": "2020-01-01"}).json()
    assert past["financings"] == [] and past["price"] is None
    body = {"subject_type": "company", "subject_id": junior, "template": "management"}
    first = client.post(f"{API}/proposals", json=body).json()
    second = client.post(f"{API}/proposals", json=body).json()
    assert first["id"] == second["id"]


def test_dalio_review_fixes_trace_dates_and_units(client, session):
    thesis = client.post(f"{API}/theses", json={"title": "T", "statement": "S"}).json()
    added = client.post(
        f"{API}/theses/{thesis['id']}/assumptions",
        json={"text": "Preis hält", "criterion": "<2,40"},
    ).json()
    assumption = added["assumptions"][-1]["id"]
    path = f"{API}/assumptions/{assumption}"
    assert client.patch(path, json={"criterion": "<3,00"}).status_code == 200
    assert client.patch(path, json={"status": "supported", "reason": "Bericht"}).status_code == 200
    assert client.patch(path, json={"status": "open"}).status_code == 400  # back needs a reason
    summaries = [c["summary"] for c in client.get(f"{API}/changes").json()["changes"]]
    assert any(s.startswith("Kriterium geändert") for s in summaries)
    assert any("jetzt „gestützt“" in s for s in summaries)
    bad = {"target_type": "asset", "target_id": 9999}
    assert client.post(f"{API}/theses/{thesis['id']}/links", json=bad).status_code == 400
    assert client.get(f"{API}/map", params={"asof": "2099-01-01"}).status_code == 422
    gold = client.get(f"{API}/map", params={"commodity": "gold", "scenario": "gold:1500"}).json()
    share = gold["summary"]["production_share_under_water"]
    assert share is None or 0.01 < share <= 1  # by-product mines no longer dilute the share
    holding = {"symbol": "DACC", "quantity": 1, "avg_price": 1, "bought_at": "2099-01-01"}
    assert client.post(f"{API}/portfolio/holdings", json=holding).status_code == 422


def test_rule_specs_financing_terms_pro_forma_and_own_entries(client, session):
    junior = _company_id(session, "Demo Junior Explorers Ltd")
    raise_ = {
        "day": "2026-10-01", "amount": 15e6, "price": 0.2, "warrants": 37.5e6,
        "warrant_price": 0.3, "warrant_expiry": "2028-10-01", "investors": "Fonds A",
    }  # fmt: skip
    created = client.post(f"{API}/companies/{junior}/financings", json=raise_).json()
    person = {"name": "Erika Muster", "shares_held": 9e6, "prior_companies": "Alpha Mining: 4x"}
    made = client.post(f"{API}/companies/{junior}/people", json=person).json()
    view = client.get(f"{API}/companies/{junior}").json()
    derived = {m["metric"]: m for m in view["derived"]}
    assert 0 < derived["cash_today"]["value"] < 24e6  # the raise, less the burn since
    assert derived["market_cap"]["value"] == view["price"] * (180e6 + 75e6)  # same share basis
    assert round(derived["dilution_overhang"]["value"], 3) == round(
        (242e6 + 75e6 + 37.5e6) / 255e6 - 1, 3
    )
    assert derived["shares_pro_forma"]["value"] == 180e6 + 75e6
    assert derived["cash_empty"]["text"].startswith("am ")  # the raise moved the date forward
    assert "study_npv_sum" in derived and "p_study_npv" in derived
    row = next(f for f in view["financings"] if f["id"] == created["id"])
    assert row["after_balance"] and row["warrants"] == 37.5e6 and row["own_entry"]
    who = next(p for p in view["people"] if p["id"] == made["id"])
    assert round(who["ownership"], 4) == round(9e6 / 255e6, 4) and who["own_entry"]
    assert client.delete(f"{API}/financings/{created['id']}").status_code == 204
    assert client.delete(f"{API}/people/{made['id']}").status_code == 204
    demo_person = next(p for p in view["people"] if not p["own_entry"])
    assert client.delete(f"{API}/people/{demo_person['id']}").status_code == 400
    after = client.get(f"{API}/companies/{junior}").json()
    assert "shares_pro_forma" not in {m["metric"] for m in after["derived"]}


def test_royalty_holder_has_a_value_and_checklist_needs_all_costs(client, session):
    royalty = client.get(f"{API}/companies/{_company_id(session, 'Demo Royalty Partners')}").json()
    derived = {m["metric"]: m for m in royalty["derived"]}
    assert derived["nav_sum"]["value"] > 0 and royalty["sensitivity"]
    pacific = client.get(f"{API}/companies/{_company_id(session, 'Demo Pacific Metals')}").json()
    costs = next(q for q in pacific["checklist"] if q["key"] == "costs")
    assert costs["answered"] is False  # one mine has no cost on file


def test_position_carries_thesis_exit_condition_and_a_decision_journal(client, session):
    thesis = client.post(f"{API}/theses", json={"title": "Kupfer knapp", "statement": "S"}).json()
    client.post(f"{API}/theses/{thesis['id']}/assumptions", json={"text": "Preis über 3"})
    body = {
        "symbol": "DJEX", "quantity": 1000, "avg_price": 0.3, "thesis_id": thesis["id"],
        "exit_condition": "Verkauf, wenn Finanzierung unter 0,20", "intent": "Optionalität auf Kupfer",
    }  # fmt: skip
    holding = client.post(f"{API}/portfolio/holdings", json=body).json()["id"]
    row = client.get(f"{API}/portfolio").json()["holdings"][0]
    assert row["thesis"]["title"] == "Kupfer knapp" and row["thesis"]["direct"]
    assert row["exit_condition"].startswith("Verkauf")
    path = f"{API}/portfolio/holdings/{holding}"
    assert client.patch(path, json={"reason": ".", "exit_condition": "nie"}).status_code == 400
    moved = {"reason": "Finanzierung kam besser", "exit_condition": "Verkauf unter 0,15"}
    assert client.patch(path, json=moved).status_code == 200
    assert (
        client.patch(path, json={"reason": "andere These passt", "thesis_id": 9999}).status_code
        == 400
    )
    assert client.post(f"{path}/sell", json={"reason": "weg"}).status_code == 400
    sold = {"reason": "Annahme widerlegt", "price": 0.5}
    assert client.post(f"{path}/sell", json=sold).status_code == 200
    assert client.get(f"{API}/portfolio").json()["holdings"] == []
    journal = client.get(f"{API}/portfolio/decisions").json()
    assert [d["kind"] for d in journal] == ["sell", "adjust", "buy"]
    assert "vorher:" in journal[1]["reason"] and "Finanzierung unter 0,20" in journal[1]["reason"]
    assert "→ neu:" in journal[1]["reason"] and "unter 0,15" in journal[1]["reason"]
    bought = journal[2]["snapshot"]
    assert bought["thesis"]["assumptions"][0]["status"] == "open" and bought["price"]
    assert bought["figures"]["Kasse"].endswith("USD")
    assert "Capex" in bought["assets"]["Demo Projekt Cobre Alto"]


def test_reference_date_hides_todays_research_sources_and_questions(client, container, session):
    asset = session.scalars(select(Asset).where(Asset.name == "Demo Mina Laguna Clara")).one()
    made = client.post(
        f"{API}/proposals",
        json={
            "subject_type": "asset",
            "subject_id": asset.id,
            "template": "fill_metric",
            "metric": "aisc",
        },
    ).json()
    ticket = client.post(f"{API}/proposals/start", json={"ids": [made["id"]]}).json()[0]
    execute_ticket(container, ticket["id"])
    client.post(
        f"{API}/proposals",
        json={"subject_type": "asset", "subject_id": asset.id, "template": "takeover"},
    )
    now = client.get(f"{API}/assets/{asset.id}").json()
    assert now["card"]["knowledge"]["status"] in ("deep", "new") and now["documents"]
    then = client.get(f"{API}/assets/{asset.id}", params={"asof": "2025-06-30"}).json()
    assert then["card"]["knowledge"]["status"] in ("unexamined", "known")
    assert then["card"]["knowledge"]["open_questions"] == 0
    assert then["proposals"] == [] and then["tickets"] == []
    assert all(d["published_at"] <= "2025-06-30T23:59" for d in then["documents"])
