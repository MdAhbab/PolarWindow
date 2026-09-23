# ADR-1: Precompute horizon masks; compute timelines on demand

**Status:** Accepted (amended 2026-09-23, see the end)
**Date:** 2026-09-18
**Deciders:** backend lead (sole engineer on this build)
**Relates to:** N1 (slider p95 < 150 ms), N2 (mask build budget), §6 of `docs/system-design.md`

## Context

Two computations sit behind every screen, and they differ by four orders of
magnitude in cost.

**The horizon mask.** 1440 azimuth rays × ~600 distance samples each, every
sample a bilinear read into a LOLA GeoTIFF. Roughly 900k terrain reads per site.
Measured on the synthetic reference implementation in `frontend/src/lib/geometry/mask.ts`
the equivalent 360-ray version takes 30–50 ms in JS against an analytic height
function; against a real raster with I/O and 4× the rays it is tens of seconds.
It depends on **nothing but the site** — not the date, not the window.

**The visibility timeline.** One vectorised `spkpos` call for the whole window
plus numpy arithmetic. ~40 ms for 2,835 samples × 2 bodies. It depends on the
site *and* the window, and the window is exactly what the user drags.

The interaction that defines the product is the date slider, and the frontend's
motion spec (M1: 708 h swept in 14 s, linear, never eased) means a request lands
roughly every 200 ms during playback across 7 sites. If a request costs 30 s,
there is no product.

The question is not *whether* to precompute the mask — that is forced. It is
**how much more than the mask** to precompute, and at what resolution.

## Decision

Three tiers.

**Tier 1 — precomputed, per site, offline (worker).**
The horizon mask at **0.25° azimuth resolution** (1440 rays) out to
**50 km**, with variable step (5 m near, coarsening to 250 m far). Stored as
three float32 arrays in `horizon_masks`. Built once per (site, engine_version).
Never on a request path.

**Tier 2 — precomputed, coarse, offline (worker).**
A **1-hour-step** visibility table per (site, body) covering the whole demo year:
az, el and margin as float32 arrays in `visibility_tables`, plus the derived
four-numbers in `site_window_metrics` for a default reference window. This is
what `GET /sites` summaries and the initial `/compare` ranking read. ~8,766
samples × 2 bodies × 20 sites × 12 B ≈ 4 MB total.

**Tier 3 — on demand, cached (api).**
Timelines and windows at **900 s (15 min)** default step, 300 s floor. Computed
per request from the Tier-1 mask plus a live `spkpos` call, Redis-cached on the
quantised key, single-flighted.

### The two resolution numbers, justified

