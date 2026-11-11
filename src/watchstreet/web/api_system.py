"""Portfolio, sources, system status and the manual."""

import json
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any

import markdown
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from watchstreet.agents.base import AgentError, AgentRequest
from watchstreet.analysis.imports import parse_table, table_from_records
from watchstreet.constants import (
    HEARTBEAT_STALE_AFTER,
    LAST_SCAN_KEY,
    MAX_DOCUMENT_CHARS,
    MAX_IMPORT_ROWS,
    MIN_IMPORT_CHARS,
    REGISTRY_MAX_SPAN_DEG,
    SCAN_REQUEST_KEY,
    SESSION_TTL,
    WORKER_HEARTBEAT_KEY,
)
from watchstreet.container import (
    AGENT_CONFIG_KEY,
    RUNTIME_RUNNERS,
    Container,
    agent_config,
    runner_for,
)
from watchstreet.domain import DataOrigin, SubjectType, TicketStatus, WorkflowKey
from watchstreet.models import (
    Asset,
    Company,
    Document,
    Holding,
    Stake,
    Thesis,
    ThesisLink,
    Ticket,
    WatchEntry,
)
from watchstreet.services import imports, portfolio, proposals
from watchstreet.services.state import touch, updated_at
from watchstreet.services.tickets import create_ticket
from watchstreet.timeutil import utcnow
from watchstreet.web import payloads
from watchstreet.web.auth import COOKIE, Auth
from watchstreet.web.deps import ContainerDep, SessionDep, get_or_404

router = APIRouter(tags=["system"])
API = "/api/v1"
MANUAL_FILE = "user-manual.md"
AGENT_TEST_CHARS = 200
REGISTRY_SOURCES = {"wikidata": "Wikidata", "mrds": "USGS MRDS"}


@router.get("/healthz")
def healthz(session: SessionDep) -> dict[str, str]:
    """Deep check: the database must answer."""
    session.execute(text("SELECT 1"))
    return {"status": "ok"}


@router.get(f"{API}/system")
def system(session: SessionDep, container: ContainerDep) -> dict[str, Any]:
    heartbeat = updated_at(session, WORKER_HEARTBEAT_KEY)
    scan = updated_at(session, LAST_SCAN_KEY)
    counts = dict(
        session.execute(select(Ticket.status, func.count()).group_by(Ticket.status)).all()
    )
    return {
        "is_demo": container.is_demo,
        "market": container.market.name,
        "runner": runner_for(container, session).name,
        "agent_available": runner_for(container, session).name != "offline",
        "unverified": len(imports.unverified_facts(session)),
        "worker_alive": heartbeat is not None and utcnow() - heartbeat < HEARTBEAT_STALE_AFTER,
        "worker_heartbeat": heartbeat.isoformat() if heartbeat else None,
        "last_scan": scan.isoformat() if scan else None,
        "tickets": {status: counts.get(status, 0) for status in TicketStatus},
        "assets": session.scalar(select(func.count()).select_from(Asset)),
        "documents": session.scalar(select(func.count()).select_from(Document)),
    }


@router.post(f"{API}/system/scan")
def request_scan(session: SessionDep) -> dict[str, str]:
    """Ask the worker to run the background scan (prices, events, engine) now."""
    touch(session, SCAN_REQUEST_KEY)
    return {"status": "requested"}


@router.get(f"{API}/manual")
def manual(container: ContainerDep) -> dict[str, str]:
    path = Path(container.settings.docs_dir) / MANUAL_FILE
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Handbuch nicht gefunden")
    source = path.read_text(encoding="utf-8").replace("](screenshots/", "](/manual-assets/")
    return {"html": markdown.markdown(source, extensions=["tables", "toc", "fenced_code"])}


# --- session ----------------------------------------------------------------------------


class LoginBody(BaseModel):
    password: str


