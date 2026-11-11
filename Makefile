.PHONY: frontend install fmt lint architecture typecheck security test check run worker demo sonar

PY ?= python

install:
	$(PY) -m pip install -e ".[dev]"
	pre-commit install || true

fmt:
	ruff format .
	ruff check . --fix

lint:
	ruff format --check .
	ruff check .

# Layering and dependency rules from [tool.importlinter] in pyproject.toml.
architecture:
	lint-imports

typecheck:
	mypy

security:
	bandit -q -r src -c pyproject.toml

test:
	pytest

# The full quality gate. CI and pre-commit run exactly this; nothing merges red.
check: lint architecture typecheck security test

run:
	uvicorn watchstreet.web.app:app_factory --factory --reload --port 8000

worker:
	$(PY) -m watchstreet.worker

# Build the single-page app into src/watchstreet/web/static/app (needs Node 22).
frontend:
	cd frontend && npm ci && npm run build

# Local run with synthetic data and without an agent (no network, no keys).
demo: frontend
	WATCHSTREET_MARKET_PROVIDER=demo WATCHSTREET_AGENT_RUNNER=offline \
	WATCHSTREET_DATABASE_URL=sqlite:///./data/demo.db \
	sh -c '$(PY) -m watchstreet.worker & uvicorn watchstreet.web.app:app_factory --factory --port 8000'

# Needs the sonarqube service (docker compose --profile quality up -d sonarqube)
sonar: test
	docker compose --profile quality run --rm sonar-scanner
