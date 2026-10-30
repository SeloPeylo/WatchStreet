# Code-Tour für Neueinsteiger

Diese Führung zeigt in ca. 15 Minuten, wo was liegt und wie eine Anfrage durch den Code läuft.
Die Regeln dahinter stehen in [engineering-rules.md](engineering-rules.md), die Schichten in
[architecture.md](architecture.md).

## 1. Verzeichnis-Landkarte (`src/watchstreet/`)

Imports zeigen nur nach unten (von oben nach unten gelesen); `make architecture` prüft das.

| Paket / Datei | Wozu |
|---|---|
| `web/` | HTTP-Rand. `routes_portfolio.py` (Dashboard, Holdings, Watchlist), `routes_stocks.py` (Aktienseite, Datenpunkte, Chart-API), `routes_tickets.py`, `routes_intel.py` (News, Karte, Graph, Dokumente), `routes_system.py` (Status, Handbuch). Gemeinsames in `helpers.py`. Routen parsen nur Eingaben, rufen einen Service auf und rendern ein Template. |
| `worker.py` | Eigener Prozess: Herzschlag, periodischer Scan, Tickets abarbeiten. |
| `harness/` | Läuft im Worker. `executor.py` führt ein Ticket aus, `scheduler.py` legt Ereignis- und Refresh-Tickets an, `ingest.py` holt Feeds, `tripwires.py` erzeugt Erdbeben- und Rohstoff-Alarme. |
| `container.py` | Kompositionswurzel: baut Settings, DB, Marktdaten, Agent-Runner und Fetcher zusammen. Nur hier werden Implementierungen gewählt; Tests geben Fakes hinein. |
| `workflows/` | Was ein Ticket tut. `definitions.py` (konkrete Workflows + `REGISTRY`), `llm.py` (Basisklasse für Agenten-Workflows), `analysis.py` (JSON-Antwortformat), `tools.py` + `doc_tools.py` (Tool-Handler), `tool_schemas.py` / `tool_args.py` / `tool_payloads.py` (Schemas, Argument-Parsing, Lese-Payloads), `facts.py` (Faktenblatt), `briefing.py`, `intel_flows.py` (SEC, Filings, News-Triage). |
| `services/` | Anwendungsfälle auf der Datenbank: `portfolio`, `tickets`, `knowledge` (Ergebnisse speichern), `followups` (Guardrails für Folgetickets), `datapoints`, `entities` (Graph schreiben), `graph` und `exposure` (Graph- und Länder-Sichten), `scores`, `intel`, `feeds` u. a. Services `flush`, committen nie. |
| `agents/` | Adapter zu KI-Modellen hinter dem `AgentRunner`-Protokoll: `offline.py` (regelbasiert), `http_runners.py` (Anthropic, OpenAI-kompatibel), `cli_runner.py`, `factory.py`; `tools.py` = Tool-Calling-Bausteine. |
| `profiles/` | Reine Bewertungslogik: `registry.py` (Profile als Tabellen), `scoring.py`, `derive.py`, `classify.py`. |
| `market/`, `intel/`, `geo.py`, `commodities.py` | Datenquellen: Kurse (`market/yahoo.py`, `demo.py`), `intel/fetch.py` (einziger Weg ins Internet), `intel/connectors/` (EDGAR, RSS, GDELT), `intel/documents.py` (Dokumente, Zitatprüfung). |
| `models.py`, `db.py`, `migrate.py`, `migrations/` | ORM-Tabellen, Engine/Session, Alembic. Migrationen sind eingefrorene Historie. |
| `workflow_specs.py`, `drafts.py`, `config.py` | Deklarativer Workflow-Katalog, Ergebnis-DTOs (`WorkflowResult`), Einstellungen. |
| `domain.py`, `constants.py`, `timeutil.py`, `errors.py` | Vokabular (Enums wie `TicketStatus`, `DataOrigin`), alle Schwellen/Limits, UTC-Zeit, Fehlerbasis. |

## 2. Der Weg eines Tickets: "Holding eintragen" bis "Seite zeigt Wissen"

1. **Formular** `POST /holdings` -> `web/routes_portfolio.py: holdings_add`. Zahlen/Datum werden mit
   `web/helpers.py: parse_number/parse_date` geprüft, Fehler zeigen das Formular erneut (400).
2. **Service** `services/portfolio.py: add_holding` legt Aktie + Holding an und ruft
   `services/tickets.py: create_ticket` (Workflow `initial_holding`, Status `queued`). Die Route macht
   danach einen Redirect mit Flash-Meldung; `session_scope` committet.
3. **Worker** `worker.py: tick` -> `drain_queue` -> `services/tickets.py: claim_next` (atomares
   `UPDATE ... WHERE status='queued'`, mehrere Worker sind sicher).
4. **Ausführung** `harness/executor.py: execute_ticket` baut den `WorkflowContext`, holt den Workflow
   per `workflows/definitions.py: get_workflow` und ruft `workflow.run(ctx)`.
