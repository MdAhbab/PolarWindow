# POLAR WINDOW — runbook

For whoever is holding this at a demo, deploying it, or picking it up cold.

Read §1 first. Almost every failure is one of the four in §2.

---

## 1. Cold start on a new machine

Prerequisites: Python 3.12, Node 20+, Docker (or a local Postgres and Redis),
and about 250 MB of download.

```bash
make install     # dependencies
make seed        # kernels + terrain + sites + masks. ~10 min, once.
make dev         # services, api on :8000, frontend on :5173
```

`python3 run.py` does all of this in one command. On a machine without Docker or
a database it creates the project's own PostgreSQL in `.local/pgdata` (this
machine only, no password) on the port in `PW_DATABASE_URL`. When the NASA
servers are slow, copy the data from a machine that has it (`--export-data` and
`--data-from`, in the README's quick start).

Processes started by `run.py` are tracked in `.local/run.pids` (JSON) to avoid
affecting other checkouts or unrelated software on the host. If a required port
(8000 or 5173) is occupied by a foreign process, the runner refuses to terminate
it, logs an informative error with the foreign process command line, and exits with
code 1. On shutdown, all child processes receive termination signals concurrently;
compute workers get up to `POLAR_STOP_GRACE_S` (default 15 s) to return claimed jobs
cleanly before SIGKILL. Exit codes: `0` (clean), `1` (child crash), `130` (Ctrl+C),
and `143` (SIGTERM). Project-local database and Redis instances remain running for fast
restarts; stop them explicitly with `python3 run.py --stop-services`.

`make seed` is a **hard prerequisite**, not an optimisation. Until it runs the
API starts, answers `/healthz`, and returns 409 with a readable message for
every geometry request. It runs the steps below, and each is separately
re-runnable:

| Step | Downloads | Time | Idempotent |
|---|---|---|---|
| `make kernels` | ~130 MB SPICE | 1–3 min | yes, verifies each file by SHA256 and skips |
| `make dem` | ~115 MB LOLA 80 m | 2–4 min | yes, skips if present |
| `make sites` | — | ~20 s | yes, overwrites |
| `make missions` | — | ~2 s | yes, replaces the mission tables from `data/missions.json` |
| `make worker` | ~8 MB per polar site | 1–3 min | yes, skips existing masks |
| `make tiles` | — | ~45 s | yes, overwrites (z0–z5, ~134 MB) |

**Verify it worked:**

```bash
curl -s localhost:8000/healthz | jq '.status, .kernels.loaded, .dem.fine_windows'
# "ok", true, 18   (15 candidates + 3 polar mission targets)
curl -s localhost:8000/api/v1/sites | jq '.items | length'
# 15               (candidates; ?kind=all gives 22)
curl -s localhost:8000/api/v1/missions | jq '.total'
# 20
curl -s localhost:8000/api/v1/sites/connecting-ridge/metrics \
  | jq '{sun: (.sunlit_s/3600|round), night: (.longest_dark_s/3600|round), cache: .meta.cache}'
# roughly {"sun": 574, "night": 122, "cache": "miss"}, then "hit" on a repeat
```

If `fine_windows` is less than the site count, some per-site terrain windows
failed to download. That is **not fatal**. Those sites fall back to the 80 m
regional tile, report lower `coverage`, and say so in `meta.uncertainty`. Re-run
`make worker` to retry them.

---

## 2. The four failures

### 2.1 "SPICE kernel missing" / `/healthz` says `down`

**By far the most common.** The error message names the file, its expected size,
the NAIF URL and the command:

```
SPICE kernel missing: de440.bsp
  expected at : /data/kernels/de440.bsp
  download    : https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/planets/de440.bsp
  needed for  : Planetary ephemeris. Without it there are no Sun or Earth positions…
  fix         : make kernels
```

```bash
make kernels
```

If NAIF is unreachable (corporate networks often block it), download the five
files listed by `/healthz` in a browser into `data/kernels/` and re-run. The
metakernel is *generated* from what is on disk, so nothing else needs editing.

A **truncated** kernel is worse than a missing one: a partial SPK can `furnsh`
without error and then return wrong vectors. So every file is size-checked
before use. If you see "looks truncated", delete it and re-fetch.

### 2.2 "This site has not been surveyed yet" (409)

`make seed` has not run, or has not run for this site.

```bash
make worker                                   # all sites
cd backend && uv run python -m app.workers.precompute --sites nobile-rim-2
```

The API deliberately does not build a mask on demand: it is ~45 ms of tight
numpy plus a multi-second terrain fetch, and putting it on a request path would
make the first click of a demo take a minute.

### 2.3 "Failed to fetch" in the browser, but curl works

CORS. The frontend's origin is not in `PW_CORS_ORIGINS`. Vite takes the next
free port when 5173 is busy, so check what it actually printed.

```bash
curl -si -H 'Origin: http://localhost:5174' localhost:8000/api/v1/sites \
  | grep -i access-control-allow-origin
```

Defaults cover 5173, 5174 and 4173 on both `localhost` and `127.0.0.1`.

### 2.4 Numbers look wrong / did not change

Check `meta.engine_version` in the response against the one in
`backend/app/config.py`. Masks and reference metrics are stamped with it, and a
mismatch means stale geometry is being served.

```bash
curl -s localhost:8000/api/v1/sites/connecting-ridge/metrics | jq .meta
```

`cache: "hit"` with an old `computed_at` means Redis is serving a previous
engine version. That should be impossible, since the version is in the cache
key. If it happens: Settings → Project → *Clear saved results* (it deletes only
this service's `pw:*` keys), then `make seed`. From a shell, the same thing is
`curl -X DELETE -H "authorization: Bearer $TOKEN" localhost:8000/api/v1/settings/cache`.

### The project manager's controls

Settings → Project, in the dashboard, does what used to need a shell:

| Task | In Settings | Undo |
|---|---|---|
| Turn the AI off (every panel answers from the measurements) | AI assistant → Off | On |
| Change which Gemini model is tried first | Move a model up or down | Reset the AI settings |
| A model was skipped for quota and the quota was raised | Try skipped models now | none needed |
| Clear the AI activity log before a demo | Clear the AI activity log, then confirm | none: the log only records |
| Stale results after new data | Clear saved results, then confirm | none needed: results are worked out again |

The panel's *System* list says whether the terrain map, the Sun and Earth
positions, the database and the cache are working, and counts the missions,
sites, AI runs and saved results.

To rebuild masks after a change to `core/`:

```bash
cd backend && uv run python -m app.workers.precompute --force
```

---

## 3. Before the demo

Fifteen minutes, in this order:

```bash
make lint            # ruff, mypy --strict, the layering contracts
make test            # rebuilds polar_window_test, then every backend test
make test-fe         # frontend unit and component tests
curl -s localhost:8000/healthz | jq .status          # "ok", not "degraded"
```

Then, by hand. These are the things no test covers:

1. **Open `/site`.** No data-source badge should show in the header. If one
   says *Partial data*, `/healthz` is telling you something; fix that first.
2. **Drag the date slider.** Numbers must move. Watch the network panel: after
   the first pass every request should report `cache: "hit"`.
3. **Open `/compare`.** Change the ranking metric; the order must change.
4. **Stop the API and reload.** The *Saved copy* badge appears and the
   missions still load from the offline copy.
5. **Call one agent.** Prompt quality is *not* covered by CI, because every test
   scripts the model, so this is a genuine manual gate:
   ```bash
   curl -s -X POST localhost:8000/api/v1/agents/explain \
     -H 'content-type: application/json' -d '{"site_id":"connecting-ridge"}' | jq '.status, .result.paragraph'
   ```
   `"degraded"` without `PW_GEMINI_API_KEY` is **correct behaviour**, not a
   failure: the paragraph is generated from the measurements. With a key, read
   the paragraph and check it says something true.
6. **Open Settings → Project and read the AI activity log** (or
   `GET /api/v1/agents/runs`). It should have rows. This is the demo's evidence.
   To start with an empty log, clear it first (§2, the project manager's
   controls).

**Rehearse with the network off.** Set `OFFLINE=1` (in `.env` or the shell)
and restart the API. Nothing is downloaded (a missing kernel or DEM is a loud
error naming the fix), the agents answer from the measurements without calling
the model, and every other endpoint behaves exactly as online, because all of
it is local. `make test-fast` also runs with no services at all.

**The offline copy.** The frontend also builds without a backend:
`npm run build:snapshot` serves the demo path from `public/snapshot/`. Refresh
that folder with `npm run snapshot` against a running API.

---

## 4. Deploying on one host

This is a single-node demo, not a production service. `docker compose up` runs
the whole backend: Postgres, Redis, a `migrate` step (the database migrations),
a `data` step (it fetches what `data/` lacks and builds the skylines), the API on
:8000, the compute worker and the feeds worker. The frontend is not a service:
`make frontend` serves it on :5173 against this API.

**Before the first start**

- Copy `.env.example` to `.env` (it is optional, and needs Docker Compose 2.24 or
  newer). Every service reads it, and so do make and `run.py`. The compose file
  sets only what differs inside a container: the database URL, the Redis URL and
  the data folder.
- `data/` is a bind mount (`./data:/data`), not a named volume, so
  `docker compose down -v` cannot destroy the kernels and terrain that take so
  long to fetch. Every service writes there, so on Linux it must be writable by
  uid 10001 (`sudo chown -R 10001 data`).
- On a new machine the `data` step downloads about 600 MB (the core and
  lifecycle tiers) before the API and the workers start. On a machine that has
  the data it is a check. The README says how to copy the data from another
  machine first. Leave at least 1 GB free: the map tiles built from the terrain
  add up to 150 MB.
- Set what matters in `.env`. `.env.example` lists every variable:

| Setting | Value |
|---|---|
| `PW_CORS_ORIGINS` | Must include the origin the frontend is served from. The single most common failure (§2.3). |
| `PW_DEMO_SIGN_IN` | `true` for the judged demo, `false` anywhere real. |
| `PW_JWT_SECRET` | A long random value if more than one API process serves requests. Blank is fine for one process: sessions then end on restart and the dashboard signs in again by itself. |
| `PW_GEMINI_API_KEY` | Optional. Without it every agent answers `degraded` from the measurements. |
| `PW_DOWNLOAD_KERNELS_ON_START` | Keep `false`. A container that silently pulls 114 MB at boot turns a fast, obvious failure into a slow mystery. |

**Start**

```bash
PW_CODE_VERSION=$(git rev-parse --short=12 HEAD) docker compose up -d
docker compose logs -f data             # the first start: the downloads
```

`PW_CODE_VERSION` is recorded with every answer. The image has no git, so the
commit is named here. The `migrate` step runs `alembic upgrade head` and exits.
Upgrades add tables, columns, indexes and triggers (one corrects stored values)
and drop nothing, so running them again is safe. The drops are in the downgrades.

A failed download does not keep the app from starting. It is in the `data`
step's log, and `/healthz` reports what is missing. Fix the cause, then run
`docker compose run --rm data` and `docker compose restart api compute`. To add
the validation tier, which only checks our numbers:
`docker compose run --rm data polar-data sync --tier validation`.

When the stack is up, run the checks in §1 and §3.

**What a demo host leaves out, and why**

| Left out | Why |
|---|---|
| Staging, canary or blue-green | One node, one demo. There is nowhere to stage to. |
| Load testing | The slider is spot-checked by one loose timed assertion in the integration suite, and the compute queue has its own load run (`docs/test-plan.md`). |
| Alerting and on-call | `/healthz` is the monitoring. |
| Rate limits on reads | Reads are public data. Writes and the AI panels are limited per address (§7), and each AI run is bounded at 20 s with one retry. |
| Real sign-in | Judges get in with one click, so the session has no password. Before anything real, set `PW_DEMO_SIGN_IN=false` and put an identity provider in front of `/auth`. |
| Secrets manager | One optional API key, from the environment. |
| High availability | Single node by design. |
| Backups | `make seed` rebuilds the sites and skylines in about ten minutes. It cannot rebuild what was recorded or entered: the feeds' snapshots (forecasts of record), the change history, the team's readiness items, parts, risks and limits, and the AI activity log. Back the database up if those matter. |

---

## 5. Operating notes

**Tests have their own database.** `make test` first runs `make test-db`, which
rebuilds `polar_window_test` from the migrations plus a copy of the seeded rows,
and the suite uses Redis database 1. Running the suite never changes what the
dev API serves.

**Kernels are pinned.** `uv run polar-kernels verify` checks every file against
its SHA256; `polar-kernels fetch` downloads what is missing (refused under
`OFFLINE=1`).

**Everything degrades except Postgres.**

| Down | Effect |
|---|---|
| Redis | Latency only. `meta.cache` reads `"bypass"`. |
| Gemini | Agents return `degraded` with a deterministic summary. Nothing else. |
| LOLA subset | Masks fall back to a spherical horizon, `coverage` drops, responses say so. |
| SPICE | No Sun or Earth positions. `/healthz` 503. Sites, terrain and tiles still serve. |
| Postgres | Total. No fallback: sites and masks live there. |

**Logs.** `docker compose logs -f api`. A guard rejection logs at WARNING with
the agent, the attempt and the violation kind. That is expected traffic, not an
error.

**The SPICE thread.** All ephemeris access goes through one thread per process
(`docs/system-design.md` §4.2). If concurrent cold timelines start queuing, add
API replicas, not threads. Kernel state is per-process and read-only after
startup, so replicas are free.

**Database size.** Small: 15 masks at ~17 KB, 15 metric rows, and whatever the
feeds worker, the team's entries and the agent runs add. The DEM subset (~250 MB
on the volume) is the only thing that is large, and it is not in Postgres.

---

## 6. Rollback

There is no deployment pipeline to roll back. What you can revert:

| Change | Revert |
|---|---|
| Geometry (`core/`) | Restore the code; run `make test-geo`. The golden fixtures will fail loudly if the physics moved, with the worst offending bearing and both values. |
| Engine version bump | Put the old value back in `config.py` and `make worker --force`. Old masks are orphaned, not deleted. |
| Migration | `cd backend && uv run alembic downgrade -1`. The schema is additive, so the previous image still runs. |
| Frontend | `git revert`, `make codegen` if the API contract moved. |
| The AI layer misbehaves | Turn the AI off in Settings, or unset `PW_GEMINI_API_KEY` and restart. Every agent answers from the measurements. The four numbers are unaffected. |
| Redis misbehaves | `PW_REDIS_ENABLED=false`. It costs latency, changes no number and reports `cache: "bypass"`. |

**Rollback does not need a data reload.** Masks are stamped with
`engine_version`. An older image reads its own masks or rebuilds them, and never
silently serves geometry from a different engine.

**Golden fixtures cannot be regenerated by accident.** `make golden-update`
refuses without `GOLDEN_UPDATE_REASON`, and writes that reason into the manifest
alongside the kernel set and DEM product. A golden diff in review is the signal
that a refactor changed the physics.

---

## 7. The mission lifecycle: processes, keys, feed outages

**Processes.** Besides the API, two workers (ADR-8, ADR-12), both reading the same
Postgres:

| Process | Start | Does | If it is not running |
|---|---|---|---|
| compute worker | `make compute` (`run.py` starts `POLAR_COMPUTE_WORKERS`, default 2) | trip, contact and launch answers, one job at a time each | a section stays "being worked out"; after a while its message says "the compute worker is not running (make compute)" |
| feeds worker | `make feeds` (`make feeds-once` for one pass) | records weather, space weather, launch schedules, DSN Now | live numbers age past their budgets and are replaced by the reason; `/healthz` stays up |

After a code change restart the API **and** the compute workers: a worker keeps the
code it started with, and a stored answer is reused until its inputs or engine
versions change (ADR-13). Stopping a worker hands its job back without spending an attempt.

**Keys** (all optional, in `.env`, never committed or printed):

| Setting | Needed for | Without it |
|---|---|---|
| `PW_GEMINI_API_KEY` | the AI helpers | they answer `degraded` with a plain summary |
| `PW_NASA_API_KEY` | DONKI (api.nasa.gov) | DEMO_KEY, 30 requests an hour |
| `PW_EARTHDATA_TOKEN` | `make thunder-climatology` (GHRC via OPeNDAP) and Earthdata downloads | the lightning rules show no climatology |
| `PW_JWT_SECRET` | sign-in tokens that survive an API restart | a random secret per process: people sign in again after a restart |

**A feed is failing.** `GET /api/v1/feeds` lists every product with its age, last
error and breaker. `/healthz` says `degraded` (200, never `down`) while any product
is failing; stale data alone does not degrade it. Each number that needs the feed
says why it is missing, and every other section is unaffected
(`tests/integration/test_chaos.py`). A signed-in project manager can ask for one
provider now: `POST /api/v1/feeds/{provider}/refresh` (audited). After five failed
runs the breaker holds the provider for a cool-down, then tries once. Known from
this network: Launch Library 2 answers 429 when the shared IP is over its limit (the
interval is already 30 min); NGA's NAVAREA IV API returns an error page; GEOS-FP's
host does not answer.

**A job failed.** Its message is the answer until the inputs change (a failed job
is not retried on every page load). `POST /api/v1/jobs/{id}/retry` (signed in)
queues it again (recorded in `/history?entity=job`); `GET /api/v1/jobs/{id}` shows
its progress.

**Sections answer 503 "Too many answers are being worked out".** 200 jobs are
waiting (`PW_MAX_QUEUED_JOBS`); stored answers still read. Start more compute
workers (`POLAR_COMPUTE_WORKERS`) or wait; `make load-compute` measures what two
workers get through (`docs/test-plan.md`, "Load on the compute queue").

**A write answers 429.** One address made more changes in a minute than its
allowance (`PW_RATE_SIGN_IN_PER_MIN` 60, `PW_RATE_AGENTS_PER_MIN` 20,
`PW_RATE_COMPARE_PER_MIN` 60, `PW_RATE_WRITES_PER_MIN` 120; `PW_RATE_LIMITS=off` turns
them off). `Retry-After` says when to try again. The counts live in the API process
and reset when it restarts. Bodies over `PW_MAX_BODY_BYTES` (64 KB) are refused (413).

**Long commands**, cached where they can be: `make hindcast-weather` (~40 min),
`make hindcast-reforecast` (~30–60 min; multi-year GEFSv12 wind verification against pad ASOS),
`make hindcast-hrrr` (~35 min; HRRR AWS byte-range verification),
`make thunder-climatology` (~1.5 h), `make validate-trip` (~7 min with the loops),
`make validate-capsule` (~20 s), `make validate-radiation`, `make space-climate`.
Their results are committed under `data/` (see `docs/data-sources.md`).

Run `make help` to list every make target with its description.

**Native rover terrain.** `python -m app.data.rover_terrain` from `backend/`
fetches 5 m LOLA site windows south of 87.5 degrees S and 3/4 m LROC NOBILE
windows inside their footprints. `polar-data sync --tier lifecycle` includes
the same step after seeding sites. Downloads can take several minutes per
stereo window; completed windows are reused. The API selects the finest
window covering the requested neighbourhood with known ground at the lander,
otherwise 20/80 m terrain, and keys the answer by the selected file's SHA-256.
Rover map tiles read that same file. Keep completed files immutable; changing
one after a job is queued requires another request. The surface illumination
skyline continues to use its separate model. See [coverage and external account
status](planning-updates.md).
