# ADR 0001: Architecture review and layering

Status: accepted, implemented on branch `worktree-agent-ab4465a035611b5e5`.
Scope: Python code outside presentation (`web/templates`, `web/static` were not touched).

## Context

WatchStreet grew quickly (stock tickets, agent harness, profiles, intel layer). The intended
direction is `domain/constants -> models -> profiles/market/intel kernel -> services ->
workflows -> harness -> web`, but it was only a convention. This review checks it against the
import graph (all `from watchstreet...` statements parsed with `ast`, plus `grep` for
`noqa: PLC0415` and `TYPE_CHECKING`) and fixes what blocked a clean direction. Behaviour is
unchanged; every pre-existing test still passes unmodified except for import paths.

## Findings

### Critical (fixed)

| # | Finding | Evidence | Fix |
|---|---|---|---|
| C1 | `services` and `workflows` imported each other (package cycle). | `services/tickets.py` -> `workflows.definitions.get_workflow`; `services/followups.py` -> `workflows.definitions.REGISTRY`; `services/knowledge.py`, `services/intel.py` -> `workflows.base` (draft DTOs); `services/scenarios.py` -> `workflows.valuation`; reverse: `workflows/*` -> `services/*`. | Draft/result DTOs moved to `drafts.py`; workflow metadata (label, `user_creatable`, `needs_topic`) moved to the declarative `workflow_specs.py` (workflows read it through properties); `workflows/valuation.py` -> `services/valuation.py`. |
| C2 | `profiles` (pure domain data) imported from `workflows`. | `profiles/registry.py` -> `workflows.scoring.Criterion`. | `workflows/scoring.py` -> `profiles/scoring.py` (pure maths belongs next to the profile tables). |
| C3 | `intel/ingest.py` and `intel/tripwires.py` pulled the whole stack into the `intel` kernel and formed a cycle with the container. | `intel/tripwires.py` -> `services.cockpit`, `services.intel`, `workflows.base`; `intel/ingest.py` -> `container` behind `TYPE_CHECKING`, `container` -> `intel.ingest.seed_feeds`. | Both modules moved to `harness/` (they are worker jobs); `seed_feeds`/`DEFAULT_FEEDS` moved to `services/feeds.py`. The `TYPE_CHECKING` workaround is gone. |
| C4 | Clean checkout failed 21 tests: `src/watchstreet/data/countries.json` is package data but was ignored by the unanchored `data/` rule in `.gitignore`. | `git check-ignore -v` -> `.gitignore:5:data/`; `git ls-files` did not list the file. | `.gitignore` uses `/data/`; file is tracked. |
| C5 | Schema drift risk: only `create_all`, no migrations (docs said "introduce Alembic before the first schema change"). | `container.build_container` -> `Base.metadata.create_all`. | Alembic introduced, see Decision below. |

### Important

