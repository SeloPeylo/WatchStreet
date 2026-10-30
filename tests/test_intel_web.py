from sqlalchemy import select

from tests.test_intel_flows import mining_stock
from watchstreet.domain import WorkflowKey
from watchstreet.harness.executor import execute_ticket
from watchstreet.harness.ingest import run_ingest
from watchstreet.harness.scheduler import scan_due
from watchstreet.models import Document, Entity, Feed, IntelItem, Stock, Ticket
from watchstreet.services import tickets as tk
from watchstreet.worker import drain_queue


def populated(container):
    stock_id = mining_stock(container)
    run_ingest(container)
    drain_queue(container)
    return stock_id


def test_all_new_pages_render_empty(client):
    for path in (
        "/intel",
        "/intel/feeds",
        "/graph",
        "/map",
        "/commodities",
        "/api/graph",
        "/api/map",
    ):
        assert client.get(path).status_code == 200, path
    assert client.get("/documents/999").status_code == 404
    assert "Keine Meldungen" in client.get("/intel").text
    assert "Noch keine Beziehungen" in client.get("/graph").text or client.get(
        "/api/graph"
    ).json() == {"nodes": [], "edges": []}


def test_intel_page_shows_sources_and_filters(client, container):
    stock_id = populated(container)
    page = client.get("/intel").text
    assert "Quelle öffnen" in page and "Primärquelle" in page and "Warum für dich relevant" in page
    assert "Erdbeben" in page and "Streik" in page and "im Dokument gefunden" in page
    assert 'rel="noopener noreferrer"' in page and "javascript:" not in page
    hazard = client.get("/intel?category=hazard").text
    assert "Erdbeben" in hazard and "Streik" not in hazard
    primary = client.get("/intel?primary=1").text
    assert "Erdbeben" in primary and "Streik" not in primary
    assert "Streik" in client.get(f"/intel?stock={stock_id}&severity=3").text
    assert "Keine Meldungen" in client.get("/intel?severity=5").text
    assert "Keine Meldungen" in client.get("/intel?stock=9999").text


def test_unsafe_urls_never_become_links(client, container):
    populated(container)
    with container.session_factory() as s:
        item = s.scalar(select(IntelItem).where(IntelItem.category == "geopolitics"))
        item.source_url = "javascript:alert(1)"
        s.commit()
    page = client.get("/intel").text
    assert 'href="javascript:' not in page and 'href="#"' in page


def test_feed_management(client, container):
    populated(container)
    assert "SEC EDGAR" in client.get("/intel/feeds").text
    assert (
        client.post("/intel/feeds", data={"name": "Mein Feed", "url": "ftp://nope"}).status_code
        == 400
    )
    assert (
        client.post(
            "/intel/feeds",
            data={"name": "Mein Feed", "url": "https://feed.example/rss", "doc_kind": "gov"},
            follow_redirects=False,
        ).status_code
        == 303
    )
    with container.session_factory() as s:
        feed = s.scalar(select(Feed).where(Feed.name == "Mein Feed"))
        feed_id, kind = feed.id, feed.doc_kind
    assert kind == "gov"
    client.post(f"/intel/feeds/{feed_id}/toggle")
    with container.session_factory() as s:
        assert s.get(Feed, feed_id).enabled is False
    client.post(f"/intel/feeds/{feed_id}/delete")
    assert client.post("/intel/feeds/9999/toggle").status_code == 404
    assert client.post("/intel/feeds/9999/delete").status_code == 404
    client.post("/intel/refresh")
    assert scan_due(container)


