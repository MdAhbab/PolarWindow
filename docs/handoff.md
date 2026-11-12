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
passed. Integration and Playwright E2E were NOT re-run after the review pass (they last passed
before it: 184 of 184, and 60 of 61 with the one failure fixed); Chromium v1243 is installed. SPICE
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

## 7. Clarity pass (13 November)

From the clarity-pass plan, the part due before the video: Part A on the Missions list, Part B
steps 1, 4 and 6, Part C for the sky view, and the model name off answers (Part F).

- `GET /missions` rows carry `steps`: six `{section, mark, scenario_id}` in journey order. `mark`
  is `record`, `example` (only a done preset scenario answers it; `scenario_id` is the first),
  `input` or `none` (`sections_service.step_marks`). The running API must be restarted to send it.
- The Missions list draws them as solid, hatched and hollow marks with one legend and a filter
  (`components/StepStrip.tsx`). Each mark opens its step, in the worked example when hatched.
- A step marked `example` opens on that worked example (`ScenarioGate`). "Show only what is
  published" keeps the reader on the record for the session (`useActiveScenario.recordOnly`).
- A step the defaults cannot fill ends with "Choose the landing spot and landing date", which
  opens the builder. No more "would still not be enough".
- Fixed: a worked example's Contact step failed with "no running event loop" (progress reported
  from a worker thread). Presets with a failed step re-run on the next API start.
- The sky view (`scenes/DomeCard.tsx`): a quarter turn on first view, a drag pill, edge arrows and
  arrow keys, a sliding compass strip, "Face the Sun" and "Face Earth".
- Answers read "AI answer · N numbers checked". The model and timing stay in the run log.

The rest of the plan, done the same day:

- Part B 2, 3 and 5 (`core/scenario.py`: `default_site`, `default_landing`, `trip_precedent`).
  A worked example assumes a landing spot (the provider's latest published target in the
  mission's region, else the latest CLPS one there), a landing day (the record's year or month,
  else five days after a published launch, else the first of the month after next; a first day
  that has passed moves to that too) and a trip (the one the same lander's or provider's last
  flight flew, else the newest). Each says where it came from. A finished preset that skipped
  a step these can now fill, or waited on its example trip, runs again at the next API start.
  Dry run: all 15 planned missions can work out Launch, Trip, Surface, Contact and Return.
- Part A, the rest: the same marks on Home's project cards and missions to explore, the legend
  under Your projects, and "Worked example" on a mission's step bar where only an example answers.
- Part D: each checked number carries the margin and unit its lookup gave (`guards.margin_of`).
  Answers show durations as tiles with their margin (or "no margin given"), shares as a bar,
  and "How this answer was made" in three steps (Looked up, Checked, Written) with Technical
  details closed. The field says "Ask about IM-2"; page questions stay above it.
- Part E: a kind mark on every tile (worked out, published, entered, assumed; `KindMark.tsx`);
  "About this number" titles the panel a tile's label opens (kept inline, not a sheet); the page
  foot is one closed "Sources, method and marks" row with both legends.
- Parts G and H: three doors and "How it works" on Home; "IM-2, step 4 of 6: Surface. Next:
  Contact." on each step; a sun and contact ring on each site row; Compare's measures as buttons
  at every width ("Order by"); "Start from a file" on Missions.
- Part F: `src/test/words.test.ts` fails the build on a long dash, a model or vendor name, or a
  banned word in any on-screen string. 27 sentences over 20 words were split or cut. Strings
  built with `${...}` were not scanned for length.

Then the items left from the first list:

- Payload kinds are small icon chips on mission rows and on the instrument filter
  (`PayloadIcon.tsx`). Play glows out twice on the first visit only. The energy chart says values
  show on a tap. Site, Compare and Plan have one Report button at the top right of the title.
- A tile's label opens an "About this number" sheet (value, margin, kind, meaning, source, what to
  know). Tests open it through `src/test/dialog.ts`, since jsdom has no `showModal`.
- When the example landing day is only assumed, the launch search runs from 10 days before it to
  60 after. A done preset re-runs only when a default it used changed, a step skipped for a
  missing value can now run, or its example trip was still being worked out.
