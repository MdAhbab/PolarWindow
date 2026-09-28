# Lifecycle API contract (v1, 2026-09-27)

The shared contract between the backend and the frontend for the six mission
sections: **Ready · Launch · Trip · Landing (existing surface screens) · Contact · Return**.
The backend implements these shapes exactly; the frontend builds against them
(fixtures first, then the generated `schema.ts`). A change to a shape is made
here first, with a line in *Changes* at the bottom, then in code.

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
  one_forecast: { system: "NWS" | "HRRR" | "GEOS-FP"; value: Quantity; over: boolean }[];
  disagreement: boolean;
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

Exports: `GET /missions/{id}/trip/export?format=oem|spk|csv`.

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

Exports: `GET /missions/{id}/contact/plan?format=ion|csv`.
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
  limit_km: number; passed: boolean; mission_team_km: number;   // the mission's own simulation
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

`POST /auth/demo` accepts an optional body `{name: string, team?: string}`
(no body: name "Demo project manager"). The response adds
`user: {id: number, name: string, team: string | null}`. Every write records
that user. `GET /auth/me` returns the same `user`.

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
    limit's unit, at the rule's height). Observation rules have `per_system: []` and
    `observed.state: "no_data"` with a plain `detail` (the lightning rules add NWS's
    chance of thunder in that hour). `climatology` is null (not built); `disagreement`
    is false (one system).
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
