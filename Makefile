# POLAR WINDOW
#
# `make help` lists everything. The order below is the order a new machine
# needs them in, and `make dev` does the whole thing.

SHELL := /bin/bash
UV    := $(shell command -v uv 2>/dev/null || echo "$$HOME/.local/bin/uv")
BE    := backend
FE    := frontend
DATA  := data

.DEFAULT_GOAL := help
.PHONY: missions validate-trip test-db help install kernels dem sites seed tiles services db-up migrate dev api worker \
        compute feeds feeds-once catalogues \
        frontend test test-fast test-int test-geo lint fmt typecheck contracts \
        golden-update openapi codegen clean nuke check

help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# --- setup -----------------------------------------------------------------

install: ## Install backend and frontend dependencies
	cd $(BE) && $(UV) sync --extra dev
	cd $(FE) && npm install

kernels: ## Download and verify the SPICE kernels by sha256 (~130 MB, once; refuses under OFFLINE=1)
	cd $(BE) && $(UV) run polar-kernels fetch

dem: ## Fetch the regional LOLA elevation model (~115 MB, once; refuses under OFFLINE=1)
	cd $(BE) && $(UV) run python -m app.data.ingest_lola regional

sites: dem ## Resolve candidate sites against the elevation model
	cd $(BE) && $(UV) run python -m app.data.ingest_sites \
	  ../$(DATA)/dem/regional_80m.npz ../$(DATA)/sites.json

missions: migrate ## Load the cited CLPS mission list and create target sites (ADR-5, ADR-6)
	cd $(BE) && $(UV) run python -m app.data.ingest_missions

seed: kernels sites migrate missions ## Everything the API needs before it can answer
	cd $(BE) && $(UV) run python -m app.workers.precompute
	$(MAKE) tiles

tiles: ## Pre-render the map tile pyramid z0-z5 (ADR-4)
	cd $(BE) && $(UV) run python -m app.data.ingest_lola tiles --max-zoom 5

# --- services --------------------------------------------------------------

services: ## Start Postgres and Redis (docker compose, or local if you prefer)
	docker compose up -d postgres redis

migrate: ## Apply database migrations
	cd $(BE) && $(UV) run alembic upgrade head

# --- run -------------------------------------------------------------------

dev: ## The whole stack: services, seed, api and frontend
	$(MAKE) services
	$(MAKE) seed
	$(MAKE) -j2 api frontend

api: ## Run the API with reload
	cd $(BE) && $(UV) run uvicorn app.main:app --reload --port 8000

worker: ## Run the precompute worker once
	cd $(BE) && $(UV) run python -m app.workers.precompute

compute: ## Run the compute worker: trip, contact and launch answers (ADR-12)
	cd $(BE) && $(UV) run python -m app.workers.compute

feeds: ## Run the feeds worker: records weather, space weather and DSN Now (ADR-8)
	cd $(BE) && $(UV) run python -m app.workers.feeds

feeds-once: ## Fetch every due live product once, then exit
	cd $(BE) && $(UV) run python -m app.workers.feeds --once

catalogues: ## Validate the cited catalogues under data/catalogues
	cd $(BE) && $(UV) run python -m app.data.catalogues

frontend: ## Run the Vite dev server
	cd $(FE) && npm run dev

# --- quality ---------------------------------------------------------------

test-db: ## Rebuild polar_window_test from the migrations and the seeded rows
	cd $(BE) && $(UV) run python -m app.tests.fixtures.make_test_db

test: test-db ## Everything, against polar_window_test (needs a seeded dev database)
	cd $(BE) && $(UV) run pytest -q

test-fast: ## Unit, property and synthetic golden tests. No services, < 20 s
	cd $(BE) && $(UV) run pytest app/tests/unit app/tests/golden/test_synthetic_golden.py -q

test-int: ## Integration and agent tests
	cd $(BE) && $(UV) run pytest app/tests/integration -q

test-geo: ## Golden tests against the real kernels and DEM
	cd $(BE) && $(UV) run pytest app/tests/golden -q

validate-trip: ## Propagator and shadows against NASA's reconstructed trajectories (prints the docs/validation.md table)
	cd $(BE) && $(UV) run pytest app/tests/golden/test_propagate_vs_clps.py app/tests/golden/test_eclipse_vs_spice.py -q
	cd $(BE) && $(UV) run python -m app.tests.golden.validate_trip
	cd $(BE) && $(UV) run pytest app/tests/golden/test_launch_vs_clps.py -q
	cd $(BE) && $(UV) run python -m app.tests.golden.validate_launch 2>/dev/null
	cd $(BE) && $(UV) run pytest app/tests/golden/test_loops_vs_clps.py -q
	cd $(BE) && $(UV) run python -m app.tests.golden.validate_loops 2>/dev/null

test-fe: ## Frontend units: the adapter, the cache keys, the exports
	cd $(FE) && npm test --silent

lint: ## ruff + mypy strict + the layering contracts
	cd $(BE) && $(UV) run ruff check app && $(UV) run ruff format --check app
	cd $(BE) && $(UV) run mypy app
	cd $(BE) && $(UV) run lint-imports

fmt: ## Format
	cd $(BE) && $(UV) run ruff format app && $(UV) run ruff check app --fix

typecheck: ## Frontend types
	cd $(FE) && npm run check

contracts: ## Just the import-linter layering contracts
	cd $(BE) && $(UV) run lint-imports

check: lint test test-fe typecheck ## Everything CI runs

golden-update: ## Re-pin the golden fixtures. Requires GOLDEN_UPDATE_REASON.
	@test -n "$$GOLDEN_UPDATE_REASON" || { \
	  echo "Refusing: a golden diff means the physics changed. Say why:"; \
	  echo '  GOLDEN_UPDATE_REASON="..." make golden-update'; exit 1; }
	cd $(BE) && $(UV) run python app/tests/golden/generate.py

# --- contract --------------------------------------------------------------

openapi: ## Emit docs/openapi.json from the running app definition
	cd $(BE) && $(UV) run python -c "\
import json, pathlib; from app.main import create_app; \
p=pathlib.Path('../docs/openapi.json'); p.write_text(json.dumps(create_app().openapi(), indent=2)); \
print('wrote', p)"

codegen: openapi ## Regenerate the frontend's typed client from the schema
	cd $(FE) && npm run codegen

# --- housekeeping ----------------------------------------------------------

clean: ## Remove build output and caches
	rm -rf $(FE)/dist $(BE)/.pytest_cache $(BE)/.mypy_cache $(BE)/.ruff_cache
	find . -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true

nuke: clean ## Also remove downloaded data. Re-running `make seed` takes ~10 min.
	rm -rf $(DATA)/kernels $(DATA)/dem $(DATA)/tiles $(DATA)/sites.json