- An example spot says first when the record names a target with no single point (Blue Ghost 3,
  Gruithuisen Domes).
- The words test also reads multi-line JSX text and template strings. The LCROSS site note now
  says "most closely studied"; the database keeps the old words until the sites are ingested again.
- The five first-time tasks from Home, counted by hand in the browser: IM-2's longest night 2 taps;
  Blue Ghost 3 on the surface 2 taps (3 while its examples are still queued); face Earth 3 taps
  (Check a landing site, Site, Face Earth); compare two sites 2 taps; ask and see how the answer
  was made 2 taps. No wrong turns. Not yet tried with a person who has never seen the app.

Some planned missions may keep a hollow Launch: a few months of searching can still hold no
landing the Sun rule allows at the assumed spot. That is the calculation's answer, said on the step.

To see it all: restart `run.py`. The API queues the presets again at start, and the workers then
work them out with the new rules (about a minute each).

Gates at the end: ruff, ruff format, mypy, 10 import contracts clean; 974 backend unit tests
passed, 2 skipped; frontend type check clean, 526 tests passed. Every main page checked at 375
and 1440 wide: no sideways scroll. Integration and end-to-end were not run; the end-to-end demo
was updated for the new answer words.

## 8. What is left (written 13 November, 03:00 Dhaka)

This section is the work list for the next session. Sections 2 and 3 still hold: the rules and the gates.
The plan behind section 7 is in `docs/clarity-pass-plan.md`. The design audit's working notes are on the
owner's PC only, under `.local/review/audit-2026-11-12/` (specs in `flow/`, rulings in
`flow/lead-rulings.md`, which outrank the specs).

Dates that shape the order (Dhaka time): the long video is recorded on Friday 13 November from 9:30 AM, so
the app must run cleanly on the owner's PC by then. The project page is submitted on Saturday 14 November.
The site then stays up for about ten weeks of judging.

### 8.1 How the lead works with agents

- The lead plans, briefs, checks and commits. Agents build. At most three agents at once: one Opus and one
  Sonnet, or two Sonnets, or one Opus and two Sonnets. Effort `xhigh`.
- Never resume an agent that stopped or finished with a large context. Read what it left, check it, commit
  what passes, and brief a fresh agent.
- Each brief names the files the agent owns and the files it must not touch. Two agents never own the same
  file in the same round. An agent that needs another's file says so in its report.
- Each agent writes its report file as it goes, under `.local/review/audit-2026-11-12/flow/reports/`, so a
  cut-off agent leaves a record.
- Agents do not commit, push, stash, reset, clean or restart the app. The lead runs the gates of section 3
  itself, looks at screenshots of what changed, and commits by explicit path.
- Commits: `git -c core.safecrlf=false commit`, message `Area: one plain sentence` and a plain body, no
  attribution line of any kind. Work goes to `main`. Before a push: `git fetch`, then
  `git merge --ff-only origin/main` if behind (a plain `git pull --rebase` fails here because of the next point).
- `docs/report/**` is the owner's and has uncommitted changes. Never stage, restore or edit it.
  `.env` is never read, printed or committed.
- Files have mixed line endings. Keep each file's own. No `sed -i`.

### 8.2 First: the app must be right for the recording

1. Restart `run.py` and wait until the presets are worked out (about a minute each, about 45 in all).
   Then check the Missions list: every planned mission should show striped marks, with hollow only where
   section 7 says a hollow Launch is the true answer.
2. Run the five first-time tasks of section 7 once more in the browser.
3. Walk the six demo shots in `docs/submission/task_ahbab.md` exactly as written. Where a label or a click
   in that file does not match the screen, fix the file, not the app, unless the app is wrong.
4. Check Compare says "1st", "2nd", "3rd" and never "best".

### 8.3 The front page's films: build them again from the new clips

The owner replaced the generated clips on 13 November. The page still plays the old ones.