def test_document_page_and_agent_reading_request(client, container):
    stock_id = populated(container)
    with container.session_factory() as s:
        quake_doc = s.scalar(select(Document).where(Document.publisher == "USGS"))
        news_doc = s.scalar(select(Document).where(Document.kind == "news"))
        sync = tk.create_ticket(s, s.get(Stock, stock_id), WorkflowKey.SEC_SYNC)
        s.commit()
        quake_id, news_id = quake_doc.id, news_doc.id
        sync_id = sync.id
    execute_ticket(container, sync_id)
    with container.session_factory() as s:
        filing_id = s.scalar(select(Document.id).where(Document.url.like("%demo-10k.htm")))
    page = client.get(f"/documents/{filing_id}").text
    assert (
        "Item 2. Properties" in page
        and "Von einem Agenten lesen lassen" in page
        and "SEC EDGAR" in page
    )
    assert "Von einem Agenten" not in client.get(f"/documents/{news_id}").text
    assert (
        "Erdbeben" in client.get(f"/documents/{quake_id}").text
        or "M5" in client.get(f"/documents/{quake_id}").text
    )
    resp = client.post(f"/documents/{filing_id}/read", follow_redirects=False)
    assert resp.status_code == 303
    with container.session_factory() as s:
        ticket = s.scalar(select(Ticket).order_by(Ticket.id.desc()))
        assert ticket.workflow == "read_filing" and ticket.params["topic"] == f"doc:{filing_id}"
        orphan = Document(url="https://o.example", text="t", kind="news", content_hash="h")
        s.add(orphan)
        s.commit()
        orphan_id = orphan.id
    assert client.post(f"/documents/{orphan_id}/read").status_code == 400


def test_graph_and_relation_forms(client, container):
    stock_id = populated(container)
    data = client.get(f"/api/graph?stock={stock_id}&depth=2").json()
    names = {n["name"] for n in data["nodes"]}
    assert {"Carlin", "Cadia"} <= names and any(e["kind"] == "owns" for e in data["edges"])
    assert client.get(f"/graph?stock={stock_id}").status_code == 200
    ok = client.post(
        "/graph/relations",
        data={
            "source": "Caterpillar",
            "source_kind": "supplier",
            "target": "Carlin",
            "target_kind": "mine",
            "kind": "supplies",
            "strength": "0,4",
            "country": "USA",
        },
        follow_redirects=False,
    )
    assert ok.status_code == 303
    assert "Caterpillar" in {
        n["name"] for n in client.get(f"/api/graph?stock={stock_id}&depth=3").json()["nodes"]
    }
    bad = client.post("/graph/relations", data={"source": "A", "target": "B", "kind": "teleports"})
    assert bad.status_code == 400
    assert (
        client.post(
            "/graph/relations", data={"source": "A", "target": "B", "strength": "viel"}
        ).status_code
        == 400
    )


def test_map_api_and_asset_location(client, container):
    populated(container)
    payload = client.get("/api/map").json()
    assert {a["name"] for a in payload["assets"]} == {"Carlin", "Cadia"}
    assert any(
        i["category"] == "hazard" and i["url"].startswith("https://quake.demo.example/")
        for i in payload["intel"]
    )
    assert payload["exposure"]["United States of America"]["share"] > 0.5
    with container.session_factory() as s:
        s.add(Entity(name="Boddington", kind="mine", stock_id=None))
        s.commit()
        new_id = s.scalar(select(Entity.id).where(Entity.name == "Boddington"))
    assert (
        "Boddington" in client.get("/map").text
        and "Assets ohne Standort" in client.get("/map").text
    )
    assert (
        client.post(
            f"/entities/{new_id}/location",
            data={"lat": "-32,8", "lon": "116,4", "country": "Australia"},
            follow_redirects=False,
        ).status_code
        == 303
    )
    assert "Boddington" in {a["name"] for a in client.get("/api/map").json()["assets"]}
    assert (
        client.post(f"/entities/{new_id}/location", data={"lat": "123", "lon": "1"}).status_code
        == 400
    )
    assert (
        client.post(f"/entities/{new_id}/location", data={"lat": "x", "lon": "1"}).status_code
        == 400
    )
    assert client.post("/entities/9999/location", data={"lat": "1", "lon": "1"}).status_code == 404


def test_commodity_cockpit_with_scenarios(client, container):
    populated(container)
    page = client.get("/commodities").text
    for needle in (
        "Gold",
        "Kupfer/Gold",
        "Gold/Silber",
        "NAV je Aktie",
        "+20 %",
        "-20 %",
        "Modellannahme",
    ):
        assert needle in page, needle
    assert "NEM" in page
