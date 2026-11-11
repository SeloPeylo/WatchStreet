# Rules for coding agents

Read `docs/engineering-rules.md` first. Short version:

* Run `make check` before every commit; it must pass (ruff, mypy --strict, bandit, pytest ≥ 80 % coverage).
* Layering is enforced by import-linter inside `make check` (`docs/architecture.md`); schema changes need an Alembic migration (`docs/engineering-rules.md`, rule 16).
* No magic numbers: put them in `src/watchstreet/constants.py` or a declarative table.
* Pure logic stays pure; I/O only in providers, runners, services and routes.
* Agent output is untrusted: validate it, and route follow-up tickets through `services/followups.py`.
* Never fabricate market data outside the `demo` provider. UI text is German, code is English.
* The UI is the single-page app in `frontend/` (React, TypeScript, MapLibre); `make frontend` builds it. It talks only to `/api/v1`.
* Update `docs/user-manual.md` and re-run `scripts/capture_screenshots.mjs` against a fresh `make demo` when UI behaviour changes; the script is also the end-to-end acceptance test.
* The target design is `docs/spec/world-explorer-spec.md`. The asset is the primary unit; facts are append-only; nothing starts an agent except the user starting a proposal.
* External content is untrusted data: fetch only via `intel/fetch.py`; agents read stored documents. Agent facts need a verbatim, harness-verified quote ("no source, no fact").