| New clip (in the workspace root, beside `polarwindow/`) | Size | Length | What it shows |
|---|---|---|---|
| `light.mp4` | 1920 x 1080, 24 fps | 12.0 s | The Sun low over the cratered pole |
| `shadow.mp4` | 1920 x 1080, 24 fps | 12.0 s | A lander; a hill's shadow crosses it and passes |
| `earth.mp4` | 1920 x 1080, 24 fps | 10.0 s | A lander with Earth sinking behind a hill |
| `rim.mp4` | 1920 x 1080, 24 fps | 12.0 s | A low flight over rocks to a crater rim; Earth shows at the end |
| `descent.mp4` | 1920 x 1080, 24 fps | 14.9 s | Coming down from above toward the craters |

All have stereo AAC sound (the music is part of the clip). None has black bars. The old set was four
clips at 1280 x 720, two of them with bars, and "rim and descent" was one 20 s clip. That clip is gone.

What has to change:

- `frontend/scripts/landing-video.mjs`: the `films` table. The `original` names (`rim` no longer exists as
  `rin and descent.mp4`), `secs` (12, 12, 10, and the end film), `crop` (now false for all), and the
  masters. The old masters in `.local/review/audit-2026-11-12/video/up/` are from the old clips: do not use
  them. The new clips are already 1920 wide, which is the page's large size, so no upscale is needed. Build
  straight from the new clips. (The page shows a film at up to 1.25 times its width, so 1920 covers
  screens to 2400 wide. Upscale again only if the owner asks for sharper on larger screens.)
- The end of the page: decide with the owner whether it plays `rim` then `descent` joined as one loop
  (27 s, cross-faded at the join and at the loop point) or one of them. Default if no answer: join them,
  rim first.
- `shadow` and `earth` are driven by scroll: 120 frames at 12 per second (`SCRUB_FRAMES`, `SCRUB_FPS` in
  `frontend/src/components/landing/film.ts`). `shadow` is now 12 s, so either take every second frame of
  the best 10 s or raise the frame count. Keep each file under its size cap.
- `BEATS` in `film.ts` were set against the old frames (when the shadow reaches the lander, when the hill
  covers Earth). Set them again by looking at the new frames, and check each caption still says what the
  picture shows at that moment.
- Posters (`*-poster.jpg`, two sizes) come from the same run. `grain.png` stays.
- Budget: no file over 10 MB, the folder under 45 MB.
- Check on the page at 1440 and 390, both themes, with reduced motion, and with the files missing (the
  fallbacks must still work). Run the landing tests.
- Tools already on the PC: ffmpeg and ffprobe paths are in `.local/review/audit-2026-11-12/video/env.sh`.

`frontend/public/landing/` (17 files, about 41 MB) is not in git. A fresh clone has no films. Ask the owner
once: commit the rebuilt folder (simplest for the server), or copy it to the server by hand. Until the
owner answers, do not commit it.

### 8.4 End-to-end tests

Last full run: 12 November, after the "Screens" commit `95e81d1` and before the clarity pass: 50 passed,
11 failed, all in `frontend/e2e/lifecycle.spec.ts`. Log: `.local/review/audit-2026-11-12/e2e-round2.log`.

- Seven fail only because the test still expects a long dash where the screen now says "to"
  ("60 to 95 h", "18 to 26%", "blocked 325 to 425 m"): tests at lines 89, 387, 499, 553, 1370, 1416, 1458.
  The file has 19 long dashes in expectations and `demo.spec.ts` has one. Change the tests, not the app.
- Line 347 (space weather now): a label it looks for by name was reworded ("north-south").
- Line 851 (trip and contact): the answer sentence now ends differently after "covers,". Read the test
  and the sentence side by side.
- Line 1130 (return): the waves and wind sentence was missing from the answer. Find out whether the
  forecast feed was down or the sentence moved into a row.
- Line 1252 (radiation): a stored result keeps its old wording until it is worked out again.

The clarity pass then changed many more words and was not followed by an end-to-end run. So: run the
whole suite, fix test expectations that only lag the new words, and treat anything else as a real fault.
Then retake the recorded screens in `frontend/e2e/__screens__` (all will differ). Integration tests were
also not run after the clarity pass.

### 8.5 Design items still open

