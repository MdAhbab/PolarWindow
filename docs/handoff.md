# Handoff

State as of 2026-11-12. This file describes how the product is put together, the rules
that do not bend, how to run and check it, the shapes the frontend work needs, and where a
review should look hardest. The plan for the experience work is `docs/experience-plan.md`.
The wire contract between frontend and backend is `frontend/src/lib/api/experience.types.ts`;
the generated one is `docs/openapi.json` and `frontend/src/lib/api/schema.ts`.

## 1. How the product is built

The app answers four numbers for a mission or a site (sunlight hours, contact hours, the
longest night, the longest time without contact), each with a margin and a source, and
never blends them into a score. On top of that sit the lifecycle steps (Ready, Launch,
Trip, Surface, Contact, Return), the Ask dock, project entry from a file or by hand, and
"what if" scenarios.

### Layout of the work

| Piece | Where | ADR |
|---|---|---|
| Shell, Home, Ask dock, activity tray, mission hub | `frontend/src/components/{AppShell.tsx,home,activity,ask,lifecycle}`, `screens/{HomeScreen,MissionHub}.tsx` | |
| Project skyline job, honest step states, scenario re-run when a phase failed | `backend/app/workers/handlers/site_build.py`, `services/{sections,scenario,job}_service.py` | |
| Projects, file intake, scenarios, presets, activity | `backend/app/services/`, `api/v1/routes/`, `workers/presets.py`; screens `ProjectNewScreen`, `ProjectEditScreen`, scenario components | |
| AI: dates with their precision, today's date in the prompt, slow-model fall-through and cooldown, intake reading | `backend/app/agents/{tools,base,chatter,intake}.py` | |
| AI guard: a number is accepted when a tool wrote it with the same adjacent word | `backend/app/agents/guards.py` | 3 |
| Link budget on the Contact step | `core/rf_link.py`, `workers/handlers/{link_budget,contact}.py`, `services/contact_service.py` | 20 |
| Power and thermal | `core/{power,thermal}.py`, `data/diviner.py`, `services/energy_service.py`, `routes/energy.py` | 21 |
| Landing dispersion | `core/{dispersion,hazards}.py`, `data/pgda.py`, `services/dispersion_service.py`, `routes/dispersion.py` | 22 |
| Surface mesh simulation | `core/mesh.py`, `services/mesh_service.py`, `routes/mesh.py` | 23 |
| SPICE worker pool, off by default | `core/spice_pool.py`, `core/spice.py`, `scripts/bench_spice_pool.py` | 24 |
| Frontend panels: power and temperature, landing ellipse, downlink budget, mesh | `frontend/src/components/surface/*`, `lib/api/surface.ts`, `lib/api/surface.types.ts` | |
| External datasets, all downloaded | `data/external/SOURCES.md`; registry entries `diviner_prp`, `pgda_lola_5m`, `pgda_illumination` in `backend/app/data/registry.py` | |

`frontend/src/lib/api/surface.types.ts` aliases the generated types where the schema models
a shape (requests, quantities, series, link budget). The responses that the service types as
a loose `dict` (energy `inputs`, `model` and `ground`; most of the dispersion response; the
mesh `nodes`, `links`, `helpers` and `terrain`) stay hand-written and say so in a comment.

### What the frontend relies on that the contract does not spell out

- A refused project save returns 422 with `detail.errors: [{field, message}]`.
- `IntakeDTO.fields` uses dotted keys such as `target.lat_deg`, `launch.date`, `lifecycle.*`.
- An `entered` or `file` source has the person's name in `publisher`, the file name in
  `title`, and an empty URL.
- A scenario's contact result always carries `start` and `end`.
- `ProjectLifecycleIn` (`backend/app/api/v1/schemas/projects.py`) takes, all optional:
  `vehicle_id`, `vehicle_name`, `pad_id`, `pad_name`, `transfer_type`, `flight_days`,
  `lunar_orbit_days`, `sun_el_min_deg`, `sun_el_max_deg`, `bands`, `ground_stations`,
  `relays`, `mass_kg`, `rovers`, `returns`, `field_sources`, `eirp_dbw`, `eirp_tol_db`,
  `gt_dbk`, `frequency_mhz`, `data_rates_kbps`, `required_ebn0_db`, `required_margin_db`.
  `project_service.py` carries them into the stored lifecycle block. The Contact step shows the
  downlink budget when the EIRP, an X-band frequency (8200 to 8600 MHz) and the required Eb/N0
  are all stated; otherwise it says line of sight only and names what is missing.

