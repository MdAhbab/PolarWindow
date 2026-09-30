# POLAR WINDOW

**Sunlight and contact with Earth for every NASA CLPS mission and for candidate
landing sites at the Moon's south pole.**
NASA Space Apps Challenge 2026: *CLPS Lunar Mission Browser*.

A project manager picks a mission or a site and reads, in about ten seconds,
how much sunlight a lander gets, how long it can talk to Earth, and the longest
stretch it has to survive alone. The numbers are computed from real NASA terrain
and real Sun and Earth positions, and each one shows how far it could be off.

Each mission is also followed through its delivery, section by section: **Ready**
(readiness items, parts, risks, as the team enters them), **Launch** (the flown
launch with its published period, or opportunities backed out from the landing with
solved climb azimuths, launch weather rules, forecast disagreement checks, and multi-year
hindcast verification), **Trip** (distance, shadow, burns, correction budget, EGM2008
gravity, a radiation screening), **Contact** (who can hear the lander, planned relays
as ranges, active orbiter passes, and rover line-of-sight viewshed tiles), **Return**
(where the booster comes down, sea and wind, capsule entry check against OSIRIS-REx)
and space weather now. No section gives a verdict: the evidence is shown rule by rule
and people decide (`docs/lifecycle-api.md`).

```bash
make install     # backend and frontend dependencies
make seed        # SPICE kernels, LOLA terrain, 15 sites, horizon masks (about 10 min, once)
make dev         # postgres, redis, API on :8000, frontend on :5173
make compute     # the compute worker: trip, contact and launch answers
make feeds       # the feeds worker: weather, space weather, launch schedules
```

