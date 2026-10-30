# Engineering rules and guardrails

The gate is `make check`; CI and pre-commit run the same thing. Nothing merges red.

| Guardrail | Tool | Config |
|---|---|---|
| Formatting | `ruff format` | `pyproject.toml` |
| Lint, incl. **magic numbers** (`PLR2004`), complexity ≤ 10, annotations, security (`S`), naive datetimes (`DTZ`), bool traps (`FBT`) | `ruff check` | `[tool.ruff.lint]` |
| **Architecture** (layers, forbidden imports) | `import-linter` (`make architecture`) | `[tool.importlinter]` |
| Types | `mypy --strict` on `src/` | `[tool.mypy]` |
| Security | `bandit` | `[tool.bandit]` |
| Tests | `pytest`, branch coverage ≥ 80 % | `[tool.pytest.ini_options]` |
| Deep static analysis | **SonarQube Community** | `sonar-project.properties`, `docker-compose.yml` profile `quality` |

## Project rules

1. **No magic numbers or strings with meaning.** Thresholds, limits, timeouts, intervals live in `constants.py` or in declarative tables (e.g. scoring criteria). Tests are exempt.
2. **Pure logic separate from I/O.** Scoring, indicators and guardrails are pure functions; HTTP, DB and subprocesses live at the edges.
3. **Providers and agents sit behind protocols** (`MarketDataProvider`, `AgentRunner`). New backends add a class and a factory entry, nothing else.
4. **Agents propose, the harness disposes.** Agent output is validated (pydantic) and follow-ups pass `services/followups.py` before they become tickets.
5. **Knowledge is never only in a ticket.** Findings are persisted as insights, scores or thesis versions (`services/knowledge.py`).
6. **Never invent data.** Missing figures reduce coverage; they are not filled in. Fake data exists only in the explicit `demo` provider.
7. **Timezone-aware UTC** everywhere (`timeutil.utcnow`).
8. **Absolute imports only**, no wildcard imports, no commented-out code.
9. **External content is untrusted data.** Only `intel/fetch.py` talks to the outside (public hosts only, size/redirect/content-type limits). Agents never fetch; they read stored documents. Rendered links pass `safe_url`. XML via `defusedxml`.
10. **No source, no fact.** Agent-written facts (datapoints, relations, intel) carrying a document must quote it verbatim; `verify_quote` checks it. Without a document an agent fact is capped at confidence `low`. User entries are never overwritten by agents or API data.
11. Every behaviour change comes with a test; every `noqa`/`nosec` carries a reason.

## Architecture rules (enforced by `make architecture`)

Layer order, top to bottom: `web|worker > harness > container > workflows > services|agents >
profiles > market|intel|geo|commodities > models|migrate > db > workflow_specs|drafts|config >
domain|constants|timeutil|errors`. A module may import from lower layers only; `|` siblings
never import each other. Diagram and rationale: `docs/architecture.md`, `docs/adr/0001-architecture-review.md`.

12. **Dependencies point down.** No cycles, no `TYPE_CHECKING`/function-local imports to hide one
    (`noqa: PLC0415` needs a reason and a review). If a lower layer needs something from a higher
    one, move the shared piece down (as done for `drafts.py` and `workflow_specs.py`) or inject it.
13. **Routes are thin.** A route parses input, calls a service, renders. Rules (thresholds, filters,
    validation, aggregation) live in `services/`. Route modules never import each other; shared web
    helpers go to `web/helpers.py`.
14. **Services flush, callers commit.** `session_scope` (web dependency, worker) owns the
    transaction. No `commit()` inside services, providers or workflows.
15. **No N+1.** Loops over entities load their relations up front (`selectinload`/`joinedload`,
    `IN` queries). New list/exposure code gets a test that the number of SELECTs does not grow with
    the data (see `tests/test_persistence.py`).
16. **Schema changes need a migration.** Edit `models.py`, then
    `alembic -c alembic.ini revision --autogenerate -m "..."`, review, commit both.
    `tests/test_migrations.py` fails on drift. Migrations must work on SQLite and PostgreSQL and be
    safe to run twice.
17. **Frameworks stay at the edge**: FastAPI/Jinja only in `web`, `httpx` only in the adapters
    (`intel.fetch`, `market.yahoo`, `agents.http_runners`), SQLAlchemy not in the pure core
    (`profiles`, `market`, `agents`, `geo`, `commodities`).
18. **Errors**: deliberate errors derive from `WatchStreetError`; catch `Exception` only at a process
    or ticket boundary and record it.
19. **New workflow** = `WorkflowSpec` in `workflow_specs.py` + class in `workflows/definitions.py`;
    `tests/test_architecture.py` fails if one side is missing.

## SonarQube

```bash
docker compose --profile quality up -d sonarqube      # http://localhost:9000 (admin/admin, change it)
# create a project token, then:
export SONAR_TOKEN=...
make check                                            # produces coverage.xml
make sonar
```
