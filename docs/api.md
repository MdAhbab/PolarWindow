# POLAR WINDOW — API reference

Base URL `/api/v1`. Interactive docs at `/api/v1/docs`; the machine-readable
schema at `/api/v1/openapi.json`, which is what `frontend/src/lib/api/schema.ts`
is generated from (`make codegen`). **Never hand-write the client.**

- Times are **ISO 8601 UTC**, always with `Z`.
- Durations are **seconds**, always. Hours are a presentation unit and the
  conversion happens once, in the frontend adapter.
- Angles are **degrees**. Azimuth is from north, clockwise.
- Reading needs no session: the sites, missions, numbers and tiles are public
  data. A **session** (a JWT from `POST /auth/demo`, sent as
  `Authorization: Bearer <token>`) is needed for the four AI panels, which cost
  model quota, and for the project settings, which change the service for
  everyone. See *Sign-in* and *Settings* below.

---

## The `meta` envelope

Every 200 response carries `meta`, and `meta.uncertainty` is **never absent and
never null**. That is a product rule, enforced by a parameterised test across
every endpoint, not a convention.

```jsonc
"meta": {
  "computed_at": "2026-09-18T12:31:04.882Z",
  "engine_version": "hz-2/vis-2",
  "cache": "hit",              // hit | miss | bypass ("bypass" = Redis is down)
  "compute_ms": 10.1,
  "resolution": {
    "azimuth_deg": 0.25,
    "azimuth_count": 1440,
    "time_step_s": 900,
    "max_range_m": 50000.0,
    "dem_product": "LOLA_LDEM_80S_20M + LDEM_80S_80M",
    "dem_resolution_m": 20.0,
    "ephemeris": "de440 + moon_pa_de440 (MOON_ME)",
    "frame": "MOON_ME"
  },
  "uncertainty": {
    "dem_vertical_error_m": 4.0, // the worst tier that set this site's skyline
    "dem_resolution_m": 20.0,
    "coverage": 1.0,            // fraction of sampled terrain inside the DEM
    "horizon_el_deg": 0.0078,   // that error, at the range the skyline is set
    "edge_timing_s": 61527.5,   // null when `grazing` is true — see below
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

**`dem_vertical_error_m` is the coarsest tier that actually set this site's
skyline**, not the finest tier available. A site whose horizon is set by ridges
beyond the 20 m window carries the 80 m tier's error on those bearings, and
reporting the 20 m figure would claim a precision the answer does not have.

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
    "detail": "No horizon mask for 'nobile-rim-2' at engine hz-2/vis-2. Run `make seed`.",
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
| `kind` | `candidate` \| `mission_target` \| `all` | Default `candidate`, so the v1 list is unchanged |
| `limit` / `offset` | int | Default 100 / 0 |

Every site also carries `kind`, `coordinate_rule` (`derived_open_sky` or
`published`) and `terrain_modelled`. `elev_m` and `slope_deg` are `null` where
no elevation model covers the site: an unknown height is not zero.

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
  "source_note": "Derived, not catalogued. The search was centred on … at …. The landing point is the post with the most open sky (lowest coarse horizon) among those with local slope <= 12 deg and height in the top 10% of a disc of 0-8 km around that anchor, measured on LOLA LDEM 80S (PDS Geosciences Node) at 80 m posts. Not a surveyed landing ellipse and not an official candidate site."
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

Parallel arrays rather than an array of objects: 2,836 samples × 2 bodies × 5
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
  "duration_s": 437688.0, "tolerance_s": 61527.5, "grazing": false,
  "start_tolerance_s": 453.5,  // null when this edge is the window, not a crossing
  "end_tolerance_s": 61525.8,
  "open_start": false, "open_end": false,
  "blocked_by_bearing_deg": 177.0, "blocked_by_el_deg": -0.12
}]
```

Naming the cause is the difference between an answer and an assertion.

**`open_start` / `open_end`: the window bounds this arc, not the geometry.** The
arc was still running when the window opened or was still running when it
closed, so its `duration_s` is a **lower bound** — the real stretch is longer by
an unknown amount. `tolerance_s` is the quadrature sum of the two edges that are
real crossings; an open edge contributes nothing to it, because there is no
crossing to time, and its per-edge tolerance is `null`. A client that renders an
open arc with `≈` rather than `≥` is reporting a number the server did not
claim.

