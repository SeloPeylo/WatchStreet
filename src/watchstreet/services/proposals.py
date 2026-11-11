"""Research proposals: collected first, started deliberately (human in the loop)."""

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from watchstreet.analysis.rules import value_score
from watchstreet.constants import DEDUPE_WINDOW, MAX_OPEN_PROPOSALS_PER_SUBJECT
from watchstreet.domain import DataOrigin, ProposalState, SubjectType, ThesisStatus, WorkflowKey
from watchstreet.errors import WatchStreetError
from watchstreet.metrics import KEY_METRICS_PRODUCING, KEY_METRICS_PROJECT, METRICS
from watchstreet.models import (
    Asset,
    Company,
    DocumentLink,
    Proposal,
    Stake,
    Thesis,
    ThesisLink,
    Ticket,
)
from watchstreet.services.tickets import create_ticket
from watchstreet.timeutil import utcnow

HIGH, MEDIUM, LOW = 1.0, 0.6, 0.3


class ProposalError(WatchStreetError, ValueError):
    """Invalid proposal input."""


@dataclass(frozen=True)
class Template:
    key: str
    label: str
    workflow: WorkflowKey
    question: str  # may use {name} and {metric}


TEMPLATES: dict[str, Template] = {
    t.key: t
    for t in (
        Template(
            "fill_metric",
            "Fehlende Kennzahl beschaffen",
            WorkflowKey.FILL_METRIC,
            "{metric} für {name} aus Primärquellen beschaffen.",
        ),
        Template(
            "estimate_cost",
            "Kosten schätzen",
            WorkflowKey.ESTIMATE_COST,
            "Stückkosten von {name} als begründete Bandbreite schätzen.",
        ),
        Template(
            "takeover",
            "Übernahmeziel?",
            WorkflowKey.STRATEGIC_QUESTION,
            "Ist {name} ein plausibles Übernahmeziel für benachbarte Betreiber?",
        ),
        Template(
            "strategic",
            "Strategische Bedeutung",
            WorkflowKey.STRATEGIC_QUESTION,
            "Welche strategische Bedeutung hat {name}?",
        ),
        Template(
            "cost_structure",
            "Kostenstruktur erklären",
            WorkflowKey.STRATEGIC_QUESTION,
            "Warum weichen die Kosten von {name} von der Vergleichsgruppe ab?",
        ),
        Template(
            "financing",
            "Finanzierung klären",
            WorkflowKey.STRATEGIC_QUESTION,
            "Wie finanziert {name} die nächsten zwölf Monate, und zu welchen Konditionen?",
        ),
        Template(
            "management",
            "Management beurteilen",
            WorkflowKey.STRATEGIC_QUESTION,
            "Wer führt {name}, mit welcher Erfolgsbilanz und wie viel eigenem Geld?",
        ),
        Template(
            "profile",
            "Objekt-Profil recherchieren",
            WorkflowKey.STRATEGIC_QUESTION,
            "Status, Betreiber, Produktion und Kosten von {name} aus Primärquellen belegen.",
        ),
        Template(
            "verify",
            "Importierte Angabe prüfen",
            WorkflowKey.VERIFY_IMPORT,
            "{metric} für {name} gegen Primärquellen prüfen.",
        ),
        Template("free", "Freie Frage", WorkflowKey.STRATEGIC_QUESTION, "{question}"),
        Template(
            "read_document",
            "Dokument lesen",
            WorkflowKey.READ_DOCUMENT,
            "Dokument zu {name} abrufen und auswerten.",
        ),
    )
}


def subject_label(session: Session, subject_type: str, subject_id: int) -> str:
    models: dict[str, Any] = {
        SubjectType.ASSET: Asset,
        SubjectType.COMPANY: Company,
        SubjectType.THESIS: Thesis,
    }
    model = models.get(subject_type)
    row = session.get(model, subject_id) if model else None
    if row is None:
        msg = "Das Objekt, auf das sich der Vorschlag bezieht, existiert nicht"
        raise ProposalError(msg)
    return str(getattr(row, "name", None) or row.title)


def _in_portfolio(session: Session, asset_id: int) -> bool:
    companies = session.scalars(
        select(Company)
        .join(Stake, Stake.company_id == Company.id)
        .where(Stake.asset_id == asset_id)
    )
    return any(c.stock is not None and c.stock.holding is not None for c in companies)


