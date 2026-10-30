# Engineering rules and guardrails

The gate is `make check`; CI and pre-commit run the same thing. Nothing merges red.

| Guardrail | Tool | Config |
|---|---|---|
| Formatting | `ruff format` | `pyproject.toml` |
| Lint, incl. **magic numbers** (`PLR2004`), complexity ≤ 10, annotations, security (`S`), naive datetimes (`DTZ`), bool traps (`FBT`) | `ruff check` | `[tool.ruff.lint]` |
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

## SonarQube

```bash
docker compose --profile quality up -d sonarqube      # http://localhost:9000 (admin/admin, change it)
# create a project token, then:
export SONAR_TOKEN=...
make check                                            # produces coverage.xml
make sonar
```
