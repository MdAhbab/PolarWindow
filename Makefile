# POLAR WINDOW
#
# `make help` lists every target. On a new machine: make install, make seed, make dev.
# `python3 run.py` does the same in one command, needs no Docker, and fetches the rest
# of the data (`polar-data sync`; backend/app/data/registry.py lists it).

SHELL := /bin/bash
UV    := $(shell command -v uv 2>/dev/null || echo "$$HOME/.local/bin/uv")
BE    := backend
FE    := frontend
DATA  := data

.DEFAULT_GOAL := help
# Every target is a command, not a file (and `frontend` is also a folder), so all are phony.
.PHONY: $(shell sed -n 's/^\([a-zA-Z_-]*\):.*/\1/p' $(MAKEFILE_LIST))

help: ## Show this help
	@awk 'BEGIN {FS = ":.*## "} \
	  /^##@/ {printf "\n\033[1m%s\033[0m\n", substr($$0, 5)} \
	  /^[a-zA-Z_-]+:.*## / {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

##@ Set up
install: ## Install backend and frontend dependencies
	cd $(BE) && $(UV) sync --extra dev
	cd $(FE) && npm install

services: ## Start Postgres and Redis with docker compose (local ones work too)
	docker compose up -d postgres redis

migrate: ## Apply the database migrations
	cd $(BE) && $(UV) run alembic upgrade head

kernels: ## Download the SPICE kernels, checked by SHA-256 (~130 MB, once; not under OFFLINE=1)
	cd $(BE) && $(UV) run polar-kernels fetch

dem: ## Fetch the regional LOLA terrain model (~115 MB, once; not under OFFLINE=1)
	cd $(BE) && $(UV) run python -m app.data.ingest_lola regional

sites: dem ## Resolve the candidate sites against the terrain model (writes data/sites.json)
	cd $(BE) && $(UV) run python -m app.data.ingest_sites \
	  ../$(DATA)/dem/regional_80m.npz ../$(DATA)/sites.json

missions: migrate ## Load the cited CLPS mission list and create its target sites (ADR-5, ADR-6)
	cd $(BE) && $(UV) run python -m app.data.ingest_missions

worker: ## Precompute every site's skyline and reference numbers (resumes; the step in seed)
	cd $(BE) && $(UV) run python -m app.workers.precompute

tiles: ## Pre-render the map tiles, zoom 0 to 5 (ADR-4)
	cd $(BE) && $(UV) run python -m app.data.ingest_lola tiles --max-zoom 5

seed: kernels sites missions ## Everything the API needs before it can answer (~10 min, once)
	$(MAKE) worker
	$(MAKE) tiles

##@ Run
dev: ## Services, seed, then the api, both workers and the frontend together
	$(MAKE) services
	$(MAKE) seed
	$(MAKE) -j4 api compute feeds frontend

api: ## Run the API with reload on :8000
	cd $(BE) && $(UV) run uvicorn app.main:app --reload --port 8000

compute: ## Run the compute worker: trip, contact and launch answers (ADR-12)
	cd $(BE) && $(UV) run python -m app.workers.compute

feeds: ## Run the feeds worker: records weather, space weather and DSN Now (ADR-8)
	cd $(BE) && $(UV) run python -m app.workers.feeds

feeds-once: ## Fetch every due live product once, then exit
	cd $(BE) && $(UV) run python -m app.workers.feeds --once

frontend: ## Run the Vite dev server on :5173
	cd $(FE) && npm run dev

##@ Rebuild the data kept in data/
climatology: ## Wind at 50 m by month and hour at the pads, from NASA POWER (no key)
	cd $(BE) && $(UV) run python -m app.data.climatology

thunder-climatology: ## Thunder hours by month and hour at the pads, from GLM (needs PW_EARTHDATA_TOKEN; ~1.5 h)
	cd $(BE) && $(UV) run python -m app.data.thunder_climatology

space-climate: ## Oulu neutron monitor, past solar particle events and DONKI's, for the radiation screening
	cd $(BE) && $(UV) run python -m app.data.space_climate

hindcast-weather: ## GEFS wind shares against the Cape's weather station for a year (~30 min, cached)
	cd $(BE) && $(UV) run python -m app.feeds.hindcast

hindcast-reforecast: ## GEFSv12 reforecast wind shares against KXMR and KVBG, many years (resumable; HOURS, default 24)
	cd $(BE) && $(UV) run python -m app.feeds.hindcast_reforecast --hours $(or $(HOURS),24)

hindcast-hrrr: ## HRRR's 10 m wind against KXMR and KVBG, 2021-2025 (resumable; stops after HOURS, default 2)
	cd $(BE) && $(UV) run python -m app.feeds.hindcast_hrrr --hours $(or $(HOURS),2)

catalogues: ## Validate the cited catalogues under data/catalogues
	cd $(BE) && $(UV) run python -m app.data.catalogues

