# Lifecycle API contract (v1, 2026-09-27)

The shapes of the six mission sections, **Ready · Launch · Trip · Landing · Contact · Return**, and the log of their changes. Every endpoint, the envelope, errors and sign-in are in [api.md](api.md).

This is the contract between the backend and the frontend. The backend
implements these shapes exactly; the frontend builds against them (fixtures
first, then the generated `schema.ts`). A change to a shape is made here first,
with a line in *Changes* at the bottom, then in code. Landing is the existing
surface screens.

The 1 October planning update keeps these response shapes. Engines are
`wx-3`, `los-3`, and `lw-7`: wind verification follows the selected forecast
lead and tested threshold; rover terrain selects native 3/4/5 m windows when
their coverage and lander ground permit, otherwise 20/80 m, and terrain tiles
use that same selected file; pad-limit endpoints must pass coast, flight and
same-opportunity checks before a planned window is published. A failed window
retains a nominal instant with its reason in the opportunity note. See
[coverage, validation and account status](planning-updates.md).

Radiation engine `rad-5` recomputes cached belt results with the published
0.3°/year SAA longitudinal drift compensation. The native Windows loader from
`rad-4` is retained. Response shapes and the factor-of-two map uncertainty stay
the same. Of the seven passages run in SPENVIS, five pass the 5% implementation
comparison and two miss it on protons (+5.75% and +5.40%); see
[the radiation validation](validation.md) for the cause.

Return can use a [locally imported Copernicus wave subset](copernicus-marine.md)
for its existing `wave_height_m` quantity. It retains NOAA wind and source
references. Selection requires an import no older than 24 hours, a time within
90 minutes, coverage of the zone, a valid ocean cell and distance at most 20 km.
Unavailable subset values fall back to NOAA. Subset import time is recorded as
fetch time; it is never claimed to be the model's forecast issuance time.

All paths are under `/api/v1`. Reading is public; every write needs a named
session (ADR-17). Shapes are written TypeScript-style; `?` means optional,
`| null` means the field is always present but may be null.

## Common pieces

```ts
type Provenance = "computed" | "published" | "entered" | "assumed";

// ADR-9. Exactly one margin form, or no_margin_reason; value null => missing_reason.
interface Quantity {
  value: number | null; unit: string; provenance: Provenance;
  pm: number | null; lo: number | null; hi: number | null; factor: number | null;
  open: boolean;                   // lower bound: the dates cut it short
  no_margin_reason: string | null; missing_reason: string | null;
  source: string | null;           // who entered it, or the URL it was published at
}

interface Share { k: number; n: number; lo: number; hi: number; checked: boolean }

interface SourceRef {
  name: string; url: string | null; issued_at: string | null; fetched_at: string | null;
  licence: string | null; snapshot_id: number | null;
}

interface LifecycleMeta {
  computed_at: string;
  uncertainty: { kind: "composite"; parts: { source: string; note: string }[] };
  engines: Record<string, string>;       // e.g. {"traj": "traj-1", "vis": "vis-2"}
  sources: SourceRef[];
  stale: boolean;                        // an input is past its staleness budget
  compute_ms: number | null;
}

// A time stretch. `open_start`/`open_end`: cut by the chosen dates.
interface Stretch { start: string; end: string; open_start: boolean; open_end: boolean }

// Heavy answers are jobs (ADR-12). A section endpoint returns 202 with this
// while its answer is being computed; the client polls GET /jobs/{id}.
interface JobRef { job_id: number; status: "queued" | "running" | "done" | "failed";
  progress: number | null; message: string; poll_after_s: number }

// Every section response has this envelope.
interface Section<T> { data: T; meta: LifecycleMeta }
```

Section status, shown in the mission hub's journey bar (never a verdict):

```ts
interface SectionStatus {
  section: "ready" | "launch" | "trip" | "landing" | "contact" | "return";
  state: "available" | "computing" | "needs_input" | "not_applicable" | "no_data";
  summary: string;          // one plain sentence, e.g. "12 of 31 items ready; 2 blocked"
  as_of: string | null;
}
```

`GET /missions/{id}/sections` → `Section<SectionStatus[]>` (six entries, in order).

## Ready (T3)

`GET /missions/{id}/ready` → `Section<Ready>`

```ts
type ReadyState = "not_started" | "in_build" | "in_test" | "test_passed"
  | "delivered" | "integrated" | "verified_on_lander" | "ready" | "blocked";
type ItemKind = "lander" | "payload" | "rover" | "launch_vehicle" | "range"
  | "ground_booking" | "relay_agreement" | "ops_team" | "licence";

interface ReadyItem {
  id: string; kind: ItemKind; name: string; organisation: string | null;
  state: ReadyState; blocked_reason: string | null;
  changed_at: string | null; changed_by: string | null; evidence_url: string | null;
  source: "public" | "entered";          // prefilled from missions.json, or entered
  tests: { kind: "vibration" | "shock" | "thermal_vacuum" | "emi_emc" | "functional";
           result: "passed" | "failed" | "not_done"; report_url: string | null; date: string | null }[];
}
interface Milestone { id: string; name: string; date: Quantity; done: boolean; source: string | null }
interface Risk {
  id: string; title: string; cause: string; consequence_text: string;
  scale_id: string;
  ratings: { category: "safety" | "technical" | "cost" | "schedule";
             likelihood: number; consequence: number }[];   // never multiplied
  trend: "rising" | "steady" | "falling"; owner: string | null; mitigation: string | null;
  links: { readiness_items: string[]; parts: string[]; lessons: string[] };
}
interface Ready {
  counts: Record<ReadyState, number>;     // counts, never a percentage
  items: ReadyItem[]; milestones: Milestone[]; risks: Risk[];
  parts: { total: number; spares: number; lost: number; damaged: number; failed: number };
  lessons_available: number; lessons_adopted: number;
}
```

Writes (named session): `POST /missions/{id}/ready/items`,
`PATCH /ready/items/{item_id}` body `{state, date, evidence_url, note, blocked_reason?}`
(409 on an illegal move, with the allowed next states), `GET /ready/items/{item_id}/history`
→ audit entries `{at, by, before, after, note}`.
Parts: `GET|POST /missions/{id}/parts`, `PATCH /parts/{part_id}`,
`GET /parts/{part_id}/impact` → `{stops_working: {id, name, kind}[]}`.
Risks: `GET|POST /missions/{id}/risks`, `PATCH /risks/{risk_id}`; `GET /risk-scales`.
History: `GET /landing-history` → attempts `{mission, agency, date, outcome, cause, source_url}[]`
plus `counts {attempts, landed_working, landed_tipped_or_partial, failed}`.
Lessons: `GET /lessons` → `{id, text, from_mission, year, source_url, checklist_item}[]`;
`POST /missions/{id}/lessons/{lesson_id}/adopt`.

## Launch (T2 D1/D2, T4)

`GET /missions/{id}/launch?from=&to=` → `Section<LaunchCalendar>` or 202 `JobRef`

