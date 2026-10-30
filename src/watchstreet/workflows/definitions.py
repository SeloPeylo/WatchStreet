"""The concrete workflows and their registry."""

from typing import Any

from sqlalchemy import select

from watchstreet.constants import DEFAULT_INTERVAL, TECHNICAL_SCHEME
from watchstreet.domain import InsightCategory, WorkflowKey
from watchstreet.drafts import InsightDraft, ScoreDraft, WorkflowResult
from watchstreet.market.base import MarketDataError
from watchstreet.models import MarketEvent
from watchstreet.profiles.registry import PROFILES, get_profile
from watchstreet.profiles.scoring import technical_score
from watchstreet.services.valuation import compute_valuation
from watchstreet.workflows.base import Workflow, WorkflowContext
from watchstreet.workflows.briefing import Briefing
from watchstreet.workflows.intel_flows import IntelTriage, ReadFiling, SecSync
from watchstreet.workflows.llm import LlmWorkflow


class InitialHolding(LlmWorkflow):
    key = WorkflowKey.INITIAL_HOLDING
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
    persist_scores = True
    task = (
        "Erstbewertung einer Watchlist-Aktie. Wäge ab, ob sich ein Kauf lohnt, nenne Argumente "
        "dafür und dagegen, formuliere eine These und schlage Folgetickets vor."
    )


class TopicAnalysis(LlmWorkflow):
    key = WorkflowKey.TOPIC_ANALYSIS
    task = (
        "Analysiere das angegebene Thema ('topic') für diese Aktie anhand der Fakten und des "
        "bisherigen Wissens. Liefere konkrete Erkenntnisse als Insights."
    )


class EventReview(LlmWorkflow):
    key = WorkflowKey.EVENT_REVIEW
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
    persist_scores = True
    task = (
        "Prüfe die bestehende Investmentthese ('thesis') gegen die aktuellen Fakten, Scores im "
        "Vergleich zu 'previous_scores' und neue Meldungen. Setze thesis_status und begründe."
    )


class ClassifyStock(LlmWorkflow):
    key = WorkflowKey.CLASSIFY_STOCK
    task = (
        "Bestimme, welches Bewertungsprofil zu dieser Aktie passt (siehe 'company_info' und "
        "'available_profiles'). Setze es mit set_profile bzw. im Feld 'profile'. Ändere es nur, "
        "wenn das aktuelle Profil offensichtlich falsch ist."
    )

    def extra_facts(self, ctx: WorkflowContext) -> dict[str, Any]:  # noqa: ARG002
        return {"available_profiles": {k: p.description for k, p in PROFILES.items()}}


class ResearchDatapoints(LlmWorkflow):
    key = WorkflowKey.RESEARCH_DATAPOINTS
    task = (
        "Das Bewertungsprofil braucht Eingaben ('missing_inputs'), die keine Kennzahlen-API "
        "liefert. Rufe get_datapoint_specs auf und trage nur Werte ein, die du belastbar kennst, "
        "mit Quelle und ehrlicher Konfidenz. Rate nicht; nicht Gewusstes bleibt eine Lücke. "
        "Schlage danach valuation_score als Folgeticket vor."
    )

    def extra_facts(self, ctx: WorkflowContext) -> dict[str, Any]:
        profile = get_profile(ctx.stock.profile)
        return {
            "datapoint_specs": [
                {"key": d.key, "label": d.label, "unit": d.unit, "per_subject": d.per_subject}
                for d in profile.datapoints
            ],
        }


class ValuationScore(Workflow):
    key = WorkflowKey.VALUATION_SCORE

    def run(self, ctx: WorkflowContext) -> WorkflowResult:
        quote = ctx.market.try_quote(ctx.stock.symbol)
        fundamentals = ctx.market.fundamentals(ctx.stock.symbol)
        result = compute_valuation(
            ctx.market, ctx.stock, quote.price if quote else None, fundamentals
        )
        if result is None:
            return WorkflowResult(summary="Zu wenige Kennzahlen für einen Bewertungs-Score.")
        missing = result.details.get("missing", [])
        note = " (vorläufig)" if result.details.get("provisional") else ""
        gaps = f" Lücken: {', '.join(missing)}." if missing else ""
        return WorkflowResult(
            summary=f"{get_profile(ctx.stock.profile).label}: {result.label} "
            f"({result.value}){note}, "
            f"Abdeckung {result.details['coverage']}.{gaps}",
            scores=[ScoreDraft(result.scheme, result.value, result.label, result.details)],
            insights=[
                InsightDraft(InsightCategory.VALUATION, f"{result.scheme}: {result.label}{note}")
            ],
        )


class TechnicalSnapshot(Workflow):
    key = WorkflowKey.TECHNICAL_SNAPSHOT

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
        ClassifyStock(),
        ResearchDatapoints(),
        Briefing(),
        SecSync(),
        ReadFiling(),
        IntelTriage(),
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
