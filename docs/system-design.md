# POLAR WINDOW — System Design

Status: accepted for the hackathon build (M1–M8).
Author: backend/architecture pass, 2026-09-18.
Scope: everything behind `frontend/`. The frontend's visual design is fixed and
out of scope; its *data source* is what changes.

---

## 0. What already exists, and what that constrains

`frontend/` is a complete, working React 19 + Vite + Tailwind v4 application with
its own TypeScript geometry engine in `frontend/src/lib/geometry/`. It already:

- ray-casts a 360-bearing horizon mask against a **synthetic** height field,
- projects Sun/Earth sub-points into a local ENU frame with a **mean-element**
  analytic ephemeris,
- refines every skyline crossing by bisection and attaches a timing tolerance,
- derives the four key numbers and the compound (no-Sun ∧ no-link) events,
- runs the whole thing in a Web Worker and streams per-site results to a
  zustand store.

That is not a mockup to be replaced. It is a **reference implementation of the
contract**, and it tells us three things that shape this design:

1. **The DTO shape is already decided.** `SiteMetrics`, `BodyResult`, `Arc`,
   `TrackSample`, `HorizonMask` in `frontend/src/lib/types.ts` are what the
   components consume. The backend's response schemas mirror them 1:1 (snake_case
   on the wire, camelCase after a thin adapter). Any other choice means rewriting
   components, which the brief forbids.
2. **Only two functions are actually wrong.** `terrain.heightAt()` (synthetic,
   should be LOLA) and `ephemeris.subSolarPoint/subEarthPoint()` (mean-element,
   should be SPICE). Everything downstream of them — mask, track, arcs, metrics —
   is correct in structure. The Python `core/` is a port of that structure with
   the two inputs made real, which also gives us a free cross-check: the two
   implementations must agree on synthetic inputs.
3. **The client already has a compute-progress state machine**
   (`idle|running|ready|error`, `done/total`, per-site streaming). Replacing a
   Worker with HTTP must preserve that, or the loading UI degrades. This drives
   the per-site-parallel fetch design in §6 rather than one fat `/compare` call.

### The invariant that outranks the others

`CLAUDE.md` invariant 1: *no hardcoded metric; every number on screen is derived*.
The backend inherits it as: **no endpoint returns a number it did not compute
from an ephemeris and a height field, and every response states which ones those
were.** That is why `meta.uncertainty` is mandatory rather than decorative, and
why the agent layer's grounding guard (§8) is the highest-risk component in the
system.

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

### Non-functional

| # | Target | Why this number |
|---|---|---|
| N1 | Date-slider p95 **< 150 ms** warm, < 600 ms cold | The slider fires on drag. Above ~150 ms the terminator sweep (M1, 708 h in 14 s) visibly stutters and the product's core claim — "move the slider and the numbers genuinely change" — stops feeling true. |
| N2 | Horizon mask build **< 90 s** per site offline | 1440 rays × ~600 samples. Off the request path entirely, so this is a seeding budget, not a latency budget. |
| N3 | Cold start **< 20 s** including kernel furnsh | Judges restart things. de440 is ~114 MB; it must be baked into the image layer, not downloaded at boot. |
| N4 | Agent p95 **< 20 s**, hard timeout 20 s, 1 retry, then deterministic fallback | A demo that hangs on an LLM call is a failed demo. The fallback is non-negotiable. |
| N5 | Correctness: golden fixtures stable to **±0.05° elevation, ±0.02 h arc edges** | Tighter than the DEM's own contribution (±2 m at 1.4 km ⇒ ±0.08°), so the test catches refactor drift without failing on float noise. |
| N6 | Availability: single-node, no HA | It is a hackathon. Documented explicitly so nobody mistakes it for a production posture. |

### Constraints

- ~One engineer, a hackathon time budget. Every "proper" choice that costs a day
  and buys robustness nobody will observe is the wrong choice; this is stated
  once here and then applied consistently in the ADRs.
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
│ engine_version    text      'hz-1'                 │
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
│ dem_coverage      text      'full' | 'partial' | 'synthetic'
│ computed_at       timestamptz                      │
│ compute_ms        float                            │
└────────────────────────────────────────────────────┘
   UNIQUE (site_id, engine_version, azimuth_count)