**0.25° azimuth (1440 rays).** The brief specifies it and it survives scrutiny
for a concrete reason. The blocking features that matter here are close: site A's
night is caused by one ridge at 1.4 km range, 1,150 m wide across the line of
sight. That ridge subtends `2·atan(575/1400) ≈ 45°` — enormous. But the *edges*
of it are where the arc timing comes from, and near the pole the Sun's azimuth
sweeps at 360°/708 h ≈ **0.51 °/h**. So one azimuth bin of 0.25° is **29 minutes
of Sun motion**. At 1.0° resolution it would be ~2 hours — coarser than the arc
edges we claim to resolve by bisection, which would make the bisection
theatre. 0.25° puts the mask's angular quantisation (29 min) just below the
timing tolerance the DEM error already implies (±2 m at 1.4 km ⇒ 0.08°, and at
the ridge's crossing rate that is ~10–30 min). The two error sources are then
the same order, which is the right place to stop: refining either one alone buys
nothing.

Cost check: 1440 rays at ~60 s per site × 20 sites = 20 minutes of offline
compute, run once, parallel across worker processes. Acceptable.

**900 s time step for Tier 3.** Over a 708 h window that is 2,835 samples, which
matches the frontend's existing `TRACK_STEP_H = 0.25` exactly — deliberate, so
the Python and TypeScript engines can be diffed sample-for-sample during the
port. At 0.51 °/h azimuth rate, 900 s is 0.13° of Sun motion, i.e. **half an
azimuth bin**: fine enough that no crossing is ever skipped between samples, so
every sign change is bracketed and then bisected to ~1 s. Halving it to 450 s
doubles payload and compute to resolve nothing the bisection does not already
resolve.

**3600 s for Tier 2.** 0.51 °/h × 1 h = 0.51°, i.e. two azimuth bins. That *can*
skip a narrow blocker, and that is accepted — Tier 2 exists to rank and to
filter, never to answer. Every response built from it reports
`meta.resolution.time_step_s = 3600` and the UI shows the coarse badge. It is a
different claim, labelled as one.

## Options Considered

### Option A: Precompute everything — masks and fine timelines for a fixed year

| Dimension | Assessment |
|-----------|------------|
| Complexity | Medium (a big batch job, plus cache-invalidation on engine bumps) |
| Cost | 20 sites × 2 bodies × 8,766 h × 4 samples/h × 20 B ≈ **28 GB** |
| Latency | Excellent — every read is a slice |
| Flexibility | **Poor** — the window is fixed; arbitrary `start`/`end`/`step` die |

**Pros:** trivially fast; no SPICE on the request path at all.
**Cons:** 28 GB is not shippable, and it forecloses the arbitrary-window API the
frontend's slider and the `/compare` endpoint both need. Rebuilding after any
engine change costs hours.

### Option B: Compute everything on demand, cache aggressively

| Dimension | Assessment |
|-----------|------------|
| Complexity | Low — one code path, no worker, no precompute tables |
| Cost | Zero storage |
| Latency | **Cold: 30 s+.** Warm: 40 ms |
| Flexibility | Excellent |

**Pros:** simplest possible system; one implementation to test.
**Cons:** the cold path includes the mask build. First load of the map screen
would ray-cast 7 sites serially — minutes. A judge's first impression is the
cold path, every time. Disqualifying.

### Option C (chosen): Precompute the site-invariant part, compute the window-dependent part

| Dimension | Assessment |
|-----------|------------|
| Complexity | Medium — two processes, one extra table family |
| Cost | ~350 KB masks + 4 MB coarse tables |
| Latency | Cold 40–120 ms, warm < 10 ms |
| Flexibility | Full — any window, any step within bounds |

**Pros:** the expensive thing is expensive exactly once, and it is the thing that
genuinely never changes. Arbitrary windows stay possible. Storage is negligible.
**Cons:** two deployment units; a site is unusable until its mask exists, so
seeding is a hard prerequisite and `/sites` must have a `summary: null` path.

### Option D: Precompute masks; precompute *coarse* timelines only; no fine tier

Considered and rejected mid-analysis. It removes Tier 3, so the slider reads the
1 h table directly. Fast and simple — but 0.51° per sample is coarser than the
mask's own 0.25° bins, so the slider would visibly *miss* the narrow blockers the
whole product exists to reveal. It would make site A's 64 h night flicker
between 63 and 66 h depending on phase. Rejecting a design because it produces
numbers that wobble for a reason the user cannot see is the right call here.

## Trade-off Analysis

The decisive axis is **what varies**. The mask varies with the site alone and
costs 10⁴× more than the timeline; the timeline varies with the window, which is
the one thing the user manipulates continuously. Precomputing along the axis that
does not vary is free flexibility; precomputing along the axis that does (Option
A) buys latency by destroying the API.

The second axis is **cold-path honesty**. Option B's warm numbers are excellent
and its warm numbers are also irrelevant, because the demo is a sequence of cold
paths in front of people who will not wait. Designing for the cold path is the
whole reason Tier 1 exists.

Storage never entered the decision: 4 MB versus 28 GB is not a trade-off, it is
an elimination.

## Consequences

**Easier**
- The slider is a cache lookup plus 40 ms, and the numbers move as it moves.
- Adding a site is a worker job, not a schema change or a redeploy.
- `core/horizon.py` is called from exactly one place (the worker), so it can be
  slow, numba-jitted and unapologetically imperative without polluting the API.

**Harder**
- **A site is not usable until seeded.** Every read path needs a
  "mask not yet built" branch: `/sites` returns `summary: null`, `/timeline`
  returns 409 with a problem-detail the UI renders as its uncertain state.
  `make seed` is a real prerequisite and the runbook says so first.
- **Engine versioning is now load-bearing.** Masks and coarse tables are stamped
  with `engine_version`; bumping it orphans them and the API must not silently
  serve stale geometry. The version appears in `meta` on every response so a
  mismatch is visible rather than mysterious.
- Two processes to run, so `docker-compose` and the Makefile grow a worker.

**To revisit**
- If mask resolution ever needs to exceed 0.25° (a 10 m DEM would justify 0.1°),
  storage per site goes to 43 KB and the 50 km range should shrink — beyond
  ~30 km the curvature drop of r²/2R exceeds any real polar relief anyway.
- If the demo window extends past a few years, Tier 2 stops fitting comfortably
  and should become a computed-on-write materialised view or move to a
  time-series store.

## Action Items

1. [ ] `core/horizon.py`: ray-march with variable step, numba `@njit` on the
       inner loop, pure-python fallback behind a flag for debuggability.
2. [ ] `workers/precompute.py`: mask build → `horizon_masks`, coarse table →
       `visibility_tables`, reference metrics → `site_window_metrics`.
3. [ ] `services/*`: every read path branches on missing precompute and returns
       the uncertain contract, never a zero.
4. [ ] Stamp `engine_version` on write; assert it on read; surface in `meta`.
5. [ ] Golden fixtures pinned at 0.25°/900 s so a resolution change is a visible,
       reviewed diff rather than a silent one.

---

## Amendment, 2026-09-23: measured costs, and Tier 2 superseded

**What changed.** The build was measured (`defects-phase1.md` D6, D8, D9), and
two of this ADR's premises did not hold:

- **The mask costs ~130 ms per site, not ~60 s.** It ranged 128–131 ms over all
  15 sites against the real 20 m and 80 m products. That is not "20 minutes of
  offline compute". The precompute decision stands, because the mask still
  depends only on the site. But the reason is now reuse and determinism, not
  cost.
- **There are 15 candidate sites**, plus one site per CLPS mission target
  (ADR-6). There are not 20.
- **Tier 2 (`visibility_tables`) was never built**, and it is now superseded.
  Timelines cost p50 12.5 ms cold for 708 h at 900 s. The one consumer that
  needs a long span is the v2 date picker, and it is served by
  `GET /sites/{id}/calendar`. That endpoint computes on demand at 3600 s and is
  Redis-cached (system-design §10.6). A year is 8,760 samples, about 3× a
  timeline. A table would add a migration, a worker stage and a staleness rule
  to save tens of milliseconds on a request a user makes once per site.
- **The `/sites` list summaries** come from `site_window_metrics`, one reference
  window at 900 s, as built. The worker additionally warms each mission's
  surface window.

**Unchanged.** Masks are precomputed at 0.25° over 50 km. Timelines and metrics
are computed on demand, and quantisation and caching work as in §6.

**numba (done, 2026-09-24).** All 1,440 rays are now sampled in one vectorised
call, and the per-sample skyline selection is one kernel,
`core.horizon.skyline_reference`, compiled with `numba.njit(cache=True)`. The
plain-Python function is the same source and stays as the reference;
`test_numba_and_python_agree` pins them together on four surfaces. Measured on
real LOLA terrain (median of four runs, 0.25°, 50 km):

| Site | JIT | Python kernel | Previous per-ray numpy loop | max \|Δ el\| |
|---|---|---|---|---|
| Connecting Ridge | 43 ms | 333 ms | ~129 ms | 0 |
| Malapert massif | 44 ms | 329 ms | ~129 ms | 0 |
| Faustini rim | 44 ms | 320 ms | ~129 ms | 0 |

At 0.1° (3,600 rays) the JIT build takes 142 ms. A finer mask is therefore a
seeding choice, not a cost problem (judge question J3).

**Action items, amended**
1. [x] numba `@njit(cache=True)` ray-march selection with the Python
       reference kept; parity test in place; timings recorded above.
2. [x] ~~coarse table → `visibility_tables`~~. Superseded by the calendar
       endpoint.
3. [ ] Calendar endpoint, and warming mission surface windows in the worker.
