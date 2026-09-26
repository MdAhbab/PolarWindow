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
  official: { probability_pct: number; concerns: string[]; pdf_url: string;
              entered_by: string; entered_at: string } | null;
  space_weather_now: { kp: Quantity; proton_10mev_pfu: Quantity; xray_class: string | null;
                       alerts: string[] };
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
interface Return {
  booster: { landing: "droneship" | "land" | "expended" | "unknown";
             zone: { lat_deg: number; lon_deg: number; pm_km: number } | null;
             wave_height_m: Quantity | null; wind_m_s: Quantity | null;
             limits: { wave_height_m: Quantity | null; wind_m_s: Quantity | null };
             hazard_area_seen: boolean | null } | null;
  capsule: { applicable: boolean; reason: string | null;
             zone: { lat_deg: number; lon_deg: number; pm_km: number } | null;
             wave_height_m: Quantity | null; wind_m_s: Quantity | null;
             daylight: boolean | null } | null;
}
```

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