@router.get(f"{API}/session")
def session_state(request: Request) -> dict[str, bool]:
    auth: Auth = request.app.state.auth
    return {"auth_required": auth.required, "logged_in": auth.is_valid(request.cookies.get(COOKIE))}


@router.post(f"{API}/login")
def login(body: LoginBody, request: Request, response: Response) -> dict[str, bool]:
    auth: Auth = request.app.state.auth
    token = auth.login(body.password)
    if token is None:
        raise HTTPException(status_code=401, detail="Falsches Passwort oder vorübergehend gesperrt")
    response.set_cookie(
        COOKIE,
        token,
        max_age=int(SESSION_TTL.total_seconds()),
        httponly=True,
        samesite="strict",
        secure=request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https",
    )
    return {"logged_in": True}


@router.post(f"{API}/logout")
def logout(response: Response) -> dict[str, bool]:
    response.delete_cookie(COOKIE)
    return {"logged_in": False}


# --- sources -------------------------------------------------------------------------


@router.get(f"{API}/documents")
def documents(session: SessionDep) -> list[dict[str, Any]]:
    rows = session.scalars(select(Document).order_by(Document.id.desc()))
    return [payloads.document(d) for d in rows]


@router.get(f"{API}/documents/{{document_id}}")
def document(document_id: int, session: SessionDep) -> dict[str, Any]:
    return payloads.document(get_or_404(session, Document, document_id), with_text=True)


class DocumentBody(BaseModel):
    asset_id: int
    url: str
    title: str = ""


@router.post(f"{API}/documents")
def add_document(body: DocumentBody, session: SessionDep) -> dict[str, Any]:
    """Queue fetching and reading a source by URL; the user asking for it is the approval."""
    if not body.url.startswith(("http://", "https://")):
        raise HTTPException(status_code=422, detail="Nur http(s)-Adressen sind erlaubt")
    proposal = proposals.create_proposal(
        session,
        SubjectType.ASSET,
        body.asset_id,
        "read_document",
        params={"url": body.url, "title": body.title or body.url},
    )
    if proposal is None:
        raise HTTPException(status_code=400, detail="Vorschlag konnte nicht angelegt werden")
    return payloads.ticket(proposals.start(session, proposal))


# --- registry --------------------------------------------------------------------------


class RegistryBody(BaseModel):
    source: str = "wikidata"
    company: str = ""
    south: float = 0.0
    west: float = 0.0
    north: float = 0.0
    east: float = 0.0


@router.post(f"{API}/registry/import")
def registry_import(
    body: RegistryBody, session: SessionDep, container: ContainerDep
) -> dict[str, Any]:
    """Queue loading mine locations from a public register for a map area or a company."""
    if container.is_demo:
        raise HTTPException(
            status_code=400, detail="Im Demo-Modus werden keine echten Registerdaten geladen"
        )
    company = body.company.strip()
    if body.source not in REGISTRY_SOURCES or (company and body.source != "wikidata"):
        raise HTTPException(status_code=422, detail="Unbekanntes Register")
    span = max(body.north - body.south, body.east - body.west)
    if not company and not 0 < span <= REGISTRY_MAX_SPAN_DEG:
        raise HTTPException(
            status_code=422, detail="Kartenausschnitt zu gross – bitte näher heranzoomen"
        )
    title = (
        f"Register: Minen von {company}"
        if company
        else f"Register {REGISTRY_SOURCES[body.source]}: Kartenausschnitt laden"
    )
    params = body.model_dump() if not company else {"company": company}
    ticket = create_ticket(
        session, SubjectType.REGION, 0, WorkflowKey.EXPLORE_REGISTRY, title, params=params
    )
    return payloads.ticket(ticket)


# --- analysis import ------------------------------------------------------------------


class ImportBody(BaseModel):
    """An analysis as a table (CSV, TSV, ';' or Markdown) in ``text``, or as ``rows``."""

    title: str = Field(default="", max_length=300)
    source: str = Field(default="", max_length=120)
    text: str = Field(default="", max_length=MAX_DOCUMENT_CHARS)
    rows: list[dict[str, Any]] = Field(default_factory=list, max_length=MAX_IMPORT_ROWS)


