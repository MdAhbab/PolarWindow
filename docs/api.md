# POLAR WINDOW — API reference

Base URL `/api/v1`. Interactive docs at `/api/v1/docs`; the machine-readable
schema at `/api/v1/openapi.json`, which is what `frontend/src/lib/api/schema.ts`
is generated from (`make codegen`). **Never hand-write the client.**

- Times are **ISO 8601 UTC**, always with `Z`.
- Durations are **seconds**, always. Hours are a presentation unit and the
  conversion happens once, in the frontend adapter.
- Angles are **degrees**. Azimuth is from north, clockwise.
- No authentication. This is a read-only public dataset served on a demo host.

---

## The `meta` envelope

Every 200 response carries `meta`, and `meta.uncertainty` is **never absent and
never null**. That is a product rule, enforced by a parameterised test across
every endpoint, not a convention.

```jsonc
"meta": {
  "computed_at": "2026-09-18T12:31:04.882Z",
  "engine_version": "hz-1/vis-1",
  "cache": "hit",              // hit | miss | bypass ("bypass" = Redis is down)
  "compute_ms": 30.5,
  "resolution": {
    "azimuth_deg": 0.25,
    "azimuth_count": 1440,
    "time_step_s": 900,
    "max_range_m": 50000.0,
    "dem_product": "LOLA_LDEM_80S_20M",
    "dem_resolution_m": 20.0,
    "ephemeris": "de440 + moon_pa_de440 (MOON_ME)",
    "frame": "MOON_ME"
  },
  "uncertainty": {
    "dem_vertical_error_m": 2.0,
    "dem_resolution_m": 20.0,
    "coverage": 1.0,            // fraction of sampled terrain inside the DEM
    "horizon_el_deg": 0.0177,   // that error, at the range the skyline is set
    "edge_timing_s": 61485.8,   // null when `grazing` is true — see below
    "grazing": false,
    "penumbra_sun_deg": 0.2665,
    "penumbra_earth_deg": 0.9705,
    "notes": ["Terrain is modelled to 50 km around the site; …"]
  }
}
```

**`edge_timing_s: null` is a stronger statement than a large number.** It means
at least one crossing is a graze — the body approaches the skyline almost
tangentially and the hour it crosses is not knowable from this data. The totals
stand; their edges do not. Render the word, not a `±`.

**`coverage < 1`** means terrain is missing on some bearings, which fall back to
a smooth-sphere horizon and are likely optimistic. Say so where it appears.

---

## Errors

RFC 9457 problem details, wrapped in `detail`, plus a `ui` block the frontend's
error panel renders directly — so the copy for a failure lives with the code
that knows what failed, and can be improved without a frontend deploy.

```jsonc
{
  "detail": {
    "type": "https://polar-window.dev/errors/horizon-not-built",
    "title": "This site has not been surveyed yet",
    "status": 409,
    "detail": "No horizon mask for 'nobile-rim-2' at engine hz-1/vis-1. Run `make seed`.",
    "ui": {
      "still_works": "Sites that have been surveyed are unaffected, and this site's coordinates and terrain are still shown.",
      "retryable": true,
      "action": "Run make seed"
    }
  }
}
```

| Status | `type` | When |
|---|---|---|
| 404 | `site-not-found` | Unknown site id |
| 404 | `unknown-layer` / `tile-out-of-scheme` | Bad tile request |
| 409 | `horizon-not-built` | Site exists, precompute has not run |
| 422 | `bad-window` | Step or window outside bounds |
| 422 | `invalid-request` | Request body or query failed validation |
| 422 | `too-many-sites` / `unknown-metric` | `/compare` misuse |
| 503 | `kernel-missing` | SPICE not loaded |
| 503 | `dem-missing` | Elevation model absent |

Agent endpoints **do not** use error statuses for "cannot answer". They return
200 with `status: "insufficient_data"` or `"degraded"` — those are answers, the
UI has states for both, and turning a working guard into a 5xx would make it
look like a broken service.

---

## Sites

### `GET /sites`

| Param | Type | Notes |
|---|---|---|
| `q` | string | Substring of name or region |
| `region` | string | e.g. `shackleton`, `nobile` |
| `lat_min` / `lat_max` | float | −90…0 |
| `min_sun_fraction` | 0…1 | Coarse filter, reference window |
| `max_longest_dark_s` | seconds | Coarse filter, reference window |
| `limit` / `offset` | int | Default 100 / 0 |

```bash
curl "localhost:8000/api/v1/sites?min_sun_fraction=0.7"
```