### Known gaps recorded on 11 November and not rechecked since

- A scenario's Surface step shows four numbers and a sentence, no day-by-day chart.
- The quiet "What if..." link shows on every available step, including flown missions.
- The unsaved-work guard on the project form does not cover the browser Back button.

### Datasets

`data/external/` is not in git. `data/external/SOURCES.md` lists each dataset with its source
and use. All of it is on disk (2.5 GB, no failed file); `bash data/external/_tools/fetch_external.sh data/external`
from the repository root fetches the lot and skips what is already there. The power model reads
`diviner_prp/` (build its index once with `python -m app.data.diviner build` from `backend/`);
the landing ellipse reads `pgda_lola_5m/` and `pgda_illumination/`. Only five sites have a 5 m
slope map (elsewhere the ellipse falls back to the app's 20 m terrain and says so): `connecting-ridge`, `peak-near-shackleton`, `de-gerlache-rim`,
`de-gerlache-kocher-massif`, `leibnitz-beta-plateau`. Not obtainable: Artemis III region
coordinates (names and a map image only) and the NASA LSP vehicle performance data (a web form).

## 2. Rules that do not bend

These are the product's, not any one session's. A change that breaks one is wrong even if
every test passes.

- No invented numbers. A figure is computed, published, entered or assumed, and says
  which (`app.core.quantity.Quantity`), with a margin and where it came from.
- Never a composite score, a rank or a verdict (ADR-0001). The panels say what was
  worked out and what was not modelled; the person decides.
- `backend/app/core/` is pure: no I/O, database, network or clock. `lint-imports`
  enforces the layering (10 contracts). Only workers import `app.feeds`.
- The AI may only state numbers that are in a tool result (`agents/guards.py`).
- Scenario values are always labelled You / Published / Live / Default, are never written to
  the mission record, and every write needs a named session.
- Assumed inputs are marked on screen with the `.pw-scenario` hatch. Amber is the Sun,
  cyan is Earth. Type is Archivo and IBM Plex Mono. Do not introduce a new accent.
- A POST that computes and stores nothing needs: route, schema, service; an entry in
  `NOT_A_CHANGE` with `set()` in `app/tests/unit/test_request_limits.py`; an allowance
  in `app/api/limits.py`; one `include_router` line in `app/main.py`.

Git:

- Work goes to `main`. Commit after each verified piece, then push.
- **No Claude co-author, collaborator or attribution line in any commit, PR or push.**
- Message style: `Area: one plain sentence`, with a plain body when it helps.
- Files are mixed CRLF and LF. Commit with `git -c core.safecrlf=false commit`, add by
  explicit path, and keep each file's existing line endings when patching.
- The remote is `https://github.com/MdAhbab/PolarWindow.git`. The old URL redirects;
  `git remote set-url origin https://github.com/MdAhbab/PolarWindow.git` stops the notice.
- **A teammate is working on the design from `main`.** Before every push:
  `git pull --rebase origin main`. Do not restyle shared files wholesale
  (`frontend/src/styles/globals.css`, `components/AppShell.tsx`, `components/ui/*`);
  make the smallest edit and say so in the commit. New work goes in new files where it can.
- `polarwindow/.env` holds the Gemini key and a JWT secret. It is ignored by git. Never
  commit it, print it or paste it anywhere.

Working agreements: at most one Opus and one or two Sonnet agents at a time (Pro plan). Never
resume a stopped agent; read what it left, gate it, commit what passes, and start a fresh one
with a short brief that names the files to read.

## 3. Running and checking

Backend, from `backend/`:

```
.venv\Scripts\python.exe -m ruff check app
.venv\Scripts\python.exe -m ruff format --check app
.venv\Scripts\python.exe -m mypy app
.venv\Scripts\lint-imports.exe
.venv\Scripts\python.exe -m pytest app/tests/unit -q -p no:cacheprovider
```

Frontend, from `frontend/`: `npm run check` and `npx vitest run`.

Last gate run (12 November, after the review pass): ruff, ruff format, mypy and the 10 import
contracts clean; 931 backend unit tests passed, 2 skipped; frontend type check clean, 401 tests
passed. Integration: 184 of 184; Playwright E2E: 61 of 61 (Chromium v1243 installed). SPICE
worker-pool benchmark (`scripts/bench_spice_pool.py`, `K=8` sweeps of 30 d at 900 s): 1 thread
`0.141 s`, pool of 2 `0.072 s` (`1.95x`), pool of 4 `0.046 s` (`3.08x`), all bit-identical.

To regenerate the contracts: from `backend/` write `docs/openapi.json` with the command in the
Makefile's `openapi` target, then `npm run codegen` in `frontend/`. After a change to the data
registry, `polar-data readme --write` rewrites the README's data table (a test fails if the two
disagree).

