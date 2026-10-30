"""Document-driven workflows: SEC sync (deterministic), filing reading and news triage (agents)."""

from typing import Any

from sqlalchemy import select

from watchstreet.agents.base import AgentError
from watchstreet.constants import (
    MAX_FILINGS_STORED,
    SEC_FORMS_ALERT,
    SEC_FORMS_FULLTEXT,
)
from watchstreet.domain import InsightCategory, WorkflowKey
from watchstreet.intel.connectors.edgar import ANNUAL_QUARTERLY_FORMS, extract_facts
from watchstreet.intel.documents import outline, store_document
from watchstreet.intel.fetch import FetchError
from watchstreet.models import Document
from watchstreet.profiles.registry import get_profile
from watchstreet.services.datapoints import as_points, latest
from watchstreet.workflows.base import (
    DatapointDraft,
    FollowUp,
    InsightDraft,
    IntelDraft,
    Workflow,
    WorkflowContext,
    WorkflowResult,
)
from watchstreet.workflows.doc_tools import DocToolBox, IntelToolBox
from watchstreet.workflows.llm import LlmWorkflow
from watchstreet.workflows.valuation import missing_inputs

FULLTEXT_PER_RUN = 2
OUTLINE_IN_PROMPT = 25
DOC_TOPIC_PREFIX = "doc:"
SEVERITY_ALERT_FILING = 3
SEVERITY_ROUTINE_FILING = 2

FILING_SYSTEM = (
    "Du liest eine Einreichung (z. B. 10-K) für ein Ticket-System und extrahierst belegte Fakten. "
    "Regeln: Nutze list_sections/search_document/read_document, um gezielt zu lesen, nicht alles. "
    "Jede Aussage, die du speicherst (record_datapoint, record_relation, record_asset, "
    "add_insight), braucht ein WÖRTLICHES Zitat (mindestens 20 Zeichen) aus dem Dokument; "
    "der Harness prüft es und "
    "lehnt Unbelegtes ab. Was nicht im Text steht, wird nicht gespeichert. Erfinde nichts. "
    "Schließe mit 2-5 deutschen Sätzen Zusammenfassung."
)
INTEL_SYSTEM = (
    "Du schneidest Quellen für eine Aktie auf das Relevante zu (keine Anlageberatung). Prüfe jede "
    "Quelle (get_document, falls nötig). Für Relevantes rufe publish_intel genau einmal auf, mit "
    "einem wörtlichen Beleg-Zitat aus der Quelle (mindestens 20 Zeichen). Bewerte Auswirkung "
    "(direction) und Schwere ehrlich; Rauschen ignorierst du. Primärquellen (filing, gov, press) "
    "wiegen schwerer als Medienberichte. Schließe mit 1-3 Sätzen Zusammenfassung auf Deutsch."
)


