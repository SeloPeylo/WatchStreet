"""Analysis import: visible at once, unverified, never overwriting sourced figures."""

from watchstreet.analysis.imports import canonical, number, parse_table, status_of
from watchstreet.config import Settings
from watchstreet.container import build_container
from watchstreet.domain import DataOrigin, TicketStatus
from watchstreet.harness.executor import execute_ticket
from watchstreet.models import Asset, Fact, Ticket
from watchstreet.web.app import create_app

API = "/api/v1"
TABLE = """Meine Kupferliste, Stand November
name;company;commodity;country;lat;lon;status;production;aisc (USD/lb);reserves
Mina Prueba Norte;Prueba Mining Corp;copper;Chile;-23.5;-69.1;production;120 Mio;1,85;2.4e9
Proyecto Sin Lugar;Prueba Mining Corp;copper;Peru;;;development;;;
Demo Mina Altiplano;Demo Andes Copper Corp;copper;Chile;;;production;999;9.99;
"""


def test_parser_reads_tables_numbers_and_statuses():
    rows = parse_table(TABLE)
    assert [r.fields["name"] for r in rows][:2] == ["Mina Prueba Norte", "Proyecto Sin Lugar"]
    assert rows[0].fields["aisc"] == "1,85" and "aisc (USD/lb)" not in rows[0].fields
    markdown = "| Mine | Rohstoff | AISC |\n|---|---|---|\n| A Mine | gold | 1,234 |\n"
    assert parse_table(markdown)[0].fields == {
        "name": "A Mine",
        "commodity": "gold",
        "aisc": "1,234",
    }
    assert parse_table("Nur Fliesstext ohne Tabelle.") == []
    assert canonical("Unbekannt") is None
    assert number("1,234") == 1234.0 and number("1.234,5") == 1234.5 and number("1,85") == 1.85
    assert number("190 Mio") == 190e6 and number("4.0e9") == 4.0e9 and number("n/a") is None
    assert number("2.2 USD/lb") == 2.2
    assert status_of("Produktion") == "production" and status_of("?") is None


def _import(client, **body):
    response = client.post(f"{API}/imports", json={"title": "Liste", **body})
    assert response.status_code == 201, response.text
    return response.json()


def test_import_shows_unverified_figures_and_never_overwrites_sourced_ones(client, session):
    report = _import(client, text=TABLE, source="Newsletter")
    assert report["created"] == 1 and report["matched"] == 1 and report["facts"] == 3
    assert any("Koordinaten" in line for line in report["skipped"])
    assert len(report["conflicts"]) == 2  # the demo mine keeps its sourced production and cost
    new = session.scalars(select_asset("Mina Prueba Norte")).one()
    card = client.get(f"{API}/assets/{new.id}").json()["card"]
    metrics = {m["metric"]: m for m in card["metrics"]}
    assert card["status"] == "production" and metrics["aisc"]["value"] == 1.85
    assert metrics["aisc"]["unverified"] and metrics["production"]["value"] == 120e6
    assert client.get(f"{API}/system").json()["unverified"] == 3
    # the same import again changes nothing; a changed figure updates the earlier import
    again = _import(client, text=TABLE.replace("1,85", "1,95") + "\n")
    assert again["facts"] == 1 and again["unchanged"] == 2 and again["created"] == 0
    assert len(client.get(f"{API}/imports/unverified").json()) == 3


def select_asset(name):
    from sqlalchemy import select

    return select(Asset).where(Asset.name == name)


def test_user_confirms_or_retracts_an_imported_figure(client, session):
    _import(client, text=TABLE)
    rows = {r["metric"]: r for r in client.get(f"{API}/imports/unverified").json()}
    confirmed = client.post(f"{API}/facts/{rows['aisc']['fact_id']}/confirm").json()
    assert confirmed["origin"] == "user" and not confirmed["unverified"]
    retracted = client.post(f"{API}/facts/{rows['reserves']['fact_id']}/retract").json()
    assert retracted["retracted"]
    left = client.get(f"{API}/imports/unverified").json()
    assert [r["metric"] for r in left] == ["production"]
    asset = client.get(f"{API}/assets/{rows['aisc']['subject_id']}").json()["card"]
    metrics = {m["metric"]: m for m in asset["metrics"]}
    assert metrics["reserves"]["provenance"] == "unknown" and not metrics["aisc"]["unverified"]
    assert client.post(f"{API}/facts/{rows['aisc']['fact_id']}/confirm").status_code == 400
    assert client.post(f"{API}/facts/{rows['reserves']['fact_id']}/retract").status_code == 400


