# Architecture

## Layers and dependency direction

Imports point **downwards only**. The rule is enforced by import-linter (`make architecture`,
contracts in `pyproject.toml`); the reasoning is in [ADR 0001](adr/0001-architecture-review.md).

```
 web (app, routes_*, helpers, deps, formatting)  |  worker      HTTP / process edges
 ─────────────────────────────────────────────────────────────────────────
 harness     executor, scheduler, ingest (feeds -> tickets), tripwires        runs inside the worker
 container   composition root: settings, engine + migrations, market, runner, fetcher
 workflows   Workflow classes, LlmWorkflow, tools (+args/schemas/payloads), facts   what a ticket does
 ─────────────────────────────────────────────────────────────────────────
 services  | agents      use cases on the database  |  AgentRunner adapters (llama, OpenAI, CLI, offline)
 profiles                 profile tables, classify, derive, scoring (pure)
 market | intel | geo | commodities    provider adapters + cache, documents/fetch/connectors/triage (kernel), pure data
 models                   SQLAlchemy ORM          migrate (Alembic upgrade)
 db                       engine, session_scope, UtcDateTime
 ─────────────────────────────────────────────────────────────────────────
 workflow_specs | drafts | config      declarative workflow catalogue, result DTOs, settings
 domain | constants | timeutil | errors
```

Siblings separated by `|` must not import each other. What goes where:

* **Foundation**: enums, thresholds (`constants.py`, no magic numbers elsewhere), `WatchStreetError`,
  `drafts.py` (what a workflow hands to the harness) and `workflow_specs.py` (label, rules per
  workflow key). Services need to know *that* a workflow exists, never how it runs.
* **Services** own the database rules and are the only place that changes state on behalf of the UI,
  the harness and the agents. They never import workflows, harness, container or web. Transaction
  boundaries are set by the caller (`session_scope` in the web dependency and in the worker);
  services `flush`, they do not `commit`.
* **Ports**: `MarketDataProvider`, `AgentRunner`, `Fetcher` (+ `EdgarClient`). `container.build_container`
  is the only place that picks implementations; tests inject fakes there.
* **Web** routes parse input, call a service, render. One router module per area (`routes_portfolio`, `routes_stocks`, `routes_tickets`, `routes_intel`,
  `routes_system`); shared helpers live in `web/helpers.py`; route modules never import each other.


```
 Browser ── web (FastAPI, Jinja, SVG candles) ──┐
                                                ├── Postgres container (./data/postgres)
 worker ── scheduler ── executor ── workflows ──┘   (SQLite for tests / `make demo`)
              │            │            ├── MarketService (cache) → Yahoo | Demo
              │            │            └── AgentRunner → llama.cpp container | OpenAI-compat | Anthropic | CLI | Offline
              └ hourly: news scan → event_review tickets; periodic refresh tickets
```