class SecSync(Workflow):
    key = WorkflowKey.SEC_SYNC
    label = "SEC-Abgleich"
    description = (
        "Holt neue Einreichungen von SEC EDGAR und leitet Aktienzahl/Nettoverschuldung aus den "
        "XBRL-Daten ab (deterministisch, mit Quelle; kein LLM)."
    )

    def run(self, ctx: WorkflowContext) -> WorkflowResult:
        edgar, stock = ctx.edgar, ctx.stock
        if edgar is None:
            return WorkflowResult(summary="EDGAR ist nicht konfiguriert.")
        cik = edgar.cik_for(stock.symbol)
        if cik is None:
            return WorkflowResult(
                summary=f"Kein SEC-Eintrag für {stock.symbol} (nur US-Notierungen/ADRs).",
            )
        result = WorkflowResult(summary="", data={"cik": cik})
        wanted = [
            f
            for f in edgar.recent_filings(cik)
            if f.form in (*SEC_FORMS_FULLTEXT, *SEC_FORMS_ALERT)
        ]
        fulltext = 0
        for filing in wanted[:MAX_FILINGS_STORED]:
            if ctx.session.scalar(select(Document.id).where(Document.url == filing.url)):
                continue
            text = filing.description or filing.form
            if filing.form in SEC_FORMS_FULLTEXT and fulltext < FULLTEXT_PER_RUN:
                text, fulltext = edgar.filing_text(filing.url), fulltext + 1
            doc, _ = store_document(
                ctx.session,
                url=filing.url,
                text=text,
                kind="filing",
                publisher="SEC EDGAR",
                title=f"{filing.form} {filing.filed:%Y-%m-%d} – {stock.symbol}",
                published_at=filing.filed,
                stock_id=stock.id,
                meta={"form": filing.form, "cik": cik, "accession": filing.accession},
            )
            result.insights.append(
                InsightDraft(
                    InsightCategory.NOTE,
                    f"Neue Einreichung {filing.form} vom {filing.filed:%d.%m.%Y}",
                    doc.id,
                ),
            )
            result.intel.append(self._intel(ctx, filing, doc))
            if filing.form in ANNUAL_QUARTERLY_FORMS and fulltext and not result.followups:
                self._propose_reading(ctx, result, doc)
        count = self._datapoints(ctx, result, cik)
        stored = len(result.intel)  # one alert item per newly stored filing
        result.summary = (
            f"{stored} neue Einreichung(en) gespeichert, {count} Datenpunkt(e) aus XBRL."
        )
        return result

    @staticmethod
    def _intel(ctx: WorkflowContext, filing: Any, doc: Document) -> IntelDraft:
        alert = filing.form in SEC_FORMS_ALERT
        return IntelDraft(
            headline=f"Neue Einreichung {filing.form}: {ctx.stock.symbol}",
            summary=filing.description,
            category="company",
            severity=SEVERITY_ALERT_FILING if alert else SEVERITY_ROUTINE_FILING,
            document_id=doc.id,
            impacts=((ctx.stock.id, "unknown", f"{filing.form} eingereicht"),),
            dedupe_key=f"filing:{filing.accession}",
            published_at=filing.filed,
        )

    @staticmethod
    def _propose_reading(ctx: WorkflowContext, result: WorkflowResult, doc: Document) -> None:
        if getattr(ctx.runner, "supports_tools", False):
            result.followups.append(
                FollowUp(
                    WorkflowKey.READ_FILING,
                    f"{DOC_TOPIC_PREFIX}{doc.id}",
                    "Neue Einreichung: Fakten, Zulieferer und Assets extrahieren.",
                ),
            )

    @staticmethod
    def _datapoints(ctx: WorkflowContext, result: WorkflowResult, cik: int) -> int:
        edgar = ctx.edgar
        if edgar is None:
            return 0
        try:
            facts = extract_facts(edgar.facts(cik))
        except FetchError:
            return 0
        profile = get_profile(ctx.stock.profile)
        added = 0
        known = {(d.key, d.value) for d in latest(ctx.stock) if d.origin == "api"}
        for fact in facts:
            if profile.spec(fact.key) is None or (fact.key, fact.value) in known:
                continue
            result.datapoints.append(
                DatapointDraft(
                    key=fact.key,
                    value=fact.value,
                    unit=fact.unit,
                    source=edgar.facts_url(cik),
                    confidence="high",
                    origin="api",
                    text="",
                ),
            )
            result.insights.append(
                InsightDraft(
                    InsightCategory.NOTE,
                    f"XBRL ({fact.form}, {fact.period_end}): {fact.key} aus {fact.concept}",
                ),
            )
            added += 1
        return added