```ts
interface Opportunity {
  id: string; pad_id: string; pad_name: string; vehicle_id: string;
  t0: Quantity;                               // unit "s since epoch" rendered as a time ± minutes
  kind: "instantaneous" | "window"; window_open: string | null; window_close: string | null;
  transfer: { type: "direct" | "phasing_loops"; flight_days: Quantity; orbit_wait_days: Quantity };
  landing: { time: Quantity; sun_elevation_deg: Quantity; sunlight_after_h: Quantity;
             earth_up: boolean };
  weather: "forecast" | "climatology" | "none";   // what the weather tab can show for it
}
interface LaunchCalendar {
  pads: { id: string; name: string; lat_deg: number; lon_deg: number; operator: string }[];
  opportunities: Opportunity[];
  landing_rule: { sun_elevation_min_deg: Quantity; sun_elevation_max_deg: Quantity;
                  earth_required: boolean; note: string };
  published_t0: Quantity | null;              // the mission's own published launch time
}
```

`GET /missions/{id}/launch/weather?opportunity=` (or `?t0=&pad=`) → `Section<LaunchWeather>`

```ts
interface RuleRow {
  id: string; text: string; source_url: string;
  class: "model" | "proxy" | "observation";
  limit: Quantity;                             // provenance published or entered
  per_system: { system: "GEFS" | "ECMWF-ENS" | "AIFS-ENS";
                share: Share | null; missing_reason: string | null }[];
  one_forecast: { system: "NWS" | "HRRR" | "GEOS-FP"; value: Quantity; over: boolean;
                  note: string | null }[];   // HRRR: how it did against the station; NWS: keeps no archive
  disagreement: boolean;
  disagreement_note: string | null;          // who disagrees and how, in plain words
  observed: { state: "clear" | "seen" | "no_data"; detail: string } | null;  // GLM etc.
  climatology: { share: number; years: string; source: string } | null;
}
interface LaunchWeather {
  t0: string; lead_time_h: number;
  rules: RuleRow[];
  official: { id: number; probability_pct: number; concerns: string[]; pdf_url: string;
              entered_by: string; entered_at: string } | null;
  range_conflicts: { name: string; t0: string; pad: string }[];
}
```

Writes: `PUT /missions/{id}/launch/official-forecast`, `PUT /vehicles/{id}/limits`.

## Trip (T2 C0–C4, E)

`GET /missions/{id}/trip` → `Section<Trip>` or 202 `JobRef`

```ts
interface Trip {
  source: "flown" | "designed" | "none";      // flown = NAIF CLPS reconstruction
  none_reason: string | null;
  start: string; end: string;
  samples: { t: string; earth_km: number; moon_km: number;
             light: "lit" | "penumbral" | "dark"; heard: boolean }[];   // <= 2,000 points
  shadow: Stretch[]; heard: Stretch[];
  numbers: { sunlight_h: Quantity; heard_h: Quantity;
             longest_shadow_h: Quantity; longest_unheard_h: Quantity };
  burns: { t: string; name: string; dv_m_s: Quantity }[];
  moon_pull: { equal_pull_km: number; sphere_of_influence_km: number;
               t_equal_pull: string | null };
  radiation: { belt_hours: Quantity; fluence_gt10mev: Quantity; gcr_dose_mgy_day: Quantity;
               screening_note: string; confirm_in: string[] } | null;
}
```

Exports: `GET /missions/{id}/trip/export?format=oem|csv` (default `oem`).

## Contact (T1)

`GET /missions/{id}/contact?start=&end=` → `Section<Contact>` or 202 `JobRef`

```ts
interface Node { id: string; kind: "station" | "relay" | "lander" | "rover" | "earth";
  name: string; operator: string | null;
  status: "operating" | "planned" | "not_launched";
  orbit: "real" | "planned" | null; launch_note: string | null }
interface Link { from: string; to: string; stretches: Stretch[];
  data_rate_kbps: Quantity | null; margin_db: Quantity | null }
interface Contact {
  nodes: Node[]; links: Link[];
  numbers: { direct_h: Quantity; via_relay_h: Quantity;   // relay as a lo/hi range
             either_h: Quantity; station_hears_h: Quantity;
             longest_unheard_h: Quantity; longest_message_wait_min: Quantity;
             dark_and_unheard_h: Quantity };
  relays: { id: string; name: string; adds_h: Quantity; status: string }[];
  link_budget_note: string | null;             // "line of sight only: radio power not published"
  bookings: { station: string; start: string; end: string; entered_by: string }[];
}
```

Exports: `GET /missions/{id}/contact/plan?format=ion|csv&rate_bps=&start=&end=&relay=` (the same dates and
`relay` as the answer; ION needs `rate_bps`).
Rover: `GET /missions/{id}/contact/rover?rover=` →
`Section<{ viewshed_tile: string | null; out_of_sight_share: Quantity;
longest_out_of_sight_m: Quantity; resolvable: boolean; reason: string | null }>`.
Bookings: `POST /missions/{id}/contact/bookings`.

## Return (T4 B2, H)

`GET /missions/{id}/return` → `Section<Return>`

```ts
interface Zone { lat_deg: number; lon_deg: number; pm_km: number | null }  // null: size not published
interface SeaLimits { wave_height_m: Quantity; wind_m_s: Quantity }   // never null; missing until entered
interface Return {
  booster: { landing: "droneship" | "land" | "expended" | "unknown";
             zone: Zone | null;                 // droneship of a flown launch: position not published
             note: string;                      // plain words: where it came down, or the practice
             wave_height_m: Quantity | null;    // null for a landing on land
             wind_m_s: Quantity | null;
             limits: SeaLimits;                 // entered by the team (providers do not publish)
             hazard_area_seen: boolean | null } | null;   // null: cancelled, or vehicle not published
  capsule: { applicable: boolean; reason: string | null;
             zone: Zone | null;
             wave_height_m: Quantity | null; wind_m_s: Quantity | null;
             daylight: boolean | null;
             limits: SeaLimits;
             model_check: CapsuleModelCheck | null } | null;  // null: cancelled
}
// The capsule entry model flown from OSIRIS-REx's reconstructed entry state, against where
// its capsule landed (make validate-capsule); null when that check has not been run here.
interface CapsuleModelCheck {
  case: string; distance_km: number; distance_range_km: [number, number];
  limit_km: number; passed: boolean;             // false when distance_km is over limit_km
  atmosphere: string;                            // the air the fall went through, in plain words
  mission_team_km: number;                       // the mission's own simulation
  ellipse_99_km: [number, number]; measured_inside_ellipse: boolean;
  checked_at: string; sources: string[]; note: string;         // note: plain words
}
```