5. **Workflow** `workflows/llm.py: LlmWorkflow.run`: `workflows/facts.py: gather_facts` berechnet alles
   Deterministische (Kurs, Scores, P/L). Danach entweder Tool-Modus (`ToolBox` in `workflows/tools.py`,
   Agent ruft `add_insight`, `set_thesis`, `propose_followup` ...) oder JSON-Modus
   (`workflows/analysis.py: parse_analysis`). Ergebnis: ein `WorkflowResult` aus Entwürfen (`drafts.py`).
6. **Wissen speichern** `services/knowledge.py: store_result` schreibt Insights, Scores, These,
   Datenpunkte, Graph, Intel. Folgetickets laufen durch `services/followups.py: apply_followups`
   (Guardrails: Duplikate, Tiefe, Kapazität). Danach wird das Ticket `done` und ein Briefing eingeplant
   (`executor._record_success`).
7. **Seite** `GET /stocks/{id}` -> `routes_stocks.py: _stock_view` lädt Scores, Datenpunkte, Briefing,
   Zeitleiste und rendert `templates/stock.html`. Die Ticketseite pollt `/api/tickets/status`.

Fehler: jede Ausnahme im Executor wird am Ticket gespeichert (`status=failed`, `error`), der Worker
läuft weiter. Von Hand wiederholen: `POST /tickets/{id}/retry`.

## 3. Wo ändere ich was?

* **Neuer Workflow:** `WorkflowSpec` in `workflow_specs.py` (Label, Regeln) + Klasse in
  `workflows/definitions.py` (meist `LlmWorkflow` mit `task`) + Eintrag in `REGISTRY`. Ist er
  rein regelbasiert, `Workflow.run` selbst implementieren. `tests/test_architecture.py` schlägt an, wenn
  eine Seite fehlt. Für den Offline-Runner ggf. Handler in `agents/offline.py: HANDLERS`.
* **Neues Bewertungsprofil:** `Profile` in `profiles/registry.py` (Kriterien-Tabelle mit
  `criterion(...)`, Linse, Datenpunkt-Specs), in `PROFILES` eintragen, Zuordnung in
  `profiles/classify.py`.
* **Neue Datenquelle:** Kurse: Klasse mit `MarketDataProvider`-Protokoll + Eintrag in
  `market/service.py: build_provider`. News/Dokumente: Parser in `intel/connectors/`, Abruf immer über
  `intel/fetch.py`, Feed in `services/feeds.py`.
* **Neues Agent-Tool:** Schema in `workflows/tool_schemas.py`, Handler-Methode in `ToolBox`
  (`workflows/tools.py`; Dokumenten-Tools in `doc_tools.py`), Eintrag in `ToolBox.tools()`. Argumente
  nur über `workflows/tool_args.py` parsen, Fehler als `ToolError` (der Agent sieht den Text).
* **Neue Seite/Route:** Service-Funktion in `services/`, dünne Route im passenden `routes_*.py`,
  Template in `web/templates/`, Handbuch `docs/user-manual.md` aktualisieren.
* **Neuer KI-Anbieter:** Klasse mit `AgentRunner`-Protokoll in `agents/`, Eintrag in `agents/factory.py`.
* **Neue Tabelle/Spalte:** `models.py` ändern, `alembic -c alembic.ini revision --autogenerate`, beide committen.

## 4. Die 10 wichtigsten Konventionen

1. `make check` muss grün sein (ruff, import-linter, mypy strict, bandit, pytest >= 80 %).
2. Keine Magic Numbers: Schwellen in `constants.py` oder deklarative Tabellen.
3. Reine Logik (Scoring, Payloads, Parser) ist von I/O getrennt; I/O nur in Providern, Runnern, Services, Routen.
4. Abhängigkeiten zeigen nur nach unten; Routenmodule importieren sich nie gegenseitig (Gemeinsames in `web/helpers.py`).
5. Services `flush`, der Aufrufer committet (`session_scope`).
6. Agenten schlagen vor, der Harness entscheidet: Agentenausgabe ist unvertraut, wird validiert; Folgetickets nur über `services/followups.py`.
7. Kein Beleg, keine Tatsache: Agentenfakten mit Dokument brauchen ein wörtliches Zitat (`verify_quote`); ohne Dokument höchstens Konfidenz `low`; Nutzereinträge werden nie überschrieben.
8. Nie Marktdaten erfinden; Fehlendes senkt die Abdeckung. Fake-Daten gibt es nur im `demo`-Provider.
9. Keine N+1-Abfragen: Beziehungen vorab laden; neue Listen bekommen einen SELECT-Zähltest (`tests/test_persistence.py`).
10. Code und Kommentare Englisch, UI-Texte Deutsch; Zeiten immer UTC-aware (`timeutil.utcnow`); jede `noqa`/`nosec` mit Begründung; Verhaltensänderung = Test.
