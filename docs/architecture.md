# Architecture

Target design: [`spec/world-explorer-spec.md`](spec/world-explorer-spec.md). This page describes what is built.

## Shape

```
frontend/ (React, TypeScript, MapLibre)  ──HTTP──▶  /api/v1 (FastAPI)
                                                     │
web (api_*, payloads, deps, security)                ▼
  └▶ services (world, facts, proposals, tickets, theses, engine, events, prices, changes, portfolio,
               companies, registry, imports, macro, charts)
        └▶ pure logic: economics · temporal · analysis
              └▶ adapters: market (Yahoo, demo) · intel (fetch, documents, connectors) · catalogs
                    └▶ models ▶ db
worker ▶ harness (scan, executor) ▶ workflows.research ▶ agents (offline, llama.cpp, OpenAI-compatible, Anthropic, CLI)
```

`import-linter` enforces these layers in `make check` (contracts in `pyproject.toml`).

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

## Macro and claims

`intel/connectors/fred` is the declarative table of macro series; `services/macro` stores
observations (`MacroPoint`), derives net liquidity, annual rates and ratios with the pure rules in
`analysis/macro`, and re-expresses prices in gold or in real terms. `intel/connectors/claims` is
the table of mineral-tenure registers; answers are shown, never stored.

Demo macro series are a real snapshot. `src/watchstreet/data/macro_history.csv.gz` holds the full
FRED history from 2003 of every series in `fred.SERIES`, in the published units, dated 16 Nov 2026.
With `WATCHSTREET_MARKET_PROVIDER=demo`, `intel/demo` serves these rows where it would otherwise
serve the live CSV. Refresh it by hand with `python scripts/snapshot_macro_history.py`; the script
writes nothing unless every series downloads. Source: Federal Reserve Bank of St. Louis (FRED). The
series belong to their publishers, named on each series page at fred.stlouisfed.org. Rows a source
no longer serves are kept from the previous bundle (FRED now serves the S&P 500 only for a rolling
year; the past does not change). The bundle also holds the World Bank monthly gold price (`GOLDWB`,
`intel/connectors/gold_monthly`, read from the public-domain package `datasets/gold-prices`,
ODC-PDDL-1.0; World Bank data CC BY 4.0), because FRED dropped the London gold price in 2022. Added
for the purchasing-power band (snapshot 17 Nov 2026): `AHETPI` (hourly earnings, BLS),
`PCOPPUSDM` and `PURANUSDM` (IMF primary commodity prices) and `NASDAQXAU` (PHLX Gold/Silver Sector
index, © Nasdaq, from September 2004).

`services/purchasing` measures one price in five yardsticks at once (CPI, hourly wage, M2, gold,
oil; a declarative table with each yardstick's bias). Every line is a ratio of two dollar prices,
so the dollar cancels; `analysis/purchasing` turns them into monthly changes, median, inner and
outer band and a per-month agreement count, without fitting or filling anything.

## Charts

`services/charts` builds four views on stored observations: the yardstick matrix, the lever chain
(`analysis/macro.chain_path`: links multiply to the price, so their log changes add up exactly),
lenses (`analysis/expression`: a small series algebra with unit checks, saved in `Lens`) and the
regime map with the decisions of the journal. Weekly share closes are stored in `SharePrice` by
`services/prices.sync_history`. Nothing is fitted or forecast.

## Not built yet

Where the product is heading (public site, several users, sign-in, subscription, advertising,
oil and gas, timber, the next chart model) is described in
[`spec/product-vision.md`](spec/product-vision.md). Smaller gaps: marker clustering, satellite
images, saved scenarios, server-sent events (the UI polls). `intel/connectors/edgar` is tested
against recorded answers but not yet called by a workflow; it is kept for reading debt schedules
and filings.
