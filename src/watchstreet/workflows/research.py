"""The four research workflows. Deterministic steps come first; an agent is asked only for what
needs judgement, and everything it returns passes the same evidence checks as any other input.
"""

import json
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from watchstreet.agents.base import AgentError, AgentRequest, AgentRunner
from watchstreet.agents.tools import Tool, ToolError
from watchstreet.analysis.rules import peer_range
from watchstreet.commodities import BY_KEY
from watchstreet.constants import MAX_AGENT_FACTS, MAX_CONTEXT_SNIPPETS, MAX_FOLLOWUPS_PER_TICKET
from watchstreet.domain import (
    ClaimKind,
    DataOrigin,
    Epistemic,
    FindingKind,
    Provenance,
    Stance,
    SubjectType,
    WorkflowKey,
)
from watchstreet.errors import WatchStreetError
from watchstreet.intel import documents
from watchstreet.intel.fetch import Fetcher
from watchstreet.metrics import EXTRACT_PATTERNS, METRICS, PRODUCING_STATUSES, parse_number
from watchstreet.models import Asset, Document, DocumentLink, Finding, Thesis, Ticket
from watchstreet.services import theses as thesis_service
from watchstreet.services.changes import log_change
from watchstreet.services.engine import peer_costs
from watchstreet.services.facts import FactError, FactInput, record_fact
from watchstreet.services.proposals import create_proposal
from watchstreet.services.world import ViewContext, card, load_bundle, primary_commodity

OFFLINE_RUNNER = "offline"
SUMMARY_CHARS = 300
SENTENCE_END = re.compile(r"\.(?=\s|$)|\n")
SYSTEM_PROMPT = (
    "Du bist ein Research-Agent für Rohstoffinvestments. Antworte ausschliesslich mit einem "
    'JSON-Objekt: {"answer": str, "uncertainties": [str], "alternatives": [str], '
    '"facts": [{"metric": str, "value": number|null, "low": number|null, '
    '"high": number|null, "unit": str, "basis": str, "document_id": int|null, '
    '"quote": str, "provenance": "reported"|"estimated"}], "followups": [str]}. '
    "Ein berichteter Wert braucht document_id und ein wörtliches Zitat aus diesem Dokument. "
    "Was du nicht belegen kannst, bleibt unbekannt. Keine Anlageempfehlungen."
)


class WorkflowError(WatchStreetError, RuntimeError):
    """A workflow cannot run (wrong subject, missing parameter)."""


class FactDraft(BaseModel):
    metric: str
    value: float | None = None
    low: float | None = None
    high: float | None = None
    unit: str = ""
    basis: str = ""
    document_id: int | None = None
    quote: str = ""
    provenance: str = Provenance.REPORTED


class AgentAnswer(BaseModel):
    answer: str = ""
    uncertainties: list[str] = []
    alternatives: list[str] = []
    facts: list[FactDraft] = []
    followups: list[str] = []


@dataclass
class ResearchContext:
    session: Session
    ticket: Ticket
    runner: AgentRunner
    fetcher: Fetcher
    view: ViewContext
    is_demo: bool = False


@dataclass
class ResearchResult:
    answer: str = ""
    fact_ids: list[int] = field(default_factory=list)
    uncertainties: list[str] = field(default_factory=list)
    alternatives: list[str] = field(default_factory=list)
    not_found: list[str] = field(default_factory=list)
    sources: list[int] = field(default_factory=list)
    followups: list[str] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)
    agent_used: bool = False


# --- shared steps ---------------------------------------------------------------


def _asset(ctx: ResearchContext) -> Asset:
    asset = ctx.session.get(Asset, ctx.ticket.subject_id)
    if ctx.ticket.subject_type != SubjectType.ASSET or asset is None:
        msg = "Dieser Workflow braucht eine Mine oder ein Projekt als Bezug"
        raise WorkflowError(msg)
    return asset


def linked_documents(session: Session, subject_type: str, subject_id: int) -> list[Document]:
    return list(
        session.scalars(
            select(Document)
            .join(DocumentLink, DocumentLink.document_id == Document.id)
            .where(DocumentLink.subject_type == subject_type, DocumentLink.subject_id == subject_id)
            .order_by(Document.published_at.desc())
        )
    )