Checked in the code on 13 November: these are not done. Details and file lines are in the audit folder's
`flow/known-gaps.md`, `flow/work-packages.md` (rounds 3 to 7) and `flow/reports/O2.md`, `S2.md`.

- A scenario's Surface step still shows only four totals with no chart and no margins
  (`MissionDetailScreen.tsx`, "four totals only"). Known gap 1.
- "What if…" still shows on missions that have flown (`WhatIfLink` takes no status). Known gap 2.
- Unsaved work in the project form is still lost on the browser's Back button (no `useBlocker`). Known gap 3.
- `MapScreen.tsx` and `MissionDetailScreen.tsx` still use the old 120 h constant directly. They should use
  `useBatteryLimit()` so the limit reads "entered" or "(assumed)" with the hatch, as on Site, Compare and
  the report. `MissionDetailScreen` should also pass the chosen start date to its Ribbons.
- A tile's figure and its margin can still wrap apart at 390 wide. The headline and the tiles round the
  same figure differently (quarter hours against whole hours).
- The Plan chart draws "longest time without contact" in magenta though no limit applies to it, and at
  1440 the chart is wider than its panel.
- `SettingsSheet` says "Light is best for printing and projectors": the word "best" is banned on screen.
- On a phone, Ask is still a floating button over the bottom bar. The ruling (L-1) is a fourth item in the
  bottom bar.
- Chosen dates are not kept in the page address, so a reload loses them.
- One stage line shared by the six steps, a project's progress and a scenario's phases (`StageLine`) was
  planned and not built. Check first whether the clarity pass's step marks already do this job; if they do,
  drop it.
- Loading skeletons do not match the loaded pages' height, so pages jump as they load.
- `docs/conventions.md`: Motion table rows M4 and M5 are out of date.

Before building any of these, check it against the current screen: the clarity pass may have changed the
ground under it.

### 8.6 The final design check

From the plan's Part I. After everything above:

1. Full gates on both sides, integration and end-to-end included.
2. Fresh screenshots of every page at 1440 and 390, light and dark.
3. Read every page against this list: one main action; no sentence over 20 words; no long dash; no model
   or vendor name; every assumed value hatched; no number without its margin and kind; no step that
   dead-ends; every view that turns or plays has a visible cue; nothing cut or scrolling sideways on a
   phone; 44 px tap targets; readable contrast; amber only for the Sun, cyan only for Earth, magenta only
   for over a limit; no score, rank verdict or "best".
4. The five first-time tasks again. If the owner can, one person who has never seen the app.
5. Update this file.

### 8.7 Putting it on Google Cloud

Target: one Compute Engine VM at `https://clpsspaceapps.ahbab.dev`, nginx in front, a Let's Encrypt
certificate from certbot, PostgreSQL, results worked out on the owner's PC and carried over. The owner
connects the VM over SSH to the session; the first step there is a `git clone`. A `.dev` address only
works over HTTPS, so the certificate comes before anything is shown.

Start from what exists: `docs/runbook.md` section 4 ("Deploying on one host"), `run_onVM.py` (installs
Docker, builds, downloads data, starts the stack; has `--data-from` for a data zip made by
`run.py --export-data`), `docker-compose.yml` (web, api, compute, feeds, postgres, redis),
`backend/Dockerfile`, `frontend/Dockerfile`, `frontend/nginx.conf`. A first check was cut short; its
notes are in `.local/review/audit-2026-11-12/flow/reports/DEPLOY.md`.

Found so far:

- Migrations are in order: one Alembic head (`a7c9e1b3d5f8` on 12 November; the clarity pass may have added
  more, so run `alembic heads` again). The local database was at the head.
- PostgreSQL 16 on both sides (`run.py` pins 16.11; compose uses `postgres:16-alpine`), so a
  `pg_dump -Fc` from the PC restores on the VM. The database was 56 MB.
