# WatchStreet

Ticket-driven stock portfolio tracker. You enter what you own (**Holdings**) and what interests you (**Watchlist**); a harness spawns agents that work through **tickets** (analysis jobs with predefined workflows) and accumulate findings, scores and an investment thesis per stock.

* Free public data (Yahoo Finance, hourly candles), candlestick chart without external JS libs
* Agents: rule-based `offline`, `anthropic`, OpenAI-compatible (e.g. Ollama), or any CLI agent
* Deterministic scoring schemes + LLM workflows, guardrails for agent-proposed follow-ups

**User manual (German, with screenshots):** [docs/user-manual.md](docs/user-manual.md) – also served at `/manual`.

## Run

```bash
cp .env.example .env                              # choose agent / data provider
docker compose up --build                         # web + worker + Postgres -> http://localhost:8000
docker compose --profile llm-gpu up --build       # + local llama.cpp on the host GPU (NVIDIA)
docker compose --profile llm-cpu up --build       # + local llama.cpp on CPU
```

* **Data layer:** Postgres in its own container, files in `./data/postgres` (inside the project). Tests also run on SQLite.
* **Local LLM:** put a GGUF model into `./models` ([models/README.md](models/README.md)), set `LLAMA_MODEL` and `WATCHSTREET_AGENT_RUNNER=llama` in `.env`. GPU/CPU/RAM limits are configurable there.
* **Tool calling:** the agent gets deterministic facts up front and calls tools to read details and to record insights, thesis and follow-up tickets (guardrails answer immediately). Falls back to JSON output if the model has no tool support.

**Intel area:** news center with direct sources, world map with country exposure, dependency graph (suppliers/customers/assets), commodity & macro cockpit with NAV scenarios, SEC EDGAR filings read by agents with harness-verified quotes. Set `WATCHSTREET_SEC_USER_AGENT` (SEC requires a contact).

Offline demo (synthetic data, rule-based agent, no network): `make demo` after `make install`.

## Develop

```bash
make install   # editable install + dev tools + pre-commit
make check     # ruff format/lint, import-linter (architecture), mypy --strict, bandit, pytest (coverage >= 80 %)
```

Static analysis with SonarQube: see [docs/engineering-rules.md](docs/engineering-rules.md). Architecture: [docs/architecture.md](docs/architecture.md). Rules for coding agents: [CLAUDE.md](CLAUDE.md).