┌────────────────────────────────────────────────────┐
│ visibility_tables    — the COARSE precomputed layer│
├────────────────────────────────────────────────────┤
│ id            uuid PK                              │
│ site_id       text FK                              │
│ body          text   'sun' | 'earth'               │
│ engine_version text                                │
│ mask_id       uuid FK → horizon_masks              │
│ epoch_start   timestamptz    covers the demo year  │
│ epoch_end     timestamptz                          │
│ step_s        int            3600 (1 h)            │
│ az_deg        bytea  float32[n]                    │
│ el_deg        bytea  float32[n]                    │
│ margin_deg    bytea  float32[n]   el − mask(az)    │
│ computed_at   timestamptz                          │
└────────────────────────────────────────────────────┘
   UNIQUE (site_id, body, engine_version, step_s, epoch_start)

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
│ model          text   'gemini-3.8-flash'           │
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
    "penumbra_deg": 0.26,
    "notes": [
      "DEM clipped to 50 km around the site; terrain beyond is not modelled.",
      "Shadow edges are resolution-limited: a 20 m post cannot resolve a boulder."
    ]
  },
  "engine_version": "hz-1/vis-1",
  "cache": "hit" | "miss" | "bypass"
}
```

`uncertainty` is never omitted and never null. When a value genuinely cannot be
computed the field carries the reason (`"grazing": true` with
`"edge_timing_s": null`), because invariant 2 says show the word, not a fake
precision.

### 5.2 Endpoints

#### `GET /api/v1/sites`
Query: `q` (name/region substring), `region`, `lat_min`, `lat_max`,
`min_sun_fraction`, `max_longest_dark_s`, `limit`, `offset`.
The metric filters are served from `site_window_metrics` against the **default
reference window** and say so in `meta`; they are a coarse pre-filter, not an
answer.

```jsonc
{ "items": [ { "id","code","name","lat_deg","lon_deg","elev_m","note",
               "region","source","source_url",
               "summary": { "sun_fraction_up","longest_dark_s",
                            "earth_fraction_up","longest_blackout_s",
                            "reference_window": {"start","end"} } | null } ],
  "total": 18, "meta": {...} }
```
`summary` is `null` — not zeroed — when the site has not been precomputed. The
UI's uncertain state exists for exactly this.

#### `GET /api/v1/sites/{id}`
Adds `horizon_summary` (`max_el_deg`, `max_el_bearing_deg`, `mean_el_deg`,
`dem_coverage`) and the full provenance block.

#### `GET /api/v1/sites/{id}/horizon`
Query: `step_deg` (0.25 | 0.5 | 1.0, default 1.0 — the frontend draws 360 points).
```jsonc
{ "site_id": "...", "azimuth_step_deg": 1.0, "azimuth_count": 360,
  "el_deg": [ ... ], "range_m": [ ... ], "tol_deg": [ ... ],
  "max_el_deg": 5.12, "max_el_bearing_deg": 309.0, "meta": {...} }
```
Downsampling 1440 → 360 takes the **maximum** over each group of 4, never the
mean. A skyline is an upper envelope; averaging it invents sky where a ridge is.

#### `GET /api/v1/sites/{id}/timeline`
Query: `start`, `end`, `step_s` (300…7200, default 900), `bodies` (default both).
This is the date-slider endpoint and the one N1 is about.
```jsonc
{ "site_id": "...", "start": "...", "end": "...", "step_s": 900,
  "t": [ 0, 900, 1800, ... ],            // seconds from `start`, int32
  "sun":   { "az_deg": [...], "el_deg": [...], "mask_el_deg": [...],
             "margin_deg": [...], "state": [2,2,1,0,...] },   // 2 lit 1 penumbral 0 dark
  "earth": { ... },
  "meta": {...} }
```
Parallel arrays, not an array of objects: 2,835 samples × 2 bodies × 5 fields is
~1.1 MB as objects and ~230 KB as arrays, before compression.

#### `GET /api/v1/sites/{id}/windows`
Derived intervals. This is what `Arc` becomes.
```jsonc
{ "site_id","start","end",
  "sun":   { "arcs": [ { "up": true, "start","end","duration_s",
                         "tolerance_s", "grazing": false,
                         "blocked_by_bearing_deg": null,
                         "blocked_by_el_deg": null } ],
             "up_s","down_s","fraction_up",
             "longest_down_s","longest_down_tolerance_s" },
  "earth": { ... },
  "compound": [ { "start","end","duration_s" } ],
  "worst_compound_s": 41400,
  "meta": {...} }
```

#### `GET /api/v1/sites/{id}/metrics`
The four numbers, and nothing that dilutes them.
```jsonc
{ "site_id","start","end",
  "sunlit_s": 204120, "earth_contact_s": 89280,
  "longest_dark_s": 230400, "longest_blackout_s": 928800,
  "sun_fraction_up": 0.80, "earth_fraction_up": 0.35,
  "worst_compound_s": 41400,
  "autonomy": { "required_s": 49680, "survival_needed_s": 230400,
                "compound_inside_dark": true },
  "meta": {...} }
```
Deliberately **no composite score.** `CLAUDE.md` forbids it and the reason is
sound: a score hides which corner was given up, and the trade is the product.

#### `POST /api/v1/compare`
```jsonc
// request
{ "site_ids": ["a","b","c"], "start": "...", "end": "...",
  "rank_by": "longest_dark", "step_s": 900 }
