"""Registry import, tested against responses recorded from the real services."""

from pathlib import Path

import httpx
from sqlalchemy import select

from watchstreet.intel.connectors import registry
from watchstreet.intel.fetch import Fetcher
from watchstreet.models import Asset, Stake, Ticket
from watchstreet.services.registry import import_mines
from watchstreet.worker import drain_queue

API = "/api/v1"
FIXTURES = Path(__file__).parent / "fixtures"
BOX = {"south": 40.5, "west": -116.6, "north": 41.0, "east": -116.0}


def _fetcher(requests: list[str] | None = None) -> Fetcher:
    def respond(request: httpx.Request) -> httpx.Response:
        if requests is not None:
            requests.append(str(request.url))
        if request.url.host == "query.wikidata.org":
            body = (FIXTURES / "wikidata_company.json").read_text(encoding="utf-8")
            return httpx.Response(
                200, text=body, headers={"content-type": "application/sparql-results+json"}
            )
        body = (FIXTURES / "mrds_box.xml").read_text(encoding="utf-8")
        return httpx.Response(200, text=body, headers={"content-type": "text/xml"})

    client = httpx.Client(transport=httpx.MockTransport(respond))
    return Fetcher(client, lambda _host: ["93.184.216.34"], min_interval_s=0)


def test_wikidata_rows_are_merged_into_mines_with_operators():
    requests: list[str] = []
    mines = registry.wikidata_by_company(_fetcher(requests), 'Freeport-"McMoRan')
    assert "Freeport-McMoRan" in httpx.URL(requests[0]).params["query"]  # quote removed
    names = {m.name for m in mines}
    assert {"Grasberg Mine", "Morenci Mine"} <= names and len(mines) < 19  # 19 raw rows
    grasberg = next(m for m in mines if m.name == "Grasberg Mine")
    assert grasberg.external_id == "Q119297" and round(grasberg.lat, 2) == -4.05
    assert "Freeport-McMoRan" in grasberg.operators + grasberg.owners
    assert "copper" in grasberg.commodities and grasberg.country == "Indonesia"
    box = registry.wikidata_in_box(_fetcher(requests), registry.Box(-25, -70.5, -21, -68))
    assert box and "Point(-70.5 -25)" in httpx.URL(requests[1]).params["query"]


def test_mrds_keeps_only_our_commodities_and_developed_sites():
    mines = registry.mrds_in_box(_fetcher(), registry.Box(**BOX))
    assert 0 < len(mines) < 40
    assert {m.status_hint for m in mines} <= {"Producer", "Past Producer", "Prospect"}
    assert all(set(m.commodities) <= {"gold", "silver", "copper", "uranium"} for m in mines)
    assert all(m.url.startswith("https://mrdata.usgs.gov/") for m in mines)


def test_import_creates_sourced_assets_once(session):
    mines = registry.wikidata_by_company(_fetcher(), "Freeport-McMoRan")
    before = len(list(session.scalars(select(Asset))))
    first = import_mines(session, mines)
    again = import_mines(session, mines)
    assert first.created > 0 and again.created == 0 and again.known == first.created + first.known
    assert len(list(session.scalars(select(Asset)))) == before + first.created
    grasberg = session.scalars(select(Asset).where(Asset.name == "Grasberg Mine")).one()
    assert grasberg.registry_source == "wikidata" and grasberg.statuses == []
    stake = session.scalars(select(Stake).where(Stake.asset_id == grasberg.id)).first()
    assert stake.document_id and "according to the register" in stake.quote


def test_registry_import_is_refused_in_demo_and_validated(client):
    assert client.post(f"{API}/registry/import", json=BOX).status_code == 400


def test_registry_import_end_to_end(client, container, session, monkeypatch):
    monkeypatch.setattr(type(container), "is_demo", property(lambda _self: False))
    container.fetcher = _fetcher()
    assert client.post(f"{API}/registry/import", json={**BOX, "north": 80}).status_code == 422
    assert client.post(f"{API}/registry/import", json={**BOX, "source": "x"}).status_code == 422
    bad = client.post(f"{API}/registry/import", json={"company": "X", "source": "mrds"})
    assert bad.status_code == 422
    queued = client.post(f"{API}/registry/import", json={**BOX, "source": "mrds"}).json()
    assert queued["status"] == "queued" and "USGS MRDS" in queued["title"]
    client.post(f"{API}/registry/import", json={"company": "Freeport-McMoRan"})
    assert drain_queue(container) == 2
    tickets = list(session.scalars(select(Ticket)))
    assert all(t.status == "done" for t in tickets) and "neue Objekte" in tickets[0].summary
    world = client.get(f"{API}/map").json()["features"]
    imported = [f["properties"] for f in world if not f["properties"]["is_demo"]]
    assert imported and {p["status"] for p in imported} == {"unknown"}
    assert client.get(f"{API}/map", params={"asof": "2020-01-01"}).json()["features"] != []
    past = client.get(f"{API}/map", params={"asof": "2020-01-01"}).json()["features"]
    assert all(f["properties"]["is_demo"] for f in past)  # no dated status, not in the past
    grasberg = session.scalars(select(Asset).where(Asset.name == "Grasberg Mine")).one()
    card = client.get(f"{API}/assets/{grasberg.id}").json()
    assert (
        card["card"]["registry_source"] == "wikidata" and card["documents"][0]["kind"] == "dataset"
    )
    assert card["card"]["knowledge"]["status"] == "unexamined"
    body = {"subject_id": grasberg.id, "template": "profile"}
    assert "Status, Betreiber" in client.post(f"{API}/proposals", json=body).json()["question"]