### `GET /sites/{id}/metrics`

The four numbers, and nothing that dilutes them.

```jsonc
{ "sunlit_s": 2067837.7, "earth_contact_s": 1549023.0,
  "longest_dark_s": 437647.8, "longest_blackout_s": 1002477.0,
  "sun_fraction_up": 0.81044, "earth_fraction_up": 0.607103,
  "worst_compound_s": 138206.2,
  "longest_dark_open": false,       // as on an arc: true means "at least this"
  "longest_blackout_open": false,
  "worst_compound_open": false,
  "autonomy": { "worst_compound_s": 138206.2, "required_autonomy_s": 165847.5,
                "margin_fraction": 0.2,
                "survival_needed_s": 437647.8, "compound_inside_dark": true,
                "survival_open": false, "worst_compound_open": false } }
```

The `*_open` flags carry the same meaning here as on an arc: the window, not the
geometry, ended the stretch, so the figure is a floor. A 30-day window across a
site whose night runs 322 h reports 167 h with `longest_dark_open: true` — the
number is not wrong, but reading it as the night is.

`margin_fraction` is the server's own reserve on top of the worst compound
event; `required_autonomy_s` already includes it. Clients convert units and
nothing else — recomputing the margin client-side is how the headline figure and
the sentence describing it drift apart.

`survival_needed_s` is the whole night, not the blackout, when the blackout
falls inside it: if the radio is silent for 40 h in the middle of a 122 h night,
the battery still has to carry the 122 h. Conflating them under-sizes the
battery, which is the dangerous direction to be wrong in.

Each number also carries its own uncertainty and bounds:

| Field | Meaning |
|---|---|
| `sunlit_tolerance_s`, `earth_contact_tolerance_s` | Every crossing's edge tolerance, in quadrature |
| `longest_dark_tolerance_s`, `longest_blackout_tolerance_s` | The longest gap's two edges, in quadrature; `null` when an edge is a graze (`*_grazing: true`) |
| `sunlit_full_disc_s` / `sunlit_any_limb_s` | Time the whole solar disc / any part of it was above the skyline. The headline `sunlit_s` times the disc centre; these bracket it. Sampled at the step. Same for `earth_contact_*`. |

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
  "items": [{ "site_id": "connecting-ridge", "position": 1,
              "rank": null, "rank_range": [1, 2],
              "tied": false, "tied_with": [], "incomparable_with": ["de-gerlache-rim"],
              "censored": false, "grazing": false, "uncertainty_s": 61560.0,
              "metrics": { … }, "delta_vs_best": { "sunlit_s": 0.0, … } }],
  "ties": [],
  "unavailable": [{ "site_id": "ghost", "reason": "…" }] }
