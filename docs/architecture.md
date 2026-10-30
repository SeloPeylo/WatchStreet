# Architecture

```
 Browser ── web (FastAPI, Jinja, SVG candles) ──┐
                                                ├── Postgres container (./data/postgres)
 worker ── scheduler ── executor ── workflows ──┘   (SQLite for tests / `make demo`)
              │            │            ├── MarketService (cache) → Yahoo | Demo
              │            │            └── AgentRunner → llama.cpp container | OpenAI-compat | Anthropic | CLI | Offline
              └ hourly: news scan → event_review tickets; periodic refresh tickets
```

* **Intake**: adding a holding/watch entry creates the stock and an initial ticket (`initial_holding` / `initial_watch`, high priority).
* **Ticket lifecycle**: `queued → running → done|failed|cancelled`. `claim_next` is an atomic conditional UPDATE, so more workers are safe. Stuck `running` tickets are requeued.
* **Workflow** = `run(ctx) → WorkflowResult` (summary, insights, scores, thesis, follow-ups). LLM workflows share `LlmWorkflow`: gather facts (including existing thesis, insights and previous scores → memory), ask the agent for schema-validated JSON (one retry), translate.
* **Knowledge store**: `Insight`, `Score` (history per scheme), `Thesis` (versions with status), `MarketEvent`, all linked to the producing ticket. The stock page and timeline are views over them.
* **Self-improving loop**: periodic `thesis_check` compares fresh scores with stored ones and appends a new thesis version; negative events trigger checks; follow-ups are bounded by guardrails.
* **Profiles** (`profiles/`): `classify` (sector/industry -> profile, deterministic), `registry` (declarative criteria tables, required datapoints, view *lens*), `derive` (pure maths: mine NAV via NPV annuity, margins, rule of 40, P/FFO). Precedence of who set a profile: user > agent > auto.
* **Datapoints**: sourced inputs (`key`, `subject`, `value`, `source`, `confidence`, `origin`), newest per key+subject wins, user entries are protected from agents. The agent supplies inputs, code computes results; missing inputs surface as `missing` and `provisional` on the score instead of guesses.
* **Layered stock page**: briefing on top (stored in `briefings`, rule-based draft first, agent polish via `set_briefing`, regenerated after each finished ticket and deduplicated), then panels in the profile's lens order.
* **Tool calling** (`agents/tools.py`, `workflows/tools.py`): the harness computes everything deterministic first (quote, SMA/RSI, scores, P/L) and sends a compact fact sheet (token saving). The agent may call read tools (`get_price_summary`, `get_fundamentals`, `get_news`, `get_knowledge`) and write tools (`add_insight`, `set_goal`, `set_thesis`, `propose_followup`). Write tools only fill drafts; the harness persists them after the run. `propose_followup` runs the guardrail check immediately and returns the verdict to the model. Loop limit `MAX_TOOL_STEPS`; tool errors are fed back as text. Token usage and tool calls are stored on the ticket. If the server rejects `tools`, the workflow falls back to the JSON path.
* **Local LLM**: `llama.cpp` server container (`llm-cpu` / `llm-gpu` profiles), model files from `./models`, OpenAI-compatible API at `http://llama:8080/v1`; runner kind `llama`.
* **Agents**: `offline` is a deterministic rule engine producing the same JSON schema (labelled as such). Real LLMs receive `SYSTEM_PROMPT` + facts.
* **Schema management**: `create_all` at start (web creates, worker waits for web). Introduce Alembic before the first schema change in production.

Extension points: new workflow → subclass in `workflows/definitions.py` and register; new data source → implement `MarketDataProvider`; per-ticket agent selection → add `runner` to ticket params and resolve in `executor`.
