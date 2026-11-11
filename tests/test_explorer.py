"""The explorer end to end on the synthetic demo world: API, research loop, engine, portfolio."""

import json
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import select

from watchstreet.agents.tools import ToolRun
from watchstreet.domain import DataOrigin, Provenance, SubjectType, TicketStatus
from watchstreet.harness.scan import run_scan, scan_due
from watchstreet.intel.connectors.usgs import Quake
from watchstreet.intel.fetch import Fetcher
from watchstreet.models import Asset, Document, Event, Fact, Finding, Proposal, Ticket
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
    document = session.scalars(select(Document).where(Document.title.contains("Altiplano"))).one()
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
    document = session.scalars(select(Document).where(Document.title.contains("Altiplano"))).one()
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
    assert len(client.get(f"{API}/templates").json()) == 7


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
        client.patch(f"{API}/assumptions/{assumption}", json={"status": "supported"}).json()[
            "status"
        ]
        == "supported"
    )
    assert client.patch(f"{API}/assumptions/{assumption}", json={"status": "x"}).status_code == 400


def test_portfolio(client):
    holding = {"symbol": "nem", "quantity": 10, "avg_price": 40.0, "intent": "Goldhebel"}
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