A mission still to fly whose booster may land on a droneship: `zone` is 700 km along the
next designed opportunity's launch direction, and `wave_height_m` / `wind_m_s` are
GFS-Wave's one forecast there (`provenance: "published"`, source the run's URL). A value
that is not there is `provenance: "computed"` with its `missing_reason` (nothing is
published for it). `meta.computed_at` is the time of the newest input (a catalogue's
compile date, the stored launch calendar, the GFS-Wave fetch, the team's limits), not
the time of the request; `meta.sources` lists where the landing or the practice is from.

## Data sources and jobs

`GET /feeds` → `{feeds: {provider, product, last_ok, age_s, stale, next_run, errors,
licence, breaker: "closed" | "open" | "half_open"}[]}` (Settings → Data sources).
`POST /feeds/{provider}/refresh` (named session).
`GET /jobs/{job_id}` → `JobRef` (+ `assessment_id` when done).
`/healthz` gains `feeds: {ok: number, stale: number, failing: number}` (degraded, never down).

## Named sign-in (ADR-17)

The body of `POST /auth/demo` (`{name, team?}`), the `user` in the answer and
`GET /auth/me` are in [api.md](api.md), *Sign-in*. Every write records that user.

## Changes

- 2026-09-27: v1.
- 2026-09-27 (requested by the frontend; built against these meanwhile):
  - Parts list: `GET /missions/{id}/parts` → `{parts: Part[]}`,
    `Part {id, name, part_number: string | null, serial: string | null,
    parent_item_id: string | null, status: "installed" | "spare" | "in_test" |
    "damaged" | "failed" | "lost", location: string | null, changed_at: string | null,
    changed_by: string | null}`. POST/PATCH take the same fields minus `id` and `changed_*`.
  - Risk scales: `GET /risk-scales` → `{default_id: string, scales: {id, name,
    source_url: string | null, likelihood: {level: number, words: string}[],
    consequence: {category, levels: {level: number, words: string}[]}[]}[]}`.
    POST/PATCH risks take `Risk` minus `id`.
  - Change history for any entered record: `GET /history?entity=ready_item|part|risk|booking|forecast|limits&id=`
    → `{entries: {at, by, before, after, note}[]}` (the readiness route may stay as an alias).
  - Writes' bodies: `POST /missions/{id}/ready/items` `{kind, name, organisation}`;
    `PUT /missions/{id}/launch/official-forecast` `{probability_pct, concerns: string[], pdf_url}`;
    `PUT /vehicles/{id}/limits` `{limits: {rule_id, value, unit, note: string | null}[]}`;
    `POST /missions/{id}/contact/bookings` `{station, start, end, note?}`.
  - Sea limits for Return: `PUT /missions/{id}/return/limits`
    `{booster: {wave_height_m, wind_m_s}, capsule: {wave_height_m, wind_m_s}}` (numbers or null).
  - Lessons per mission: `GET /lessons?mission={id}` adds `adopted: boolean` to each lesson.
  - Parameters: `GET /parameters` → `{parameters: {id, name, value: Quantity, note: string | null,
    changed_by: string | null, changed_at: string | null}[]}`; `PUT /parameters/{id}` `{value, note}`.
  - `Launch.vehicle_id` on `LaunchCalendar` (the vehicle whose limits apply), so the limits form knows where to write.
- 2026-09-27 (backend, as built):
  - `GET /feeds` rows also carry `provider_name` (plain words), `location` (pad or
    buoy id, or null), `data_time` (the time the data refers to: model run, issue
    time or newest reading), `staleness_budget_s` and `last_error`. `age_s` is the
    age of the data, not of the last fetch; `errors` is the number of failed
    attempts in a row. `stale` is also true when nothing has been recorded yet.
  - `POST /feeds/{provider}/refresh` → `{provider, products, message}`.
  - `POST /jobs/{job_id}/retry` (named session) queues a failed job's key again.
  - `/healthz` is `degraded` when a feed is failing; stale data alone does not
    degrade it (each number already says its age).
  - A write from a session without a name answers 403 with type `.../name-needed`.
- 2026-09-27 (backend, Ready as built):
  - `ReadyItem` adds `state_known: boolean` (false for a prefilled item nobody has
    entered a state for: show "not entered yet"; such items are left out of `counts`)
    and `allowed_next: ReadyState[]`. `Ready` adds `not_entered: number`.
    Item ids are `{mission}--{suffix}` (no slash), e.g. `im-2--lander`.
  - For a flown mission every prefilled item is `ready` with the launch record as
    its evidence (`source: "public"`); for a planned one, `state_known` is false.
  - `PUT /ready/items/{item_id}/tests` `{kind, result, report_url, date}` records one
    environmental test (report link and date required unless `not_done`).
  - A 409 from `PATCH /ready/items/{id}` carries `detail.allowed` (the allowed states).
  - History entries add `action` (create, move, update, test, set, adopt, refresh).
  - `GET /parts/{id}/impact` adds `note`; `GET /landing-history` adds `since`,
    `note` and per attempt `cause_url`, `clps`, `mission_id`.
  - `GET /lessons` returns `{lessons: [...]}`; `POST .../adopt` → `{adopted, item_id}`.
  - `GET /risk-scales` scales add `notes`. The one scale shipped has five levels and
    no level words: GSFC-HDBK-8005A leaves them to a non-public procedure, so the
    project's own words are to be entered.
  - `GET /parameters` ids: `battery_limit_h`, `landing_sun_min_deg`,
    `landing_sun_max_deg`, `surface_days`; a value is missing (with the reason) until entered.
- 2026-09-27 (backend, Contact as built):
  - `Contact` adds `start`, `end`, `window_note` (which dates were used: the mission's
    surface dates by default, else the reference lunar day, said so), `light_time_s
    {min, max}`, `longest_wait_from` and `sun_total_h`. `Booking` adds `note`.
  - `dark_and_unheard_h` is the longest single stretch that is dark and out of contact.
  - With no relay planned, `via_relay_h` is missing ("No relay is planned") and
    `either_h` equals `direct_h`; with a planned relay whose orbit is not published,
    both are missing with that reason, and `relays[].adds_h` is missing too.
  - `data_rate_kbps` and `margin_db` are null (no lander radio figures are published);
    `link_budget_note` says so.
  - `GET /missions/{id}/contact/plan?format=csv|ion`: ION needs `rate_bps` (the lander's
    rate is not published; without it the answer is 422 saying so).
  - `POST /missions/{id}/contact/bookings` → the booking with `id`, `entered_by`, `entered_at`.
  - 409 `no-contact` when a mission has no landing spot or was cancelled.
- 2026-09-27 (backend, Trip as built for flown missions):
  - `Trip` adds `coverage_note` (NASA's reconstruction may cover the trip in separate
    stretches, as IM-1's does; numbers then describe only those) and `burns_note`.
    `burns` is empty: burns are not published with the reconstructions.
  - `samples[].heard` and `heard_h` are line of sight to a DSN antenna above its mask.
  - A mission that has not flown answers 200 with `source: "none"` and the reason;
    a flown one answers 202 with a job the first time.
- 2026-09-27 (backend, frontend's queue):
  - `Trip` adds `covered: Stretch[]`: the stretches NASA's reconstruction covers
    (never open-ended); anything between two is a gap with no data.
  - `GET /missions/{id}/trip/export?format=oem|csv` (default `oem`): the flown
    trajectory, Earth-centred SPICE J2000 (EME2000), every 10 minutes, one CCSDS OEM 2.0
    segment (or CSV `stretch` number) per covered stretch. 409 `no-export` for a mission
    with no flown trajectory.
  - Contact for a lander lost before landing (Peregrine) is 409 `no-contact`.
  - A "longest" of zero is never `open` (engines `net-3`, `traj-2`).
- 2026-09-27 (backend, Launch as built, engines `lw-1`, `traj-2`, `vis-2`):
  - `GET /missions/{id}/launch?from=&to=` (default: today for 90 days; at most 180; 422
    otherwise). 200 at once, with no opportunities and `none_reason`, when there is
    nothing to work from (cancelled; pad, vehicle or landing spot not published; no
    reconstructed launch of the vehicle); otherwise 202 with a job the first time.
  - `LaunchCalendar` adds `none_reason: string | null`, `start`, `end` (dates used;
    null for a flown mission), `dates_note`, and `vehicle_id` (as agreed).
  - `Opportunity` adds `basis: "reconstructed" | "designed" | "published"` (how `t0` was
    worked out), `note` (one or two plain sentences: how, and anything unusual such as
    a coast longer than any flown one), `azimuth_deg`, `dv_tli_m_s` and `coast_min`
    (Quantities; `azimuth_deg` is missing with the reason for a flown launch).
  - A flown mission (IM-1, IM-2, Blue Ghost 1, Peregrine) has one opportunity, id
    `{pad}-flown`: its launch worked out again from NASA's reconstruction (± seconds) or,
    for Peregrine, the published liftoff. `landing.time` is the published landing
    (± its precision); `sun_elevation_deg` then has `lo`/`hi` over that span.
  - A planned one (Griffin-1 today) has up to two opportunities a day, id
    `{pad}-{YYYYMMDDTHHMM}`: `t0` ± 44 min (`pm`), `landing.time` with `lo`/`hi` = the
    allowed landing stretch it falls in, `orbit_wait_days` `assumed` (its `source` says
    from what). `weather` is `forecast` within 16 days of now, else `none` (no
    climatology yet). `kind` is always `instantaneous`; `window_*` null.
  - `landing_rule` minimums are missing with the reason until entered in Settings; the
    calendar then counts any landing with the Sun up and rising and the Earth up.
- 2026-09-27 (backend, launch weather and Return as built, engine `wx-1`):
  - `GET /missions/{id}/launch/weather?opportunity=` (an id from the calendar, including
    `{pad}-flown`) or `?t0=&pad=`; 422 without either. Answers at once (no job).
    `LaunchWeather` adds `pad_id`, `vehicle_id`, `note` (one sentence on what is covered)
    and `range_note` (where `range_conflicts` come from, or why they are not known).
  - Rules are the vehicle's, word for word, from `weather_rules` (Falcon 9's published
    set; the range's lightning rules for every Eastern Range vehicle), plus any rule the
    team entered a limit for (`PUT /vehicles/{id}/limits`), which then shows
    `limit.provenance: "entered"`. A limit not published is missing with the reason.
  - `per_system` is listed for model and proxy rules only, always GEFS, ECMWF-ENS,
    AIFS-ENS in that order; a share is present only for a wind rule with a known limit
    and a recorded GEFS step within 3 h of `t0` (else `missing_reason` says which:
    past, beyond 16 days, not yet fetched, fields do not describe the rule). ECMWF and
    AIFS are not recorded yet. `one_forecast` is HRRR within 1 h of `t0` (value in the
    limit's unit, at the rule's height) and, when the National Weather Service's hourly grid
    holds a wind for the hour of `t0`, NWS (its 10 m wind carried to the rule's height on a
    neutral profile over open flat ground, roughness 0.03 m). Observation rules have `per_system: []` and
    `observed.state: "no_data"` with a plain `detail` (the lightning rules add NWS's
    chance of thunder in that hour). `climatology` is null (not built); `disagreement`
    is true when two systems put a wind rule on opposite sides (see the 2026-09-29 weather
    line under *Changes*), false otherwise.
  - `PUT /missions/{id}/launch/official-forecast` → the stored forecast with `id`,
    `entered_by`, `entered_at`. `PUT /vehicles/{id}/limits` → `{vehicle_id, limits:
    {rule_id, value, unit, note, entered_by, entered_at}[]}`; a wind rule takes mph, kt,
    m/s or km/h, any other rule its own unit (422 otherwise); it replaces the vehicle's list.
  - `GET /missions/{id}/return`: `booster` adds `note` (plain words: where it came down,
    or the vehicle's practice and the flown CLPS landings); `zone.pm_km` is
    `number | null` (null when the zone's size is not published); a droneship's zone is
    null (its position is not published, only 700 km downrange). `wave_height_m` is null
    for a landing on land. `capsule` adds `limits`. `booster` and `capsule` are null for
    a cancelled delivery; `booster` is null when the vehicle is not published.
  - `PUT /missions/{id}/return/limits` (numbers above zero or null) → the `Return` section.
    Changes are in `/history?entity=limits&id={vehicle}` and `id=return:{mission}`,
    and `entity=forecast&id={mission}`.
  - The feeds worker also records GEFS (`nomads/gefs_launch/{region}`) at the steps
    nearest each designed opportunity's `t0` within 16 days (at most 6 per run).
- 2026-09-27 (backend, frontend's queue): a queued `JobRef.message` says how many answers
  are being worked out before it ("Waiting for a compute worker; 2 answers are being worked
  out first."). `run.py` starts two compute workers (`POLAR_COMPUTE_WORKERS` to change).
- 2026-09-27 (backend, C3/C4 and the frontend's queue; engines `traj-3`, `lw-2`):
  - `Trip.burns` lists the burns found in NASA's reconstruction up to the arrival at the
    Moon, each shown as one instant, named in plain words: "Burn near the highest point of
    the orbit" / "... lowest point ...", "Leaving Earth for the Moon", "Correction 1", …,
    "Entering lunar orbit". `dv_m_s` has no ± (its `no_margin_reason` says how far the
    paths before and after the burn meet). `burns_note` says what is not seen (burns in a
    gap of the reconstruction, burns in lunar orbit) and, for Peregrine, the steady push.
  - `Trip` adds `corrections: Corrections | null` and `corrections_note: string | null`
    (why there is none: not flown, did not reach the Moon, no plan):
    ```ts
    interface Corrections {
      label: string;                 // "A budget for these assumed errors, not a prediction …"
      burns: { name: string; t: string; p95_m_s: Quantity; p99_m_s: Quantity }[];  // three
      total_p95_m_s: Quantity; total_p99_m_s: Quantity;  // p99 lo/hi = 95 % bootstrap interval
      linear_p99_m_s: Quantity;      // the same worked out linearly (a check)
      arrival_altitude_km: Quantity; // median, lo/hi = 1st and 99th percentile
      runs: number; missed: number;  // runs with no close pass of the Moon, counted
      assumptions: { what: string; value: string }[];   // every error is assumed
      plan_note: string; flown_note: string;
    }
    ```
  - `Opportunity` adds `weather_note: string`. `weather: "none"` means no forecast numbers;
    the weather route still answers with the rules and limits for any opportunity
    (flown, past, or beyond 16 days), and `weather_note` says which.
  - Launch calendar: one opportunity per sweep of the climb plane past the Moon's
    direction, which happens twice a sidereal day; instants of the same sweep within 12 h
    (aimed at different landings) are one opportunity, the one reaching the earliest
    landing. Two of any three opportunities in a row are at least 12 h apart; a calendar
    day holds at most two except when one sweep's instant falls just after midnight and
    the next day's just before the following midnight.
  - Plain words: no "TLI" in notes or reasons ("leaving Earth for the Moon"). A feed with
    no data says so without the fetch error; `range_note` has no developer text.
  - The assumed lunar-orbit wait (a lander with no flown precedent) is 1 d with no range;
    its `no_margin_reason` gives the flown landers' waits as a choice, not a spread.
  - `GET /vehicles/{id}/limits` → `VehicleLimits` (with each limit's `note`); 404 for an
    unknown vehicle. `RuleRow` adds `units: string[]` (units a limit can be entered in, the
    published one first; empty = no unit published, any unit taken) and `limit_note`
    (the team's note with an entered limit). A missing limit carries `units[0]` as its
    unit (was `""` for wind rules).
- 2026-09-27 (backend, B0/B2 GFS-Wave):
  - The feeds worker records `nomads/gfswave/florida`: GFS-Wave's latest run at 24 and 48 h
    and at the steps nearest upcoming designed opportunities (at most 8), on a one-degree
    lattice of its grid over the sea east of the Cape (26–32° N, 80–70° W): significant wave
    height, main wave period, wind at 10 m.
  - `Return.booster` for a mission still to fly whose booster may land on a droneship:
    `zone` is the point 700 km (the flown CLPS droneship distance) along the next designed
    opportunity's launch direction from its pad (`pm_km` null), and `wave_height_m` /
    `wind_m_s` are GFS-Wave's one forecast there at the step nearest that liftoff (within
    1.5 h, lattice point within 80 km), `provenance: "published"`, source the run's URL; the
    `note` says where and for which opportunity. Otherwise they are missing with the reason.
- 2026-09-27 (backend, B0/B1 GLM):
  - The feeds worker records `goes/glm/{florida|vandenberg}` (GOES-19 / GOES-18 lightning
    mapper, AWS open data): for each pad, the good-quality flashes within 20 nmi in the last
    half hour (distance, time) and the counts within 5, 10 and 20 nmi. It fetches only while
    a designed opportunity from the region is less than six hours away (half an hour is
    about 90 files, 22 MB); otherwise the row stays without data.
  - `RuleRow.observed` for the lightning rule is `clear` or `seen` when the launch time is
    within six hours (or one hour past) and a recent GLM half hour is recorded; the `detail`
    gives the count within the rule's distance, the half hour and the last flash, and says
    it is now, not at the launch time. Otherwise `no_data` as before.
  - `GET /feeds` lists the new products; provider `goes` ("NOAA GOES lightning mapper").
- 2026-09-27 (backend, B1 wind climatology; engine `lw-3`):
  - `RuleRow.climatology` is filled for a wind rule with a known limit (published or
    entered, in a speed unit): `share` = how often NASA POWER's hourly wind at 50 m (MERRA-2
    reanalysis; the rule's 162 ft is 49 m) was above the limit in the launch's month and UTC
    hour, `years` "2001-2024", `source` in words (hours counted, and that a reanalysis
    cell's hourly mean is smoother than the pad's tower). Null for every other rule.
  - A designed opportunity more than 16 days ahead says `weather: "climatology"` when the
    vehicle has a published wind limit and the pad's region has a climatology (Falcon 9 at
    the Cape and Vandenberg); otherwise `none`. `weather_note` says which.
  - `make climatology` rebuilds `data/climatology/power_ws50m_{region}.json` (keyless).
- 2026-09-27 (backend, T4 Verification):
  - `Share.checked` for a wind rule's GEFS share is true only when `make hindcast-weather`
    found that rule passing the plan's gate at the pad's region. The 2025 check at KXMR
    does not pass (1 event in 682 verified runs), so it stays false; the weather answer's
    `meta.uncertainty` part "Checked against observations" gives the scores in one
    sentence, and `note` says whether any rule has passed.
- 2026-09-28 (backend, frontend's queue):
  - The `Return` block above now shows the shape as served (`note`, `capsule.limits`,
    nullable `pm_km`, `SeaLimits` never null, GFS-Wave values at a planned droneship zone).
  - A missing sea or wind value in Return is `provenance: "computed"` (was `"published"`),
    with its `missing_reason`. `booster.note` no longer names its source inline; the source
    is in `meta.sources` (Launch Library 2's landing records, or the vehicle's record).
    `meta.computed_at` is the newest input's time, not the request's.
  - `DELETE /missions/{id}/launch/official-forecast` (named session) takes back the forecast
    shown (the latest entered) → `{removed_id, official}` where `official` is the forecast
    entered before it, now shown again, or null. 404 `nothing-to-remove` when none is
    entered. Recorded in `/history?entity=forecast&id={mission}` with `action: "delete"`.
- 2026-09-28 (backend, lightning climatology; engines `lw-4`, `wx-2`):
  - `RuleRow.climatology` is also filled for the lightning rules (`er-lightning`,
    `er-thunderstorm`) when the pad's region has a thunder climatology: `share` = how often
    thunder could be heard in the pad's 0.05-degree grid cell in the launch's month and UTC
    hour, `years` "2019-2025", `source` in words (hours with thunder of the hours seen by the
    lightning mappers, and that thunder at the pad is not the rule's own distance). From NASA
    MSFC's Combined GLM Hourly Thunder Hour data (GHRC DAAC, doi:10.5067/GLM/HTH/DATA301).
  - A designed opportunity more than 16 days ahead says `weather: "climatology"` also when
    only the thunder climatology can be read (a lightning rule applies to the vehicle);
    `weather_note` names what the weather tab shows.
  - `make thunder-climatology` (needs `PW_EARTHDATA_TOKEN`) rebuilds
    `data/climatology/glm_thunder_{region}.json` through NASA Earthdata's OPeNDAP (only the
    pads' cells are read; a day's file is 600 MB).
- 2026-09-28 (backend, radiation screening; engine `rad-2`):
  - `Trip.radiation` is filled for a flown trip (and `Trip` adds `radiation_note: string |
    null`, why there is none). It keeps the contract's fields and adds:
    ```ts
    interface Radiation {
      belt_hours: Quantity;               // factor 2; open = the climb out before NASA's
                                          // reconstruction is not counted (a lower bound)
      belt_passes: number;
      electron_fluence_gt1mev: Quantity;  // cm^-2, AE8, factor 2
      fluence_gt10mev: Quantity;          // cm^-2, trapped protons (AP8), factor 2
      gcr_dose_mgy_day: Quantity;         // mGy/d in silicon, ± 30 %, before shielding
      surface: { site_id: string; open_sky: Quantity;        // 1 = flat horizon
                 gcr_dose_mgy_day: Quantity } | null;        // at the landing site
      surface_note: string | null;        // why no surface dose (no skyline for the site;
                                          // it did not land), or why it is assumed
      sep_events: { t: string; link: string }[];   // NOAA >10 MeV threshold crossings
      sep_note: string;                             // during the trip (NASA DONKI)
      scenarios: { id: string; name: string; fluence_gt10mev: Quantity;
                   fluence_gt30mev: Quantity; source_url: string }[];  // Oct 1989, Oct 2003, Aug 1972
      screening_note: string; confirm_in: string[];  // SPENVIS, OLTARIS, CREME-MC
    }
    ```
    Each computed Quantity's `source` says in words how it was worked out (the maps and why
    MIN or MAX, the other maps' value; the measured reference and the modulation scaling).
    A past event's `no_margin_reason` gives the measurement and NOAA's listed peak.
  - `make space-climate` rebuilds `data/radiation/{oulu_nm_monthly,sep_scenarios,
    donki_sep_goes}.json`; `make validate-radiation` prints the docs/validation.md tables.
- 2026-09-28 (backend, space weather now):
  - `GET /space-weather` → `Section<SpaceWeather>` (public, answers at once, no job):
    ```ts
    interface SpaceWeather {
      now: { kp: Quantity; proton_10mev_pfu: Quantity; proton_100mev_pfu: Quantity;
             xray_class: string | null; solar_wind_km_s: Quantity; bz_nt: Quantity;
             alerts: string[];                          // SWPC headlines of the last 24 h
             xray_missing_reason: string | null;        // why no xray_class
             alerts_missing_reason: string | null };    // null: the list is current
      outlook: { issued: string | null; days: string | null;
                 s1_or_greater_pct: number[] | null;   // SWPC's day 1-3 chance, verbatim
                 kp_max_expected: number | null; text: string | null;  // the 3-day forecast
                 missing_reason: string | null };
      donki: { cme: { id; start; speed_m_s; earth_arrival_estimates; link }[];
               flares: { id; peak; class; link }[];
               sep: { id; time; instruments; link }[];
               counts: { cme: number | null; flares: number | null; sep: number | null };
               days: number | null; missing_reason: string | null };  // lists: newest 20
      note: string;
    }
    ```
    Each `now` number is `published` with the SWPC URL, or missing with the feed's reason;
    `meta.computed_at` is the newest reading's time and `meta.stale` says if any is past its
    budget. No dose here: doses are in `Trip.radiation`.
- 2026-09-28 (H): `Return.capsule.model_check` (`CapsuleModelCheck | null`): the capsule
  entry model against OSIRIS-REx's landing (9.5 km, limit 10 km; 99 % area 51.4 by 21.4 km
  holds the real point), with a plain-words `note`. For a mission that returns something
  (none of the CLPS ones) `applicable` is true and `reason` says no entry state is published.
- 2026-09-28 (frontend queue): `GET/PUT /vehicles/{id}/limits` for an unknown vehicle is a
  404 `vehicle-not-found` problem (was `mission-not-found`). `Opportunity.weather_note` and
  `LaunchWeather` notes say "the weather rules show …" (no "tab"). `Trip.burns_note` for a
  trip with no burn found says so for that trip (the stretches the reconstruction covers up
  to the arrival) before the method.
- 2026-09-28 (hardening, track I):
  - Every write is refused past its allowance with **429** `too-many-requests` and
    `Retry-After` (seconds), per client address in a sliding minute: sign-in 60, AI
    assistant 20, site comparison 60, every other change 120. Reads are never limited.
  - A request body over 64 KB is refused with **413** `too-large`.
  - A section that needs a new job while 200 jobs already wait answers **503** `queue-full`
    with `Retry-After: 60` (joining a job already queued for the same key still works).
  - Settings changes and job retries are in the history: `GET /history?entity=settings&id=ai|agent_runs|cache`
    (`action`: `set`, `reset`, `retry`, `delete`) and `GET /history?entity=job&id={job_id}`
    (`action: "retry"`, `after.job_id` the new job). `entity` also takes `parameter`,
    `lesson`, `milestone`, `feed`.
  - Input bounds (422 `invalid-request` past them): numbers must be finite; sea limits
    `wave_height_m` ≤ 30, `wind_m_s` ≤ 100; vehicle limit `value` ≤ 10^6 and `rule_id` ≤ 64
    chars; forecast `concerns[]` ≤ 500 chars each, `pdf_url` ≤ 2,000; risk `scale_id` ≤ 64,
    `ratings` 1–20, each link list ≤ 200 ids of ≤ 160 chars; booking `station` ≤ 64 chars
    and a booked pass at most 24 hours (a longer one is a 422 `bad-request`); agents'
    `site_id` ≤ 160.
  - CORS now allows `PATCH` (readiness items, parts, risks); browsers were refused it.
  - A queued `JobRef.message` says the compute worker is not running only when nothing is
    ahead of the job; contact jobs are worked out before launch calendars, and those before
    trips (cheapest first).
- 2026-09-28 (backend, D1 climb direction; engine `lw-5`):
  - Launch: a designed `Opportunity` climbs at the mean inertial azimuth of the vehicle's
    direct lunar flights (Falcon 9: 87.7°; due east with ± 44 min when it has none);
    `azimuth_deg` is that value (`assumed`, the flights named in `no_margin_reason`) and
    `t0.pm` is 18 min (was 44). A climb outside the pad's azimuth limits (over the ground)
    gives no opportunities, with `none_reason`. A flown opportunity's `azimuth_deg` is now
    `computed` (was missing): the inertial azimuth from NASA's reconstruction, the ground
    azimuth and the pad's limits in `no_margin_reason`.
- 2026-09-28 (backend, the frontend's queue; engine `rad-3`):
  - `LaunchWeather.space_weather_now` is dropped (use `GET /space-weather`);
    `LaunchWeather.official` adds `id`. `PUT .../official-forecast` answers the stored row's
    `entered_at` (was the request time), so both answers carry the same time.
  - `GET /space-weather`: `now.xray_missing_reason`, `now.alerts_missing_reason` (null when
    the list is current, so `[]` means no alert in 24 h), `donki.counts {cme, flares, sep}`
    (how many DONKI gave; the lists keep the newest 20). SWPC's alert list and DONKI's lists
    have no `issued_at`: they are as new as the last fetch that found them current, which a
    source's `fetched_at` now gives (an unchanged body adds no snapshot).
  - `Return.meta.sources`: the Launch Library 2 and vehicle catalogue sources carry
    `fetched_at`, the date the record was read.
  - `Trip.radiation`: `belt_hours`, `electron_fluence_gt1mev` and `fluence_gt10mev` are
    missing with the reason when nothing is counted and the reconstruction starts beyond the
    belts (IM-1); `surface` is null with `surface_note` for a lander that did not land
    (Peregrine); `surface.open_sky` is `assumed` and `surface_note` says so where the
    elevation model does not cover the site (Blue Ghost 1); `sep_note` says "One solar
    particle event … its" / "2 … events … their".
- 2026-09-29 (backend, planned relays in Contact; engine `net-4`):
  - `GET /missions/{id}/contact?relay=` (repeatable, at most 3): planned relays from the catalogue to
    add to the mission's own, to see what each would add. 422 for an unknown id or a real orbiter
    kept only to check pass calculations (LRO, Danuri, Chandrayaan-2, CAPSTONE).
  - `Contact.relays[]` adds `via_h` (time the lander can reach Earth through that relay),
    `launch_status` (the catalogue status), `for_this_mission` (false for an added one),
    `orbit {periapsis_km, apoapsis_km, inclination_deg, arg_periapsis_deg, period_h}` (Quantities:
    heights above the mean radius; `published` with `source`, or `assumed` with `lo`/`hi`),
    `orbit_note` and `sweep_note` (what was swept; null when nothing was worked out). `status`
    stays the launch note.
  - With a relay whose orbit is known, `via_relay_h`, `either_h`, `relays[].adds_h`,
    `relays[].via_h`, `longest_unheard_h` and `longest_message_wait_min` are ranges
    (`provenance: "assumed"`, `lo`/`hi`, value = the middle) over the relay's unknown node and
    phase (36 x 36) and both ends of any assumed inclination or argument of periapsis. "Through the
    relay" = the relay in view of the lander and of Earth at once (geometry, as `direct_h`);
    "heard" through it = in view of the lander and of a ground station at once (the Moon may hide
    the relay from the station); a message may wait on the relay (store and forward).
  - `Contact.direct_only {longest_unheard_h, longest_message_wait_min}` (null without a relay):
    the same two numbers without the relay. `Contact.relay_note`: one plain sentence.
    `longest_wait_from` and `links` stay direct-only; the contact plan export lists direct
    contacts only (a relay's passes depend on its unknown placement).
  - Catalogue: Lunar Pathfinder heights 673.4 × 7331.8 km (ESA), inclination assumed 46.8–54.9°
    (two figures in circulation), argument of periapsis assumed 85–95°; Altus-1's orbit is not
    published and is assumed from NASA's LCRNS reference constellation 3.1 (five frozen orbits:
    1745–1751 × 17391–17427 km, 52.5–59.4°, 85.4–92.5°, about 30 h).
- 2026-09-29 (backend, real orbiters in Contact; plan F2):
  - `Contact.orbiters[]`: `{id, name, operator, naif_id, note, source: SourceRef | null,
    covered: Stretch | null, passes: (Stretch & {max_elevation_deg})[], pass_count, in_view_h,
    longest_pass_min, longest_gap_h}` for LRO, Danuri, Chandrayaan-2 and CAPSTONE: when each
    is above the landing spot's skyline (a point; 30 s grid, edges bisected), from JPL Horizons'
    trajectory the feeds worker records. `in_view_h.pm` sums the edges' skyline timing; the
    numbers are missing with the reason when no trajectory covers the dates (the feeds keep a
    week ago to 30 days ahead, and each flown mission's surface days). `Contact.orbiters_note`:
    geometry only, never a relay service; the orbiters are not `nodes` and not in any number.
  - `GET /feeds` adds provider `horizons`, product `vectors`, one row per orbiter (location
    = its id) and per orbiter and flown mission (`lro@im-2`); CAPSTONE's weekly row records
    "no trajectory after 14 August 2026" as data (stale, not failing).
- 2026-09-29 (backend, rover line of sight; plan F5, engine `los-1`):
  - `GET /missions/{id}/contact/rover?rover=&radius_m=&lander_antenna_m=&rover_antenna_m=&freq_mhz=`
    → `Section<RoverOut>` or 202 `JobRef` (a `rover` job; cheapest first). Rovers are the mission's
    listed rovers and payloads that move (`im-2/yaoki`, `griffin-1/flip`, `im-3/cadre`,
    `im-3/lvx`); default the first. 409 `no-rover` without one; 422 for an unknown rover or a
    value out of range (radius 50–5000 m, default 500; antennas 0–50 m, defaults 2 m and 0.5 m;
    30–100000 MHz, default 2400; the defaults are `assumed` and say so).
  - `RoverOut` = the contract's fields plus, as the frontend asked: `rover {id, name}`,
    `share_basis: "drive" | "ground" | null` (always `ground` today: no drive is published),
    `radius_m`, `viewshed {bearings_deg (72, every 5°), ranges_m (20), sight, radio}` with
    states `"clear" | "blocked" | "uncertain"` indexed [bearing][range]; also
    `radio_not_clear_share` (%, the radio path's twin of `out_of_sight_share`), `assumptions
    {lander_antenna_m, rover_antenna_m, radio_mhz}`, `terrain {product, post_m,
    vertical_error_m}` and `note`. Shares are percent over the ground within `radius_m`, each
    cell weighted by its ring: `lo` counts blocked cells, `hi` blocked and uncertain, the value
    is their middle (no margin when nothing is uncertain). `longest_out_of_sight_m` is missing
    (no drive is published). `viewshed_tile` is null (no tile layer yet).
  - A site north of 80° S (outside the polar terrain model) answers 200 at once with
    `resolvable: false`, the reason, `viewshed`, `radius_m`, `share_basis`, `assumptions` and
    `terrain` null and the numbers missing.
- 2026-09-29 (backend, D1 launch windows; engine `lw-6`; no shape change):
  - `kind`/`window_open`/`window_close` of a flown launch are what Launch Library 2
    published: Peregrine (07:18–08:03 UTC) and Blue Ghost 1 (06:06–06:45 UTC) are `window`,
    IM-1 and IM-2 `instantaneous`. The note says which.
  - A planned opportunity is `window` only when the vehicle's direct lunar launches were
    published with windows (it steers); its ends are the instants designed at the pad's two
    azimuth limits, `t0` stays the instant at the climb direction used. Falcon 9's (IM-1,
    IM-2) were single instants, so Griffin-1 stays `instantaneous`; a vehicle with no
    direct lunar launch is shown as an instant and the note says it is not published.
  - `data/missions.json` `t0` may carry `window_open`/`window_close` (UTC, equal for a
    single instant); `GET /missions` does not show them.
- 2026-09-29 (backend, relay contacts in the contact plan; engine `net-5`; the frontend follows):
  - `GET /missions/{id}/contact/plan?format=ion|csv` takes `start`, `end` (the frontend already sent
    them and they were ignored, so a plan was for the default dates) and `relay=` (repeatable, at most 3,
    as for the answer: a relay that is not the mission's own is added to the graph). Without `relay` the
    plan lists direct contacts only, as before. A relay asked for is listed with its contacts at ONE
    placement of the 5,184 swept (its node and phase are unknown), the one whose time through the relay
    is nearest the middle of the range: `lander` to the relay (above the landing spot's skyline) and the
    relay to each station (above its mask, the Moon not in the way), edges from 5-minute samples. CSV:
    a sixth column `basis` (`direct`, or `planned relay; node .. deg, phase .. deg, one of 5184
    placements`). ION: `#` lines say the relay is PLANNED, which placement, that it is not a forecast,
    and the ranges (time through it, time it adds) over all placements; then `a contact` and `a range`
    per contact, the range from that link's farthest light time. 422 when a relay asked for has no
    usable orbit or is not a relay service.
  - The contact job keeps each relay's links at that placement beside `data` (a `plan` key of the
    stored result, never in the section); `net-4` answers are worked out again. No shape of the
    section changes.
- 2026-09-29 (backend, the rover's line of sight as map tiles; no engine change):
  - `RoverOut.lander {lat_deg, lon_deg}` (null with no map) is where the viewshed is centred, so a map can
    place the tiles. `RoverOut.viewshed_tile` is filled (it was null): `/tiles/viewshed/{answer}/{z}/{x}/{y}.png` under
    `/api/v1`, with the stored answer's own number in it, so a tile never changes; null with no map
    (not resolvable). `GET /tiles/viewshed/{answer}/{z}/{x}/{y}.png?layer=sight|radio|terrain`
    (default `sight`): 256 px PNG in the terrain tiles' scheme (a quadtree over the regional model's
    +-303,960 m, x east, y south) to zoom 12 (the terrain tiles stop at 7); 204 where the layer draws
    nothing, which is most of the grid.
  - `sight` and `radio` draw each cell as the twin lists it (cells end half way between the sampled
    ranges and each bearing covers +-2.5 degrees): clear is Earth's blue filled, blocked dark with 45
    degree stripes, uncertain a light wash with -45 degree stripes, all translucent so the relief shows
    through. `terrain` is the hillshade of the elevation model the answer read, the 20 m window at the
    landing spot where there is one (the regional 80 m model is blocks at a rover's scale).
  - 404 `no-viewshed` (no such answer, not a rover answer, or nothing to draw), `unknown-layer`,
    `tile-out-of-scheme`; 422 past zoom 12; 503 `dem-missing` for `terrain`. Tiles are cached under
    `data/tiles/viewshed/{answer}/` and can be deleted at any time.
- 2026-09-29 (backend, the relays a comparison can add; no engine change):
  - `GET /relays` (no session; answers at once) lists the relay services in the catalogue, in its order:
    `{relays: [{id, name, operator, status, launch_note, orbit_known, orbit_note, serves_missions}]}`.
    `id` is what `?relay=` takes on the contact answer and its plan. `orbit_known` is false when a relay's
    orbit lacks a height, the tilt or the argument of periapsis: it can still be compared (the answer says
    time through it is not worked out) but the plan refuses it with 422. `serves_missions` are the missions
    it is planned for, where it is in the answer already. Real orbiters kept only to check pass
    calculations are not listed.
- 2026-09-29 (H): `Return.capsule.model_check.atmosphere` (string, always present): the air the
  modelled fall went through and what it was given, in plain words: NRLMSISE-00 driven by the
  entry day's solar radio flux and geomagnetic activity (10.7 cm flux 174.1 the day before, ap 4
  at the time), or the U.S. Standard Atmosphere 1976 with the reason when the day's values are not
  on disk. With that air the check is 12.1 km from the real landing point (9.4 to 14.8 over the
  drag range) and `passed` is false against the 10 km limit (the standard atmosphere gave 9.5 km,
  6.7 to 12.2); `note` names the air and gives the distance in the others. `ellipse_99_km` is now
  51.2 by 21.8.
- 2026-09-29 (weather, no shape change): `per_system[].share.checked` is now true for the Falcon 9 wind
  rule at Vandenberg's pads, for a launch up to 48 h ahead: the 13-year GEFS reforecast against KVBG
  passes the plan's gate (Brier skill 0.37 at 24 h, 0.22 at 48 h, 95 % 0.15 to 0.57 and 0.02 to 0.42;
  reliability within 0.1). It stays false at the Cape (CRPS skill -0.95 at 24 h: the runs' wind is worse
  than the station's own record) and for a launch further out than 48 h, where `LaunchWeather.note` says
  the check reached only 48 h. The meta part "Checked against observations" gives the numbers.
- 2026-09-29 (backend, relay catalogue; no shape change): `data/catalogues/relays.json` lists IM-4's two lunar data
  relay satellites (`im-4-relay-1`, `im-4-relay-2`), planned for 2027 as Intuitive Machines' release of 8 April 2025
  says (read as distributed through GlobeNewswire; the company's own pages did not load). The release names neither
  satellite and gives no orbit, so the ids are this project's labels, no orbit is assumed and every orbit field says
  "Not published": `GET /relays` gives `orbit_known: false` and the contact answer's `adds_h` and `via_h` for them are
  `missing_reason`, not a number. `data/missions.json` gives IM-4 no `comms.relays`, so `for_this_mission` is false
  for them until it does (not a catalogue matter).
- 2026-09-29 (weather, additive): `OneForecast.note` (string or null) says how that forecast did against a
  weather station's record: HRRR's, from `data/hindcast/hrrr_wind_{region}.json` (`make hindcast-hrrr`,
  the 10 m wind at KXMR or KVBG for 2021-2025 at the lead nearest the step shown, and its over/under
  call at the limit brought to 10 m); NWS's says it keeps no archive, so it cannot be checked.
  `RuleRow.disagreement` is now worked out and `RuleRow.disagreement_note` (string or null) says who
  disagrees and how. NWS, which is now listed in `one_forecast` beside HRRR when its grid has the hour,
  and HRRR each disagree with GEFS when their side (over/under) is the one GEFS's 95 % share interval
  excludes (entirely below one half for over, entirely above for under); NWS and HRRR disagree with
  each other when on opposite sides and further apart than HRRR's measured 10 m error (its RMSE at
  that lead, carried to the rule's height), or on opposite sides at all when that is not known. It
  stays false when only one system has an answer.
- 2026-09-29 (feeds, additive): `GET /feeds` rows carry `note` (string or null). For a product fetched only
  while a launch is near (today `goes/glm`, in the six hours before an opportunity) it says so, and `stale`
  is judged by when the worker last asked (`last_ok`) and not by the data the product holds, so an empty
  one is idle and not "stale"; `age_s` is still null with no data. `LaunchWeather.meta.stale` no longer
  counts an old GLM snapshot, which is not shown and not part of the answer then. No shape change to the
  launch weather. `nomads/gefs_launch` (the GEFS steps nearest each opportunity) had been refused every time
  since its cost, 373 requests, was more than the provider's allowance holds (120); it now costs at most
  what the bucket holds and a run already fetched whole is not asked for again.
- 2026-09-29 (weather, no shape change): `per_system[].share.checked` is false again for the Falcon 9 wind
  rule at Vandenberg's pads, so it is false at both pads and `LaunchWeather.note` reads "None has passed a check
  against observations yet." again for both. The 13-year GEFS reforecast is now scored on all 1,583 days
  planned (it was 845 when the earlier line saying it is true at Vandenberg was written): the Brier skill still clears the plan's 0.1 (0.30 at
  24 h, 0.24 at 48 h, 95 % 0.16 to 0.41 and 0.09 to 0.38), but the reliability bin for a share of 1.0 now holds
  41 cases (20 before, too few to count) and the wind was above the limit in 36 of them, 0.88 against a share of
  1.0, past the 0.1 the gate allows, so `passes` is false; the meta part "Checked against observations" gives the
  numbers. The Cape stays false (CRPS skill -0.97 at 24 h, 95 % -1.08 to -0.86). `OneForecast.note` for HRRR
  now carries the 95 % range of its skill against the station's usual wind and says "no higher or lower"
  where its lean rounds to nothing. No field is added or removed.
- 2026-09-29 (trip, additive): `Assumption` in `Corrections.assumptions[]` gains `basis` ("published" | "assumed")
  and `source` (string | null). Where a launch vehicle user's guide gives orbital injection accuracies (Falcon 9,
  Vulcan, New Glenn), `basis` is "published" and `source` cites the guide, table and page; where unpublished,
  `basis` is "assumed" and `source` is null. `Corrections.label` clarifies that errors are assumed except where
  the launch vehicle's guide publishes them.
- 2026-09-29 (return, no shape change): `Return.capsule.model_check.atmosphere` default is now NRLMSIS 2.1 (Emmert
  et al. 2022) driven by the entry day's solar flux and ap indices. Independent mesospheric measurements (TIMED/SABER
  136 profiles and Table Mountain Rayleigh lidar 9 nights) pick NRLMSIS 2.1 over NRLMSISE-00 (RMS density bias
  0.6 % and 1.6 % vs 3.7 % and 5.0 %). With NRLMSIS 2.1, the OSIRIS-REx landing distance is 6.6 km (3.9 to 9.3 km
  over the drag range), satisfying the plan's 10 km limit (`passed: true`). Ellipse 99 % is 51.1 by 21.5 km (43.7 by
  0.3 km with no wind).
- 2026-09-30 (backend, Contact and Orbiters; engines `net-6`, `los-2`): `Node.status` gains
  `"launched_not_operating"`. `Orbiter.note` is `string | null` (says only where its recorded
  trajectory stops short of the dates, null when it covers them all; `orbiters_note` keeps the
  general caveat). Plain words: `Viewshed.radio` and `RoverOut.radio_not_clear_share` say "the space
  around the line of sight that the radio signal needs".