##@ Check our numbers against real ones (each prints its docs/validation.md tables)
validate-trip: ## Propagator, shadows, launch times and loops against NASA's reconstructed trajectories (~7 min)
	cd $(BE) && $(UV) run pytest app/tests/golden/test_propagate_vs_clps.py app/tests/golden/test_eclipse_vs_spice.py -q
	cd $(BE) && $(UV) run python -m app.validation.validate_trip
	cd $(BE) && $(UV) run pytest app/tests/golden/test_launch_vs_clps.py -q
	cd $(BE) && $(UV) run python -m app.validation.validate_launch 2>/dev/null
	cd $(BE) && $(UV) run pytest app/tests/golden/test_loops_vs_clps.py -q
	cd $(BE) && $(UV) run python -m app.validation.validate_loops 2>/dev/null

validate-radiation: ## Belts (IRBEM against SPDF's AE8/AP8), cosmic rays against CRaTER, particle events against NOAA
	cd $(BE) && $(UV) run python -m app.validation.validate_radiation 2>/dev/null

validate-orbiters: ## Real orbiters' passes against JPL Horizons (network; writes data/contact/orbiters_check.json)
	cd $(BE) && $(UV) run python -m app.validation.validate_orbiters 2>/dev/null

validate-viewshed: ## Rover-to-lander line of sight on the polar terrain against a brute-force line test
	cd $(BE) && $(UV) run python -m app.validation.validate_viewshed 2>/dev/null

validate-viewshed-gdal: ## Independent GDAL reference on matched lunar raster pixels (99% gate)
	cd $(BE) && $(UV) run python -m app.validation.validate_viewshed_gdal

validate-capsule: ## Capsule entry against OSIRIS-REx's landing (writes data/capsule/orex_check.json)
	cd $(BE) && $(UV) run python -m app.validation.validate_capsule 2>/dev/null

##@ Test and lint
test-db: ## Rebuild polar_window_test from the migrations and the seeded rows
	cd $(BE) && $(UV) run python -m app.tests.fixtures.make_test_db

test: test-db ## Every backend test, against polar_window_test (needs a seeded dev database)
	cd $(BE) && $(UV) run pytest -q

test-fast: ## Unit, property and synthetic golden tests. No services, < 20 s
	cd $(BE) && $(UV) run pytest app/tests/unit app/tests/golden/test_synthetic_golden.py -q

test-int: ## Integration and agent tests
	cd $(BE) && $(UV) run pytest app/tests/integration -q

test-geo: ## Golden tests against the real kernels and terrain
	cd $(BE) && $(UV) run pytest app/tests/golden -q

test-fe: ## Frontend units: the adapter, the cache keys, the exports
	cd $(FE) && npm test --silent

load-compute: ## Load test of the compute queue, every section at once (WORKERS=2; writes data/load)
	cd $(BE) && PW_TEST_DB_NAME=polar_window_load $(UV) run python -m app.tests.fixtures.make_test_db
	cd $(BE) && WORKERS=$${WORKERS:-2} $(UV) run python -m app.tests.load.load_compute

lint: ## ruff, mypy strict and the layering contracts (make fmt fixes the format)
	cd $(BE) && $(UV) run ruff check app && $(UV) run ruff format --check app
	cd $(BE) && $(UV) run mypy app
	cd $(BE) && $(UV) run lint-imports

contracts: ## Just the import-linter layering contracts
	cd $(BE) && $(UV) run lint-imports

fmt: ## Format the backend
	cd $(BE) && $(UV) run ruff format app && $(UV) run ruff check app --fix

golden-update: ## Re-pin the golden fixtures. Requires GOLDEN_UPDATE_REASON.
	@test -n "$$GOLDEN_UPDATE_REASON" || { \
	  echo "Refusing: a golden diff means the physics changed. Say why:"; \
	  echo '  GOLDEN_UPDATE_REASON="..." make golden-update'; exit 1; }
	cd $(BE) && $(UV) run python app/tests/golden/generate.py

##@ API contract
openapi: ## Write docs/openapi.json from the app's definition
	cd $(BE) && $(UV) run python -c "\
import json, pathlib; from app.main import create_app; \
p=pathlib.Path('../docs/openapi.json'); p.write_text(json.dumps(create_app().openapi(), indent=2)); \
print('wrote', p)"

codegen: openapi ## Regenerate the frontend's typed client from the schema
	cd $(FE) && npm run codegen

##@ Clean up
clean: ## Remove build output and caches
	rm -rf $(FE)/dist $(BE)/.pytest_cache $(BE)/.mypy_cache $(BE)/.ruff_cache
	find . -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true

nuke: clean ## Also remove the kernels, terrain, tiles and site list; make seed brings them back (~10 min)
	rm -rf $(DATA)/kernels $(DATA)/dem $(DATA)/tiles $(DATA)/sites.json