```

**Each value is an interval** (system-design §10.7). A measured value is
`value ± uncertainty_s`, where the tolerance is the site's own for that metric.
A window-cut longest gap (`censored: true`) is `[value, ∞)`. One site beats
another only when their intervals do not overlap in its favour:

- `rank` is a number when the place can be stated. Measured sites whose
  intervals overlap share it (`tied_with`, and a group in `ties`).
- `rank` is `null` when a lower bound or an untimeable edge makes the place
  unknowable. `rank_range` is then what can be said, and `incomparable_with`
  says against whom. **Never label such a site "best".**

**`unavailable`** carries sites that could not be computed. One unsurveyed site
never blanks the comparison.

`/compare` fans out to the same service `GET /metrics` uses, so the two can
never disagree — asserted by an integration test.

---

## Missions (contract v2)

CLPS deliveries, from the cited `data/missions.json` (ADR-5,
`docs/data-sources.md`). A field no source confirms is `null` and named in
`unconfirmed_fields`; it is never filled in.

### `GET /missions`

| Param | Notes |
|---|---|
| `status` (repeatable) | `planned`, `in_transit`, `operating`, `completed`, `partial_success`, `landing_failed`, `lost_before_landing`, `cancelled`, `reassigned` |
| `payload_type` (repeatable, any-of) | `volatiles`, `geology_geophysics`, `heat_flow`, `radiation_space_weather`, `exosphere_dust`, `imaging`, `landing_navigation`, `communications`, `laser_retroreflector`, `rover_mobility`, `technology_demo`, `other` |
| `provider`, `region`, `q` | `region` ∈ `south_polar`, `nearside`, `farside`, `polar_other` |
| `from`, `to` | Landing (else launch) date range |

```bash
curl "localhost:8000/api/v1/missions?payload_type=volatiles"
```

Each item has the mission's facts (dates as `{date, precision, as_published}`,
where the phrase is what to show), its `target` with `coordinate_kind`
(`actual_landing` from LROC, `planned_target`, or `feature_centre` = the IAU
centre of the named target, **not a landing point**), the `site_id` standing
for the target, its `surface_window {start, end, basis, note}` and a `summary`
of the four numbers over that window, or `null` when there is none.

`surface_window.basis`: `published` (landing and end both sourced to the day),
`planned` (landing plus a sourced duration), `assumed` (landing plus one lunar
daylight period, named as an assumption), `none` (no single window; use the
calendar).

### `GET /missions/{id}`

The brief plus `outcome_note`, `end_of_mission`, `payloads[]` (each with its
`source_url` and this project's `instrument_types`), `sources[]` with access
dates, `notes[]` (conflicts between NASA pages, recorded rather than resolved),
`ellipse_ring` (null unless a landing ellipse is published) and `site`. 404 is a
problem detail.

A target outside 80°S has `terrain_modelled: false`: Sun and Earth are computed
against a smooth sphere and every response for that site says so in
`meta.uncertainty.terrain_modelled` and its notes. On the far side Earth never
rises: `feature-schrodinger` returns `earth_contact_s: 0`.

### `GET /sites/{id}/calendar`

`start`, `end` (≤ 730 days), `bucket=day|month`. Per bucket: sun and Earth
fractions, sunlit and Earth-contact seconds, and the longest dark and blackout
stretches with `*_open` when a bucket edge cut them. One hourly timeline over
the span, split at UTC day or month boundaries. About 115 ms cold for a year by
month; a cache hit is about 2 ms.

---

## Mission lifecycle (contract `docs/lifecycle-api.md`)

The lifecycle sections have their own reference, kept with the frontend as the
contract: `docs/lifecycle-api.md` (shapes and their *Changes*) and
`docs/openapi.json` (generated, `make openapi`). In short:

| Endpoint | Answer |
|---|---|
| `GET /missions/{id}/sections` | each section's state and a line of words |
| `GET /missions/{id}/ready`, `.../ready/items`, `.../parts`, `.../risks`, `GET /lessons` | readiness items, milestones, parts, risks as entered (writes need a named sign-in; audited) |
| `GET /missions/{id}/launch` | the flown launch, or opportunities backed out from the landing (job) |
| `GET /missions/{id}/launch/weather` | each weather rule at one launch time with what each forecast says |
| `PUT`/`DELETE /missions/{id}/launch/official-forecast`, `GET`/`PUT /vehicles/{id}/limits` | the team's entries (audited) |
| `GET /missions/{id}/trip` (+ `/export?format=oem\|csv`) | distance, shadow, burns, correction budget, radiation (job) |
| `GET /missions/{id}/contact` (+ `/plan`, `/bookings`) | who can hear the lander and how long a message waits (job) |
| `GET /missions/{id}/return`, `PUT .../return/limits` | the booster's landing, sea and wind, the capsule and its entry model's check |
| `GET /space-weather` | space weather now, each value with its age |
| `GET /jobs/{id}`, `POST /jobs/{id}/retry` | a heavy answer's progress; retry a failed one |
| `GET /feeds`, `POST /feeds/{provider}/refresh` | every live source and its age; fetch one now (signed in) |

A heavy answer that is not stored yet comes back **202** with a `JobRef`; poll
`GET /jobs/{id}` and ask again when it is `done`.

## Tiles

`GET /tiles/{layer}/{z}/{x}/{y}.png` (the suffix is optional), layers `hillshade` | `illumination` | `psr`. `make seed` pre-renders z0–z5 (4,095 tiles, ~134 MB); z6–z7 render on first request.

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
TOKEN=$(curl -s -X POST localhost:8000/api/v1/auth/demo | jq -r .token)
curl -X POST localhost:8000/api/v1/agents/advise \
  -H "authorization: Bearer $TOKEN" \
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
the guard be *shown working* rather than asserted to exist. Besides ungrounded
numbers and dates, the guard rejects verdict words (`kind: "verdict_word"`:
go/no-go, "safe", a readiness percentage, a risk score, an overall chance of
launch), even in a denial.

`ask` can read the missions too: `tool` in `tool_calls` and `provenance` may be
`list_missions`, `get_mission_sections`, `get_mission_section` or
`get_space_weather` besides the six site tools. A mission section reaches the
model cut to at most 200 numbers, and a section not worked out yet is reported,
never started (ADR-6, amended 2026-09-28).

Without a session these four answer **401** with `WWW-Authenticate: Bearer`.
When the project manager has turned the AI off in Settings they still answer,
with `status: "degraded"` and a summary built from the measurements.

### `GET /agents/runs`

Every invocation, whatever its outcome, with its tool calls, latency, tokens and
guard failures. This is the demo's proof that the AI layer is real and bounded.
Public, like every read.

---

## Sign-in

### `POST /auth/demo`

A project manager's session with no user name or password: the front page's
*Open the dashboard* button. For a judged demo; `PW_DEMO_SIGN_IN=false` turns
it off, and it then answers **403** with a problem detail.

```jsonc
{ "token": "eyJ…", "token_type": "bearer", "subject": "demo-3f9a1c2e",
  "role": "project_manager", "role_name": "Project manager",
  "expires_at": "2026-09-25T09:00:00Z" }
