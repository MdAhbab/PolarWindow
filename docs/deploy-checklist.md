# Deploy checklist — POLAR WINDOW

**Release:** first deployment of the backend and the wired frontend
**Date run:** 2026-09-18 · **Target:** single-node demo host, docker compose

This is a hackathon demo, not a production service, and the checklist says so
where it matters. Items that would be non-negotiable in production and are
deliberately skipped here are listed in *Not doing, and why*.

---

## Pre-deploy — verified

| | Check | Result |
|---|---|---|
| ✅ | `ruff check` | All checks passed |
| ✅ | `ruff format --check app` | 98 files already formatted |
| ✅ | `mypy --strict` | No issues in 98 source files |
| ✅ | Layering contracts (import-linter) | **8 kept, 0 broken** |
| ✅ | Test suite | **295 passed** (201 unit, 75 integration, 19 golden) in 18.1 s |
| ✅ | Frontend unit and component tests (`make test-fe`) | **129 passed** |
| ✅ | Browser tests (`npm run e2e`, axe included) | **18 passed**, zero serious or critical axe findings |
| ✅ | Frontend build | `tsc -b && vite build` clean, 164 KB gz JS + 9 KB gz CSS |
| ✅ | OpenAPI emitted and client regenerated from it | 19 paths, 52 schemas |
| ✅ | Golden fixtures present with a provenance manifest | 3 sites, kernels + DEM recorded |
| ✅ | No test reaches a live model API | autouse transport block |

### Data and migrations

- [ ] **`make seed` has run on the target volume.** This is the one hard
      prerequisite. Until it does, every geometry endpoint returns 409 with a
      readable message — the API starts and reports the problem rather than
      crashing, but nothing computes.
- [ ] `alembic upgrade head` — the API container runs this on boot. Three
      migrations; their upgrades only add tables and columns or relax NOT NULL,
      so re-running is safe. The drops are in the downgrades.
- [ ] `data/` volume is a **bind mount**, not a named volume. 250 MB of kernels
      and terrain take ten minutes to re-fetch, and `docker compose down -v`
      must not be able to destroy them.
- [ ] Verify the volume has ≥ 1 GB free (kernels 130 MB, DEM ~250 MB, tiles up
      to 150 MB).

### Configuration

- [ ] `PW_CORS_ORIGINS` includes the origin the frontend is actually served
      from. **The single most common failure.** Defaults cover the Vite dev
      ports; a deployed frontend needs its real origin added.
- [ ] `PW_DATABASE_URL` and `PW_REDIS_URL` point at the compose services, not
      at localhost.
- [ ] `PW_GEMINI_API_KEY` — optional. Without it every agent returns
      `status: "degraded"` with a deterministic summary built from the
      measurements. That is correct behaviour, not a failure.
- [ ] `PW_DOWNLOAD_KERNELS_ON_START` stays **false**. A container that silently
      pulls 114 MB at boot turns a fast, obvious failure into a slow mystery.

---

## Deploy

```bash
docker compose up -d postgres redis
docker compose run --rm worker          # seeds sites, masks, reference metrics
docker compose up -d api
```

### Smoke test

```bash
curl -s localhost:8000/healthz | jq '.status, .kernels.loaded, .dem.fine_windows'
# expect: "ok", true, 15

curl -s localhost:8000/api/v1/sites | jq '.items | length'
# expect: 15

curl -s localhost:8000/api/v1/sites/connecting-ridge/metrics \
  | jq '{sun: (.sunlit_s/3600|round), night: (.longest_dark_s/3600|round), cache: .meta.cache}'
# expect roughly: {"sun": 574, "night": 122, "cache": "miss"} then "hit" on a repeat

curl -s -X POST localhost:8000/api/v1/agents/explain \
  -H 'content-type: application/json' -d '{"site_id":"connecting-ridge"}' | jq .status
# expect "ok" with a key, "degraded" without — both are correct
```

### By hand, because no test covers it

1. Open `/clocks`. The provenance badge must read **MEASURED**. *Partial data*
   means `/healthz` is telling you something — fix that first.
2. Drag the date slider. Numbers must move, and after one pass the network
   panel should show `cache: "hit"` on repeats.
3. Open `/compare`, change the ranking metric, confirm the order changes.
4. Open `/states` — all four states render live.
5. **Read one agent paragraph.** Prompt quality is not covered by CI, because
   every test mocks the model. This is a genuine manual gate.
6. Open `/api/v1/agents/runs` and confirm it has rows.

---

## Rollback

| Trigger | Action |
|---|---|
| `/healthz` reports `down` | Check `kernels.missing`; run `make kernels`, restart the api |
| Geometry numbers changed unexpectedly | `make test-geo`. Golden fixtures report the worst offending bearing and both values. |
| Migration failed | `alembic downgrade -1`; the schema is additive so the previous image still runs |
| Agent layer misbehaving | Unset `PW_GEMINI_API_KEY` and restart. Every agent degrades to a deterministic summary; the four numbers are unaffected. |
| Redis misbehaving | `PW_REDIS_ENABLED=false`. Costs latency, changes no number, reports `cache: "bypass"`. |

**Rollback does not require a data reload.** Masks are stamped with
`engine_version`; an older image reads its own masks or rebuilds them, and never
silently serves geometry from a different engine.

---

## Not doing, and why

Named so the absences are decisions rather than oversights.

| Skipped | Why |
|---|---|
| Staging environment | One node, one demo. There is nowhere to stage to. |
| Canary / blue-green | Same. |
| Load testing | N1 is verified by one timed assertion in the integration suite. A real load suite is not a hackathon deliverable. |
| Alerting and on-call | Nobody is on call for a hackathon entry. `/healthz` is the monitoring. |
| Rate limiting | Read-only public data on a demo host. The agent endpoints are the only expensive ones and they are bounded at 20 s with one retry. |
| Secrets manager | One optional API key, supplied by environment. |
| HA / failover | Explicitly single-node in the system design. Stated rather than implied. |
| Backups | Everything in Postgres is regenerable by `make seed` in about ten minutes. The only irreplaceable data is the agent run log, which is demo evidence, not records. |

---

## Known state at time of writing

- `make` and `git` work on the build machine, and the repository is under
  version control, so rollback is `git revert` of the release commit.
- Tiles are pre-rendered to z5 by `make seed`; z6 and z7 render on first
  request and are written through.
- The frontend also builds without a backend: `npm run build:snapshot` serves
  the demo path from `public/snapshot/` (refresh it with `npm run snapshot`
  against a running API).
