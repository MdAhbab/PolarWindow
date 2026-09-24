# POLAR WINDOW

**Sunlight and contact with Earth for every NASA CLPS mission and for candidate
landing sites at the Moon's south pole.**
NASA Space Apps Challenge 2026: *CLPS Lunar Mission Browser*.

A project manager picks a mission or a site and reads, in about ten seconds,
how much sunlight a lander gets, how long it can talk to Earth, and the longest
stretch it has to survive alone. The numbers are computed from real NASA terrain
and real Sun and Earth positions, and each one shows how far it could be off.

```bash
make install     # backend and frontend dependencies
make seed        # SPICE kernels, LOLA terrain, 15 sites, horizon masks (about 10 min, once)
make dev         # postgres, redis, API on :8000, frontend on :5173
```

Or `python3 run.py`: it starts Postgres and Redis, installs what is missing, and
runs the API and the frontend together. The frontend also runs with no backend
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
docs/              system design, seven ADRs, API, data sources, validation,
                   test plan, runbook, accessibility, and the judge report
```

The layering is enforced, not trusted: `make contracts` runs import-linter over
eight contracts (`core/` does no I/O, routes import neither the ORM nor the data
layer, services import no FastAPI, `spiceypy` is reached only through
`core/spice.py`, agents reach the domain only through `agents/tools.py`).

## The AI helpers

Four agents over the same numbers, reachable only through six declared tools,
running on Google Gemini models with a fallback order set in Settings:

- **What is it like at this site?** (A1): one plain paragraph about a site.
- **Find sites that meet a requirement** (A2): ranks sites against a stated need,
  and says plainly when nothing qualifies.
- **Summary memo** (A3): a memo for the team on the printable report.
- **Ask about missions and sites** (A4): questions in plain language over the data.

**Every number in an answer must trace to a tool result.** An answer with a
number that is not in the tool outputs is rejected, the model is told which one,
and it gets one retry. Fail twice, time out, or have no model configured, and
the answer is replaced by a summary built directly from the measurements. The
four numbers never depend on an API key. Every run, rejections included, is
recorded and shown in the AI activity log (Settings → Project).

## Tests

```bash
make test-fast               # unit, property and synthetic golden tests; no services
make test                    # all 316 backend tests: unit, integration, golden
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
- **Hindcast against flown landers** in `docs/validation.md`.
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
- No screen-reader user has tested the announcements yet.

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
| `docs/adr/` | Seven decision records |
| `docs/api.md`, `docs/openapi.json` | The REST API |
| `docs/data-sources.md` | Every dataset and where it comes from |
| `docs/validation.md` | Hindcast of flown landers |
| `docs/test-plan.md` | What is tested and why |
| `docs/accessibility.md` | WCAG audit and fixes |
| `docs/runbook.md`, `docs/deploy-checklist.md` | Running and deploying it |
| `docs/conventions.md` | Invariants, and the plain-English word list |

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
