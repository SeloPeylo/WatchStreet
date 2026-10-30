"""Declarative catalogue of the workflows: key, German label, description and ticket rules.

This is the part of a workflow that the *rest* of the system needs to know about (creating a
ticket, validating a proposed follow-up, listing workflows in the UI). The behaviour lives in
``watchstreet.workflows``; keeping the metadata here lets ``services`` stay below ``workflows``
in the dependency direction. ``tests/test_architecture.py`` checks both sides stay in sync.
"""

from dataclasses import dataclass

from watchstreet.domain import WorkflowKey


@dataclass(frozen=True)
class WorkflowSpec:
    key: WorkflowKey
    label: str
    description: str
    user_creatable: bool = True
    needs_topic: bool = False

    def default_title(self, symbol: str, topic: str) -> str:
        suffix = f": {topic}" if topic else ""
        return f"{self.label} – {symbol}{suffix}"


SPECS: dict[str, WorkflowSpec] = {
    spec.key: spec
    for spec in (
        WorkflowSpec(
            WorkflowKey.INITIAL_HOLDING,
            "Bestandsaufnahme (Holding)",
            "Ausgangslage einer gehaltenen Aktie: Ziel, These, Bewertung und Technik.",
            user_creatable=False,
        ),
        WorkflowSpec(
            WorkflowKey.INITIAL_WATCH,
            "Kaufprüfung (Watchlist)",
            "Erstbewertung einer beobachteten Aktie: lohnt sich ein Kauf?",
            user_creatable=False,
        ),
        WorkflowSpec(
            WorkflowKey.TOPIC_ANALYSIS,
            "Themenanalyse",
            "Vertiefende Analyse zu einem frei wählbaren Thema (z. B. Risiken, Burggraben).",
            needs_topic=True,
        ),
        WorkflowSpec(
            WorkflowKey.EVENT_REVIEW,
            "Ereignis-Prüfung",
            "Bewertet neue Meldungen: relevant für die These? Handlungsbedarf?",
            user_creatable=False,
        ),
        WorkflowSpec(
            WorkflowKey.THESIS_CHECK,
            "These prüfen",
            "Testet die aktuelle Investmentthese gegen neue Daten und Scores.",
        ),
        WorkflowSpec(
            WorkflowKey.CLASSIFY_STOCK,
            "Profil bestimmen",
            "Ordnet die Aktie einem Typ zu (Minen, Tech, ...); "
            "der Typ bestimmt das Bewertungsschema.",
        ),
        WorkflowSpec(
            WorkflowKey.RESEARCH_DATAPOINTS,
            "Datenpunkte recherchieren",
            "Trägt fehlende Bewertungs-Eingaben (z. B. Minen, AISC, Reserven) mit Quelle ein.",
        ),
        WorkflowSpec(
            WorkflowKey.BRIEFING,
            "Briefing",
            "Fasst zusammen, worauf es jetzt ankommt (Regeln, optional vom Agenten verfeinert).",
            user_creatable=False,
        ),
        WorkflowSpec(
            WorkflowKey.SEC_SYNC,
            "SEC-Abgleich",
            "Holt neue Einreichungen von SEC EDGAR und leitet Aktienzahl/Nettoverschuldung aus "
            "den XBRL-Daten ab (deterministisch, mit Quelle; kein LLM).",
        ),
        WorkflowSpec(
            WorkflowKey.READ_FILING,
            "Einreichung lesen",
            "Ein Agent liest eine Einreichung gezielt und extrahiert Datenpunkte, "
            "Zulieferer/Kunden und Assets – jeweils mit wörtlichem, vom Harness geprüftem Zitat.",
            user_creatable=False,
        ),
        WorkflowSpec(
            WorkflowKey.INTEL_TRIAGE,
            "Nachrichten-Zuschnitt",
            "Bewertet neue Quellen auf Relevanz für die Aktie und veröffentlicht belegte "
            "Intel-Items.",
            user_creatable=False,
        ),
        WorkflowSpec(
            WorkflowKey.VALUATION_SCORE,
            "Bewertungs-Score",
            "Deterministisches, profilabhängiges Bewertungsschema inkl. NAV/Margen (kein LLM).",
        ),
        WorkflowSpec(
            WorkflowKey.TECHNICAL_SNAPSHOT,
            "Technik-Snapshot",
            "Trend, Momentum und RSI aus den Stundenkerzen (kein LLM).",
        ),
    )
}


def get_spec(key: str) -> WorkflowSpec:
    try:
        return SPECS[key]
    except KeyError as exc:
        msg = f"Unknown workflow: {key}"
        raise ValueError(msg) from exc