Or `python3 run.py`: it starts Postgres and Redis (on a machine that has never
run the app it creates the project's own database in `.local/pgdata`), installs
what is missing, runs the API, the workers and the frontend together, and then
downloads the data the app reads, or copies it from a friend's machine (see
[Required data](#required-data)). The frontend also runs with no backend
at all from a saved copy of the API's answers: `cd frontend && npm run build:snapshot && npm run preview`.

---

## The problem

The challenge brief says the existing tools have "complicated interfaces" that
make it "difficult to evaluate critical information with efficiency". The
science of polar lighting is solved; getting a decision out of it is the slow
part. POLAR WINDOW answers that with four numbers that always appear together:

| | |
|---|---|
| **Time in sunlight** | hours the Sun is above the site's own skyline: when the solar panels charge |
| **Time in contact with Earth** | hours Earth is above it: when the lander can radio home directly |
| **Longest night** | the single longest stretch without sunlight: what the battery must survive |
| **Longest time without contact** | the single longest stretch with Earth out of sight: how long the lander works alone |

The last two are the ones that end missions, and a total or an average hides
them. There is **no combined score** anywhere in the system, and a test makes
sure there never will be: a score ranks sites on one axis and hides which corner
was given up, and that trade is the decision.

## What it finds

Fifteen candidate sites, one lunar day from 14 March 2027, computed by this build:

| code | site | lat | sunlight | contact with Earth | longest night | longest time without contact |
|---|---|---|---|---|---|---|
| B | Connecting Ridge | 89.44°S | **81 %** | 61 % | **122 h** | 278 h |
| E | de Gerlache-Kocher massif | 88.44°S | 74 % | 69 % | ≥ 101 h | 221 h |
| D | de Gerlache rim | 88.66°S | 74 % | 70 % | ≥ 112 h | 213 h |
| C | Peak near Shackleton | 89.78°S | 73 % | 63 % | **64 h** | 263 h |
| N | Sverdrup rim | 87.99°S | 70 % | 45 % | 167 h | 387 h |
| M | Leibnitz Beta plateau | 85.23°S | 59 % | **76 %** | 291 h | 171 h |
| J | Nobile rim 1 | 84.36°S | 57 % | **82 %** | 304 h | **130 h** |
| G | Malapert massif | 85.99°S | 56 % | 80 % | ≥ 288 h | 138 h |
| A | Shackleton rim, east shoulder | 89.30°S | 47 % | 57 % | 206 h | 304 h |
| … | *(six more)* | | | | | |

"≥" marks a night the chosen dates cut short, so the real night is longer. The
API returns this as `longest_dark_open`, and Compare never calls such a value
best.

Three findings came out of the physics rather than being designed in:

- **The power and contact trade is a latitude trade.** Of the five sites above
  70 % sunlight, four sit within 1.6° of the pole and have 61–70 % contact with
  Earth; the fifth, Sverdrup rim, sits 2° out and gets 45 %. Both sites above
  76 % contact sit four to six degrees out and pay for it with nights of 304 h
  and at least 288 h.
- **At the pole the Sun never rises, and that is not the problem.** At
  Connecting Ridge the Sun stays between −1.6° and −0.7° for the whole month.
  The site is still sunlit 81 % of the time, because it stands 1,958 m up and
  looks *down* at a skyline averaging −2.4°. Terrain, not season, decides power.
- **Contact with Earth at the pole is limited by the Moon's wobble (libration),
  not by terrain.** Earth's elevation swings through about 13° on a 27-day
  cycle, so polar sites lose it for days in one long stretch.

## Who it is for

One stakeholder: **the project manager of a lunar lander mission**, choosing
where and when to land. They read everything, and they run the service for
their team from **Settings**: the AI assistant, its activity log, saved results
and a health check of the data. There is no separate admin account. Judges get
the same view with one click.

There is one view for everyone, in plain English. Detail is there on request:
press a number's label to see what it means (and its professional name, such as
"Direct-to-Earth contact"), and open any closed row (*What blocks the Sun and
Earth here?*, *How sure is this?*, *Change the dates*) to see more in place.

## The screens

| route | |
|---|---|
| `/` | Front page: why the pole is hard, on a 3D Moon whose south-polar terrain is the real LOLA map, and one button in |
| `/missions` | Every NASA CLPS delivery, flown and planned: filters, a map of where they land, a timeline |
| `/missions/:id` | One mission: status and dates, then the four numbers at its landing spot over its days on the surface; target, payloads and sources open on request |
| `/map` | The south pole from above, the shadow at the moment shown, and every candidate site |
| `/site` | One site: the four numbers and two rings, sunlight outside and contact with Earth inside |
| `/compare` | Two to eight sites side by side, ranked by one measure at a time; "too close to call" where the data cannot separate them |
| `/plan` | Every time without contact, what the lander must handle alone, and downloads (spreadsheet, SPICE) |
| `/skyline` | The skyline all around a site, and what blocks the Sun |
| `/report` | A one-page printable report |

**Signing in.** *Open the dashboard* asks the API for a project manager's
session (`POST /api/v1/auth/demo`, a signed JWT) with no user name or password.
Reading is public; the session is checked where it matters, on the AI panels
(they use model quota) and the project settings (they change the service for
everyone). `PW_DEMO_SIGN_IN=false` turns the button off anywhere real.

**The guide.** On the first visit a bar along the bottom introduces each major
feature once, in nine short steps. *Guide* in the header brings it back.

---

## How it computes

1. **Terrain.** The LOLA polar elevation model `LDEM_80S_20M` (20 m posts) from
   the PDS Geosciences Node, fetched per site as a 20 km window, with an 80 m
   regional tile out to 50 km.
2. **Skyline.** A ray-cast over 1,440 directions at 0.25°, out to 50 km, with the
   Moon's curvature subtracted; a ridge only counts where it stands above the
   noise its own terrain error could produce.
3. **Sun and Earth positions.** SPICE `spkpos` against DE440 in the `MOON_ME`
   frame, with light-time and stellar aberration, turned into each site's local
   east/north/up frame with unit vectors (the textbook azimuth formula loses its
   precision within a degree of the pole).
4. **Stretches.** Every rise and set against the skyline is bracketed at 15
   minutes and refined by bisection. Each crossing carries a timing margin: the
   terrain's height error divided by how fast the body crosses the skyline.
5. **The four numbers, and the stretches with neither sunlight nor contact**,
   which size what the lander must do on its own.

Change the dates and the numbers are recomputed: the geometry is evaluated, not
replayed. Ray-casting one skyline takes about 45 ms and is done once per site;
after that a 708-hour timeline at 900 s steps costs about 15 ms cold and 4 ms
warm over HTTP (Apple M3, 24 September 2026).

**A site is not a crater.** The IAU coordinate of a named crater is its centre,
which is the permanently shadowed floor (LOLA gives −2,767 m at Shackleton's
centre). So site coordinates are derived, not asserted: each name's centre is an
anchor, and the site is the most open-skied landable point in a stated ring
around it, found in the terrain. The anchor, the search area and the rule are
stored on every site and returned by the API.

## Architecture

```
frontend/          React 19, Vite, Tailwind v4, TanStack Query, zustand, three.js
  src/lib/api/     generated types, typed client, adapters, query hooks
  e2e/             Playwright browser tests with axe accessibility checks
backend/
  app/core/        pure computation, no I/O: kernels, spice, horizon,
                   visibility, intervals, metrics, timeline, projections
  app/data/        LOLA access, site resolution, tile rendering
  app/db/          SQLAlchemy 2.x models, one repository per aggregate
  app/services/    policy; never imports FastAPI, so workers and agents
                   call exactly the code the routes do
  app/api/v1/      routes and pydantic schemas only
  app/agents/      four agents, six tools, the number guard
  app/workers/     precompute: skylines and reference numbers
data/              CLPS mission records, each field with a source and access date
docs/              system design, decision records, API, data sources, validation,
                   test plan, runbook, and the judge report
```

The layering is enforced, not trusted: `make contracts` runs import-linter over
eight contracts (`core/` does no I/O, routes import neither the ORM nor the data
layer, services import no FastAPI, `spiceypy` is reached only through
`core/spice.py`, agents reach the domain only through `agents/tools.py`).

## The AI helpers

Four agents over the same numbers, reachable only through ten declared tools
(six over the sites, four read-only ones over the missions' sections, each result
cut to at most 200 numbers), running on Google Gemini models with a fallback
order set in Settings:

- **What is it like at this site?** (A1): one plain paragraph about a site.
- **Find sites that meet a requirement** (A2): ranks sites against a stated need,
  and says plainly when nothing qualifies.
- **Summary memo** (A3): a memo for the team on the printable report.
- **Ask about missions and sites** (A4): questions in plain language over the data.

**Every number in an answer must trace to a tool result.** An answer with a
number that is not in the tool outputs is rejected, the model is told which one,
and it gets one retry. Fail twice, time out, or have no model configured, and
the answer is replaced by a summary built directly from the measurements. An
answer with a verdict word (go/no-go, "safe", a readiness percentage, a risk
score) is rejected the same way. The four numbers never depend on an API key. Every run, rejections included, is
recorded and shown in the AI activity log (Settings → Project).

## Tests

```bash
make test-fast               # unit, property and synthetic golden tests; no services
make test                    # all backend tests: 459 fast, 162 integration, 36 golden
make test-fe                 # 140 frontend unit and component tests
cd frontend && npm run e2e   # 20 browser tests with axe (WCAG 2.1 AA); API on :8000
make lint                    # ruff, mypy --strict, import-linter
```

- **Property tests** (hypothesis) over the interval arithmetic: partition,
  alternation, contiguity, inversion symmetry, concatenation, monotonicity.
- **Golden fixtures** for three sites with different physics, pinned with stated
  tolerances; `make golden-update` refuses without `GOLDEN_UPDATE_REASON`.
- **The ray-march is tested against analytic surfaces** whose skyline can be
  worked out by hand: a plane, a cone, a wall, a ramp and a crater bowl.
- **Hindcast against flown landers** in `docs/validation.md`, with the trip,
  launch, loops, radiation and capsule entry checked against NASA's
  reconstructions and published results (`make validate-trip`,
  `validate-radiation`, `validate-capsule`).
- **Chaos**: a live feed down, slow, malformed or stale leaves its number missing
  with the reason and every other section working (`test_chaos.py`).
- **No test reaches the real Gemini API**: the transport is blocked in tests.

## Known limits

Named, rather than left for someone to find:

- The 120 h battery limit is a stand-in. The backend returns durations and
  refuses to return verdicts, because a verdict needs a thermal model this
  system does not have.
- The map's shadow is where the Sun sets on flat ground (hills are not counted).
  Every number uses each site's real skyline.
- Terrain height error is a per-product constant (2 m for 20 m data, 4 m for
  80 m), not a per-pixel figure.
- Outside 80°S there is no terrain data, so a skyline there is a flat horizon and
  says so on screen.
- No screen-reader user has tested the arc list, the mission list or the guide. Two
  colour pairs also fall short of WCAG contrast: the light theme's month-strip bars
  and the borders of input fields. Each is a one-value token change (see
  `docs/conventions.md`, Accessibility).
- The AI answers' number check accepts a whole number that matches any tool value
  within ±0.5 under five unit conversions, so a match by coincidence is possible.
  Each claim's provenance names the field it matched (`docs/system-design.md`
  §11.3).