def test_structured_rows_and_verification_against_primary_documents(client, container, session):
    rows = [{"name": "Demo Mina Laguna Clara", "aisc": 9.5}, {"name": "Demo Mina Laguna Clara 2"}]
    report = _import(client, rows=rows)
    assert report["facts"] == 1 and len(report["skipped"]) == 1
    assert client.post(f"{API}/imports/verify").json() == {"created": 1}
    assert client.post(f"{API}/imports/verify").json() == {"created": 0}
    proposal = next(p for p in client.get(f"{API}/proposals").json() if p["template"] == "verify")
    ticket = client.post(f"{API}/proposals/start", json={"ids": [proposal["id"]]}).json()[0]
    assert execute_ticket(container, ticket["id"]) == TicketStatus.DONE
    done = session.get(Ticket, ticket["id"])
    assert "weicht ab" in done.summary  # the demo report states the real cost
    assert client.get(f"{API}/imports/unverified").json() == []
    current = session.scalars(
        select_fact(done.subject_id, "aisc").where(Fact.superseded_by.is_(None))
    ).one()
    assert current.origin == DataOrigin.API and current.quote


def select_fact(asset_id, metric):
    from sqlalchemy import select

    return select(Fact).where(Fact.subject_id == asset_id, Fact.metric_key == metric)


def test_free_text_needs_an_agent_and_bad_input_is_rejected(client):
    report = _import(client, text="Ein langer Fliesstext über eine Mine ohne jede Tabelle darin.")
    assert report["rows"] == 0 and report["ticket_id"] is None and "Agenten" in report["skipped"][0]
    assert client.post(f"{API}/imports", json={"text": "kurz"}).status_code == 422


class FakeRunner:
    name = "fake"

    def complete(self, request):
        if request.workflow == "test":
            return "OK"
        return (
            '{"rows": [{"name": "Mina Texto", "commodity": "gold", "lat": "-10.5", "lon": "-75.2",'
            ' "aisc": "1100", "quote": "Mina Texto in Peru produces gold at an AISC of 1100."},'
            ' {"name": "Mina Erfunden", "commodity": "gold", "lat": "1", "lon": "1",'
            ' "quote": "Dieser Satz steht nicht im Text."}]}'
        )


def test_agent_breaks_free_text_into_rows_and_unquoted_rows_are_dropped(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'agent.db'}", market_provider="demo",
        docs_dir=str(tmp_path / "docs"),
    )  # fmt: skip
    container = build_container(settings, runner=FakeRunner())
    from fastapi.testclient import TestClient

    with TestClient(create_app(container)) as client:
        text = "Notiz vom Wochenende. Mina Texto in Peru produces gold at an AISC of 1100."
        report = _import(client, text=text)
        assert report["ticket_id"] is not None
        assert execute_ticket(container, report["ticket_id"]) == TicketStatus.DONE
        ticket = client.get(f"{API}/tickets/{report['ticket_id']}").json()
        assert "1 neue" in ticket["summary"]
        found = client.get(f"{API}/search", params={"q": "Mina Texto"}).json()
        assert [h["label"] for h in found] == ["Mina Texto"]
        assert client.get(f"{API}/search", params={"q": "Erfunden"}).json() == []
        assert client.post(f"{API}/system/agent/test").json() == {"ok": True, "detail": "OK"}
    container.engine.dispose()


def test_agent_backend_is_set_at_runtime_and_the_key_is_never_returned(client, container, session):
    assert client.get(f"{API}/system/agent").json()["source"] == "environment"
    assert client.post(f"{API}/system/agent/test").json()["ok"] is False
    body = {"runner": "openai", "model": "qwen2.5:7b", "base_url": "http://localhost:11434/v1"}
    view = client.put(f"{API}/system/agent", json={**body, "api_key": "sk-secret"}).json()
    assert view["active"] == "openai" and view["has_key"] and "sk-secret" not in str(view)
    assert client.get(f"{API}/system").json()["agent_available"] is True
    kept = client.put(f"{API}/system/agent", json=body).json()
    assert kept["has_key"]  # an empty key keeps the stored one
    assert client.put(f"{API}/system/agent", json={"runner": "cli"}).status_code == 422
    off = client.put(f"{API}/system/agent", json={"runner": "offline"}).json()
    assert off["active"] == "offline"


def test_api_token_opens_the_api_without_a_browser_session(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'token.db'}", market_provider="demo",
        docs_dir=str(tmp_path / "docs"), password="geheim", api_token="tok-123",
    )  # fmt: skip
    container = build_container(settings)
    from fastapi.testclient import TestClient

    with TestClient(create_app(container)) as client:
        assert client.get(f"{API}/system").status_code == 401
        wrong = {"Authorization": "Bearer nope"}
        assert client.get(f"{API}/system", headers=wrong).status_code == 401
        good = {"Authorization": "Bearer tok-123"}
        assert client.get(f"{API}/system", headers=good).status_code == 200
        body = {"rows": [{"name": "Demo Mina Laguna Clara", "aisc": 9.5}]}
        assert client.post(f"{API}/imports", json=body, headers=good).status_code == 201
    container.engine.dispose()
