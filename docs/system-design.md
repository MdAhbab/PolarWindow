# POLAR WINDOW — System Design

Architecture, domain models, compute core, service boundaries, and lifecycle engines for POLAR WINDOW.

---

## 0. Architecture Principles and Constraints

The system couples a React frontend with a FastAPI backend backed by PostgreSQL, Redis, SPICE ephemerides, and LOLA lunar elevation data.

Key constraints that shape this architecture:

1. **DTO alignment.** The backend response schemas mirror the data structures consumed by frontend views (`SiteMetrics`, `BodyResult`, `Arc`, `TrackSample`, `HorizonMask`). Responses use `snake_case` on the wire, converted to `camelCase` by the client adapter.
2. **Derived metrics invariant.** As stated in `docs/conventions.md` invariant 1, no endpoint returns a hardcoded metric. Every value is derived from physics models, ephemerides, and elevation data. Responses explicitly state inputs and uncertainties in a mandatory `meta` envelope.
3. **Compute progress streaming.** The frontend streams per-site metrics and manages asynchronous job lifecycles. The backend provides predictable single-flight execution and cache semantics for parallel queries.

---

## 1. Requirements

### Functional

| # | Requirement | Served by |
|---|---|---|
| F1 | List/filter 12–20 candidate south-pole sites with provenance | `GET /sites` |
| F2 | Per-site horizon mask (azimuth → skyline elevation) | `GET /sites/{id}/horizon` |
| F3 | Sun/Earth az, el, visibility over an arbitrary window | `GET /sites/{id}/timeline` |
| F4 | Lit/dark and link/blackout intervals derived from F3 | `GET /sites/{id}/windows` |
| F5 | The four key numbers for a window | `GET /sites/{id}/metrics` |
| F6 | Rank N sites against one shared window | `POST /compare` |
| F7 | Terrain hillshade + illumination raster tiles | `GET /tiles/...` |
| F8 | Four grounded LLM agents over the above | `POST /agents/*` |
| F9 | Liveness + kernel-loaded readiness | `GET /healthz` |
| F10–F14 | CLPS missions, payloads, targets, calendar — see §10.2 | `GET /missions`, `GET /missions/{id}`, `GET /sites/{id}/calendar` |

### Non-functional

| # | Target | Why this number |
|---|---|---|
| N1 | Date-slider p95 **< 150 ms** warm, < 600 ms cold | The slider fires on drag. Above ~150 ms the terminator sweep (M1, 708 h in 14 s) visibly stutters and the product's core claim — "move the slider and the numbers genuinely change" — stops feeling true. |
| N2 | Horizon mask build **< 90 s** per site offline | 1440 rays × ~600 samples. Off the request path entirely, so this is a seeding budget, not a latency budget. |
| N3 | Cold start **< 20 s** including kernel furnsh | Judges restart things. de440 is ~114 MB; it must be baked into the image layer, not downloaded at boot. |
| N4 | Agent p95 **< 20 s**, hard timeout 20 s, 1 retry, then deterministic fallback | A demo that hangs on an LLM call is a failed demo. The fallback is non-negotiable. |
| N5 | Correctness: golden fixtures stable to **±0.05° elevation, ±0.02 h arc edges** | Tighter than the DEM's own contribution (±2 m at 1.4 km ⇒ ±0.08°), so the test catches refactor drift without failing on float noise. |
| N6 | Availability: single-node, no HA | Single-node demo posture. Documented explicitly so nobody mistakes it for a high-availability production deployment. |

### Constraints

- Design choices prioritize determinism, verifiable provenance, and reproducible evaluation.
- SPICE (CSPICE via spiceypy) is **not thread-safe** and holds **process-global**
  kernel state after `furnsh`. This is the single hardest constraint in the
  backend and it shapes §4.
- LOLA polar DEM tiles are large (the 5 m/px south-pole product is tens of GB).
  We cannot ship that. We ship a **clipped, downsampled subset** around the
  candidate sites and say so in `meta.uncertainty`.
- No NASA branding. Data product *names* are public identifiers and may be cited
  as provenance; logos and insignia may not appear.

---

## 2. Service boundaries

Four processes, one shared Postgres, one shared Redis.

```
                           ┌──────────────────────────────┐
  browser ────────────────▶│  api   (FastAPI, uvicorn)    │
   React/Vite              │  stateless · read-mostly     │
   TanStack Query          │  SPICE furnsh'd at lifespan  │
                           │  1 dedicated SPICE thread    │
                           └───┬───────────┬───────────┬──┘
                               │           │           │
                      ┌────────▼──┐  ┌─────▼────┐  ┌───▼──────────┐
                      │ postgres  │  │  redis   │  │ google-genai │
                      │ sites     │  │ timeline │  │ (egress)     │
                      │ masks     │  │ cache    │  └──────────────┘
                      │ metrics   │  │ locks    │
                      │ agent_runs│  └─────▲────┘
                      └────▲──────┘        │
                           │               │
                      ┌────┴───────────────┴─────────┐
                      │ worker (arq / plain asyncio) │
                      │ mask build · coarse tables   │
                      │ reads DEM GeoTIFF from disk  │
                      └──────────────┬───────────────┘
                                     │
                              ┌──────▼───────┐
                              │ data/ volume │
                              │ LOLA GeoTIFF │
                              │ SPICE kernels│
                              │ tile cache   │
                              └──────────────┘
```

### Boundary rules

| Boundary | Rule | Enforcement |
|---|---|---|
| `routes/` → `services/` | Routes do HTTP concerns only: parse, validate, delegate, serialise. | Import-linter contract: `app.api` may not import `app.db.models` or `sqlalchemy`. |
| `services/` → `repositories/` | Services hold policy. No `fastapi` import, ever — so they are callable from the worker and from agent tools. | Import-linter: `app.services` may not import `fastapi`. |
| `repositories/` → `db/` | The only place SQLAlchemy appears. One file per aggregate. | Import-linter: `sqlalchemy` importable only from `app.db`. |
| `core/` | **Pure functions, no I/O, no DB, no network, no clock.** Arrays in, arrays out. This is what makes golden tests possible and what lets the same code run in the worker and the API. | Import-linter: `app.core` may not import `app.db`, `app.services`, `app.api`, `httpx`, `rasterio`(*). |
| `core/spice.py` | The **only** module that imports `spiceypy`. Everything else takes vectors/arrays. | Import-linter: `spiceypy` importable only from `app.core.spice`. |
| `agents/` → system | Agents reach the system **only** through `agents/tools.py`. No agent module imports a service directly. | Import-linter + review. |