- The launch wind forecast shares are not checked against enough observations
  (one year at the Cape had one event), so they are shown as not checked.
- A designed launch time for a planned mission climbs in the direction of the
  vehicle's flown lunar launches; held out, IM-1 and IM-2 miss by 16 and 18 min
  (given its own direction each lands within a minute), so the calendar gives
  ± 18 min; the errors in the correction budget are assumed, not published.
- The capsule entry model lands OSIRIS-REx's capsule 9.5 km from where it landed
  (limit 10 km); no CLPS mission brings anything back, so no return trajectory is
  worked out.

More in `docs/report/report.pdf` (Limitations) and `docs/validation.md`.

## Keyboard

```
[  ]   step the date by 6 h        ⇧[ ⇧]  by one day
T      read the chart as a table   Space  play through the dates
```

Single-key shortcuts can be switched off in Settings (WCAG 2.1.4).

## Documentation

| | |
|---|---|
| `docs/report/report.pdf` | The judge report: what was built, measured results, limitations, questions |
| `docs/system-design.md` | Architecture, data model, API design, performance |
| `docs/adr/` | Eighteen decision records (8 to 18 cover the launch, trip, contact, readiness and data work) |
| `docs/api.md`, `docs/openapi.json` | The REST API |
| `docs/lifecycle-api.md` | The mission sections' contract (Ready to Return), with its changes |
| `docs/data-sources.md` | Every dataset and where it comes from |
| `docs/validation.md` | Hindcast of flown landers; the trip, launch, weather, radiation and capsule checks |
| `docs/test-plan.md` | What is tested and why |
| `docs/runbook.md` | Running, deploying and fixing it |
| `docs/conventions.md` | Invariants, the plain-English word list and the accessibility rules |