def _unit(asset: Asset, metric_key: str) -> str:
    commodity = BY_KEY.get(primary_commodity(asset))
    metric = METRICS[metric_key]
    if commodity is None:
        return ""
    if metric.per_unit:
        return commodity.price_unit
    return f"{commodity.unit}/Jahr" if metric.annual else commodity.unit


def _sentence_around(text: str, start: int, end: int) -> str:
    """The sentence containing a match: the verbatim quote that proves the number."""
    left = max((m.end() for m in SENTENCE_END.finditer(text, 0, start)), default=0)
    right_match = SENTENCE_END.search(text, end)
    right = right_match.start() if right_match else len(text)
    return text[left:right].strip()


def extract_metric(
    ctx: ResearchContext, asset: Asset, doc: Document, metric_key: str
) -> int | None:
    """Deterministic extraction: find the labelled number and store it with its sentence as quote."""
    pattern = EXTRACT_PATTERNS.get(metric_key)
    match = pattern.search(doc.text) if pattern else None
    if match is None:
        return None
    published = doc.published_at.date() if doc.published_at else None
    try:
        fact = record_fact(
            ctx.session,
            FactInput(
                SubjectType.ASSET,
                asset.id,
                metric_key,
                value=parse_number(match.group("value")),
                unit=_unit(asset, metric_key),
                basis=f"{METRICS[metric_key].label} laut Quelle"
                if METRICS[metric_key].is_cost
                else "",
                period_end=published,
                published_at=published,
                document_id=doc.id,
                quote=_sentence_around(doc.text, match.start(), match.end()),
                confidence="medium",
                origin=DataOrigin.API,
                ticket_id=ctx.ticket.id,
                is_demo=ctx.is_demo,
            ),
        )
    except FactError:
        return None
    return fact.id


def _context_text(ctx: ResearchContext, asset: Asset, docs: list[Document], query: str) -> str:
    bundle = load_bundle(ctx.session, [asset.id])
    data = card(asset, bundle, ctx.view)
    lines = [
        f"Objekt: {asset.name} ({data['status']}, {data['commodity']}, {asset.country})",
        f"Betreiber: {data['operator'] or 'unbekannt'}",
        "Bekannte Kennzahlen:",
    ]
    lines += [
        f"- {m['label']}: {m.get('value') or m.get('text') or 'unbekannt'} {m.get('unit', '')} "
        f"[{m['provenance']}]"
        for m in data["metrics"]
    ]
    snippets = 0
    for doc in docs:
        for hit in documents.search(doc, query):
            if snippets >= MAX_CONTEXT_SNIPPETS:
                break
            lines.append(f"Dokument {doc.id} ({doc.title}): …{hit.text}…")
            snippets += 1
    return "\n".join(lines)


def _tools(ctx: ResearchContext, asset: Asset, result: ResearchResult) -> list[Tool]:
    """Tools for tool-capable runners; each handler validates and answers in plain text."""

    def document(args: dict[str, Any]) -> Document:
        doc = ctx.session.get(Document, int(args.get("document_id", 0)))
        if doc is None:
            msg = "Dokument nicht gefunden"
            raise ToolError(msg)
        return doc

    def search(args: dict[str, Any]) -> str:
        hits = documents.search(document(args), str(args.get("query", "")))
        return "\n".join(f"[{h.offset}] {h.text}" for h in hits) or "Keine Treffer"

    def read(args: dict[str, Any]) -> str:
        return documents.read_chunk(document(args), int(args.get("offset", 0)))

    def fact(args: dict[str, Any]) -> str:
        try:
            draft = FactDraft.model_validate(args)
        except ValidationError as exc:
            raise ToolError(str(exc)) from exc
        before = len(result.fact_ids)
        _apply_facts(ctx, asset, [draft], result)
        return "gespeichert" if len(result.fact_ids) > before else result.rejected[-1]

    def followup(args: dict[str, Any]) -> str:
        result.followups.append(str(args.get("question", "")))
        return "als Vorschlag vorgemerkt"

    doc_id = {"document_id": {"type": "integer"}}

    def schema(props: dict[str, Any], required: list[str]) -> dict[str, Any]:
        return {"type": "object", "properties": props, "required": required}

    handlers: list[tuple[str, str, dict[str, Any], Callable[[dict[str, Any]], str]]] = [
        (
            "search_document",
            "Sucht Textstellen in einem gespeicherten Dokument.",
            schema({**doc_id, "query": {"type": "string"}}, ["document_id", "query"]),
            search,
        ),
        (
            "read_document",
            "Liest einen Abschnitt eines gespeicherten Dokuments.",
            schema({**doc_id, "offset": {"type": "integer"}}, ["document_id"]),
            read,
        ),
        (
            "record_fact",
            "Speichert eine Kennzahl; berichtete Werte brauchen ein wörtliches Zitat.",
            schema(
                {
                    **doc_id,
                    "metric": {"type": "string", "enum": sorted(METRICS)},
                    "value": {"type": "number"},
                    "low": {"type": "number"},
                    "high": {"type": "number"},
                    "unit": {"type": "string"},
                    "basis": {"type": "string"},
                    "quote": {"type": "string"},
                    "provenance": {"type": "string", "enum": ["reported", "estimated"]},
                },
                ["metric"],
            ),
            fact,
        ),
        (
            "propose_followup",
            "Merkt eine Folgefrage als Vorschlag für den Nutzer vor.",
            schema({"question": {"type": "string"}}, ["question"]),
            followup,
        ),
    ]
    return [Tool(name, text, params, handler) for name, text, params, handler in handlers]