* **Intake**: adding a holding/watch entry creates the stock and an initial ticket (`initial_holding` / `initial_watch`, high priority).
* **Ticket lifecycle**: `queued → running → done|failed|cancelled`. `claim_next` is an atomic conditional UPDATE (retried when another worker wins the candidate), so more workers are safe; the caller owns the commit. Stuck `running` tickets are requeued.
* **Workflow** = `run(ctx) → WorkflowResult` (`WorkflowResult` and the drafts live in `drafts.py`, label/rules in `workflow_specs.py`) (summary, insights, scores, thesis, follow-ups). LLM workflows share `LlmWorkflow`: gather facts (including existing thesis, insights and previous scores → memory), ask the agent for schema-validated JSON (one retry), translate.
* **Knowledge store**: `Insight`, `Score` (history per scheme), `Thesis` (versions with status), `MarketEvent`, all linked to the producing ticket. The stock page and timeline are views over them.
* **Self-improving loop**: periodic `thesis_check` compares fresh scores with stored ones and appends a new thesis version; negative events trigger checks; follow-ups are bounded by guardrails.
* **Profiles** (`profiles/`): `classify` (sector/industry -> profile, deterministic), `registry` (declarative criteria tables, required datapoints, view *lens*), `derive` (pure maths: mine NAV via NPV annuity, margins, rule of 40, P/FFO). Precedence of who set a profile: user > agent > auto.
* **Datapoints**: sourced inputs (`key`, `subject`, `value`, `source`, `confidence`, `origin`), newest per key+subject wins, user entries are protected from agents. The agent supplies inputs, code computes results; missing inputs surface as `missing` and `provisional` on the score instead of guesses.
* **Layered stock page**: briefing on top (stored in `briefings`, rule-based draft first, agent polish via `set_briefing`, regenerated after each finished ticket and deduplicated), then panels in the profile's lens order.
* **Tool calling** (`agents/tools.py`, `workflows/tools.py`; schemas in `tool_schemas.py`, argument parsing in `tool_args.py`): the harness computes everything deterministic first (quote, SMA/RSI, scores, P/L) and sends a compact fact sheet (token saving). The agent may call read tools (`get_price_summary`, `get_fundamentals`, `get_news`, `get_knowledge`) and write tools (`add_insight`, `set_goal`, `set_thesis`, `propose_followup`). Write tools only fill drafts; the harness persists them after the run. `propose_followup` runs the guardrail check immediately and returns the verdict to the model. Loop limit `MAX_TOOL_STEPS`; tool errors are fed back as text. Token usage and tool calls are stored on the ticket. If the server rejects `tools`, the workflow falls back to the JSON path.
* **Local LLM**: `llama.cpp` server container (`llm-cpu` / `llm-gpu` profiles), model files from `./models`, OpenAI-compatible API at `http://llama:8080/v1`; runner kind `llama`.
* **Agents**: `offline` is a deterministic rule engine producing the same JSON schema (labelled as such). Real LLMs receive `SYSTEM_PROMPT` + facts.
* **Schema management**: Alembic (`migrations/`, runtime dependency). `build_container` runs `migrate.upgrade_to_head` in web and worker; PostgreSQL serialises concurrent starters with an advisory lock; databases created before migrations existed are stamped with the baseline and upgraded. Change a model -> `alembic -c alembic.ini revision --autogenerate -m "..."` -> review -> commit; `tests/test_migrations.py` fails on model/migration drift.

Extension points: new workflow → add a `WorkflowSpec` to `workflow_specs.py`, subclass in `workflows/definitions.py` and register (a test checks both stay in sync); new data source → implement `MarketDataProvider`; per-ticket agent selection → add `runner` to ticket params and resolve in `executor`.

## Intel layer

```
feeds / GDELT queries / EDGAR / USGS ──► Fetcher (SSRF guard, limits) ──► Document (hash, text)
                                                    │                          │
                              tripwires (quakes near assets, commodity moves)  ├─ deterministic triage (watch terms)
                                                    │                          ▼
                                                    ▼                  intel_triage ticket (agent: publish_intel + quote)
                                              IntelItem ◄──────────────────────┘
SEC sync (XBRL → datapoints, filings → Documents) ──► read_filing (agent: relations/assets/datapoints + quotes)
Entity/Relation graph ──► map (assets, exposure), graph view, watch terms (suppliers) for the next triage
```

* **Documents** (`models.Document`, `intel/documents.py`): dedupe by URL+hash, `search`, `outline`, `read_chunk`, `verify_quote`.
* **Provenance rule**: an agent claim needs `document_id` + verbatim `quote` (>= 20 chars), verified by the harness (`ToolBox._grounding`, `add_relation`, `add_datapoint`). Agents never fetch URLs.
* **Entities/Relations**: directed, sourced edges (`supplies`, `owns`, `located_in`, ...); `country_exposure` derives portfolio exposure per country from assets (production x ownership) and partners, with the contributions retained for display.
* **Tripwires** (`harness/tripwires.py`) are deterministic sensors; they create `IntelItem`s directly. `harness/ingest.py` polls feeds and creates one triage ticket per stock with newly relevant documents. The `intel/` package itself stays a kernel (documents, fetch, connectors, triage) without knowledge of services or the container.
* **Cockpit/Scenarios**: `services/cockpit.py` (prices, ratios, exposure), `services/scenarios.py` re-prices the commodity in `compute_valuation(commodity_shock=...)` and reads the NAV breakdown.
* **Demo**: `intel/demo.py` is a canned HTTP transport for every host, so `WATCHSTREET_MARKET_PROVIDER=demo` exercises the whole path offline; `scripts/seed_demo.py` populates a database.
