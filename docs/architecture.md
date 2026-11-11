# Architecture

Target design: [`spec/world-explorer-spec.md`](spec/world-explorer-spec.md). This page describes what is built.

## Shape

```
frontend/ (React, TypeScript, MapLibre)  ──HTTP──▶  /api/v1 (FastAPI)
                                                     │
web (api_*, payloads, deps, security)                ▼
  └▶ services (world, facts, proposals, tickets, theses, engine, events, prices, changes, portfolio)
        └▶ pure logic: economics · temporal · analysis
              └▶ adapters: market (Yahoo, demo) · intel (fetch, documents, connectors) · catalogs
                    └▶ models ▶ db
worker ▶ harness (scan, executor) ▶ workflows.research ▶ agents (offline, llama.cpp, OpenAI-compatible, Anthropic, CLI)
```

`import-linter` enforces these layers in `make check` (`pyproject.toml`, six contracts).

## Principles in code

| Principle | Where |
|---|---|
| Asset-first | `models.Asset` with `StatusPeriod`, `Stake`, `Milestone`; facts, tickets, findings refer to `(subject_type, subject_id)` |
| Evidence-first | `services/facts.record_fact`: reported agent/API values need a stored document and a verbatim quote; estimates need a band and a method; cost figures need a definition; user entries are never overwritten |
| History-aware | `temporal/views`: `as_known` uses the publication date, `hindsight` the reporting period; a fact without publication date is invisible in `as_known` |
| Deterministic-first | `economics/mine` (interval arithmetic), `analysis/rules`, `services/engine` (gaps, cost outliers, neighbours) – no LLM |
| Human-in-the-loop | The engine and agents only create `Proposal`s; `proposals.start` (a user action) creates the `Ticket` |
| Untrusted agent output | `workflows/research`: JSON is parsed leniently, every fact goes through `record_fact`, follow-ups become proposals |

## Request flow of a map view

1. `web/deps.get_view` builds a `ViewContext` (reference date, view, scenario, effective prices).
2. `services/world.load_bundle` loads assets, facts and research state in a few queries.
3. `world.card` / `world.map_feature` compute everything else in memory, using the pure packages.

## Research flow

`Proposal (draft)` → user starts → `Ticket (queued)` → worker claims (`UPDATE … WHERE status='queued'`)
→ `workflows.research.run_workflow` → facts, `Finding`, follow-up proposals, change log → `done`.
The UI polls `/api/v1/notifications` and refreshes when something finished.

## Registry seeding and lazy research

`intel/connectors/registry` reads Wikidata (SPARQL) and USGS MRDS (WFS) through the guarded fetcher.
`services/registry.import_mines` creates assets with location, name and – if named – operator, each
backed by a stored registry document; it never sets status, production or cost. The import runs as
ticket `explore_registry` (no LLM). Profiles are then researched on request per asset.

## Company level

`services/companies.company_view` adds what decides whether a company lives to benefit from its
assets: facts on the company (cash, debt, burn, shares), derived runway and dilution, people,
financings, royalty burdens, a price sensitivity and a ten-question checklist.

## Schema

Alembic migrations in `src/watchstreet/migrations/versions`. `0003` replaces the former dashboard
tables (irreversible) and keeps stocks, holdings and the watchlist.

## Not built yet (see spec)

Marker clustering, satellite images, persons, saved scenarios, inflation and commodity-equivalent
columns, relation rules against driver series (oil/silver), login, server-sent events (the UI polls),
news connectors (RSS, GDELT, EDGAR exist as modules but are not wired to events).