def _parse_answer(raw: str) -> AgentAnswer:
    """Agent output is untrusted: accept a JSON object, otherwise keep the text as the answer."""
    start, end = raw.find("{"), raw.rfind("}")
    if start != -1 and end > start:
        try:
            return AgentAnswer.model_validate(json.loads(raw[start : end + 1]))
        except (json.JSONDecodeError, ValidationError):
            pass
    return AgentAnswer(answer=raw.strip())


def _apply_facts(
    ctx: ResearchContext, asset: Asset, drafts: list[FactDraft], result: ResearchResult
) -> None:
    for draft in drafts[:MAX_AGENT_FACTS]:
        doc = ctx.session.get(Document, draft.document_id) if draft.document_id else None
        published = doc.published_at.date() if doc and doc.published_at else None
        estimated = draft.provenance == Provenance.ESTIMATED
        try:
            fact = record_fact(
                ctx.session,
                FactInput(
                    SubjectType.ASSET,
                    asset.id,
                    draft.metric,
                    value=draft.value,
                    low=draft.low,
                    high=draft.high,
                    unit=draft.unit
                    or (_unit(asset, draft.metric) if draft.metric in METRICS else ""),
                    basis=draft.basis,
                    period_end=published,
                    published_at=published,
                    provenance=Provenance.ESTIMATED if estimated else Provenance.REPORTED,
                    claim_kind=ClaimKind.AI_INFERENCE if estimated else ClaimKind.ACTUAL,
                    document_id=draft.document_id,
                    quote=draft.quote,
                    origin=DataOrigin.AGENT,
                    ticket_id=ctx.ticket.id,
                    is_demo=ctx.is_demo,
                ),
            )
        except FactError as exc:
            result.rejected.append(f"{draft.metric}: {exc}")
            continue
        result.fact_ids.append(fact.id)
        if draft.document_id and draft.document_id not in result.sources:
            result.sources.append(draft.document_id)


def ask_agent(ctx: ResearchContext, asset: Asset, question: str, context: str) -> ResearchResult:
    """One agent session; without a configured agent the result says so instead of guessing."""
    result = ResearchResult()
    if ctx.runner.name == OFFLINE_RUNNER:
        result.uncertainties.append(
            "Kein Agent konfiguriert: nur deterministische Schritte wurden ausgeführt."
        )
        return result
    prompt = f"Frage: {question}\n\n{context}"
    if getattr(ctx.runner, "supports_tools", False):
        run = ctx.runner.run_with_tools(SYSTEM_PROMPT, prompt, _tools(ctx, asset, result))  # type: ignore[attr-defined]
        raw = str(run.text)
    else:
        raw = ctx.runner.complete(AgentRequest(ctx.ticket.workflow, SYSTEM_PROMPT, prompt))
    answer = _parse_answer(raw)
    result.agent_used = True
    result.answer = answer.answer
    result.uncertainties += answer.uncertainties
    result.alternatives += answer.alternatives
    result.followups += answer.followups
    _apply_facts(ctx, asset, answer.facts, result)
    return result


