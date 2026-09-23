# ADR-6: Mission targets are sites with published coordinates; smooth-Moon horizon outside the polar DEM

**Status:** Accepted
**Date:** 2026-09-23
**Deciders:** backend lead
**Relates to:** `docs/system-design.md` §10.3–10.4, ADR-1, ADR-5

## Context

A mission is only useful to a planner if the product can show what Sun, Earth
and terrain do **at its target over its dates**. The engine already answers that
for a *site*. Its inputs are a horizon mask built from the LOLA polar DEM, and
the SPICE vectors.

Three facts constrain how a mission reaches that engine:

1. **The DEM covers 80°S–90°S only** (`LDEM_80S_20M`, `LDEM_80S_80M`). Several
   CLPS targets are far outside it: nearside maria, far-side basins and
   mid-latitude swirls.
2. **Candidate-site coordinates are derived.** `ingest_sites.py` turns a crater
   name into a landable point by searching the DEM for open sky. A mission
   already has a point, published by NASA or the provider, and moving it would
   make it a different mission.
3. **The six agent tools are fixed by the brief.** Anything a mission adds has
   to be reachable through `get_site` and `search_sites`.

## Decision

1. **Each mission with a published target becomes a site.** It gets
   `kind = mission_target`, `coordinate_rule = published` and id
   `mission-<id>`. The coordinate is used exactly as published. All other
   pipelines (masks, metrics, windows, calendar, compare) apply unchanged.
2. **Inside 80°S**, the mask is a real ray-cast from a fine 20 km window fetched
   by the existing `data/lola.py` range reader, plus the 80 m regional product.
   `terrain_modelled = true`.
3. **Outside 80°S**, the mask is **curvature-only**: 0° on every bearing, zero
   tolerance, and `dem_product = "none (smooth sphere)"`. It is flagged
   `terrain_modelled = false`. That flag enters `meta.uncertainty` on every
   response for the site, and the UI renders the uncertain state with the
   sentence "Terrain is not modelled outside 80°S".
4. The existing 15 rows default to `candidate`, `derived_open_sky` and `true`.
   The v1 lists, goldens and masks do not change.

## Options Considered

### Option A: Mission targets as sites, smooth-Moon outside coverage (chosen)
**Pros:**
- One pipeline for every number.
- `/compare` can put a mission target next to candidates with no special case.
- Agents reach missions through the existing tools.
- The far-side result (Earth never rises) is computed rather than asserted.

**Cons:** Non-polar numbers ignore local terrain. This is mitigated by the flag
and by where these targets are. At mid-latitudes the Sun climbs tens of degrees
and a local skyline of a few degrees rarely decides illumination.

### Option B: No numbers outside 80°S
**Pros:** It is the simplest honest answer.
**Cons:** It throws away computable, useful facts: Sun elevation at landing, day
length, and whether Earth is ever up. It also makes non-polar missions dead ends
in a mission browser.

### Option C: Acquire a global DEM (for example LOLA global 118 m) for all targets
**Pros:** Terrain everywhere.
**Cons:**
- It is another large download and another ingest path.
- A 118 m product is too coarse to be credible for skyline edges.
- It is a day of work that doesn't touch the south-pole story the challenge is about.

It stays on the revisit list.

### Option D: Mission records carry numbers of their own, separate from sites
**Cons:**
- A second code path for the same physics.
- `/compare` and the agents would need to learn a new entity.
- It breaks the brief's "exactly six tools" constraint, or loses mission
  reachability for agents.

## Trade-off Analysis

The governing rule is "never fabricate a number; if the data is not there,
return the uncertain state". A smooth-Moon horizon is **not** fabricated: the
horizon is stated exactly, the vectors are SPICE, and the result is labelled
with what it ignores. Refusing to compute (B) is honest but less useful. It also
hides a real finding: far-side missions have no direct-to-Earth geometry at all.

Option A keeps one engine and one set of tests. The flag is the whole cost, and
the flag is exactly what the uncertainty contract exists to carry.

## Consequences

- **Easier:**
  - "Compare IM-2's target with Connecting Ridge" is an ordinary `/compare` call.
  - "Which targets carry volatiles instruments?" is an ordinary
    `search_sites` filter.
- **Harder:**
  - The site count roughly doubles, and the Map must filter by `kind` (default
    `candidate`) so its list doesn't change.
  - Every consumer of `meta.uncertainty` must render `terrain_modelled = false`.
- **Revisit** if the product ever needs terrain away from the pole (Option C,
  per region), or if targets at 75–80°S appear. A polar product with a lower
  latitude bound would then be worth its ingest cost.

## Action Items

1. [ ] Migration: `sites.kind`, `sites.coordinate_rule`,
       `sites.terrain_modelled` with the defaults above.
2. [ ] `core/horizon.py`: `smooth_mask(n_az)`, a pure function.
3. [ ] `data/ingest_missions.py`: create or update target sites, and fetch fine
       windows for polar targets.
4. [ ] `workers/precompute.py`: masks for mission sites, then warm each surface
       window.
5. [ ] `meta.uncertainty.terrain_modelled`, with a note, on every site-scoped
       response.
6. [ ] Tests: a smooth mask yields horizon 0°; a far-side target yields Earth
       contact 0 s with `terrain_modelled = false`; candidate goldens are
       unchanged.