def _value_parts(
    session: Session, subject_type: str, subject_id: int, template_key: str, params: dict[str, Any]
) -> dict[str, float]:
    """The five part scores; each is a simple, explainable rule."""
    key_metric = params.get("metric") in (*KEY_METRICS_PRODUCING, *KEY_METRICS_PROJECT)
    in_thesis = session.scalars(
        select(ThesisLink.id)
        .join(Thesis, Thesis.id == ThesisLink.thesis_id)
        .where(
            ThesisLink.target_type == subject_type,
            ThesisLink.target_id == subject_id,
            Thesis.status == ThesisStatus.ACTIVE,
        )
    ).first()
    recent = session.scalars(
        select(Ticket.id).where(
            Ticket.subject_type == subject_type,
            Ticket.subject_id == subject_id,
            Ticket.workflow == TEMPLATES[template_key].workflow,
            Ticket.created_at > utcnow() - DEDUPE_WINDOW,
        )
    ).first()
    has_documents = session.scalars(
        select(DocumentLink.id).where(
            DocumentLink.subject_type == subject_type, DocumentLink.subject_id == subject_id
        )
    ).first()
    held = subject_type == SubjectType.ASSET and _in_portfolio(session, subject_id)
    return {
        "insight": HIGH if template_key == "fill_metric" and key_metric else MEDIUM,
        "relevance": HIGH if in_thesis or held else LOW,
        "novelty": LOW if recent else HIGH,
        "data": HIGH if has_documents else LOW,
        "investment": HIGH if held else LOW,
    }


def open_proposals(session: Session, subject_type: str, subject_id: int) -> list[Proposal]:
    return list(
        session.scalars(
            select(Proposal).where(
                Proposal.subject_type == subject_type,
                Proposal.subject_id == subject_id,
                Proposal.state == ProposalState.DRAFT,
            )
        )
    )


def create_proposal(  # noqa: PLR0913
    session: Session,
    subject_type: str,
    subject_id: int,
    template_key: str,
    *,
    question: str = "",
    params: dict[str, Any] | None = None,
    origin: str = DataOrigin.USER,
    thesis_id: int | None = None,
) -> Proposal | None:
    """Add a proposal. Machine-made duplicates and overflow are dropped (returns ``None``)."""
    template = TEMPLATES.get(template_key)
    if template is None:
        msg = f"Unbekannte Vorlage: {template_key}"
        raise ProposalError(msg)
    params = dict(params or {})
    name = subject_label(session, subject_type, subject_id)
    metric = METRICS[params["metric"]].label if params.get("metric") in METRICS else ""
    text = question.strip() or template.question.format(name=name, metric=metric, question="")
    if not text.strip():
        msg = "Die Frage darf nicht leer sein"
        raise ProposalError(msg)
    existing = open_proposals(session, subject_type, subject_id)
    same = [
        p
        for p in existing
        if (p.origin, p.template_key, p.params, p.question)
        == (DataOrigin.USER, template_key, params, text)
    ]
    if origin == DataOrigin.USER and same:
        return same[0]  # a second click must not queue the same question twice
    if origin != DataOrigin.USER:
        duplicate = any(p.template_key == template_key and p.params == params for p in existing)
        if duplicate or len(existing) >= MAX_OPEN_PROPOSALS_PER_SUBJECT:
            return None
    parts = _value_parts(session, subject_type, subject_id, template_key, params)
    proposal = Proposal(
        subject_type=subject_type,
        subject_id=subject_id,
        thesis_id=thesis_id,
        template_key=template_key,
        question=text,
        params=params,
        origin=origin,
        value_parts=parts,
        value_score=value_score(parts),
    )
    session.add(proposal)
    session.flush()
    return proposal


def start(session: Session, proposal: Proposal) -> Ticket:
    """The deliberate step: only now a ticket exists and an agent may run."""
    if proposal.state != ProposalState.DRAFT:
        msg = "Der Vorschlag wurde bereits gestartet oder verworfen"
        raise ProposalError(msg)
    template = TEMPLATES[proposal.template_key]
    ticket = create_ticket(
        session,
        proposal.subject_type,
        proposal.subject_id,
        template.workflow,
        proposal.question,
        params={**proposal.params, "question": proposal.question, "thesis_id": proposal.thesis_id},
        proposal_id=proposal.id,
    )
    proposal.state, proposal.ticket_id = ProposalState.STARTED, ticket.id
    return ticket


def dismiss(session: Session, proposal: Proposal) -> None:
    if proposal.state == ProposalState.DRAFT:
        proposal.state = ProposalState.DISMISSED
        session.flush()


def update_question(session: Session, proposal: Proposal, question: str) -> None:
    if proposal.state != ProposalState.DRAFT or not question.strip():
        msg = "Nur offene Vorschläge mit nicht leerer Frage lassen sich ändern"
        raise ProposalError(msg)
    proposal.question = question.strip()
    session.flush()


def list_proposals(session: Session, state: str = ProposalState.DRAFT) -> list[Proposal]:
    return list(
        session.scalars(
            select(Proposal)
            .where(Proposal.state == state)
            .order_by(Proposal.value_score.desc(), Proposal.id.desc())
        )
    )