| # | Finding | Status |
|---|---|---|
| I1 | Web modules imported each other's private helpers (`routes_intel` -> `routes._render/_number/_redirect`). | Fixed: `web/helpers.py`. Route modules must not import each other (contract). |
| I2 | Domain rules in routes: worker-liveness rule, intel list filters and "primary source" filter, feed validation, score history grouping, map payload, document relations. | Fixed: `services/status.py`, `services/intel.list_items`, `services/feeds.add_feed`, `services/scores.py`, `services/mapdata.py`, `services/entities.relations_for_document`. Routes only translate HTTP. |
| I3 | `claim_next` committed inside the service, hiding a transaction boundary and silently returning `None` when it lost a race with another worker (the worker then idled a full poll interval). | Fixed: the caller owns the transaction (worker's `session_scope`), and the claim retries `CLAIM_ATTEMPTS` times. Tests simulate the race. |
| I4 | N+1 queries: `entities.country_exposure` (per stock/relation `session.get`), `portfolio.holding_rows` (lazy `holding.stock`), stock page priced every holding to show one, commodity exposure/alerts lazy-loaded datapoints per stock, document relations resolved entities one by one. | Fixed with bulk loads / `selectinload` / `joinedload`; tests assert the number of SELECTs does not grow with the number of stocks. |
| I5 | Missing indexes for hot filters. | Fixed in migration `0002`: `tickets(status, priority, id)` (claim), `documents(triaged)` (triage intake), `intel_items(published_at)` (news center, map). |
| I6 | No common exception root; failures could not be told apart from bugs at boundaries. | Fixed: `errors.WatchStreetError`, all deliberate errors derive from it (and keep `ValueError`/`RuntimeError`), tested. `except Exception` remains only at the two real boundaries (`executor.execute_ticket`, `db.session_scope`), both documented. |
| I7 | The layering was implicit. | Fixed: import-linter contracts in `pyproject.toml`, run by `make check`, pre-commit and CI. |

### Nice to have (not changed)

* `workflows/tools.py` (470 lines) mixes tool schemas, argument parsing and persistence of drafts;
  `doc_tools.py` extends it. Cohesive enough today; splitting read tools / write tools would be a
  readability refactor for the clean-code pass.
* `web/routes*.py` still contain simple `select(...)` queries and view assembly (graph/document
  pages, dashboard counters). They are read-only and thin enough; extracting them all would
  collide with the parallel frontend work.
* `Container` is passed as a service locator to `harness.ingest.run_ingest`, `scheduler.scan_*`.
  Narrower parameters (`market`, `fetcher`, `session_factory`) would be cleaner.
* `intel.fetch.Fetcher` is a concrete class, not a `Protocol`; tests inject a fake transport
  instead. Acceptable, but a `Protocol` would document the port like `MarketDataProvider` and
  `AgentRunner` do.
* `services/entities.py` (~300 lines) combines entity CRUD, graph view and exposure maths; the
  exposure part could become its own module.
* Logging is configured only in the worker (`logging.basicConfig`); the web process relies on
  uvicorn's configuration.

### Known risks (not changed, need a decision)

* **Concurrent scans.** `scan_due` is read, then `run_scan` runs and touches `LAST_SCAN_KEY` in the
  same transaction. Two workers can both decide a scan is due and both create event-review
  tickets. `claim_next` is safe for several workers, scans are not. Recommended: a compare-and-set
  lease on `system_state` and a unique constraint `market_events(stock_id, external_id)` (needs a
  migration `0003` and `IntegrityError` handling in `scan_stock_events`).
* **`requeue_stuck`** requeues any `running` ticket older than `STUCK_TICKET_TIMEOUT` (30 min) at
  worker start. With several workers, a worker that restarts can requeue a ticket another worker
  is still running (long local-LLM calls). Recommended: heartbeat/`worker_id` on the ticket.
* **PostgreSQL was not exercised in this session** (no reachable server, no Docker). The
  migrations were rendered for the PostgreSQL dialect (`alembic upgrade head --sql`) and the
  SQLite path is fully tested; CI runs the whole suite against PostgreSQL, which now also covers
  the migrations (the test fixture builds its schema through them).

## Decision: Alembic now

Introduced, minimally and with low risk:

* `alembic` is a runtime dependency; revisions live in the package (`watchstreet/migrations`) so
  they ship in the wheel/Docker image.
* `0001` is the schema as `create_all` produced it (frozen DDL, not a call to `create_all`),
  `0002` adds the indexes of I5 (idempotent, because databases created by a fresh `create_all`
  already contain them).
* `migrate.upgrade_to_head(engine)` runs in `build_container`, i.e. at start of web **and**
  worker. On PostgreSQL a transaction-scoped advisory lock serialises concurrent starters, so the
  former "worker waits for web" ordering is no longer required for correctness (docker-compose
  keeps it, which is harmless).
* Existing installations (tables, no `alembic_version`) are stamped with `0001` and then upgraded:
  no manual step, no data loss (tested).
* `tests/test_migrations.py` covers fresh install, idempotence, adoption of a legacy database,
  downgrade/upgrade and **drift** (`compare_metadata(models, migrated schema)` must be empty, so
  changing a model without a revision fails the gate).
* Workflow for schema changes: edit `models.py`, run
  `alembic -c alembic.ini revision --autogenerate -m "..."`, review the script, commit both.
  `alembic upgrade head --sql` renders the DDL for a DBA.

## Decision: enforce the architecture with import-linter

Contracts (in `pyproject.toml`, `make architecture`, part of `make check`):

1. Layer order `web|worker > harness > container > workflows > services|agents > profiles >
   market|intel|geo|commodities > models|migrate > db > workflow_specs|drafts|config >
   domain|constants|timeutil|errors` (siblings marked `|` must not import each other).
2. Web internals: `app > routes|routes_intel > helpers|deps > formatting`; route modules never
   import each other.
3. Web frameworks (fastapi, starlette, jinja2, markdown) only inside `web`.
4. `httpx` only in the four adapters (`intel.fetch`, `intel.demo`, `market.yahoo`,
   `agents.http_runners`).
5. Pure core (`profiles`, `market`, `agents`, `geo`, `commodities`) knows no SQLAlchemy, models,
   services, workflows, harness or container.
6. Foundation modules (`domain`, `constants`, `timeutil`, `errors`, `drafts`, `workflow_specs`,
   `config`) import nothing of the application above them.

Only contracts that hold today were added. A deliberately introduced violation was verified to
fail the gate. `tests/test_architecture.py` additionally keeps the declarative `workflow_specs`
table and the workflow registry in sync and checks the exception root.

## Consequences

* Changes in the persistence schema now require a migration; the drift test enforces it.
* Moving code across layers is a conscious act (edit the contract), not an accident.
* `services` can no longer depend on workflow classes; anything it needs about a workflow goes into
  `workflow_specs.py`.