@router.post(f"{API}/imports", status_code=201)
def import_analysis(
    body: ImportBody, session: SessionDep, container: ContainerDep
) -> dict[str, Any]:
    """Import an analysis. Its assets and figures appear at once, marked as unverified.

    Send either ``text`` (a table whose header names at least ``name``; further columns such as
    company, commodity, country, lat, lon, status, share, production, aisc, reserves, resources,
    capex) or ``rows`` (a list of objects with the same keys). A new asset needs ``lat``, ``lon``
    and ``commodity``; a known asset is matched by name. Imported figures never replace sourced
    or user figures. Text without a table is handed to the configured agent as a research job.
    """
    text = body.text.strip() or (table_from_records(body.rows) if body.rows else "")
    if len(text) < MIN_IMPORT_CHARS:
        raise HTTPException(status_code=422, detail="Die Analyse ist leer oder zu kurz")
    document = imports.store_analysis(session, body.title, body.source, text)
    rows = parse_table(text)[:MAX_IMPORT_ROWS]
    outcome = imports.apply_rows(session, document, rows)
    report: dict[str, Any] = {**asdict(outcome), "document_id": document.id, "ticket_id": None}
    if not rows:
        if runner_for(container, session).name == "offline":
            report["skipped"].append(
                "Keine Tabelle erkannt. Fliesstext braucht einen konfigurierten Agenten (System)."
            )
        else:
            ticket = create_ticket(
                session, SubjectType.REGION, 0, WorkflowKey.IMPORT_ANALYSIS,
                f"Analyse zerlegen: {document.title}", params={"document_id": document.id},
            )  # fmt: skip
            report["ticket_id"] = ticket.id
    session.commit()
    return report


@router.get(f"{API}/imports/unverified")
def imports_unverified(session: SessionDep) -> list[dict[str, Any]]:
    """Every imported figure that nothing has confirmed or replaced yet."""
    return imports.unverified_facts(session)


@router.post(f"{API}/imports/verify")
def imports_verify(session: SessionDep) -> dict[str, int]:
    """Queue one verification proposal per unverified figure; they start from the backlog."""
    created = 0
    for row in imports.unverified_facts(session):
        params = {"metric": row["metric"]}
        open_ones = proposals.open_proposals(session, row["subject_type"], row["subject_id"])
        if any(p.template_key == "verify" and p.params == params for p in open_ones):
            continue
        proposals.create_proposal(
            session, row["subject_type"], row["subject_id"], "verify",
            params=params, origin=DataOrigin.USER,
        )  # fmt: skip
        created += 1
    session.commit()
    return {"created": created}


# --- agent harness ---------------------------------------------------------------------


class AgentBody(BaseModel):
    runner: str
    model: str = Field(default="", max_length=120)
    base_url: str = Field(default="", max_length=300)
    api_key: str = Field(default="", max_length=400)  # empty keeps the stored key


def _agent_view(session: Session, container: Container) -> dict[str, Any]:
    config = agent_config(session)
    return {
        "active": runner_for(container, session).name,
        "source": "runtime" if config.get("runner") in RUNTIME_RUNNERS else "environment",
        "runner": config.get("runner", container.settings.agent_runner),
        "model": config.get("model", ""),
        "base_url": config.get("base_url", ""),
        "has_key": bool(config.get("api_key")),
        "choices": list(RUNTIME_RUNNERS),
    }


@router.get(f"{API}/system/agent")
def agent_settings(session: SessionDep, container: ContainerDep) -> dict[str, Any]:
    """Which agent backend runs research; the key itself is never returned."""
    return _agent_view(session, container)


