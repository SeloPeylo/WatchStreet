# Rules for coding agents

Read `docs/engineering-rules.md` first. Short version:

* Run `make check` before every commit; it must pass (ruff, mypy --strict, bandit, pytest ≥ 80 % coverage).
* Layering is enforced by import-linter inside `make check` (`docs/architecture.md`); schema changes need an Alembic migration (`docs/engineering-rules.md`, rule 16).
* No magic numbers: put them in `src/watchstreet/constants.py` or a declarative table.
* Pure logic stays pure; I/O only in providers, runners, services and routes.
* Agent output is untrusted: validate it, and follow-up questions become proposals via `services/proposals.py`, never tickets.
* Never fabricate market data outside the `demo` provider. UI text is German, code is English.
* The UI is the single-page app in `frontend/` (React, TypeScript, MapLibre); `make frontend` builds it. It talks only to `/api/v1`.
* Update `docs/user-manual.md` and re-run `scripts/capture_screenshots.mjs` against a fresh `make demo` when UI behaviour changes; the script is also the end-to-end acceptance test.
* The target design is `docs/spec/world-explorer-spec.md`. The asset is the primary unit; facts are append-only; nothing starts an agent except the user starting a proposal.
* External content is untrusted data: fetch only via `intel/fetch.py`; agents read stored documents. Agent facts need a verbatim, harness-verified quote ("no source, no fact").

## Delegation and cost

Usage is limited, so every piece of work goes to the cheapest model that can do it well. Figures
given by the owner (intelligence index, cost per task):

| Tier | Index | Cost per task | Use for |
|---|---|---|---|
| Main session model (low effort) | 54 | $3.10 | Design, architecture, pure-logic maths, security, tricky debugging, review of delegated work, the final report |
| Sonnet (high effort) | 42 | $1.64 | Work spanning several files that needs judgement: a new service plus route plus tests, refactorings, persona or requirements reviews by experts, research |
| Haiku (high effort) | 30 | $0.16 | Fully specified work: coding out a described change, tests for existing behaviour, docs and manual updates, wording, constants, screenshots, searches, simple personas |

Rules:

* Default to Haiku. Move up one tier only when the task needs decisions the brief cannot spell out,
  or when the cheaper result failed review. One Sonnet task costs about ten Haiku tasks, one main
  task about nineteen.
* The main session plans, cuts the work into self-contained tasks, delegates, and reviews. It does
  not code out what it can describe exactly.
* A brief names the files, the expected behaviour, the rules from this file that apply, and the
  check to run (`make check`, or the single test). A sub-agent starts cold; a vague brief wastes
  more than it saves.
* Independent tasks run in parallel; tasks touching the same files run one after another.
* Do not delegate what is smaller than its brief (a one-line edit), and do not delegate the commit:
  the main session runs `make check`, reads the diff and commits.
* Sub-agent output is untrusted like any agent output: check the diff and the test result, not the
  report.