```jsonc
{
  "items": [{
    "id": "connecting-ridge", "code": "B", "name": "Connecting Ridge",
    "region": "shackleton",
    "lat_deg": -89.438, "lon_deg": 222.717, "elev_m": 1957.5, "slope_deg": 1.0,
    "note": "The saddle between Shackleton and de Gerlache…",
    "summary": {
      "sunlit_s": 2067804.0, "earth_contact_s": 1548108.0,
      "longest_dark_s": 437688.0, "longest_blackout_s": 1002492.0,
      "sun_fraction_up": 0.8103, "earth_fraction_up": 0.6067,
      "worst_compound_s": 138384.0, "grazing": false,
      "reference_window_start": "2027-03-14T00:00:00Z",
      "reference_window_end": "2027-04-12T09:00:00Z",
      "reference_step_s": 900
    }
  }],
  "total": 15, "meta": { … }
}
```

**`summary` is `null` — never zeros — for a site whose precompute has not run.**
A zero is a measurement; absence is not. The metric filters exclude such sites
rather than assuming they pass, because they cannot be judged.

Summaries are computed over the **reference window**, not whatever window the
caller has on screen. `meta.uncertainty.notes` says so on every response.

### `GET /sites/{id}`

Adds `provenance` — how this coordinate came to exist — and `horizon`, a summary
of the stored mask.

```jsonc
"provenance": {
  "anchor_lat_deg": -89.45, "anchor_lon_deg": 222.0,
  "search_kind": "massif", "search_inner_km": 0.0, "search_outer_km": 8.0,
  "offset_from_anchor_km": 0.4,
  "source": "LPI Lunar South Pole Atlas (feature names and anchors)",
  "source_note": "Derived, not catalogued. Anchor is the IAU centre of … The landing point is the highest post with local slope <= 12 deg in a disc of 0-8 km around that anchor, measured on LOLA LDEM 80S at 80 m posts. Not a surveyed landing ellipse and not an official candidate site."
}
```

### `GET /sites/{id}/horizon`

`step_deg` must divide 360 and be a multiple of the stored 0.25°.

```jsonc
{ "site_id": "connecting-ridge", "azimuth_step_deg": 1.0, "azimuth_count": 360,
  "el_deg": [-3.10, -3.07, …], "range_m": […], "tol_deg": […],
  "max_el_deg": -0.062, "max_el_bearing_deg": 175.0, "meta": { … } }
```

Downsampling takes the **maximum** of each group, never the mean. A skyline is
an upper envelope; averaging it invents sky where a ridge is, and at these
sites a single ridge is the whole answer.

A negative `max_el_deg` is not a bug. A site standing above its surroundings
looks *down* at its horizon: `arccos(R / (R + h))` is 2.7° at 1,958 m.

### `GET /sites/{id}/timeline`

The date-slider endpoint. `start`, `end`, `step_s` (300…7200, default 900).

Parallel arrays rather than an array of objects: 2,835 samples × 2 bodies × 5
fields is ~1.1 MB as objects and ~210 KB as arrays.

```jsonc
{ "t_s": [0, 900, 1800, …],
  "sun":   { "az_deg": […], "el_deg": […], "mask_el_deg": […],
             "margin_deg": […], "state": [2,2,1,0,…] },
  "earth": { … } }
```

`state` is **three-valued**: `2` lit, `1` penumbral, `0` dark. The Sun's disc is
0.27° across seen from the Moon and Earth's is ~0.97°, so there is a real band
where the body is partly occluded — about 10 % of samples at a polar site. A
boolean there would be a lie at exactly the point the terrain model is weakest.

### `GET /sites/{id}/windows`

Derived intervals, each with its timing tolerance and — for a blocked arc — the
bearing and elevation of the terrain responsible.

```jsonc
"arcs": [{
  "up": false, "start": "2027-03-26T05:00:00Z", "end": "2027-03-31T07:35:00Z",
  "duration_s": 437688.0, "tolerance_s": 61485.8, "grazing": false,
  "blocked_by_bearing_deg": 177.0, "blocked_by_el_deg": -0.12
}]
```

Naming the cause is the difference between an answer and an assertion.

### `GET /sites/{id}/metrics`

The four numbers, and nothing that dilutes them.

```jsonc
{ "sunlit_s": 2067804.0, "earth_contact_s": 1548108.0,
  "longest_dark_s": 437688.0, "longest_blackout_s": 1002492.0,
  "sun_fraction_up": 0.8103, "earth_fraction_up": 0.6067,
  "worst_compound_s": 138384.0,
  "autonomy": { "worst_compound_s": 138384.0, "required_autonomy_s": 166060.8,
                "survival_needed_s": 437688.0, "compound_inside_dark": true } }
```

`survival_needed_s` is the whole night, not the blackout, when the blackout
falls inside it: if the radio is silent for 40 h in the middle of a 122 h night,
the battery still has to carry the 122 h. Conflating them under-sizes the
battery, which is the dangerous direction to be wrong in.

**There is no `score` field, and a test asserts there never will be.**