## Required data

Everything the app reads is public NASA data (most of it also listed on
[data.nasa.gov](https://data.nasa.gov/dataset)). You do not need to fetch it by
hand: `python3 run.py` starts the app first, then checks every dataset below and
downloads whatever is missing, resuming any download that was interrupted. If
the new data is something the API loads at start-up (SPICE kernels, terrain,
seeded sites), it restarts the backend for you. The same step on its own:

```bash
cd backend
uv run polar-data list                  # what is on disk and what is missing
uv run polar-data sync                  # core, lifecycle and validation data
uv run polar-data sync --tier bulk      # also the large archives (needs PW_EARTHDATA_TOKEN)
```

Keys are optional. Without `PW_EARTHDATA_TOKEN` (a free
[NASA Earthdata Login](https://urs.earthdata.nasa.gov) token) the bulk archives
are skipped and the rest works. `PW_NASA_API_KEY` (free from
[api.nasa.gov](https://api.nasa.gov)) only raises the space-weather rate limit.
Live feeds (weather forecasts, space weather now, DSN Now, the orbiters' tracks
from JPL Horizons) are not files and are not in this table; the feeds worker
fetches them on a schedule.

**Copying the data instead of downloading it.** The first download takes hours,
because some NASA archive servers send about 30 kB/s. A machine that has the
data can pass it on (about 1.1 GB, all public data, nothing secret in it):

```bash
python3 run.py --export-data ~/polar-window-data.zip   # or a folder, for example in Google Drive
```

Share the file or the folder. On the other machine, before the first start:

```bash
python3 run.py --data-from ~/Downloads/polar-window-data.zip
```

`--data-from` takes the `.zip`, the folder, or the folder holding the several
`.zip` parts Google Drive makes when it downloads a large folder. Every file is
checked against the SHA-256 listed at export: a damaged file is not used (it is
downloaded instead), a file already on the machine is never replaced, and what
the copy lacks is downloaded as usual. Without starting the app:
`uv run polar-data export PATH` and `uv run polar-data import PATH` in `backend/`.

This table is generated from `backend/app/data/registry.py`; a test fails if
the two disagree. Regenerate it with `uv run polar-data readme`.

<!-- required-data:begin (generated by `polar-data readme`; do not edit) -->

**Needed to start (fetched first)**

| Dataset | Provider | Size | Goes to `data/` | Needed for | Account |
|---|---|---|---|---|---|
| [SPICE LSK naif0012.tls](https://naif.jpl.nasa.gov/pub/naif/generic_kernels/lsk/naif0012.tls) | NASA JPL NAIF | 5.0 kB | `kernels/naif0012.tls` | Leapseconds. Without it every UTC -> ET conversion fails and no timestamp can be interpreted at all. | none |
| [SPICE SPK de440.bsp](https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/planets/de440.bsp) | NASA JPL NAIF | 100 MB | `kernels/de440.bsp` | Planetary ephemeris. Without it there are no Sun or Earth positions, so sunlight and Earth-contact hours cannot be computed. | none |
| [SPICE PCK pck00011.tpc](https://naif.jpl.nasa.gov/pub/naif/generic_kernels/pck/pck00011.tpc) | NASA JPL NAIF | 100 kB | `kernels/pck00011.tpc` | Body constants: the Moon's radii and orientation model. Without it the lunar body-fixed frame has no shape to attach to. | none |
| [SPICE PCK moon_pa_de440_200625.bpc](https://naif.jpl.nasa.gov/pub/naif/generic_kernels/pck/moon_pa_de440_200625.bpc) | NASA JPL NAIF | 10 MB | `kernels/moon_pa_de440_200625.bpc` | Lunar principal-axis orientation. Without it MOON_PA -- and therefore MOON_ME -- cannot be realised, so azimuths are meaningless. | none |
| [SPICE FK moon_de440_250416.tf](https://naif.jpl.nasa.gov/pub/naif/generic_kernels/fk/satellites/moon_de440_250416.tf) | NASA JPL NAIF | 5.0 kB | `kernels/moon_de440_250416.tf` | Frame kernel defining MOON_ME relative to MOON_PA. Without it SPICE knows the Moon's spin but not the mean-Earth frame the site coordinates are expressed in. | none |
| [LOLA south polar elevation model, 80 m (LDEM_80S_80M)](https://pds-geosciences.wustl.edu/lro/lro-l-lola-3-rdr-v1/lrolol_1xxx/data/lola_gdr/polar/img/ldem_80s_80m.img) ([data.nasa.gov](https://data.nasa.gov/dataset/lro-moon-laser-altimeter-4-gdr-v1-0)) | NASA LRO LOLA / PDS Geosciences | 116 MB | `dem/regional_80m.npz` | Terrain for every site south of 80 deg S: the skyline that decides sunlight and contact with Earth, the map tiles and site placement. | none |
| [LOLA south polar elevation model, 20 m (LDEM_80S_20M), windows around each site](https://pds-geosciences.wustl.edu/lro/lro-l-lola-3-rdr-v1/lrolol_1xxx/data/lola_gdr/polar/img/ldem_80s_20m.img) ([data.nasa.gov](https://data.nasa.gov/dataset/lro-moon-laser-altimeter-4-gdr-v1-0)) | NASA LRO LOLA / PDS Geosciences | 40 MB | `dem/fine/` | The near skyline at each site. Only a 20 km window per site is read, by HTTP range requests; the 1.85 GB file is never downloaded whole. | none |
| Skylines and reference numbers for every site (built locally) | Built from the LOLA and SPICE data above | - | `(database)` | The 1,440-bearing skyline and the four numbers for each candidate and mission site; built once, then every answer is a lookup. | none |

**Needed by the launch, trip and contact sections**

| Dataset | Provider | Size | Goes to `data/` | Needed for | Account |
|---|---|---|---|---|---|
| [SPICE PCK gm_de440.tpc](https://naif.jpl.nasa.gov/pub/naif/generic_kernels/pck/gm_de440.tpc) | NASA JPL NAIF | 10 kB | `kernels/gm_de440.tpc` | Gravitational parameters consistent with DE440. Without it the trip propagator has no masses for the Sun, Earth and Moon. | none |
| [SPICE PCK earth_1962_260806_2126_combined.bpc](https://naif.jpl.nasa.gov/pub/naif/generic_kernels/pck/earth_1962_260806_2126_combined.bpc) | NASA JPL NAIF | 31 MB | `kernels/earth_1962_260806_2126_combined.bpc` | Earth orientation (ITRF93): measured to 2026-08-06, predicted to 2126. Without it launch pads and ground stations cannot be placed in space, so launch times and station view periods cannot be computed. | none |
| [SPICE SPK earthstns_itrf93_260814.bsp](https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/stations/earthstns_itrf93_260814.bsp) | NASA JPL NAIF | 10 kB | `kernels/earthstns_itrf93_260814.bsp` | Deep Space Network antenna positions. Without it the ground stations that can hear a lander cannot be computed. | none |
| [SPICE FK earth_topo_260814.tf](https://naif.jpl.nasa.gov/pub/naif/generic_kernels/fk/stations/earth_topo_260814.tf) | NASA JPL NAIF | 10 kB | `kernels/earth_topo_260814.tf` | Local horizon frames at each Deep Space Network antenna. Without it a station's elevation above its horizon cannot be computed. | none |
| [GRAIL lunar gravity field GRGM1200A (spherical harmonics)](https://pds-geosciences.wustl.edu/grail/grail-l-lgrs-5-rdr-v1/grail_1001/shadr/gggrx_1200a_sha.tab) ([data.nasa.gov](https://data.nasa.gov/dataset/grail-moon-lgrs-derived-gravity-science-data-products-v1-0)) | NASA GRAIL / PDS Geosciences | 88 MB | `gravity/gggrx_1200a_sha.tab` | The Moon's lumpy gravity for the trip and lunar orbit: without it a low lunar orbit drifts kilometres a day from where it really is. | none |
| [GRAIL GRGM1200A label (reference radius, GM, normalisation)](https://pds-geosciences.wustl.edu/grail/grail-l-lgrs-5-rdr-v1/grail_1001/shadr/gggrx_1200a_sha.lbl) ([data.nasa.gov](https://data.nasa.gov/dataset/grail-moon-lgrs-derived-gravity-science-data-products-v1-0)) | NASA GRAIL / PDS Geosciences | 11 kB | `gravity/gggrx_1200a_sha.lbl` | Reads the gravity field correctly: the label defines its units and frame. | none |
| [DSN Telecommunications Link Design Handbook 810-005, module 301 (coverage and geometry, antenna horizon masks)](https://deepspace.jpl.nasa.gov/dsndocs/810-005/301/301O.pdf) | NASA JPL Deep Space Network | 3.1 MB | `dsn/810-005-301O.pdf` | Each Deep Space Network antenna's real horizon: the lowest elevation at which it can hear the Moon, by direction. | none |
| [DSN 810-005 module 301 Rev. O horizon mask spreadsheet (every antenna, every degree of azimuth, effective 1 May 2024)](https://deepspace.jpl.nasa.gov/dsndocs/810-005/301/Horizon-Masks-Download-V2-301O.xlsx) | NASA JPL Deep Space Network | 441 kB | `dsn/Horizon-Masks-Download-V2-301O.xlsx` | The ground-station catalogue's receive masks: when each Deep Space Network antenna can hear the Moon (python -m app.data.build_ground_stations). | none |
| [OMNI hourly solar wind, geomagnetic and solar indices (OMNI2_H0_MRG1HR), 1963 to date](https://gov-nasa-hdrl-data1.s3.amazonaws.com) ([data.nasa.gov](https://data.nasa.gov/dataset/omni-hourly-data-set)) | NASA GSFC Space Physics Data Facility, via NASA HelioCloud on AWS | 190 MB | `spaceweather/omni_hourly/` | Solar activity (F10.7, Ap) that sets air drag in Earth orbit, and the history of solar storms and proton events used to check radiation estimates. | none |

**Used only to check our numbers**

| Dataset | Provider | Size | Goes to `data/` | Needed for | Account |
|---|---|---|---|---|---|
| [IM-1 Odysseus reconstructed trajectory (CLPS SPICE archive)](https://naif.jpl.nasa.gov/pub/naif/pds/pds4/clps/clps_spice/spice_kernels/spk/clps_to2im_im1_cru_rec_240216_240221_v01.bsp) | NASA JPL NAIF / PDS | 72 kB | `clps/clps_to2im_im1_cru_rec_240216_240221_v01.bsp` | Checks our trip and launch-time calculations against where IM-1 actually flew (February 2024). | none |
| [IM-2 Athena reconstructed trajectory (CLPS SPICE archive)](https://naif.jpl.nasa.gov/pub/naif/pds/pds4/clps/clps_spice/spice_kernels/spk/clps_prime1_im2_cru_rec_250227_250306_v01.bsp) | NASA JPL NAIF / PDS | 9.5 MB | `clps/clps_prime1_im2_cru_rec_250227_250306_v01.bsp` | Checks our trip and launch-time calculations against IM-2 (March 2025). | none |
| [Blue Ghost Mission 1 reconstructed trajectory (CLPS SPICE archive)](https://naif.jpl.nasa.gov/pub/naif/pds/pds4/clps/clps_spice/spice_kernels/spk/clps_to19d_bgm1_cru_rec_250115_250302_v01.bsp) | NASA JPL NAIF / PDS | 24 MB | `clps/clps_to19d_bgm1_cru_rec_250115_250302_v01.bsp` | Checks the Earth-orbit loops and lunar orbit against Blue Ghost 1 (January to March 2025). | none |
| [Peregrine Mission One reconstructed trajectory (CLPS SPICE archive)](https://naif.jpl.nasa.gov/pub/naif/pds/pds4/clps/clps_spice/spice_kernels/spk/clps_to2ab_apm1_cru_rec_240108_240118_v02.bsp) | NASA JPL NAIF / PDS | 863 kB | `clps/clps_to2ab_apm1_cru_rec_240108_240118_v02.bsp` | Tests that the trip model notices an unmodelled push: Peregrine's propellant leak (January 2024). | none |
| [LRO reconstructed orbit, March to June 2025 (LRO SPICE archive)](https://naif.jpl.nasa.gov/pub/naif/pds/data/lro-l-spice-6-v1.0/lrosp_1000/data/spk/lrorg_2025074_2025166_v01.bsp) | NASA JPL NAIF / PDS | 7.7 MB | `validation/lro/lrorg_2025074_2025166_v01.bsp` | Checks the trip calculation in low lunar orbit against where the Lunar Reconnaissance Orbiter actually flew. | none |
| [Goldstone radar elevation model of the lunar south pole (~150 m)](https://pds-geosciences.wustl.edu/lunar/gdscc-l-dss14_dss13_dss15_dss25-5-v1/lram_10xx/data/south_pole_mosaic.img) ([data.nasa.gov](https://data.nasa.gov/dataset/goldstone-moon-dss14-dss13-dss15-dss25-5-altimetry-v1-0)) | NASA JPL Goldstone Solar System Radar / PDS Geosciences | 64 MB | `validation/goldstone/south_pole_mosaic.img` | An independent terrain measurement (radar, not laser) to check the skylines built from LOLA. | none |
| [Goldstone south pole elevation model label (projection and units)](https://pds-geosciences.wustl.edu/lunar/gdscc-l-dss14_dss13_dss15_dss25-5-v1/lram_10xx/data/south_pole_mosaic.lbl) ([data.nasa.gov](https://data.nasa.gov/dataset/goldstone-moon-dss14-dss13-dss15-dss25-5-altimetry-v1-0)) | NASA JPL Goldstone Solar System Radar / PDS Geosciences | 4.9 kB | `validation/goldstone/south_pole_mosaic.lbl` | Reads the Goldstone elevation model correctly. | none |
| [OSIRIS-REx sample return capsule, reconstructed from release to entry interface (OD 383a), 24 September 2023](https://naif.jpl.nasa.gov/pub/naif/pds/pds4/orex/orex_spice/spice_kernels/spk/src_230924_230924_230930_od383a_v1.bsp) | NASA NAIF / PDS (OSIRIS-REx SPICE archive) | 58 kB | `validation/orex/src_230924_230924_230930_od383a_v1.bsp` | The entry state the capsule entry model starts from, to check its landing point against the measured one. | none |
| [NOAA GEFS 10 m wind at the Cape, one year of archived forecasts (reduced here)](https://noaa-gefs-pds.s3.amazonaws.com) | NOAA NCEP, via AWS Open Data | 481 kB | `hindcast/gefs_wind_florida.cache.jsonl` | Re-running the one-year check of the wind rules' shares against the Cape's weather station. The result itself is kept in the repository. | none |
| [Measured air at 30-70 km on OSIRIS-REx's entry day: TIMED/SABER and the Table Mountain lidar (originals)](https://cdaweb.gsfc.nasa.gov/sp_phys/data/timed/saber/level2a_netCDF/2023/267/) | NASA TIMED/SABER (CDAWeb) and NASA JPL Table Mountain Facility (NDACC) | 82 MB | `bulk/capsule_air/` | Re-making the two small profiles the capsule's atmosphere models are checked against. The profiles themselves are kept in the repository. | none |

**Large archives, fetched only on request (`polar-data sync --tier bulk`)**

| Dataset | Provider | Size | Goes to `data/` | Needed for | Account |
|---|---|---|---|---|---|
| [KSC Advanced Ground Based Field Mill network, 1997-2012](https://data.ghrc.earthdata.nasa.gov/ghrcw-protected/kscmill__1/) ([data.nasa.gov](https://data.nasa.gov/dataset/ksc-advanced-ground-based-field-mill-v1-7b0b5)) | NASA MSFC GHRC DAAC | 1.5 TB | `bulk/kscmill/` | How often the electric field at Kennedy exceeds the launch limit, by month and hour: the history behind the field-mill launch rule. | NASA Earthdata Login (free) |
| [Combined GLM hourly thunder-hour data, 2019-2025](https://data.ghrc.earthdata.nasa.gov/ghrcw-protected/glmhth__1/) ([data.nasa.gov](https://data.nasa.gov/dataset/combined-geostationary-lightning-mapper-glm-hourly-thunder-hour-data-product)) | NASA MSFC GHRC DAAC | 77 GB | `bulk/glm_thunder_hours/` | How often lightning is seen near each launch pad, by month and hour, for dates beyond the weather forecast. | NASA Earthdata Login (free) |
| [NOAA GEFSv12 reforecast, 10 m wind at the pads, 2000-2019 (reduced here)](https://noaa-gefs-retrospective.s3.amazonaws.com) | NOAA PSL and EMC, via AWS Open Data | 759 kB | `hindcast/gefs_reforecast_wind.cache.jsonl` | Re-running the many-year check of the wind rules at the Cape and Vandenberg. Only the pads' grid points are read, by byte ranges, from a 50 GB archive; the result is kept in the repository. | none |
| [NOAA HRRR version 4, 10 m wind at the pads, 2021-2025 (reduced here)](https://noaa-hrrr-bdp-pds.s3.amazonaws.com) | NOAA NCEP, via AWS Open Data | 590 kB | `hindcast/hrrr_wind.cache.jsonl` | Re-running the check of HRRR's wind at the Cape and Vandenberg, read by byte ranges from a 100 GB archive. The result is kept in the repository. | none |
| [Hourly wind at the Cape (KXMR) and Vandenberg (KVBG) weather stations (ASOS)](https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py) | Iowa Environmental Mesonet (Iowa State University), from NWS ASOS | 10 MB | `hindcast/asos_*.csv` | The observed wind that every weather check is scored against; fetched by the three weather-check commands. | none |

<!-- required-data:end -->

## Data and credits

Every number traces to a public source, listed in full in `docs/data-sources.md`:

- **Terrain:** LOLA polar elevation models `LDEM_80S_20M` and `LDEM_80S_80M`,
  from the LOLA team via the PDS Geosciences Node.
- **Sun and Earth positions, and frames:** NAIF SPICE kernels `de440`,
  `moon_pa_de440_200625`, `moon_de440_250416`, `pck00011` and `naif0012`, from
  NAIF / JPL.
- **CLPS missions:** NASA Science CLPS delivery pages, NASA news releases and
  LROC landing-site images (NASA/GSFC/Arizona State University), with a source
  and an access date on every record in `data/missions.json`.
- **Feature names and centres:** the IAU Gazetteer of Planetary Nomenclature
  (USGS Astrogeology) and the LPI Lunar South Pole Atlas.

## License

Apache License 2.0; see `LICENSE`.

---

**This is not a NASA product and is not endorsed by NASA** or any other space
agency. It was built for the NASA International Space Apps Challenge. Data
product and mission names are the public identifiers of the sources above, used
to cite them; no agency logo or insignia appears anywhere in it.