(*) `core/horizon.py` takes a `SampleTerrain` **callable**, not a raster handle.
The rasterio-backed sampler lives in `data/` and is injected. That is what keeps
the ray-march pure and testable against a synthetic surface whose analytic
horizon we can derive by hand.

### Why these four processes and not fewer

- **api/worker split is forced by N1+N2.** A 90 s mask build cannot share a
  process with a 150 ms p95 budget, because CPython will not preempt a numba
  loop for the event loop.
- **api/worker split is *not* forced for SPICE.** Both processes furnsh the same
  kernels independently; kernel state is per-process and read-only after startup.
  That is cheap (mmap'd) and avoids an RPC hop.
- **Tiles live in `api`, not a fifth process.** See ADR-4.

---

## 3. Data model

Postgres 16. SQLAlchemy 2.x declarative, async via asyncpg. Times are
`timestamptz`; durations are **seconds** (`double precision`) on the wire and in
the DB — the frontend's "hours" is a presentation unit and the conversion happens
in the adapter, once.

```
┌────────────────────┐
│ sites              │  slug PK — stable, human-readable, appears in URLs
├────────────────────┤
│ id          text PK│  'shackleton-rim'
│ code        text   │  'A'  — the letter the UI draws
│ name        text   │
│ lat_deg     float  │  selenographic, negative south
│ lon_deg     float  │  degrees east, 0..360
│ elev_m      float  │  above the 1737.4 km reference sphere
│ note        text   │
│ region      text   │  'shackleton' | 'de-gerlache' | ... for search_sites
│ source      text   │  'Lunar South Pole Atlas' etc.
│ source_url  text   │
│ source_note text   │  how the coordinate was obtained
│ is_active   bool   │
│ created_at/updated_at
└─────────┬──────────┘
          │ 1:N (one per engine_version × resolution)
┌─────────▼──────────────────────────────────────────┐
│ horizon_masks                                      │
├────────────────────────────────────────────────────┤
│ id                uuid PK                          │
│ site_id           text FK → sites                  │
│ engine_version    text      'hz-2'                 │
│ azimuth_count     int       1440                   │
│ azimuth_step_deg  float     0.25                   │
│ max_range_m       float     50000                  │
│ el_deg            bytea     float32[1440] LE       │
│ range_m           bytea     float32[1440] LE       │
│ tol_deg           bytea     float32[1440] LE       │
│ max_el_deg        float                            │
│ max_el_bearing_deg float                           │
│ dem_product       text      'LOLA_LDEM_80S_20M'    │
│ dem_resolution_m  float     20.0                   │
│ dem_vertical_error_m float   2.0                   │
│ coverage          float     share of rays inside the DEM, 0–1
│ computed_at       timestamptz                      │
│ compute_ms        float                            │
└────────────────────────────────────────────────────┘
   UNIQUE (site_id, engine_version, azimuth_count)

┌────────────────────────────────────────────────────┐
│ site_window_metrics  — memoised four-numbers       │
├────────────────────────────────────────────────────┤
│ id                uuid PK                          │
│ site_id           text FK                          │
│ engine_version    text                             │
│ window_start      timestamptz   (quantised)        │
│ window_end        timestamptz   (quantised)        │
│ step_s            int                              │
│ sun_up_s          float                            │
│ earth_up_s        float                            │
│ longest_dark_s    float                            │
│ longest_blackout_s float                           │
│ worst_compound_s  float                            │
│ sun_fraction_up   float                            │
│ earth_fraction_up float                            │
│ grazing           bool   any crossing untimeable   │
│ computed_at       timestamptz                      │
└────────────────────────────────────────────────────┘
   UNIQUE (site_id, engine_version, window_start, window_end, step_s)

┌────────────────────────────────────────────────────┐
│ agent_runs          — the demo's proof of work     │
├────────────────────────────────────────────────────┤
│ id             uuid PK                             │
│ agent          text   'explainer'|'advisor'|'writer'|'asker'
│ model          text   the model that answered      │
│ status         text   'ok'|'insufficient_data'|'guard_rejected'
│                       |'timeout'|'degraded'|'error'│
│ request        jsonb                               │
│ response       jsonb  the validated pydantic dump  │
│ prompt_tokens  int                                 │
│ completion_tokens int                              │
│ latency_ms     float                               │
│ attempts       int    1 or 2                       │
│ guard_failures jsonb  [{kind, detail}]             │
│ error          text                                │
│ created_at     timestamptz                         │
└─────────┬──────────────────────────────────────────┘
          │ 1:N
┌─────────▼──────────────────────────────────────────┐
│ agent_tool_calls                                   │
├────────────────────────────────────────────────────┤
│ id          uuid PK                                │
│ run_id      uuid FK → agent_runs (ON DELETE CASCADE)│
│ seq         int                                    │
│ tool        text                                   │
│ args        jsonb                                  │
│ result      jsonb    truncated to 8 KB             │
│ numbers     float[]  every numeric leaf, flattened │ ◀── the grounding set
│ latency_ms  float                                  │
│ error       text                                   │
└────────────────────────────────────────────────────┘
```

### Two non-obvious modelling choices

**`agent_tool_calls.numbers` is a materialised column, not derived at check time.**
The grounding guard must answer "is 63.2 present in any tool output?" on every
retry. Flattening the JSON on write, once, makes the guard O(|claims| × |numbers|)
against a float array instead of a recursive walk of nested JSON per attempt. It
also makes the guard auditable after the fact from SQL alone, which is what lets
the demo *show* the check rather than assert it.

**Float arrays are `bytea`, not `float[]` or JSONB.** A 1440-entry mask is 5.7 KB
as raw float32 and ~20 KB as JSON text. Three arrays × 20 sites × several
engine versions is the difference between a table that fits in shared buffers and
one that does not. The cost is that you cannot query inside them in SQL — which
is fine, because nothing ever does; they are always read whole.

### Quantisation (this is load-bearing, see §6)

`window_start`, `window_end` and every Redis cache key are **quantised to the
step grid** before hashing. A slider drag emits `start=…T03:07:41Z`,
`…T03:09:02Z`, `…T03:11:30Z`; quantised to a 900 s grid all three become the same
key. Without this, the cache hit rate on the primary interaction is ~0 %.

---

## 4. The compute core

### 4.1 Layering inside `core/`

```
kernels.py   ─ download/verify/cache SPICE kernels, build the metakernel.
               The ONLY module allowed to touch the network at import-adjacent time.
               Fails loudly with the exact missing file and its URL.
spice.py     ─ the only importer of spiceypy. furnsh(), utc→et, and
               body_vectors(et[], body) → (n,3) float64 in MOON_ME.
               Serialises every CSPICE entry through one lock.
projections.py ─ pyproj transformers, lunar south polar stereographic
               (IAU_MOON sphere R=1737400) ↔ selenographic lat/lon.
horizon.py   ─ ray-march. Pure. Takes a `sample_h(x[], y[]) -> z[]` callable.
               numba-jitted inner loop with a pure-python fallback.
visibility.py─ ENU basis from lat/lon, body vector → (az, el). Pure, vectorised.
intervals.py ─ boolean/margin series → runs, gaps, longest run, bisected edges.
               Pure. Zero domain knowledge — it does not know what "dark" means.
metrics.py   ─ the four numbers + compound events, from intervals. Pure.
```

`intervals.py` knowing nothing about astronomy is deliberate: it makes the
hypothesis property tests in §8 of the test plan meaningful. A longest-run bug is
the most likely silent failure in this project (the brief says so, and it is
right), and it is only cheaply testable if the module under test accepts
arbitrary boolean arrays rather than plausible-looking sun tracks.

### 4.2 The SPICE thread

CSPICE is not thread-safe and `furnsh` mutates process-global state. Three
options were considered:

| Option | Verdict |
|---|---|
| Call spiceypy directly from async handlers | **No.** A 2,800-sample `spkpos` sweep blocks the event loop for ~15 ms; concurrent sliders queue behind each other invisibly. |
| Lock + `run_in_threadpool` (default executor) | Works, but the default executor is shared with every other `def` endpoint and file read, so SPICE work competes with itself for threads it cannot use anyway. |
| **Dedicated 1-thread executor + `asyncio.to_thread` wrapper** | **Chosen.** One thread owns all CSPICE entry. Serialisation is explicit rather than emergent. Numpy work after the vector fetch happens on that same thread and releases the GIL for the heavy parts. |

All ephemeris access is therefore `await spice.body_vectors_async(...)`, which
hops to that one thread, makes **one** vectorised `spkpos` call for the whole
window, and returns an `(n, 3)` array. One hop per request, not per sample.

### 4.3 Elevation and the penumbra

`visible = el > interp(horizon, az)` is the boolean the brief specifies. The
refinement it asks for — the Sun's ~0.26° angular radius — is implemented as a
**three-state** result, not a softened float:

```
el − horizon >  +R_sun   → lit        (full disc clear of the skyline)
el − horizon <  −R_sun   → dark       (full disc occluded)
otherwise                → penumbral  (partial illumination; magnitude reported
                                        as the fraction of the disc clear, but
                                        labelled partial, never as a power figure)
```

This matches frontend invariant 2 ("every number carries its ±, or says why it
cannot") and invariant 4 (uncertain is hatched at −45°, a distinct claim from
blocked at +45°). The frontend already has the visual vocabulary for a third
state; giving it a fake boolean would waste it and would be a lie at exactly the
place the terrain model is weakest — the shadow edge.

Earth gets the same treatment with its own radius as seen from the Moon (~0.9°),
which matters more than the Sun's: a 0.9° penumbra against a ±6.7° libration
swing is a real fraction of the contact-window edge.

---

## 5. API contract

Base `/api/v1`. Times ISO 8601 UTC with `Z`. Durations in **seconds**.
Angles in degrees. Every response body carries `meta`.

### 5.1 The mandatory `meta` envelope

```jsonc
"meta": {
  "computed_at": "2026-09-18T04:12:55.104Z",
  "resolution": {
    "azimuth_deg": 0.25,          // horizon mask angular step
    "time_step_s": 900,           // timeline sampling step
    "dem_product": "LOLA_LDEM_80S_20M",
    "dem_resolution_m": 20.0,
    "ephemeris": "de440 + moon_pa_de440 (MOON_ME)"
  },
  "uncertainty": {
    "dem_vertical_error_m": 2.0,
    "horizon_el_deg": 0.08,       // that error at the mask's own blocker range
    "edge_timing_s": 1820,        // worst arc-edge tolerance in this response
    "grazing": false,             // true ⇒ at least one crossing is untimeable
    "coverage": 1.0,              // share of the skyline set by terrain inside the DEM
    "penumbra_sun_deg": 0.2665,   // the discs' angular sizes: the partly-lit band
    "penumbra_earth_deg": 0.9705,
    "terrain_modelled": true,     // false outside 80°S: a smooth-sphere skyline
    "notes": [
      "DEM clipped to 50 km around the site; terrain beyond is not modelled.",
      "Shadow edges are resolution-limited: a 20 m post cannot resolve a boulder."
    ]
  },
  "engine_version": "hz-2/vis-2",
  "cache": "hit" | "miss" | "bypass"
}
```

`uncertainty` is never omitted and never null. When a value genuinely cannot be
computed the field carries the reason (`"grazing": true` with
`"edge_timing_s": null`), because invariant 2 says show the word, not a fake
precision.

### 5.2 Endpoints and Contracts

Detailed request/response schemas, parameter options, and payload examples are documented in dedicated reference files:

- Core site and mission endpoints, envelopes, error formats, and rate limits: see [docs/api.md](api.md).
- Mission lifecycle sections (Ready, Launch, Trip, Contact, Return) and async job ref contracts: see [docs/lifecycle-api.md](lifecycle-api.md).

### 5.3 Errors

RFC 9457 problem details, plus a `ui` block the frontend's `ErrorPanel` renders
without a translation layer (it already takes `title`, `detail`, `stillWorks`):
```jsonc
{ "type": "https://polar-window/errors/kernel-missing",
  "title": "Ephemeris unavailable",
  "status": 503, "detail": "de440.bsp is not loaded.",
  "ui": { "still_works": "Horizon masks and terrain are unaffected; Sun and Earth positions are not available.",
          "retryable": true } }
```

---

## 6. The date slider — the interaction the design is actually for

This is N1, and it is the only place where the architecture is genuinely
interesting. A drag produces overlapping, rapidly-superseded requests for
7 sites at once.

**Four mechanisms, in order of how much they buy:**

1. **Server-side quantisation.** `start`/`end` snap to the `step_s` grid before
   anything else happens. Turns a continuous drag into a small set of repeated
   keys. Biggest single win; costs nothing.
2. **Redis cache keyed on the quantised tuple** `(site, start, end, step, engine)`.
   Value is orjson + zstd. TTL 1 h for timelines, 24 h for windows/metrics
   (they are smaller and more reusable). Hit rate on a replayed drag: ~100 %.
3. **Single-flight.** A Redis `SET NX` lock per key; losers wait on the winner
   rather than duplicating a 40 ms computation 7 times. Prevents the stampede
   that otherwise happens when the slider lands on a fresh key with 7 sites
   fetching simultaneously.
4. **Client cancellation.** TanStack Query aborts superseded fetches
   (`AbortSignal` → `httpx`/uvicorn sees the disconnect). Critically the server
   **still finishes and caches** an in-flight computation rather than aborting
   it: the user is dragging *through* that value and will likely come back. An
   aborted computation is wasted work; a completed one warms the cache.

Point 4 is the counter-intuitive one and it is deliberate. Cancellation is a
client-side *bandwidth and render* optimisation, not a server-side *compute*
optimisation.

**Precompute tier.** As built, the worker precomputes masks and one reference
window's four numbers per site (`site_window_metrics`, 900 s step), which answer
`/sites` list summaries. The coarse `visibility_tables` tier was never built:
measured on-demand timelines (p50 12.5 ms cold for 708 h at 900 s) made it
unnecessary. Long spans for the date picker are served by the calendar (§10.6)
at 3600 s on demand, Redis-cached. ADR-1 (amended) argues the resolution choice.

---

## 7. Failure modes

| Failure | Blast radius | Behaviour |
|---|---|---|
| A SPICE kernel is missing | Total for Sun/Earth | `kernels.py` raises at startup with the exact filename, expected SHA and the NAIF URL. `/healthz` 503. The API still starts — so the message is *visible in the UI*, not only in a crashed container's logs. |
| A site outside the DEM | That site only | A candidate site outside the elevation model is refused when its mask is built (`core/horizon.py` raises): its coordinates or the DEM subset are wrong. A mission target outside 80°S gets a smooth-sphere skyline instead, stored with `dem_product = "none (smooth sphere)"`, and every response for it carries `meta.uncertainty.terrain_modelled = false` and a note. Rays that leave the DEM partway lower `coverage`, which the UI states. Never silently a flat horizon presented as terrain. |
| Redis down | Latency only | Cache and single-flight become no-ops behind a `try/except`. `meta.cache = "bypass"`. |
| Postgres down | Total | 503. No fallback; sites and masks live there. |
| Gemini down / slow | Agents only | 20 s timeout → 1 retry → deterministic template summary built from the same tool outputs, `status="degraded"`. Every other endpoint is unaffected. |
| Grounding guard rejects twice | That agent call | `status="guard_rejected"`, the offending numbers listed in `agent_runs.guard_failures`, and the deterministic summary returned in place of the model text. **Never** falls through to rendering the ungrounded text. |
| Worker never ran | Coarse layer | `summary: null`, UI uncertain state. Fine timelines still work — they do not depend on the precompute. |

---

## 8. Scale, and honestly where it stops

Load estimate for the target: a handful of judges and a demo screen. Call it
**10 concurrent users, 30 rps peak during a slider drag**, 20 sites, one year of
coverage.

- Timeline compute: about 10 ms CPU per site-window at 900 s step (ephemeris
  6.6 ms, Sun track 2.0 ms, Earth track 0.7 ms, measured 2026-09-24); 11 ms
  cold and 0.8 ms cached for `/metrics` over HTTP. At 30 rps with a 90 % cache
  hit rate that is well under a tenth of a core.
- Mask build: 45 ms per site with the numba kernel, plus 23 ms to load its fine
  DEM window: the 22 sites in a few seconds, once, offline.
- Storage: masks 22 × 17 KB; no coarse tables (the calendar is computed on
  demand and cached, §10.6); DEM 320 MB; kernels 127 MB; tiles to z5 134 MB.

Everything fits on one laptop-sized node, which is the correct answer for this
build and is stated so that "it scales" is never implied.

**What I would revisit if it grew:** (1) the single SPICE thread becomes the
ceiling at roughly 25 concurrent cold timelines — the fix is N api replicas, not
threads, since kernel state is per-process and read-only; (2) `bytea` arrays
would move to object storage once mask count × resolution outgrows shared
buffers; (3) the coarse table would become a proper time-series store if the
window extended past a few years; (4) tiles would move behind a CDN, at which
point ADR-4's answer flips.

---

## 9. Assumptions

1. The demo window is 2027 (the frontend's `MODEL_EPOCH` is 2027-03-14), so
   kernel coverage must include it — de440 does, comfortably.
2. Candidate-site coordinates are **derived from the DEM** by
   `data/ingest_sites.py` (IAU feature centre as anchor; the most open-skied
   landable post in the top elevation decile of a stated ring or disc).
   CLPS mission targets use the **published** coordinate as-is (§10.4).
   `source_note` records the rule per site; nothing in the product should imply
   metre-level siting.
3. "Earth contact" means **geometric line of sight to Earth's centre above the
   local skyline**. No link budget, no antenna pattern, no DSN scheduling. The
   copy must say "direct-to-Earth geometry", never "comms availability", and the
   `/metrics` field is named `earth_contact_s` for that reason.
4. The frontend's `SURVIVAL_LIMIT_H = 120` stays a client-side, clearly-labelled
   placeholder. The backend returns durations and refuses to return verdicts,
   because a verdict needs a thermal model this system does not have.

---

## 10. The CLPS scope (contract v2, 2026-09-23)

The challenge is **CLPS Lunar Mission Browser**. Everything in §1–§9 answers
"what do Sun, Earth and terrain do at a south-pole site over a window". v2 puts
**CLPS missions** in front of that engine. A mission is the entry point, and the
engine judges its target and its dates. The 15 derived candidate sites become the
alternatives a mission is compared against. Nothing in §1–§9 is removed; v2 is
additive, and every v1 response keeps its shape.

### 10.1 Information architecture

```
/missions  (home)
  ├─ lunar map: global view + south-polar inset over LOLA hillshade
  ├─ programme timeline 2024 →, linked to the map
  └─ filters: payload instrument type · status · provider · region
        │
        ▼
/missions/:id
  ├─ record: provider · lander · task order · dates (+precision) · status · outcome
  ├─ payload manifest, a source on every row, "unconfirmed" where unsourced
  └─ "Sun & Earth at this target"  (the linked site, window = surface window)
        ├─ four numbers + two-clock ring   → /site
        ├─ shift the date: window picker + month strip (calendar, §10.6)
        ├─ compare with nearby candidates  → /compare  (existing, seeded)
        └─ skyline / plan / report         → /skyline /plan /report
```

The existing screens do not change their design. They gain one entry path (from
a mission) and one capability (a movable window).

### 10.2 Requirements added

| # | Requirement | Served by |
|---|---|---|
| F10 | List and filter every CLPS delivery: status, provider, payload instrument type, region, date range, text | `GET /missions` |
| F11 | One mission with payloads, sources, unconfirmed fields, landing ellipse, surface window and linked site | `GET /missions/{id}` |
| F12 | The four numbers at a mission's target over its surface window | `GET /sites/{target}/metrics` (existing) |
| F13 | Sun/Earth fractions and longest gaps per day or month over a span of up to 730 days | `GET /sites/{id}/calendar` |
| F14 | Agents answer mission questions through the same six tools | `get_site`, `search_sites` (extended) |

| # | Target | Why |
|---|---|---|
| N7 | `GET /missions` p95 < 50 ms warm | It is the home screen; the payload filter re-queries on every change. All from Postgres, no compute. |
| N8 | Mission data needs no network at runtime | Offline demo rule. `missions.json` is committed and ingested at seed time; nothing is scraped live (ADR-5). |
| N9 | Calendar ≤ 150 ms cold for 365 days at 3600 s | 8,760 samples ≈ 3× the 708 h/900 s timeline measured at p50 12.5 ms cold. |

### 10.3 Data model

```
┌──────────────────────────────────────────────────────────┐
│ missions                                                 │
├──────────────────────────────────────────────────────────┤
│ id                 text PK   'im-2'                      │
│ name               text      'IM-2'                      │
│ vehicle_name       text?     'Athena'                    │
│ provider           text      'Intuitive Machines'        │
│ lander             text      'Nova-C'                    │
│ task_order         text?     as published                │
│ status             text      enum, below                 │
│ outcome_note       text      sourced prose, may be ''    │
│ region             text      'south_polar'|'nearside'|'farside'|'polar_other'
│ target_name        text?                                  │
│ target             jsonb?    {name, lat_deg, lon_deg (0..360 E),
│                              coordinate_kind: 'actual_landing'|
│                              'planned_target'|'feature_centre',
│                              source_url, feature_id}; null ⇒ not published
│ ellipse            jsonb?    {major_km, minor_km, azimuth_deg}, if published
│ launch             jsonb?    {date, precision: 'minute'|'day'|'month'|
│ landing            jsonb?     'quarter'|'year', as_published: the verbatim
│ end_of_mission     jsonb?     phrase, e.g. 'late 2027'}; null ⇒ unconfirmed
│ planned_surface_days float?                              │
│ sort_at            timestamptz?  landing, else launch: list order and filters
│ site_id            text? FK → sites   null until linked  │
│ sources            jsonb  [{url,title,publisher,accessed}] ≥ 1
│ unconfirmed_fields jsonb  field names with no source     │
│ notes              jsonb  conflicts between sources, kept│
│ data_version       text   sha256 of the missions.json row│
└──────────┬───────────────────────────────────────────────┘
           │ 1:N
┌──────────▼───────────────────────────────────────────────┐
│ mission_payloads                                         │
├──────────────────────────────────────────────────────────┤
│ id            text PK   '<mission>/<slug>'               │
│ mission_id    text FK → missions (ON DELETE CASCADE)     │
│ name          text                                       │
│ acronym       text?                                      │
│ organisation  text?                                      │
│ instrument_types text[]  controlled vocabulary, below    │
│ purpose       text      one sentence, from the source    │
│ source_url    text      required                         │
│ unconfirmed   bool                                       │
└──────────────────────────────────────────────────────────┘
   GIN index on instrument_types (the payload filter)
```

**`status`**: `planned`, `in_transit`, `operating`, `completed`,
`partial_success`, `landing_failed`, `lost_before_landing`, `cancelled`,
`reassigned`. The enum states the category; `outcome_note` carries the nuance,
sourced, so a tipped-over lander that returned data is never flattened to
"success" or "failure".

**`instrument_types`** (controlled vocabulary, assigned by us from each
payload's sourced purpose; the assignment rule is in `docs/data-sources.md`):
`volatiles`, `geology_geophysics`, `heat_flow`, `radiation_space_weather`,
`exosphere_dust`, `imaging`, `landing_navigation`, `communications`,
`laser_retroreflector`, `rover_mobility`, `technology_demo`, `other`.

**`sites`** gains three columns, with defaults that leave the 15 existing rows,
their masks and the golden fixtures untouched:

| Column | Values | Default |
|---|---|---|
| `kind` | `candidate` \| `mission_target` | `candidate` |
| `coordinate_rule` | `derived_open_sky` \| `published` | `derived_open_sky` |
| `terrain_modelled` | bool | `true` |

A mission target site has id `mission-<mission id>` for an `actual_landing` or
`planned_target` coordinate, with `anchor = target`,
`search_kind = 'published'`, zero search radii and zero offset. A
`feature_centre` coordinate (the IAU centre of a named target, used when no
landing point is published) maps to one **shared** site, `feature-<slug>`,
because three missions aiming at "Mons Mouton" have one coordinate and
therefore one skyline. The UI labels it "centre of Mons Mouton, not a landing
point". The precedence rules and the research log are in
`docs/data-sources.md`.

### 10.4 Coordinates and terrain coverage

The LOLA polar products cover **80°S–90°S**. That boundary decides what a
mission's numbers can claim.

| Target | Horizon mask | `terrain_modelled` | What the UI says |
|---|---|---|---|
| lat ≤ −80° and a fine window fetches | Real ray-cast (20 m + 80 m), as for candidates | `true` | Normal states |
| lat ≤ −80°, fine window missing | 80 m regional only, `coverage < 1` | `true` | Partial-coverage uncertainty (existing) |
| lat > −80° (nearside, far side, mid-latitude) | **Curvature-only** mask: 0° on every bearing, `tol = 0`, `dem_product = "none (smooth sphere)"` | `false` | Uncertain state: "Terrain is not modelled outside 80°S; Sun and Earth are computed against a smooth Moon." |
| Feature centre only | As the rows above, by latitude | as above | Plus: "Numbers are for the centre of {feature}; the landing point is not published." |
| No published target | No site | — | "Target not published", no numbers |

A smooth-Moon horizon is not a fabricated number. The Sun and Earth vectors are
still SPICE, the horizon is stated, and the flag travels in
`meta.uncertainty.terrain_modelled` into every response for that site. At
mid-latitudes the Sun climbs high enough that terrain rarely decides it. On the
far side the result is categorical and real: Earth never rises, so Earth contact
is 0 h and the mission needs a relay. The mask is **never** presented as terrain.

Mission coordinates are **published, not derived**. The open-sky search in
`ingest_sites.py` exists to turn a crater name into a landable point. A mission
already has a point, and moving it would change the mission.

### 10.5 Contract v2 endpoints

#### `GET /api/v1/missions`
Query: `status` (repeatable), `provider`, `payload_type` (repeatable, any-of),
`region`, `from`, `to` (landing date), `q`, `limit`, `offset`.
```jsonc
{ "items": [ {
    "id": "im-2", "name": "IM-2", "vehicle_name": "Athena",
    "provider": "…", "lander": "…", "status": "…", "region": "south_polar",
    "target": { "name": "…", "lat_deg": …, "lon_deg": …,
                "coordinate_kind": "actual_landing" } | null,
    "launch":  { "date": "…", "precision": "day" } | null,
    "landing": { "date": "…", "precision": "day" } | null,
    "payload_types": ["volatiles", "…"], "payload_count": 10,
    "site_id": "mission-im-2" | null,
    "terrain_modelled": true | null,
    "summary": { …SiteSummary over the surface window… } | null,
    "unconfirmed_fields": ["ellipse"] } ],
  "total": 12, "meta": {...} }
```
Values are elided on purpose; `data/missions.json` is the only place mission
facts live.

#### `GET /api/v1/missions/{id}`
The list item, plus `task_order`, `outcome_note`, `end_of_mission`,
`planned_surface_days`, `payloads[]`, `sources[]`,
`ellipse_ring: [[lat, lon], …] | null` (64 vertices, built by
`core/projections.ellipse_ring`, pure) and:
```jsonc
"surface_window": { "start": "…", "end": "…",
                    "basis": "published" | "planned" | "assumed" | "none",
                    "note": "…" }
```

| `basis` | Rule |
|---|---|
| `published` | Landing and end-of-mission are both sourced to the day or better. |
| `planned` | Landing is sourced to the day; the planned surface duration is sourced. |
| `assumed` | Landing is sourced to the day; the duration is not, so one lunar daylight period (14.77 d) is used and **named**. |
| `none` | Landing is only known to the month or coarser. There is no single window; the UI shows the calendar across the uncertainty span. |

#### `GET /api/v1/sites/{id}/calendar`
Query: `start`, `end` (≤ 730 days), `bucket` = `day` | `month`.
```jsonc
{ "site_id": "…", "start": "…", "end": "…", "bucket": "month", "step_s": 3600,
  "items": [ { "start": "…", "end": "…",
               "sun_fraction_up": 0.71, "earth_fraction_up": 0.55,
               "longest_dark_s": 410400, "longest_dark_open": true,
               "longest_blackout_s": 864000, "longest_blackout_open": false } ],
  "meta": {...} }
```
One timeline over the whole span, then runs **clipped at bucket edges**. A run
that touches a bucket edge is reported `*_open: true`, because the bucket, not
the terrain, ended it. That is the same censoring rule as the window edge in v1.

#### `GET /api/v1/sites` (changed)
Adds `kind` (default `candidate`), so the Map's candidate list is unchanged. A
mission target is reached through its mission or by `kind=mission_target`.

#### `POST /api/v1/compare` (changed)
Ranking becomes **censoring-aware and uncertainty-aware** (§10.7). Each item
gains `censored: bool` and `tied_with: [site_id]`, and `rank` becomes nullable
(`null` = cannot be ranked against at least one other item). `ties` stays.

### 10.6 The calendar and the date picker

The window has been fixed at 2027-03-14 + 708 h since M5. v2 makes it movable:
a start date and a duration in the UI, plus a month strip from the calendar. A
mission sets it to its surface window.

The calendar is computed **on demand** at 3600 s and cached in Redis under the
quantised key, not precomputed into `visibility_tables`. The arithmetic: 365
days is 8,760 samples, about 3× the 2,835 samples the timeline already serves
at p50 12.5 ms cold. A precomputed table would cost a migration, a worker stage
and a staleness rule, to save roughly 40 ms on a request the user makes once per
site. ADR-1's amendment records this and the measured figure.

The worker warms each linked mission's surface window, so a mission's four
numbers are a cache hit on first view.

### 10.7 Ranking a censored value

A `longest_dark_s` with `longest_dark_open = true` is a **lower bound**: the
window ended the night, not the terrain, so the true value is in `[v, ∞)`. A
measured value with arc-edge uncertainty `u` is in `[v − u, v + u]`. For a
"smaller is better" metric (mirror it for "larger is better"):

```
hi(X) = ∞        if X censored,  else v_X + u_X
lo(X) = v_X      if X censored,  else v_X − u_X
A beats B  ⇔  hi(A) < lo(B)
```

`u` is the item's own `edge_timing_s`, not the fixed 1 h tie tolerance the v1
ranking used (D21). "Beats" is a strict partial order, so each item gets a
**rank range** instead of a single number:

```
rank_min(X) = 1 + |{Y : Y beats X}|
rank_max(X) = n − |{Y : X beats Y}|
```

- `rank_min == rank_max` → `rank` is that number.
- The range is wider only because of overlapping **measured** values → a tie:
  `rank = rank_min`, `tied_with` lists the others (v1's "joint first").
- The range is wider because a **censored** value is involved → `rank = null`,
  `rank_range = [min, max]`. The UI says "cut short, can't rank" and never
  "best".

Worked case, the one the review reproduced (D20): Connecting Ridge measured
122 ± 17 h, de Gerlache rim ≥ 112 h (censored), Malapert ≥ 288 h (censored).
Connecting Ridge beats Malapert (139 < 288) and nothing beats it, so it is
ranked 1–2. De Gerlache rim beats nothing and nothing beats it, so it is ranked
1–3. Malapert is ranked 2–3. v1 called de Gerlache rim "best"; v2 declines,
which is the correct answer. It is a pure function in `core/metrics.py`, pinned
by hypothesis properties: a censored value never beats anything; the ranking
is invariant to input order; `rank_min ≤ rank_max`; and removing an item never
widens anyone's range.

### 10.8 Agents over missions

Still **exactly six tools**. Missions enter through the two that already take a
site:

- `get_site` returns `missions: [{id, name, provider, status, landing_date,
  landing_precision, payload_types}]` for the site. No masses, no costs: the
  numeric grounding pool (`guards.py`) stays small (D23).
- `search_sites` gains the filters `kind`, `has_mission`, `mission_status`,
  `provider` and `payload_type`. Rows stay trimmed to id, name, latitude, the
  four numbers and their `*_open` flags (C3).

So "which south-polar CLPS targets carry volatiles instruments, and how long is
their longest night?" is `search_sites(kind=mission_target,
payload_type=volatiles)` and then `get_metrics` per result. The agent never
touches a mission table directly, and the import-linter contract that agents
reach the domain only through `tools.py` still holds.

ISO dates in tool output (`2025-03-06`) must count as grounded tokens, or the
guard would reject every sentence that dates a mission. This is a guard change
with its own test.

### 10.9 Failure modes added

| Failure | Blast radius | Behaviour |
|---|---|---|
| A `missions.json` record has no source, an unknown enum, or bad coordinates | Seed time only | `ingest_missions.py` fails with the record id and field. It never loads a partial file. |
| A mission target has no site yet (ingest or precompute pending) | That mission's numbers | `site_id: null`, `summary: null`, UI uncertain state. The mission record still renders. |
| Target outside 80°S | That mission's terrain claim | `terrain_modelled: false` everywhere downstream (§10.4). |
| Landing date coarser than a day | That mission's window | `surface_window.basis = "none"`; the calendar is shown instead of one set of four numbers. |

### 10.10 Trade-offs, and what to revisit

- **Curated JSON over a live feed** (ADR-5). It is correct for an offline
  demo and for a table where every row needs a human-checked source. It goes
  stale; the 28 Oct 2026 checkpoint and `accessed` dates make staleness visible
  rather than silent.
- **One site per mission** doubles the site count at most (15 → ~30). Mask
  builds are ~130 ms each; the binding cost is the 6 MB fine DEM window per
  polar target. Both are fine at this scale (§8).
- **The payload classification is ours.** `instrument_types` is a judgement
  from each payload's sourced purpose, not a NASA taxonomy. The docs say so,
  and each payload row links its source so the judgement is checkable.
- Revisit if the scope grows beyond CLPS: a `programmes` table
  (CLPS, Artemis, international) and a global DEM tier.

---

## 11. The mission lifecycle (2026-09-27/28; tracks T1–T4, E, H, I)

The product now follows a CLPS delivery end to end: **Ready · Launch · Trip ·
Surface · Contact · Return**, plus space weather. The contract is
`docs/lifecycle-api.md`; the decisions are ADR-8 (live feeds), ADR-10
(catalogues), ADR-11 (trajectory engine), ADR-12 (heavy compute), ADR-13 (engine
versions), ADR-14 (weather rules), ADR-15 (radiation), ADR-16 (communications),
ADR-17 (project manager data), ADR-18 (kernel pinning).

### 11.1 Processes

```
 browser ──▶ api (FastAPI) ──────────────┐  reads stored answers and snapshots;
                │  202 + JobRef          │  queues a job when an answer is missing
                ▼                        ▼
 compute worker(s) ──▶ postgres ◀── feeds worker ──▶ NOAA, NASA, LL2 (outbound only)
 trip · contact ·      jobs, assessments,  fetch, parse, snapshot,
 launch jobs           assessment_inputs,  breaker, staleness budget
                       feed_snapshots/health/limits,
                       audit_log, readiness_items, parts, risks, ...
```

- **api** stays read-mostly. A heavy answer (trip, contact, launch calendar) is a
  job: its key is a hash of the kind, the engine versions it depends on (its
  *closure*) and its parameters; a stored answer with that key is served at once,
  otherwise a job is queued and the page polls `GET /jobs/{id}` (ADR-12).
- **compute worker** (`app/workers/compute.py`, one job at a time per process)
  runs the handlers in `app/workers/handlers/`. Each answer records its inputs
  (`assessment_inputs`: kernels, catalogues, feed snapshots), so it is reused
  until one of them or an engine version changes.
- **feeds worker** (`app/feeds/`) is the only code that reaches the network
  (import contract). Each product is a snapshot with its fetch time; a failing
  provider opens its breaker after five runs; the API reads the newest good
  snapshot and, past its budget, gives the reason instead of the number.

### 11.2 Sections and the code behind them

| Section | Endpoint | Engine (`app/core`) | Inputs |
|---|---|---|---|
| Ready | `/missions/{id}/ready` (+ items, parts, risks, lessons) | `readiness` | the team's entries (audited), `lessons`, `risk_scales` |
| Launch | `/missions/{id}/launch` | `launchwin`, `transfer`, `phasing`, `landing_windows`, `flown` | pads, vehicles, departure azimuth solver, NASA's reconstructions |
| Launch weather | `/missions/{id}/launch/weather` | `weather_rules`, `verification` | `weather_rules` (verbatim), GEFS, HRRR, NWS, GLM, LL2, GEFSv12 reforecast, ASOS/IEM observations |
| Trip | `/missions/{id}/trip` (+ export) | `propagate`, `forces`, `gravity`, `eclipse`, `lincov`, `belts`, `gcr` | NAIF SPKs, EGM2008, GRGM1200A, DONKI, OMNI, Oulu |
| Contact | `/missions/{id}/contact` (+ plan, bookings, rover, viewshed tiles, relays) | `contact`, `network`, `visibility`, `relay`, `rover`, `viewshed` | DSN station kernels, `ground_stations`, `relays`, JPL Horizons orbiters, 20 m LOLA DEM |
| Return | `/missions/{id}/return` | `entry`, `atmosphere` (capsule model check) | `recovery_zones`, `vehicles`, NRLMSIS 2.1 (OMNI2 indices), GFS-Wave |
| Space weather | `/space-weather` | none | SWPC, DONKI |

Every value is a `Quantity` with its provenance and ± or the reason it has none
(ADR-9); no section returns a verdict, score or overall chance (invariant 9).

Key lifecycle enhancements:
- **Capsule entry atmosphere:** The default atmosphere for the capsule entry
  model is NRLMSIS 2.1, chosen from TIMED/SABER satellite radiometry and Table
  Mountain lidar profiles for 2023-09-24 at 30 to 70 km altitude. It brings the
  modelled OSIRIS-REx sample return capsule touchdown to within 6.6 km of the
  recovery site (3.9 to 9.3 km across the drag coefficient range), meeting the
  10 km requirement. The profiles are only partly independent of the models, and
  four cautions apply (see `docs/validation.md`). The selection rule was written
  after both landing results were known. NRLMSIS 2.x was fitted to SABER
  temperatures for 2002 to 2016. The lidar density is scaled to MERRA-2. The
  producer marks the SABER files "Unvalidated". NRLMSIS 2.1 has the lower density
  difference in every cut of the profiles.
- **Published injection accuracies and correction budget:** Falcon 9, Vulcan
  Centaur and New Glenn carry the injection accuracies printed in their user
  guides. Falcon Heavy has none published, so its budget stays assumed. The
  Falcon 9 guide (Rev 2, 21 October 2015, Table 3-2, page 16) gives 3-sigma
  accuracies for a geosynchronous transfer orbit: apogee ±500 km, perigee
  ±10 km, inclination ±0.1°. It has no trans-lunar row, so the errors at
  departure are worked out from that GTO row. Linear covariance and Monte Carlo
  budgets agree within 7.1%, meeting the 10% plan tolerance.
- **Planned relays and active orbiters (ADR-16):** planned relays (Lunar Pathfinder,
  Altus-1) sweep 36 x 36 nodes and phases, presenting contact as minimum to maximum
  ranges with launch status beside them; the catalogue is exposed via `GET /relays`
  and comparisons run on demand (`?relay=`). Active orbiters from JPL Horizons are
  rendered purely as geometric line-of-sight passes over the landing spot.
- **Rover line of sight and viewshed tiles:** rover-to-lander direct visibility
  and Fresnel radio clearance are evaluated against 20 m LOLA elevation windows,
  served as zoom 12 raster map tiles (`GET /tiles/viewshed/{answer}/{z}/{x}/{y}.png`)
  with clear, blocked, or uncertain states distinguished by tone and pattern.
- **Departure azimuth and launch windows:** climb directions are solved from the
  pad-to-TLI orbital plane (Falcon 9 empirical direct departure 87.7°) within pad
  ground azimuth constraints, providing published launch periods alongside instantaneous
  liftoff opportunities.
- **Multi-year weather verification:** launch weather rules are scored against
  decades of station observations (Cape Canaveral KXMR and Vandenberg KVBG) and
  GEFSv12 reforecasts (2000-2019) with Brier and CRPS skills. High-resolution HRRR
  archive runs are read directly via S3 byte ranges. Deterministic forecast
  disagreements are surfaced with explicit notes.
- **Trip force models and Earth gravity:** Earth gravity integrates EGM2008
  spherical harmonics up to degree and order 8 with true Earth spin kinematics in
  ITRF93, resolving near-Earth tesseral residuals. Radiation belts select the magnetic
  field model appropriate to each environment (GSFC 12/66 for AP8/AE8, IGRF for modern
  baselines).
- **Compute queue scheduling:** compute jobs are prioritized cheapest-first
  (contact -> launch -> trip) to eliminate head-of-line blocking for short interactive
  requests (`make load-compute`).

### 11.3 Agents over the sections

The agents reach the lifecycle through four read-only tools (ADR-6 and ADR-3,
amended 2026-09-28): `list_missions`, `get_mission_sections`,
`get_mission_section` and `get_space_weather`. A section is cut to at most 200
numbers by `app/agents/compact.py` (values keep their ±; plot series and long
list tails are left out and named); the tools run inside
`job_service.read_only()`, so a question never queues a computation. The
grounding guard also rejects verdict words.

**The guard has a known limit.** A whole number in an answer counts as grounded
when some tool value matches it within ±0.5 under any of five conversions (none,
seconds to hours, seconds to days, fraction to per cent, degrees to arcminutes).
The more numbers the tools return, the likelier a match by coincidence. Making
the rule stricter would reject honest rounding ("80 %" for 0.7983) and push the
model toward raw seconds, so it stays. Two things contain it. Tools return
finished numbers, not sample arrays, and at most 200 per section. And the
provenance of each claim names the field it matched, so a coincidental match can
be seen. Revisit the rule if an agent gains a tool that returns a large array.

### 11.4 Failure modes added

| Failure | What a person sees | Tested in |
|---|---|---|
| a feed down, slow or malformed | its numbers missing with "the last attempt to fetch it failed"; the section's other feeds and every other section unchanged; `/healthz` degraded, never down | `test_chaos.py`, `test_feeds.py` |
| a feed stale | its numbers replaced by "N old, past its limit"; `meta.stale` true; `/healthz` unchanged | same |
| no compute worker | the section says it is waiting and, after a while, that the worker is not running | `test_job_ref.py` |
| a job fails | its message is the answer until the inputs change; a signed-in retry | `test_jobs.py`, `test_job_ref.py` |
| a catalogue value unpublished | absent with its reason, never filled | `test_catalogues.py` |
| request body over 64 KB | 413 Payload Too Large | `test_request_limits.py` |
| rate limit exceeded | 429 Too Many Requests with Retry-After header | `test_request_limits.py` |
| queue backlog over 200 jobs | 503 Service Unavailable ("Too many answers are being worked out") | `test_jobs.py` |

---

## 12. Security

This is a demo host serving public data. These are the checks that were made,
and the rules that keep them true.

| Area | State |
|---|---|
| SQL | No user input is interpolated into SQL. Raw `text()` statements use bound parameters or fixed strings, and search terms are bound parameters. |
| File paths | A tile path is built from a layer checked against a fixed tuple and three bounded integers. No user string reaches the file system. |
| Agent tools | Arguments are validated by pydantic models that forbid extra fields before anything runs. `'; DROP TABLE sites;--` as a site id fails the model and is recorded as a tool error (tested). Every tool is read-only, and an import contract stops any agent module except `tools.py` from importing a service or repository. |
| Secrets | The model key, the NASA and Earthdata keys and the token-signing secret come from the environment through typed settings (`app/config.py`). A feed snapshot never stores a key in its URL (ADR-8). |
| Sessions | HS256 JWT. The signature, issuer, expiry and required claims are checked. A token with another algorithm (such as `none`) or another secret is refused (unit tests). The client sends the token only on calls that need it, so reads carry no credential and cause no CORS preflight. It travels in the `Authorization` header, not a cookie, so a cross-site request carries none. |
| Settings changes | Model lists are checked against the configured models (no free-text names). Clearing the cache deletes only `pw:*` keys, never the whole Redis database. A destructive action needs a second, explicit step in the UI. |
| Bounds | Window at most 730 days, step 300 to 7,200 s, compare at most 8 sites, agents at most 4 rounds, 8 tool calls and 20 s. Bodies over 64 KB are refused (413). |
| Container | Runs as a non-root user. |

Reading is public by design. A session is needed for the two things that are
not reads: the AI panels, which spend model quota, and every change to the
project. The one-click sign-in (`POST /auth/demo`) is a stated demo decision
(ADR-7), switched off with `PW_DEMO_SIGN_IN=false`, and not a claim of access
control. The checks on every write route are in `docs/test-plan.md`.