@router.put(f"{API}/system/agent")
def set_agent(body: AgentBody, session: SessionDep, container: ContainerDep) -> dict[str, Any]:
    """Choose the agent backend at runtime: none, Anthropic or an OpenAI-compatible server."""
    if body.runner not in RUNTIME_RUNNERS:
        raise HTTPException(status_code=422, detail="Unbekannter Agent")
    key = body.api_key.strip() or agent_config(session).get("api_key", "")
    config = {"runner": body.runner, "model": body.model.strip(), "api_key": key}
    config["base_url"] = body.base_url.strip()
    touch(session, AGENT_CONFIG_KEY, json.dumps(config))
    session.commit()
    return _agent_view(session, container)


@router.post(f"{API}/system/agent/test")
def test_agent(session: SessionDep, container: ContainerDep) -> dict[str, Any]:
    """One tiny request to the configured backend, to see whether key and address work."""
    runner = runner_for(container, session)
    if runner.name == "offline":
        return {"ok": False, "detail": "Kein Agent konfiguriert"}
    try:
        answer = runner.complete(AgentRequest("test", "Antworte nur mit dem Wort OK.", "Test"))
    except AgentError as exc:
        return {"ok": False, "detail": str(exc)[:AGENT_TEST_CHARS]}
    return {"ok": True, "detail": answer.strip()[:AGENT_TEST_CHARS]}


# --- portfolio -----------------------------------------------------------------------


class HoldingBody(BaseModel):
    symbol: str
    quantity: float
    avg_price: float
    bought_at: date | None = None
    intent: str = ""
    thesis_id: int | None = None
    exit_condition: str = ""
    reason: str = ""


class AdjustBody(BaseModel):
    reason: str
    intent: str | None = None
    exit_condition: str | None = None
    thesis_id: int | None = None
    clear_thesis: bool = False


class SellBody(BaseModel):
    reason: str
    price: float | None = Field(default=None, gt=0)


class WatchBody(BaseModel):
    symbol: str
    note: str = ""


def _thesis_row(thesis: Thesis, today: date, *, direct: bool) -> dict[str, Any]:
    return {
        "id": thesis.id,
        "title": thesis.title,
        "direct": direct,
        "contradicted": sum(a.status == "contradicted" for a in thesis.assumptions),
        "due": sum(
            a.status == "open" and a.review_by is not None and a.review_by <= today
            for a in thesis.assumptions
        ),
    }


def _exposure(session: Session, stock_id: int) -> dict[str, Any]:
    """The company behind a position, its assets and the theses that touch them."""
    company = session.scalars(select(Company).where(Company.stock_id == stock_id)).first()
    today = utcnow().date()
    if company is None:
        return {"company": None, "assets": [], "theses": []}
    assets = list(
        session.scalars(
            select(Asset)
            .join(Stake, Stake.asset_id == Asset.id)
            .where(Stake.company_id == company.id)
        ).unique()
    )
    linked = session.scalars(
        select(Thesis)
        .join(ThesisLink, ThesisLink.thesis_id == Thesis.id)
        .where(
            ThesisLink.target_type == SubjectType.ASSET,
            ThesisLink.target_id.in_([a.id for a in assets]),
        )
    ).unique()
    return {
        "company": {"id": company.id, "name": company.name},
        "assets": [{"id": a.id, "name": a.name} for a in assets],
        "theses": [_thesis_row(t, today, direct=False) for t in linked],
    }