The app: `python run.py --skip-install` from the repo root (web on 5173, API on 8000,
PostgreSQL on 5432 from `.local/tools/pgsql`). The API does not reload on a code
change: stop the `uvicorn`, `app.workers.compute` and `app.workers.feeds` processes and
start `run.py` again. Vite does reload. Migrations: `alembic upgrade head`. Without
`PW_GEMINI_API_KEY` in `.env` every AI feature runs in its rule-based fallback.

Signing in from a script: `POST /api/v1/auth/demo` with `{"name": "Review"}` gives a
token. Chat body: `{"messages":[{"role":"user","text":"..."}],"context":{...}}`.

Screenshots: two Playwright scripts are kept in `.local/review/` (not in git, this
machine only).

- `review.cjs <outdir> [name.tag,...] [full]` takes ten pages at 1440 and 390 wide in
  both themes and prints horizontal overflow and console errors.
- `shot.cjs <path> <tool title regex> <out prefix> [theme] [label=value;...] [widths]`
  opens one lander tool on a page, presses "Work it out" and takes the section.

Gemini on this key: `gemini-3.6-flash`, `3.5-flash` and `3.5-flash-lite` answer in 3 to
5 s; `3.8-flash` and `3.7-flash` accept a request and stay silent. The local `.env`
orders the chain accordingly. 503s happen under load; the fall-through handles them.

## 4. Where the 12 November work ended

All six packages from the 12 November plan are done and pushed (`757bcbd` to `681d867`).

Checked live, in the running app:

- Landing ellipse: 0.3 s at a covered site; an uncovered one falls back to the 20 m terrain
  and says so. The earlier "no answer in 90 s" was the screenshot script never typing the six
  figures, which start empty by design.
- Mesh over HTTP and on screen at Connecting Ridge (fixture in
  `lib/api/__fixtures__/surface/connecting-ridge.mesh.json`): lander 195 h direct, 195 h on
  certain links, 168 h if uncertain links hold.
- Ask dock: answers from the model, names Launch Complex 39A, and does not call a 2025
  mission upcoming.
- Downlink budget on Contact: it needs the EIRP, an X-band frequency (8200 to 8600 MHz) and
  the required Eb/N0. With EIRP alone it says line of sight only and names what is missing.
- Every new panel at 1280 or 1440 and at 390, dark and light: no sideways scroll, no console
  errors.

Gates at the end: backend 901 unit tests passed, 2 skipped; frontend 401 tests. Integration:
184 of 184 in one full run (after `make test-db`, which had never been run on this machine).
End-to-end against the running app: 60 of 61 in one full run; the one failure was the demo
path's own timing (its date-burst hold was too short and it ran under the 60 s default), and
after the fix it passed 4 runs of 4. Live-API tests can time out on the first run after a
restart, while the jobs compute cold.

Fixed on the way, each with its reason in the commit:

- `run.py` stopped reading Vite's output after a line the Windows console could not
  print; Vite then blocked on a full pipe and the web server froze.
- The theme token `--spacing-block` made Tailwind give every `inline-block` element a
  40 px width (provenance tags overflowed). Renamed `--spacing-section`.
- Editing a project cleared its launch vehicle, pad, transfer, bands, relays, mass and
  returns. `ProjectLifecycleIn` and the edit form now also round-trip `rovers`,
  `field_sources`, `vehicle_name` and `pad_name`.
- Space weather hid all DONKI lists when one product (flares) had never fetched; and the
  `donki` adapter now uses NASA GSFC CCMC's public endpoint (`ccmc.gsfc.nasa.gov/DONKI/WS/get`)
  when no personal `PW_NASA_API_KEY` is set, avoiding `api.nasa.gov` `DEMO_KEY` 429 throttling
  that previously blocked `flr`.
- Playwright Chromium v1243 (`chromium-1243` and `chromium_headless_shell-1243`) is installed.
- `docs/README.md` and `docs/adr/README.md` list ADR-0001 to ADR-0024.
- Site page metric "what this means" buttons (`KeyNumbers.tsx`), date picker start input
  (`WindowPicker.tsx`), and provenance pills (`project/fields.tsx`) meet the 44 px phone tap
  target height; light-mode landing page captions over the Moon image use `text-ink-2` with
  mobile viewport backdrop shading (`LandingScreen.tsx`).

