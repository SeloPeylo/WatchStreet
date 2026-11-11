"""ORM rows as JSON-ready dictionaries (one place, so every endpoint answers alike)."""

from typing import Any

from watchstreet.models import (
    ChangeEntry,
    Document,
    Event,
    Fact,
    Finding,
    Milestone,
    Proposal,
    Thesis,
    Ticket,
)
from watchstreet.services.facts import display_value
from watchstreet.services.proposals import TEMPLATES

EXCERPT_CHARS = 400


def proposal(row: Proposal, subject_name: str = "") -> dict[str, Any]:
    return {
        "id": row.id,
        "subject_type": row.subject_type,
        "subject_id": row.subject_id,
        "subject_name": subject_name,
        "template": row.template_key,
        "template_label": TEMPLATES[row.template_key].label,
        "question": row.question,
        "params": row.params,
        "origin": row.origin,
        "value_score": row.value_score,
        "value_parts": row.value_parts,
        "state": row.state,
        "ticket_id": row.ticket_id,
        "thesis_id": row.thesis_id,
        "created_at": row.created_at.isoformat(),
    }


def ticket(row: Ticket, subject_name: str = "", *, full: bool = False) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": row.id,
        "subject_type": row.subject_type,
        "subject_id": row.subject_id,
        "subject_name": subject_name,
        "workflow": row.workflow,
        "title": row.title,
        "status": row.status,
        "summary": row.summary,
        "error": row.error,
        "runner": row.runner,
        "seen": row.seen,
        "created_at": row.created_at.isoformat(),
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
    }
    if full:
        data["result"] = row.result
        data["params"] = row.params
    return data


def finding(row: Finding) -> dict[str, Any]:
    return {
        "id": row.id,
        "subject_type": row.subject_type,
        "subject_id": row.subject_id,
        "ticket_id": row.ticket_id,
        "kind": row.kind,
        "epistemic": row.epistemic,
        "text": row.text,
        "uncertainty": row.uncertainty,
        "is_demo": row.is_demo,
        "created_at": row.created_at.isoformat(),
    }


def document(row: Document, *, with_text: bool = False) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": row.id,
        "url": row.url,
        "title": row.title,
        "publisher": row.publisher,
        "kind": row.kind,
        "published_at": row.published_at.date().isoformat() if row.published_at else None,
        "is_demo": bool(row.meta.get("is_demo")),
        "chars": len(row.text),
    }
    if with_text:
        data["text"] = row.text
    return data


def fact_detail(row: Fact) -> dict[str, Any]:
    """The derivation dialog: value, definition, period, source and quote, formula, inputs."""
    return {
        "id": row.id,
        "display": display_value(row),
        "value": row.value,
        "low": row.value_low,
        "high": row.value_high,
        "text": row.text,
        "unit": row.unit,
        "basis": row.basis,
        "period_end": row.period_end.isoformat() if row.period_end else None,
        "published_at": row.published_at.isoformat() if row.published_at else None,
        "recorded_at": row.recorded_at.isoformat(),
        "provenance": row.provenance,
        "claim_kind": row.claim_kind,
        "formula_key": row.formula_key,
        "inputs": row.inputs,
        "quote": row.quote,
        "confidence": row.confidence,
        "origin": row.origin,
        "superseded": row.superseded_by is not None,
        "document": document(row.document) if row.document else None,
        "is_demo": row.is_demo,
    }


def milestone(row: Milestone) -> dict[str, Any]:
    return {"id": row.id, "kind": row.kind, "day": row.day.isoformat(), "title": row.title}


def event(row: Event) -> dict[str, Any]:
    return {
        "id": row.id,
        "kind": row.kind,
        "title": row.title,
        "occurred_at": row.occurred_at.isoformat(),
        "lat": row.lat,
        "lon": row.lon,
        "severity": row.severity,
        "url": row.url,
        "is_demo": row.is_demo,
        "asset_ids": [link.asset_id for link in row.links],
    }


def change(row: ChangeEntry, subject_name: str = "") -> dict[str, Any]:
    return {
        "id": row.id,
        "at": row.at.isoformat(),
        "subject_type": row.subject_type,
        "subject_id": row.subject_id,
        "subject_name": subject_name,
        "kind": row.kind,
        "summary": row.summary,
        "old": row.old,
        "new": row.new,
    }


def thesis(row: Thesis, findings: dict[int, Finding] | None = None) -> dict[str, Any]:
    known = findings or {}
    return {
        "id": row.id,
        "title": row.title,
        "statement": row.statement,
        "horizon": row.horizon,
        "commodity": row.commodity,
        "status": row.status,
        "is_demo": row.is_demo,
        "assumptions": [{"id": a.id, "text": a.text, "status": a.status} for a in row.assumptions],
        "links": [
            {
                "id": link.id,
                "target_type": link.target_type,
                "target_id": link.target_id,
                "stance": link.stance,
                "note": link.note,
                # evidence must be readable where it is judged
                "finding": finding(known[link.target_id])
                if link.target_type == "finding" and link.target_id in known
                else None,
            }
            for link in row.links
        ],
        "asset_ids": [link.target_id for link in row.links if link.target_type == "asset"],
    }