---

## `POST /compare`

```jsonc
// request — at most 8 sites
{ "site_ids": ["connecting-ridge", "malapert-massif"], "rank_by": "longest_dark_s" }
```

`rank_by` ∈ `sunlit_s` | `earth_contact_s` | `longest_dark_s` | `longest_blackout_s`.
There is deliberately no composite option.

```jsonc
{ "rank_by": "longest_dark_s",
  "items": [{ "site_id": "connecting-ridge", "rank": 1, "metrics": { … },
              "delta_vs_best": { "sunlit_s": 0.0, … } }],
  "ties": [["de-gerlache-rim", "de-gerlache-kocher-massif"]],
  "unavailable": [{ "site_id": "ghost", "reason": "…" }] }
```

**`ties` groups sites the data cannot distinguish** (within one hour). Render
them at the same rank: ordering them asserts a difference that is not there.

**`unavailable`** carries sites that could not be computed. One unsurveyed site
never blanks the comparison.

`/compare` fans out to the same service `GET /metrics` uses, so the two can
never disagree — asserted by an integration test.

---

## Tiles

`GET /tiles/{layer}/{z}/{x}/{y}.png`, layers `hillshade` | `illumination` | `psr`.

A plain quadtree over the DEM's own ±304 km extent in lunar south polar
stereographic. `z0` is one tile; each level doubles.

- **200** with `ETag` and `Cache-Control`. `X-Tile-Source: static | dynamic`.
- **204** when the tile is inside the grid but has no data there. **Not 404** —
  the map requests a rectangular grid and the corners of a polar scene are
  legitimately empty.
- **404** only for an unknown layer or an out-of-scheme `z/x/y`.

`illumination` and `psr` are **approximations** from a ring-based horizon proxy,
stated in `X-Tile-Note`. They are right about which craters are dark; they are
not published products. `psr` in particular is a claim about many years, not
about the demo window.

---

## Agents

`POST /agents/explain` · `advise` · `brief` · `ask`

```bash
curl -X POST localhost:8000/api/v1/agents/advise \
  -H 'content-type: application/json' \
  -d '{"requirement":"at least 96 hours of Earth contact and no night longer than 150 hours"}'
```

Shared envelope:

```jsonc
{ "status": "ok",             // ok | insufficient_data | degraded
  "reason": null,             // required when status is not "ok"
  "result": { … },            // the agent's validated contract
  "provenance": [{ "claim": "81 % of the window", "value": 81.0,
                   "tool": "get_metrics", "call_seq": 2,
                   "field": "sun_fraction_up" }],
  "tool_calls": [{ "seq": 1, "tool": "get_site", "args": { … },
                   "latency_ms": 12.4, "number_count": 31 }],
  "run_id": "…", "attempts": 1, "latency_ms": 2840.2,
  "guard_failures": [] }
```

`provenance` is produced by the **grounding guard**, not by the model — a
model-authored citation would be exactly as trustworthy as the number it cites.
A `user_request` entry means the figure came from the caller's own question,
which is quoting rather than claiming.

`guard_failures` retains rejections that a retry then fixed. That is what lets
the guard be *shown working* rather than asserted to exist.

### `GET /agents/runs`

Every invocation, whatever its outcome, with its tool calls, latency, tokens and
guard failures. This is the demo's proof that the AI layer is real and bounded.

---

## `GET /healthz`

Also mounted unprefixed at `/healthz` for container health checks.

```jsonc
{ "status": "ok",            // ok | degraded | down
  "engine_version": "hz-1/vis-1",
  "kernels": { "loaded": true, "count": 6, "furnsh_ms": 27.1, "missing": [] },
  "db": "ok", "redis": "ok",
  "dem": { "regional_present": true, "fine_windows": 15, "product": "LOLA LDEM 80S …" } }
```

**200 when degraded, 503 only when down.** A missing elevation model still
leaves every ephemeris endpoint working and the UI has a state for partial data;
failing the whole check for a partial capability would take the demo down for a
condition the product already handles. A missing ephemeris is different — there
are no Sun or Earth positions at all, which is the product.

---

## Performance

Measured on a laptop, warm, against the live service:

| Endpoint | Typical | Notes |
|---|---|---|
| `/metrics` | 25–30 ms cold, < 5 ms cached | one vectorised `spkpos` per body |
| `/timeline` | 36 ms, 210 KB | 2,835 samples × 2 bodies |
| `/horizon` | < 5 ms | a stored array |
| `/compare` ×4 | ~120 ms cold | sequential; they share one SPICE thread |

**Window quantisation is why the slider is fast.** `start` and `end` snap to the
`step_s` grid before anything else happens, so a drag emitting starts 41 s apart
collapses onto one cache key. Verified: three such requests return
byte-identical bodies and report `cache: "hit"`.