- **Blocker.** Stored answers are found by a key that includes a hash of the catalogue files' bytes
  (`backend/app/data/catalogues.py`, about lines 470 to 484). On this PC git checks those files out with
  Windows line endings; a Linux clone gets Unix ones. The hashes differ, so every stored trip, contact,
  launch and scenario answer would be missed on the VM and worked out again. Fix on the VM, before the
  first start:

  ```
  echo 'data/catalogues/*.json text eol=crlf' >> .git/info/attributes
  rm data/catalogues/*.json && git checkout -- data/catalogues
  sha256sum data/catalogues/*.json | cut -c1-16     # must equal the same list printed on the PC
  ```

  A lasting fix (hash the parsed content, not the raw bytes) changes every key, so do it only together
  with a full recompute, or leave it.
- `docker-compose.yml` publishes Postgres, Redis and the api on `${PW_BIND_ADDR:-0.0.0.0}`. On a public VM
  set `PW_BIND_ADDR=127.0.0.1` (`run_onVM.py` says it does; confirm).
- A launch search for a mission with no chosen dates starts at today's date, so its key changes every day
  and it is worked out again daily. Carried results for those go stale after a day. This is normal load,
  not a fault; size the VM for it.

Still to find out, with proof from the code, before the VM is touched:

1. Which path to use on the VM: `run_onVM.py` as it is, or compose with a separate nginx on the host for
   TLS. The web container already runs nginx on port 80; decide whether certbot runs on the host in front
   of it (host nginx on 80 and 443, the web container on another local port) or inside it.
2. How the frontend finds the API in a production build, and that nothing points at `localhost`.
3. CORS, allowed hosts, upload size (the app takes a dropped file up to `PW_MAX_UPLOAD_BYTES`), and any
   long request nginx must not cut short.
4. Every setting that must change for a public site (`.env.example` names them): a new `PW_JWT_SECRET`, a
   database password, `PW_ENV`, `PW_CORS_ORIGINS`, `PW_GEMINI_API_KEY` and the model order that answers on
   this key (section 3), `PW_NASA_API_KEY`, `PW_DEMO_SIGN_IN`, the rate limits, `PW_MAX_QUEUED_JOBS`.
   Never copy the PC's `.env` to the VM by pasting it into a chat or a commit; the owner moves it.
5. Abuse and cost: the limits on sign-in, on Ask (it spends the owner's Gemini quota) and on job-starting
   routes, and what a visitor can queue.
6. Which folders under `data/` the running app needs (about 1.2 GB by `run_onVM.py`'s note), and the
   smallest set to copy.
7. Whether the presets queued at API start would swamp a small VM on first boot when results were not
   carried over, and how to carry them: dump on the PC after the presets finish, restore on the VM before
   the first start, and confirm on the VM that a stored answer is served without a new job.
8. Staying up: restart on boot, log size, disk growth, a daily `pg_dump`, a health check, and how to
   update later (`git pull`, rebuild, migrate) without losing data. Certificate renewal.
9. VM size. Earlier advice, not yet measured: e2-standard-2 (8 GB) at least, e2-standard-4 for judging
   days, 40 GB disk, region asia-south1.

Write the result as `docs/deploy-gcp.md`: numbered steps a person can paste, marked "on the PC" or "on the
VM", with the checks after each stage and a rollback. Put any nginx site file or helper under `deploy/`.
Deploy only when the owner says the VM is connected, and confirm with the owner before any step that
changes DNS, opens a firewall port or replaces a database.

### 8.8 The submission

`docs/submission/` holds the plans. `submission-drafts.md` lists the files. The team is Wali, Ryan, Ahbab,
Mehrab and Mehedi; each has a `task_<name>.md` with the words to say and how to record. Still to fill in:
the team name, each role, the music credit, the exact video tool named in the Use of AI table, the video
links. After the final gates, put the true test counts in `submission-drafts.md` and in Mehrab's line if
the total falls under 1,400.

### 8.9 Waiting on the owner

- Commit the front page's film files to git, or copy them to the server by hand (8.3).
- The end of the front page: rim and descent joined, or one of them (8.3).
- Team name and roles (8.8).
- Aurora Scout 1's owner shows as "Test Manager": rename or leave.
- `docs/paper/` (an older paper, linked from nowhere) and two unused logo files in `data/`: keep or remove.
- Scenarios for cancelled missions: default is no.