# --- workflows --------------------------------------------------------------------


def fill_metric(ctx: ResearchContext) -> ResearchResult:
    asset = _asset(ctx)
    metric_key = str(ctx.ticket.params.get("metric", ""))
    if metric_key not in METRICS:
        msg = "Keine gültige Kennzahl angegeben"
        raise WorkflowError(msg)
    label = METRICS[metric_key].label
    docs = linked_documents(ctx.session, SubjectType.ASSET, asset.id)
    for doc in docs:
        fact_id = extract_metric(ctx, asset, doc, metric_key)
        if fact_id is not None:
            return ResearchResult(
                answer=f"{label} für {asset.name} in „{doc.title}“ gefunden und mit Zitat belegt.",
                fact_ids=[fact_id],
                sources=[doc.id],
            )
    result = ask_agent(ctx, asset, ctx.ticket.title, _context_text(ctx, asset, docs, label))
    if not result.fact_ids:
        result.not_found.append(f"{label}: in {len(docs)} gespeicherten Dokument(en) nicht belegt")
        result.answer = result.answer or f"{label} für {asset.name} konnte nicht belegt werden."
        result.followups.append(f"Dokument mit {label} zu {asset.name} per URL hinzufügen")
    return result


def estimate_cost(ctx: ResearchContext) -> ResearchResult:
    asset = _asset(ctx)
    bundle = load_bundle(ctx.session)
    peers = peer_costs(bundle, asset, ctx.view)
    band = peer_range([p.value for p in peers if p.value is not None])
    if band is None:
        return ResearchResult(
            answer=f"Für {asset.name} gibt es zu wenige belegte Vergleichswerte für eine Schätzung.",
            not_found=[f"Vergleichsgruppe: nur {len(peers)} belegte Stückkosten"],
        )
    period = next((p for p in bundle.assets if p.id == asset.id), asset)
    data = card(period, bundle, ctx.view)
    producing = data["status"] in PRODUCING_STATUSES
    fact = record_fact(
        ctx.session,
        FactInput(
            SubjectType.ASSET,
            asset.id,
            "aisc" if producing else "expected_aisc",
            low=round(band[0], 2),
            high=round(band[1], 2),
            unit=_unit(asset, "aisc"),
            basis=f"Interquartilsbereich der AISC von {len(peers)} produzierenden Vergleichsminen",
            provenance=Provenance.ESTIMATED,
            claim_kind=ClaimKind.HYPOTHESIS,
            formula_key="peer_iqr",
            inputs={"fact_ids": [p.id for p in peers]},
            confidence="low",
            origin=DataOrigin.ENGINE,
            ticket_id=ctx.ticket.id,
            period_end=ctx.view.today,
            published_at=ctx.view.today,
            is_demo=ctx.is_demo,
        ),
    )
    return ResearchResult(
        answer=(
            f"Stückkosten von {asset.name} auf {band[0]:,.0f}–{band[1]:,.0f} {fact.unit} geschätzt "
            f"(Vergleichsgruppe, n={len(peers)})."
        ),
        fact_ids=[fact.id],
        uncertainties=[
            "Die Bandbreite stammt aus Vergleichsminen, nicht aus Daten dieses Objekts.",
            "Abbauverfahren, Gehalt und Standortkosten sind nicht berücksichtigt.",
        ],
    )


def strategic_question(ctx: ResearchContext) -> ResearchResult:
    asset = _asset(ctx)
    docs = linked_documents(ctx.session, SubjectType.ASSET, asset.id)
    context = _context_text(ctx, asset, docs, asset.name)
    result = ask_agent(ctx, asset, ctx.ticket.title, context)
    if not result.agent_used:
        result.answer = "Zusammenstellung der bekannten Daten ohne Bewertung:\n" + context
        result.not_found.append("Bewertung der Frage (braucht einen Agenten)")
    result.sources += [d.id for d in docs if d.id not in result.sources]
    return result


