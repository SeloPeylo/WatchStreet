# Rules for coding agents

Read `docs/engineering-rules.md` first. Short version:

* Run `make check` before every commit; it must pass (ruff, mypy --strict, bandit, pytest ≥ 80 % coverage).
* No magic numbers: put them in `src/watchstreet/constants.py` or a declarative table.
* Pure logic stays pure; I/O only in providers, runners, services and routes.
* Agent output is untrusted: validate it, and route follow-up tickets through `services/followups.py`.
* Never fabricate market data outside the `demo` provider. UI text is German, code is English.
* Update `docs/user-manual.md` (and re-run `scripts/capture_screenshots.mjs`) when UI behaviour changes.