## 5. Shapes the frontend work needs

`POST /api/v1/sites/{id}/energy`: body `{start, end, step_s?, lander_example_id?,
ground_radius_m?, lander:{...}}`. The `lander` key is required even when empty. Two
examples exist, both assumed: `nova-c-class-assumed` (flat top deck; at the pole its
battery empties in 7 h) and `nova-c-class-assumed-body-panels`.

`POST /api/v1/sites/{id}/dispersion`: body `{ellipse:{semi_major_m, semi_minor_m,
azimuth_deg}, lander:{footprint_diameter_m, cg_height_m, slope_limit_deg}, samples?}`.

`POST /api/v1/sites/{id}/mesh/simulate`:

```
{ start?, end?, step_s?, loss_threshold_s,
  nodes: [ 1..6 of { id, name?, position:{east_m,north_m} | waypoints:[{t_s,east_m,north_m}],
           antenna_height_m, battery_capacity_wh, initial_soc_fraction, own_traffic_bps,
           may_help, earth_uplink_bps?, earth_uplink_power_w? } ],
  radio: { frequency_hz, tx_power_w, forwarding_tx_power_w, tx_efficiency, antenna_gain_dbi,
           bandwidth_hz, noise_figure_db, snr_threshold_db, eps_r, polarisation },
  guard: { soc_cutoff_fraction, quota_share_per_lunar_day, max_forwarding_power_w, buffer_bytes } }
```

Response: `nodes[]` (each with `radio_state_timeline`, `radio_transitions`,
`time_in_state_h`, `direct_earth_link`, `routes[]`,
`longest_without_path_to_earth{direct_only, with_mesh, with_mesh_if_uncertain_links_hold}`),
`links[]` (`terrain_sight`, `terrain_fresnel`, `usable`, path loss), `helpers[]`.
A link is usable when its sight is `clear`; `uncertain` counts only in the third figure.

Contact: `Contact.link_budget`, `Link.passes[].{edge,peak}`, `link_budget_note`.
Typed in `lib/api/surface.types.ts` (`ContactBudgetDTO`) from the generated schema.

## 6. Review pass completed (12 November)

Checked and fixed across backend and frontend:

- `agents/guards.py`: hardened the adjacent-word rule against sentence-initial determiners,
  verbs and prepositions (`All 13`, `Launched 27`, `For 48`), designator numbers repurposed as
  measurements (`Complex 41 hours`), stop words and connectors (`41 and`, `41 for`), incomplete
  unit modifiers (`14 Earth`, `15 per`, `18 meters`, `20 degrees`), split clock times (`05:16 UTC`),
  and sign/comma/decimal/denominator/negation boundaries. Added 25 adversarial and positive unit
  tests in `test_guards.py`.
- `core/mesh.py`, `services/mesh_service.py` and `components/surface/MeshPanel.tsx`:
  - `active_relay` is entered only during steps where a node actually sends or forwards traffic
    over a usable mesh route (and helpers with a healthy direct Earth link also enter
    `active_relay` while forwarding); a node whose direct link is down with no usable route
    stays in `standby` (`0 W`; receive and idle-listening power are not modelled). Updated
    `connecting-ridge.mesh.json` to match (`lander`: 141 h `deep_sleep`, 195 h `standby`, 0 h
    `active_relay`).
  - Added `terrain.used_for` in `mesh_service.py` and a **Terrain basis** section in
    `MeshPanel.tsx` explaining that the 5 m local DEM (2 m height error) is used for
    surface-to-surface links and off-site node skylines (to 20 km), while the site point at
    `(0, 0)` uses the 20 m / 50 km site horizon mask in `meta.resolution`.
  - Audited all "uncertain" wording in `mesh_service.py` and `MeshPanel.tsx` so the two runs
    (certain links vs. if uncertain links hold) and the Fresnel reporting rule are stated
    plainly without claiming the mesh improves anything.
- `core/thermal.py`, `services/energy_service.py` and `components/surface/{EnergyPanel,EnergyCharts}.tsx`:
  stated explicitly in service notes, ground basis and chart legend that temperatures come from
  a single-node steady-state radiative balance bounded by LRO Diviner annual average and
  bolometric maximum surface temperatures (a bounding range, never a weather forecast, with the
  solid line as the midpoint of the two bounds), and marked assumed example lander inputs with
  `.pw-scenario`.