```

The token is an HS256 JWT signed with `PW_JWT_SECRET` (a random secret per
process when that is blank, so a restart ends every session; the client then
signs in again once and retries). It lasts `PW_JWT_TTL_S`, 12 hours by default.

### `GET /auth/me`

Who a session belongs to: the same fields without the token. **401** without a
valid one.

---

## Settings

The project manager's controls. Every route needs a session with the
`project_manager` role (**401** without one, **403** with another role). Each
change applies to everyone using the server, and each can be undone or is
harmless: the AI settings reset to the configured defaults, a cleared result
is worked out again when next needed, and the run log only ever records.

| | |
|---|---|
| `GET /settings` | The AI assistant (on or off, the two model orders with each model ready or skipped until when and why) and the system (terrain map, ephemeris, database, cache, and counts of missions, sites, runs and cached results) |
| `PUT /settings/ai` | `{enabled, models, models_light}`. The lists reorder or drop the configured models (`PW_AGENT_MODELS`, `PW_AGENT_MODELS_LIGHT`); an unknown or repeated model is a **422** and the previous settings stay |
| `POST /settings/ai/reset` | Back to the configured defaults |
| `POST /settings/ai/retry` | Forget every model's cooldown, e.g. after the key's quota was raised |
| `DELETE /settings/agent-runs` | Clear the AI activity log: `{what, removed, message}` |
| `DELETE /settings/cache` | Clear cached results, only this service's keys (`pw:*`), never the whole Redis database |

The AI settings are stored in `app_settings` and read on every AI request, so
every process serving the API follows the same switch.

---

## `GET /healthz`

Also mounted unprefixed at `/healthz` for container health checks.

```jsonc
{ "status": "ok",            // ok | degraded | down
  "engine_version": "hz-2/vis-2",
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

Measured over HTTP against the live service on an Apple M3, 24 September 2026 (medians; "cold" counts only cache misses):

| Endpoint | Typical | Notes |
|---|---|---|
| `/metrics` | 11 ms cold, 0.8 ms cached (median) | one vectorised `spkpos` per body |
| `/timeline` | 15 ms cold, 4 ms warm; 210 KB | 2,836 samples × 2 bodies |
| `/horizon` | 1 ms | a stored array |
| `/missions` | 4 ms warm (all 20), 3 ms with a filter | Postgres only, no geometry |
| `/calendar` | 103 ms cold for 365 days by month | one hourly timeline over the span |
| `/compare` ×8 | ~70 ms cold, ~1 ms warm | sequential; they share one SPICE thread |

**Window quantisation is why the slider is fast.** `start` and `end` snap to the
`step_s` grid before anything else happens, so a drag emitting starts 41 s apart
collapses onto one cache key. Verified: three such requests return
byte-identical bodies and report `cache: "hit"`.