@router.get(f"{API}/portfolio")
def portfolio_view(session: SessionDep, container: ContainerDep) -> dict[str, Any]:
    rows = portfolio.holding_rows(session, container.market)
    watch = portfolio.watch_entries(session)
    return {
        "holdings": [
            {
                "id": r.holding.id,
                "symbol": r.holding.stock.symbol,
                "name": r.holding.stock.name,
                "currency": r.holding.stock.currency,
                "quantity": r.holding.quantity,
                "avg_price": r.holding.avg_price,
                "bought_at": r.holding.bought_at.isoformat() if r.holding.bought_at else None,
                "intent": r.holding.intent,
                "exit_condition": r.holding.exit_condition,
                "thesis": _thesis_row(thesis, utcnow().date(), direct=True)
                if (thesis := session.get(Thesis, r.holding.thesis_id or 0))
                else None,
                "price": r.price,
                "market_value": r.market_value,
                "pnl_abs": r.pnl_abs,
                "pnl_pct": r.pnl_pct,
                "day_change_pct": r.day_change_pct,
                **_exposure(session, r.holding.stock_id),
            }
            for r in rows
        ],
        "watchlist": [
            {
                "id": w.id,
                "symbol": w.stock.symbol,
                "name": w.stock.name,
                "note": w.note,
                "price": quote.price
                if (quote := container.market.try_quote(w.stock.symbol))
                else None,
            }
            for w in watch
        ],
    }


@router.post(f"{API}/portfolio/holdings")
def add_holding(body: HoldingBody, session: SessionDep, container: ContainerDep) -> dict[str, int]:
    if body.bought_at is not None and body.bought_at > utcnow().date():
        raise HTTPException(status_code=422, detail="Das Kaufdatum liegt in der Zukunft")
    holding = portfolio.add_holding(
        session,
        container.market,
        portfolio.NewHolding(
            body.symbol, body.quantity, body.avg_price, body.bought_at, body.intent,
            body.thesis_id, body.exit_condition, body.reason,
        ),
    )  # fmt: skip
    return {"id": holding.id}


@router.patch(f"{API}/portfolio/holdings/{{holding_id}}")
def adjust_holding(
    holding_id: int, body: AdjustBody, session: SessionDep, container: ContainerDep
) -> dict[str, str]:
    """Change intent, thesis or exit condition of a position; the reason goes into the journal."""
    holding = get_or_404(session, Holding, holding_id)
    portfolio.adjust_holding(
        session, container.market, holding, body.reason, intent=body.intent,
        exit_condition=body.exit_condition, thesis_id=body.thesis_id,
        clear_thesis=body.clear_thesis,
    )  # fmt: skip
    return {"status": "adjusted"}


@router.post(f"{API}/portfolio/holdings/{{holding_id}}/sell")
def sell_holding(
    holding_id: int, body: SellBody, session: SessionDep, container: ContainerDep
) -> dict[str, str]:
    """Close a position with a reason; it stays in the decision journal."""
    holding = get_or_404(session, Holding, holding_id)
    portfolio.sell_holding(session, container.market, holding, body.reason, body.price)
    return {"status": "sold"}


@router.get(f"{API}/portfolio/decisions")
def decision_journal(session: SessionDep) -> list[dict[str, Any]]:
    """Every buy, sell and change of intent with the reason and what was known at the time."""
    return [
        {
            "id": d.id, "symbol": d.stock.symbol, "kind": d.kind, "day": d.day.isoformat(),
            "quantity": d.quantity, "price": d.price, "reason": d.reason,
            "snapshot": d.snapshot, "recorded_at": d.created_at.isoformat(),
        }
        for d in portfolio.decisions(session)
    ]  # fmt: skip


@router.delete(f"{API}/portfolio/holdings/{{holding_id}}")
def remove_holding(holding_id: int, session: SessionDep) -> dict[str, str]:
    session.delete(get_or_404(session, Holding, holding_id))
    return {"status": "deleted"}


@router.post(f"{API}/portfolio/watch")
def add_watch(body: WatchBody, session: SessionDep, container: ContainerDep) -> dict[str, int]:
    return {"id": portfolio.add_watch(session, container.market, body.symbol, body.note).id}


@router.delete(f"{API}/portfolio/watch/{{entry_id}}")
def remove_watch(entry_id: int, session: SessionDep) -> dict[str, str]:
    session.delete(get_or_404(session, WatchEntry, entry_id))
    return {"status": "deleted"}