def read_document(ctx: ResearchContext) -> ResearchResult:
    asset = _asset(ctx)
    url = str(ctx.ticket.params.get("url", ""))
    fetched = ctx.fetcher.fetch(url)
    doc, _created = documents.store_document(
        ctx.session,
        url=fetched.url,
        text=fetched.text,
        kind="other",
        publisher=urlparse(fetched.url).hostname or "",
        title=str(ctx.ticket.params.get("title", url)),
        published_at=None,
        meta={"is_demo": ctx.is_demo},
    )
    link_document(ctx.session, doc.id, SubjectType.ASSET, asset.id)
    result = ResearchResult(sources=[doc.id])
    for metric_key in EXTRACT_PATTERNS:
        fact_id = extract_metric(ctx, asset, doc, metric_key)
        if fact_id is not None:
            result.fact_ids.append(fact_id)
    agent = ask_agent(ctx, asset, ctx.ticket.title, _context_text(ctx, asset, [doc], asset.name))
    result.fact_ids += agent.fact_ids
    result.uncertainties += agent.uncertainties
    result.rejected += agent.rejected
    result.agent_used = agent.agent_used
    result.answer = agent.answer or (
        f"Dokument gespeichert ({len(doc.text):,} Zeichen); {len(result.fact_ids)} Kennzahl(en) belegt."
    )
    if doc.published_at is None:
        result.uncertainties.append(
            "Veröffentlichungsdatum unbekannt: Werte erscheinen nicht in der Sicht „damals bekannt“."
        )
    return result


def link_document(session: Session, document_id: int, subject_type: str, subject_id: int) -> None:
    exists = session.scalars(
        select(DocumentLink.id).where(
            DocumentLink.document_id == document_id,
            DocumentLink.subject_type == subject_type,
            DocumentLink.subject_id == subject_id,
        )
    ).first()
    if not exists:
        session.add(
            DocumentLink(document_id=document_id, subject_type=subject_type, subject_id=subject_id)
        )
        session.flush()


WORKFLOWS: dict[str, Callable[[ResearchContext], ResearchResult]] = {
    WorkflowKey.FILL_METRIC: fill_metric,
    WorkflowKey.ESTIMATE_COST: estimate_cost,
    WorkflowKey.STRATEGIC_QUESTION: strategic_question,
    WorkflowKey.READ_DOCUMENT: read_document,
}


def _store(ctx: ResearchContext, result: ResearchResult) -> None:
    """Persist the outcome where it will be found again: finding, proposals, thesis link."""
    ticket = ctx.ticket
    finding = Finding(
        subject_type=ticket.subject_type,
        subject_id=ticket.subject_id,
        ticket_id=ticket.id,
        kind=FindingKind.ANSWER,
        text=result.answer,
        epistemic=Epistemic.EVIDENCED
        if result.sources and result.fact_ids
        else Epistemic.HYPOTHESIS,
        uncertainty="\n".join(result.uncertainties),
        is_demo=ctx.is_demo,
    )
    ctx.session.add(finding)
    ctx.session.flush()
    for question in [q for q in result.followups if q.strip()][:MAX_FOLLOWUPS_PER_TICKET]:
        create_proposal(
            ctx.session,
            ticket.subject_type,
            ticket.subject_id,
            "free",
            question=question,
            origin=DataOrigin.AGENT,
        )
    thesis = ctx.session.get(Thesis, ticket.params.get("thesis_id") or 0)
    if thesis is not None:
        thesis_service.link(ctx.session, thesis, "finding", finding.id, Stance.CONTEXT)
    log_change(
        ctx.session,
        ticket.subject_type,
        ticket.subject_id,
        "ticket",
        f"Recherche abgeschlossen: {ticket.title}",
    )
    ticket.result = {**asdict(result), "finding_id": finding.id}
    ticket.summary = result.answer[:SUMMARY_CHARS]


def run_workflow(ctx: ResearchContext) -> ResearchResult:
    workflow = WORKFLOWS.get(ctx.ticket.workflow)
    if workflow is None:
        msg = f"Unbekannter Workflow: {ctx.ticket.workflow}"
        raise WorkflowError(msg)
    try:
        result = workflow(ctx)
    except AgentError as exc:
        result = ResearchResult(
            answer="Der Agent hat keine verwertbare Antwort geliefert.",
            uncertainties=[str(exc)],
        )
    _store(ctx, result)
    return result
