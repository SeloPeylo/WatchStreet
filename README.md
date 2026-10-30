# WatchStreet

Ticket-driven stock portfolio tracker. You enter what you own (**Holdings**) and what interests you (**Watchlist**); a harness spawns agents that work through **tickets** (analysis jobs with predefined workflows) and accumulate findings, scores and an investment thesis per stock.

* Free public data (Yahoo Finance, hourly candles), candlestick chart without external JS libs
* Agents: rule-based `offline`, `anthropic`, OpenAI-compatible (e.g. Ollama), or any CLI agent
* Deterministic scoring schemes + LLM workflows, guardrails for agent-proposed follow-ups

**User manual (German, with screenshots):** [docs/user-manual.md](docs/user-manual.md) – also served at `/manual`.

## Run

```bash
cp .env.example .env        # optional: choose agent / data provider
docker compose up --build   # web + worker -> http://localhost:8000
```

Offline demo (synthetic data, no network): `make demo` after `make install`.

## Develop

```bash
make install   # editable install + dev tools + pre-commit
make check     # ruff format/lint, mypy --strict, bandit, pytest (coverage >= 80 %)
```

Static analysis with SonarQube: see [docs/engineering-rules.md](docs/engineering-rules.md). Architecture: [docs/architecture.md](docs/architecture.md). Rules for coding agents: [CLAUDE.md](CLAUDE.md).
