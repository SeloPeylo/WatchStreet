"""The concrete workflows and their registry."""

from typing import Any

from sqlalchemy import select

from watchstreet.constants import DEFAULT_INTERVAL, TECHNICAL_SCHEME, VALUATION_SCHEME
from watchstreet.domain import InsightCategory, WorkflowKey
from watchstreet.market.base import MarketDataError
from watchstreet.models import MarketEvent
from watchstreet.workflows.base import (
    InsightDraft,
    ScoreDraft,
    Workflow,
    WorkflowContext,
    WorkflowResult,
)
from watchstreet.workflows.llm import LlmWorkflow
from watchstreet.workflows.scoring import technical_score, valuation_score


class InitialHolding(LlmWorkflow):
    key = WorkflowKey.INITIAL_HOLDING
    label = "Bestandsaufnahme (Holding)"
    description = "Ausgangslage einer gehaltenen Aktie: Ziel, These, Bewertung und Technik."
    user_creatable = False
    persist_scores = True
    task = (
        "Bestandsaufnahme einer gehaltenen Position. Erfasse die Ausgangslage, leite das Ziel "
        "ab (oder übernimm die Absicht des Nutzers), formuliere eine prüfbare Investmentthese, "
        "berücksichtige Bewertungs- und Technik-Scores und schlage sinnvolle Folgetickets vor."
    )

    def extra_facts(self, ctx: WorkflowContext) -> dict[str, Any]:
        holding = ctx.stock.holding
        return {"intent": (holding.intent if holding else "") or ctx.ticket.params.get("intent")}


class InitialWatch(LlmWorkflow):
    key = WorkflowKey.INITIAL_WATCH
    label = "Kaufprüfung (Watchlist)"
    description = "Erstbewertung einer beobachteten Aktie: lohnt sich ein Kauf?"
    user_creatable = False
    persist_scores = True
    task = (
        "Erstbewertung einer Watchlist-Aktie. Wäge ab, ob sich ein Kauf lohnt, nenne Argumente "
        "dafür und dagegen, formuliere eine These und schlage Folgetickets vor."
    )


class TopicAnalysis(LlmWorkflow):
    key = WorkflowKey.TOPIC_ANALYSIS
    label = "Themenanalyse"
    description = "Vertiefende Analyse zu einem frei wählbaren Thema (z. B. Risiken, Burggraben)."
    needs_topic = True
    task = (
        "Analysiere das angegebene Thema ('topic') für diese Aktie anhand der Fakten und des "
        "bisherigen Wissens. Liefere konkrete Erkenntnisse als Insights."
    )


class EventReview(LlmWorkflow):
    key = WorkflowKey.EVENT_REVIEW
    label = "Ereignis-Prüfung"
    description = "Bewertet neue Meldungen: relevant für die These? Handlungsbedarf?"
    user_creatable = False
    task = (
        "Bewerte die neuen Meldungen ('events') auf Relevanz für die Aktie und die bestehende "
        "These. Ignoriere Rauschen. Schlage nur bei echter Relevanz Folgetickets vor."
    )

    def extra_facts(self, ctx: WorkflowContext) -> dict[str, Any]:
        ids = ctx.ticket.params.get("event_ids", [])
        rows = ctx.session.scalars(select(MarketEvent).where(MarketEvent.id.in_(ids)))
        return {"events": [row.title for row in rows]}


class ThesisCheck(LlmWorkflow):
    key = WorkflowKey.THESIS_CHECK
    label = "These prüfen"
    description = "Testet die aktuelle Investmentthese gegen neue Daten und Scores."
    persist_scores = True
    task = (
        "Prüfe die bestehende Investmentthese ('thesis') gegen die aktuellen Fakten, Scores im "
        "Vergleich zu 'previous_scores' und neue Meldungen. Setze thesis_status und begründe."
    )


class ValuationScore(Workflow):
    key = WorkflowKey.VALUATION_SCORE
    label = "Bewertungs-Score"
    description = "Deterministisches Bewertungsschema aus Kennzahlen (kein LLM)."

    def run(self, ctx: WorkflowContext) -> WorkflowResult:
        quote = ctx.market.try_quote(ctx.stock.symbol)
        result = valuation_score(
            ctx.market.fundamentals(ctx.stock.symbol),
            quote.price if quote else None,
        )
        if result is None:
            return WorkflowResult(summary="Zu wenige Kennzahlen für einen Bewertungs-Score.")
        return WorkflowResult(
            summary=f"Bewertung {result.label} ({result.value}), "
            f"Abdeckung {result.details['coverage']}.",
            scores=[ScoreDraft(result.scheme, result.value, result.label, result.details)],
            insights=[
                InsightDraft(InsightCategory.VALUATION, f"{VALUATION_SCHEME}: {result.label}")
            ],
        )


class TechnicalSnapshot(Workflow):
    key = WorkflowKey.TECHNICAL_SNAPSHOT
    label = "Technik-Snapshot"
    description = "Trend, Momentum und RSI aus den Stundenkerzen (kein LLM)."

    def run(self, ctx: WorkflowContext) -> WorkflowResult:
        try:
            candles = ctx.market.candles(ctx.stock.symbol, DEFAULT_INTERVAL)
        except MarketDataError as exc:
            return WorkflowResult(summary=f"Keine Kursdaten: {exc}")
        result = technical_score(candles)
        if result is None:
            return WorkflowResult(summary="Zu wenige Kerzen für den Technik-Score.")
        return WorkflowResult(
            summary=f"Technik {result.label} ({result.value}).",
            scores=[ScoreDraft(result.scheme, result.value, result.label, result.details)],
            insights=[
                InsightDraft(InsightCategory.TECHNICAL, f"{TECHNICAL_SCHEME}: {result.label}")
            ],
        )


REGISTRY: dict[str, Workflow] = {
    w.key: w
    for w in (
        InitialHolding(),
        InitialWatch(),
        TopicAnalysis(),
        EventReview(),
        ThesisCheck(),
        ValuationScore(),
        TechnicalSnapshot(),
    )
}


def get_workflow(key: str) -> Workflow:
    try:
        return REGISTRY[key]
    except KeyError as exc:
        msg = f"Unknown workflow: {key}"
        raise ValueError(msg) from exc


def user_workflows() -> list[Workflow]:
    return [w for w in REGISTRY.values() if w.user_creatable]


__all__ = ["REGISTRY", "get_workflow", "user_workflows"]