// response
{ "window": {...}, "rank_by": "longest_dark",
  "items": [ { "site_id","rank","metrics": {...},
               "delta_vs_best": { "sunlit_s": -12600, ... } } ],
  "ties": [["d","e"]],          // explicit, because ranking near-equal sites is a lie
  "meta": {...} }
```
Max 8 site_ids. Computed by fanning out to the same service `GET /metrics` uses,
so `/compare` can never disagree with the per-site endpoint.

#### `GET /api/v1/tiles/{layer}/{z}/{x}/{y}.png`
`layer ∈ {hillshade, illumination, psr}`. See ADR-4.

#### `POST /api/v1/agents/{explain|advise|brief|ask}`
Each returns its agent's pydantic contract plus a shared envelope:
```jsonc
{ "status": "ok" | "insufficient_data" | "degraded",
  "reason": "…",                  // required when not ok
  "result": { ...agent-specific... } | null,
  "provenance": [ { "claim": "80 % sunlit", "value": 0.80,
                    "tool": "get_metrics", "call_seq": 1,
                    "field": "sun_fraction_up" } ],
  "run_id": "uuid",               // joins to agent_runs for the demo log
  "meta": {...} }
```
`provenance` is not optional and not cosmetic. It is the artifact the grounding
guard produces, and the demo shows it.

#### `GET /healthz`
```jsonc
{ "status": "ok"|"degraded", "kernels": { "loaded": true, "count": 5,
  "missing": [], "furnsh_ms": 812 }, "db": "ok", "redis": "ok",
  "dem": { "present": true, "product": "…", "coverage": "partial" },
  "engine_version": "hz-1/vis-1" }
```
Returns **200 when degraded** and 503 only when SPICE is unloaded, because a
missing DEM still lets every ephemeris endpoint work and the UI has a state for
partial data. Failing the whole liveness check for a partial capability would
take the demo down for a condition the UI already handles.

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

**Precompute tier.** The coarse `visibility_tables` (1 h step, whole demo year)
answer `/sites` list summaries and `/compare` ranking instantly, with
`meta.resolution.time_step_s = 3600` stated. Fine timelines (900 s or better)
are computed on demand. ADR-1 argues the resolution choice.

---

## 7. Failure modes

| Failure | Blast radius | Behaviour |
|---|---|---|
| A SPICE kernel is missing | Total for Sun/Earth | `kernels.py` raises at startup with the exact filename, expected SHA and the NAIF URL. `/healthz` 503. The API still starts — so the message is *visible in the UI*, not only in a crashed container's logs. |
| DEM tile missing for a site | That site only | Mask falls back to a spherical horizon, `dem_coverage="none"`, `meta.uncertainty.notes` says so, and the site is flagged `degraded` in `/sites`. Never silently a flat horizon presented as terrain. |
| Redis down | Latency only | Cache and single-flight become no-ops behind a `try/except`. `meta.cache = "bypass"`. |
| Postgres down | Total | 503. No fallback; sites and masks live there. |
| Gemini down / slow | Agents only | 20 s timeout → 1 retry → deterministic template summary built from the same tool outputs, `status="degraded"`. Every other endpoint is unaffected. |
| Grounding guard rejects twice | That agent call | `status="insufficient_data"` with the offending numbers listed. **Never** falls through to rendering the ungrounded text. |
| Worker never ran | Coarse layer | `summary: null`, UI uncertain state. Fine timelines still work — they do not depend on the precompute. |

---

## 8. Scale, and honestly where it stops

Load estimate for the target: a handful of judges and a demo screen. Call it
**10 concurrent users, 30 rps peak during a slider drag**, 20 sites, one year of
coverage.

- Timeline compute: ~40 ms CPU per site-window at 900 s step (one vectorised
  `spkpos` + numpy). At 30 rps with a 90 % cache hit rate that is ~0.12 cores.
- Mask build: 20 sites × ~60 s = 20 min, once, offline.
- Storage: masks 20 × 17 KB; coarse tables 20 × 2 bodies × 8,766 h × 12 B ≈ 4 MB;
  DEM subset ~2 GB; kernels ~130 MB.

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
2. Selenographic coordinates in `sites.py` are centre-of-feature, not a surveyed
   landing ellipse. `source_note` records this per site; nothing in the product
   should imply metre-level siting.
3. "Earth contact" means **geometric line of sight to Earth's centre above the
   local skyline**. No link budget, no antenna pattern, no DSN scheduling. The
   copy must say "direct-to-Earth geometry", never "comms availability", and the
   `/metrics` field is named `earth_contact_s` for that reason.
4. The frontend's `SURVIVAL_LIMIT_H = 120` stays a client-side, clearly-labelled
   placeholder. The backend returns durations and refuses to return verdicts,
   because a verdict needs a thermal model this system does not have.