class ReadFiling(Workflow):
    key = WorkflowKey.READ_FILING
    label = "Einreichung lesen"
    description = (
        "Ein Agent liest eine Einreichung gezielt und extrahiert Datenpunkte, "
        "Zulieferer/Kunden und "
        "Assets – jeweils mit wörtlichem, vom Harness geprüftem Zitat."
    )
    user_creatable = False

    def run(self, ctx: WorkflowContext) -> WorkflowResult:
        runner = ctx.runner
        if not getattr(runner, "supports_tools", False):
            msg = (
                "Einreichung lesen braucht einen Agenten mit Tool-Unterstützung "
                "(WATCHSTREET_AGENT_RUNNER=llama oder openai)."
            )
            raise AgentError(msg)
        doc = self._document(ctx)
        profile = get_profile(ctx.stock.profile)
        points = as_points(latest(ctx.stock))
        brief: dict[str, Any] = {
            "document": {"id": doc.id, "title": doc.title, "url": doc.url, "chars": len(doc.text)},
            "profile": profile.label,
            "inputs_wanted": [
                {"key": d.key, "label": d.label, "per_subject": d.per_subject}
                for d in profile.datapoints
            ],
            "still_missing": missing_inputs(profile, points),
            "sections": [
                {"offset": s.offset, "heading": s.text} for s in outline(doc)[:OUTLINE_IN_PROMPT]
            ],
        }
        box = DocToolBox(ctx, doc)
        task = (
            "Extrahiere aus der Einreichung (1) die gewünschten Eingaben als Datenpunkte, "
            "(2) wichtige Kunden/Zulieferer/Abhängigkeiten als Beziehungen, (3) Minen/Standorte "
            "als Assets mit Land, (4) die wichtigsten Risiken als Erkenntnisse. Alles mit Zitat."
        )
        run = runner.run_with_tools(  # type: ignore[attr-defined]
            FILING_SYSTEM,
            f"AUFGABE: {task}\n\n{brief}",
            box.tools(),
        )
        return box.result(
            run.text,
            {
                "runner": runner.name,
                "mode": "tools",
                "steps": run.steps,
                "tool_calls": run.tool_calls,
                "prompt_tokens": run.prompt_tokens,
                "completion_tokens": run.completion_tokens,
                "document_id": doc.id,
            },
        )

    @staticmethod
    def _document(ctx: WorkflowContext) -> Document:
        topic = str(ctx.ticket.params.get("topic", ""))
        if topic.startswith(DOC_TOPIC_PREFIX):
            doc = ctx.session.get(Document, int(topic.removeprefix(DOC_TOPIC_PREFIX)))
        else:
            doc = ctx.session.scalar(
                select(Document)
                .where(Document.stock_id == ctx.stock.id, Document.kind == "filing")
                .order_by(Document.published_at.desc()),
            )
        if doc is None or not doc.text:
            msg = "Kein lesbares Dokument gefunden (zuerst SEC-Abgleich ausführen)."
            raise AgentError(msg)
        return doc


class IntelTriage(LlmWorkflow):
    key = WorkflowKey.INTEL_TRIAGE
    label = "Nachrichten-Zuschnitt"
    description = (
        "Bewertet neue Quellen auf Relevanz für die Aktie und veröffentlicht belegte Intel-Items."
    )
    user_creatable = False
    tool_system_prompt = INTEL_SYSTEM
    task = (
        "Prüfe die gelieferten Quellen ('documents') auf Relevanz für diese Aktie, ihre These und "
        "ihre Abhängigkeiten. Veröffentliche je relevanter Quelle ein Intel-Item mit "
        "wörtlichem Zitat."
    )

    def _ids(self, ctx: WorkflowContext) -> list[int]:
        return [int(i) for i in ctx.ticket.params.get("document_ids", [])]

    def make_toolbox(self, ctx: WorkflowContext) -> IntelToolBox:
        return IntelToolBox(ctx, self._ids(ctx))

    def extra_facts(self, ctx: WorkflowContext) -> dict[str, Any]:
        rows = ctx.session.scalars(select(Document).where(Document.id.in_(self._ids(ctx))))
        return {
            "documents": [
                {
                    "id": d.id,
                    "title": d.title,
                    "publisher": d.publisher,
                    "kind": d.kind,
                    "url": d.url,
                    "relevance": d.relevance,
                    "quote_hint": d.text.strip()[:120],
                    "snippet": d.text[:400],
                }
                for d in rows
            ],
        }
