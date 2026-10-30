# Architecture

```
 Browser ── web (FastAPI, Jinja, SVG candles) ──┐
                                                ├── SQLite (WAL) volume /data
 worker ── scheduler ── executor ── workflows ──┘
              │            │            ├── MarketService (cache) → Yahoo | Demo
              │            │            └── AgentRunner → Anthropic | OpenAI-compat | CLI | Offline
              └ hourly: news scan → event_review tickets; periodic refresh tickets
```

* **Intake**: adding a holding/watch entry creates the stock and an initial ticket (`initial_holding` / `initial_watch`, high priority).
* **Ticket lifecycle**: `queued → running → done|failed|cancelled`. `claim_next` is an atomic conditional UPDATE, so more workers are safe. Stuck `running` tickets are requeued.
* **Workflow** = `run(ctx) → WorkflowResult` (summary, insights, scores, thesis, follow-ups). LLM workflows share `LlmWorkflow`: gather facts (including existing thesis, insights and previous scores → memory), ask the agent for schema-validated JSON (one retry), translate.
* **Knowledge store**: `Insight`, `Score` (history per scheme), `Thesis` (versions with status), `MarketEvent`, all linked to the producing ticket. The stock page and timeline are views over them.
* **Self-improving loop**: periodic `thesis_check` compares fresh scores with stored ones and appends a new thesis version; negative events trigger checks; follow-ups are bounded by guardrails.
* **Agents**: `offline` is a deterministic rule engine producing the same JSON schema (labelled as such). Real LLMs receive `SYSTEM_PROMPT` + facts.
* **Schema management**: `create_all` at start. Introduce Alembic before the first schema change in production.

Extension points: new workflow → subclass in `workflows/definitions.py` and register; new data source → implement `MarketDataProvider`; per-ticket agent selection → add `runner` to ticket params and resolve in `executor`.
