# POLAR WINDOW — runbook

For whoever is holding this at a demo, or picking it up cold.

Read §1 first. Almost every failure this project has is one of the four in §2,
and three of them are the same failure.

---

## 1. Cold start on a new machine

Prerequisites: Python 3.12, Node 20+, Docker (or a local Postgres and Redis),
and about 250 MB of download.

```bash
make install     # dependencies
make seed        # kernels + terrain + sites + masks. ~10 min, once.
make dev         # services, api on :8000, frontend on :5173
```

`make seed` is a **hard prerequisite**, not an optimisation. Until it runs the
API starts, answers `/healthz`, and returns 409 with a readable message for
every geometry request. It does four things, and each is separately re-runnable:

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
```

If `fine_windows` is less than the site count, some per-site terrain windows
failed to download. That is **not fatal** — those sites fall back to the 80 m
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

A **truncated** kernel is worse than a missing one — a partial SPK can `furnsh`
without error and then return wrong vectors — so every file is size-checked
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
engine version — it should be impossible, since the version is in the cache key,
but if it happens: `redis-cli FLUSHDB`, then `make seed`.

To rebuild masks after a change to `core/`:

```bash
cd backend && uv run python -m app.workers.precompute --force
```

---

## 3. Before the demo

Fifteen minutes, in this order:

```bash
make lint            # ruff, mypy --strict, 8 layering contracts
make test            # rebuilds polar_window_test, then ~280 backend tests
make test-fe         # the adapter, the cache keys, the exports
curl -s localhost:8000/healthz | jq .status          # "ok", not "degraded"
```

Then, by hand — these are the things no test covers:

1. **Open `/clocks`.** The badge should read **MEASURED**. If it says *Partial
   data*, `/healthz` is telling you something; fix that first.
2. **Drag the date slider.** Numbers must move. Watch the network panel: after
   the first pass every request should report `cache: "hit"`.
3. **Open `/compare`.** Change the ranking metric; the order must change.
4. **Open `/states`.** All four states render live.
5. **Call one agent.** Prompt quality is *not* covered by CI — every test mocks
   the model — so this is a genuine manual gate:
   ```bash
   curl -s -X POST localhost:8000/api/v1/agents/explain \
     -H 'content-type: application/json' -d '{"site_id":"connecting-ridge"}' | jq '.status, .result.paragraph'
   ```
   `"degraded"` without `PW_GEMINI_API_KEY` is **correct behaviour**, not a
   failure: the paragraph is generated from the measurements. With a key, read
   the paragraph and check it says something true.
6. **Open `/agents/runs`.** It should have rows. This is the demo's evidence.

**Rehearse with the network off.** Set `OFFLINE=1` (in `.env` or the shell)
and restart the API. Nothing is downloaded (a missing kernel or DEM is a loud
error naming the fix), the agents answer from the measurements without calling
the model, and every other endpoint behaves exactly as online, because all of
it is local. `make test-fast` also runs with no services at all.

---

## 4. Operating notes

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
| Postgres | Total. No fallback — sites and masks live there. |

**Logs.** `docker compose logs -f api`. A guard rejection logs at WARNING with
the agent, the attempt and the violation kind; that is expected traffic, not an
error.

**The SPICE thread.** All ephemeris access is serialised through one thread per
process, because CSPICE is not thread-safe and `furnsh` mutates process-global
state. If concurrent cold timelines start queuing, add API replicas — not
threads. Kernel state is per-process and read-only after startup, so replicas
are free.

**Database size.** Trivial: 15 masks at ~17 KB, 15 metric rows, and however many
agent runs the demo produces. The DEM subset (~250 MB on the volume) is the only
thing that is large, and it is not in Postgres.

---

## 5. Rollback

There is no deployment pipeline to roll back — this is a single-node demo. What
you can revert:

| Change | Revert |
|---|---|
| Geometry (`core/`) | Restore the code; run `make test-geo`. The golden fixtures will fail loudly if the physics moved, with the worst offending bearing and both values. |
| Engine version bump | Put the old value back in `config.py` and `make worker --force`. Old masks are orphaned, not deleted. |
| Migration | `cd backend && uv run alembic downgrade -1` |
| Frontend | `git revert`, `make codegen` if the API contract moved. |

**Golden fixtures cannot be regenerated by accident.** `make golden-update`
refuses without `GOLDEN_UPDATE_REASON`, and writes that reason into the manifest
alongside the kernel set and DEM product. A golden diff in review is the signal
that a refactor changed the physics.

---

## 6. Things that will bite

Learned the hard way while building this, recorded so nobody rediscovers them:

- **A crater's IAU coordinate is its floor.** Shackleton's published centre is
  at −2,767 m — a permanently shadowed hole. Site coordinates here are derived
  from the DEM. Do not "correct" them back to catalogue values.
- **Grid north is not true north** in a polar stereographic projection. It
  rotates with longitude. A ray-march done in grid coordinates reports every
  blocker at the wrong bearing — 166° wrong at Shackleton. `local_frame()`
  measures the convergence; do not remove it.
- **The LOLA polar products are true at the pole**, not at a standard parallel.
  `+lat_ts=-87.5` looks plausible and is wrong by 0.2 % in range.
- **Near-field DEM noise looks exactly like a ridge.** At 40 m a 2 m vertical
  error is 2.9° of apparent skyline, which is larger than most real horizons
  here. The mask only counts a blocker that clears its own noise floor.
- **The horizon can be negative and must not be clamped.** A site standing
  1,958 m above the lunar reference sphere looks *down* at a −2.4° horizon, and that is
  the entire reason it has 81 % sunlight while the Sun never rises above level.
- **`asyncio.run()` inside an async worker** raises. The DEM fetcher has both a
  sync and an async entry point for this reason.
- **respx cannot intercept google-genai**, because the SDK's sync client runs
  inside `asyncio.to_thread`. Model calls are blocked at our own `_generate`
  seam instead — a test that sets a fake key really did reach the live API and
  get a 400 before that was fixed.
