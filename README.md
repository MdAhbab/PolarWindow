# POLAR WINDOW

**Landing site planning for the Moon's south pole.**
NASA Space Apps Challenge 2026 — *CLPS Lunar Mission Browser*.

Sun, Earth and terrain at candidate south-pole landing sites, in one picture a
mission planner can read in about ten seconds.

```bash
make install     # backend + frontend dependencies
make seed        # SPICE kernels, LOLA terrain, 15 sites, horizon masks (~10 min, once)
make dev         # postgres, redis, api on :8000, frontend on :5173
```

---

## What problem this solves

The challenge brief says the existing tools have "complicated interfaces" that
make it "difficult to evaluate critical information with efficiency". That is an
interface problem stated as an interface problem, and this is an answer to it:
the science is solved to the second, and getting a *decision* out of it is the
part that still takes a week.

Four numbers decide a mission, and they always appear together:

| | |
|---|---|
| **Sunlight** | hours the Sun is above the site's own horizon |
| **Earth contact** | hours Earth is above it — direct-to-Earth geometry |
| **Longest dark gap** | the single longest unbroken night |
| **Longest RF blackout** | the single longest unbroken silence |

The last two are the ones that kill missions, and they are the ones a total or
an average hides. There is **no composite score** anywhere in this system, and
a test asserts there never will be: a score ranks sites on one axis and hides
which corner was given up, and the trade is the product.

---

## It computes, from real data

Not a mockup wired to fixtures, and no longer a synthetic stand-in either:

1. **Terrain** — the LOLA gridded polar DEM (`LDEM_80S_20M`, 20 m posts) from
   the PDS Geosciences Node. Fetched per site as a 20 km window by HTTP range
   request, with an 80 m regional tile covering 20–50 km.
2. **Horizon mask** — a real ray-cast: 1,440 bearings at 0.25°, stepped outward
   to 50 km, curvature drop of `r²/2R` subtracted, and a blocker only counted
   where it stands above the noise its own DEM error could produce.
3. **Positions** — SPICE `spkpos` against DE440 in the `MOON_ME` frame, with
   light-time and stellar aberration, projected into each site's local
   east/north/up frame using unit vectors rather than the textbook azimuth
   formula, which loses all its precision within a degree of the pole.
4. **Arcs** — every sign change of `elevation − skyline` is bracketed at 15
   minutes and refined by bisection, and each crossing carries a timing
   uncertainty derived from the DEM's vertical error divided by the rate the
   body crosses the skyline.
5. **The four numbers, and the compound events** — the intersection of "no Sun"
   and "no link", which is what the autonomy packet is sized from.

Change the window and the numbers are recomputed, because the geometry is
being evaluated, not replayed.

### What it says

Fifteen sites, one lunar day from 2027-03-14, computed by this build:

| code | site | lat | sun | Earth | longest night | longest blackout |
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

"≥" marks a night the window cut short: the reference window, not the
terrain, ended it, so the figure is a lower bound and the true night is
longer. The API returns this as `longest_dark_open`, and `/compare` refuses
to rank a lower bound as best.

Three findings fell out of the physics rather than being designed in:

- **The power/comms trade is a latitude trade.** Of the five sites above 70 %
  sunlight, four sit within 1.6° of the pole and have 61–70 % Earth contact;
  the fifth, Sverdrup rim, sits 2° out and gets 45 %. Both sites above 76 %
  Earth contact sit four to six degrees out and pay for it with a night of
  304 h and at least 288 h. Ice is at the pole, continuous power is at the pole, and
  continuous Earth contact is *away* from it.
- **At the pole the Sun never rises, and that is not the problem.** At
  Connecting Ridge the Sun's elevation stays between −1.6° and −0.7° for the
  entire month — it never gets above level. The site is still sunlit 81 % of
  the time, because it stands 1,958 m above the lunar reference sphere and
  looks *down* at a horizon averaging −2.4°. Terrain, not season, decides who has power.
- **Direct-to-Earth at the pole is libration-limited, not terrain-limited.**
  Earth's elevation swings through about 13° on a 27-day cycle (−7.4° to +6.0°
  at Connecting Ridge), so polar sites lose it for days at a time in one long
  stretch rather than in short terrain-cut gaps.

### A site is not a crater

Every well-known name near the south pole refers to a *crater*, and the IAU
coordinate for a crater is its **centre** — which is the permanently shadowed
floor and the worst possible place to land. Sampling LOLA at the published
centres of Shackleton, Haworth and Shoemaker returns −2,767 m, −3,316 m and
−3,932 m.

So site coordinates here are **derived, not asserted**. Each named feature's IAU
centre is an anchor; the landing point is the most *open-skied* landable post in
a stated ring or disc around it, found by searching the DEM. The anchor, the
search region, the offset and the rule are all recorded on every site and
returned by the API. One seed was removed entirely rather than moved until its
number looked acceptable — see `backend/app/data/ingest_sites.py`.

---

## The screens

| | |
|---|---|
| **S1 `/map`** | South polar stereographic, live terminator, site picker, filters |
| **S2 `/clocks`** | The signature view: two concentric rings, four numbers |
| **S3 `/compare`** | Several sites, one shared window, re-ordering by metric |
| **S4 `/horizon`** | Standing at the site, looking out at the skyline |
| **S5 `/blackout`** | Comms timeline, compound events, autonomy packet |
| **S6 `/report`** | One-page hand-over, light theme, print-ready |
| **S7 `/story`** | Four panels: why the south pole is hard |
| **S8 `/states`** | Empty, loading, error and uncertain — live, not drawn |

Three audience faces (planner / educator / public) change density and pacing.
They never change the data, and they never drop a caveat to make a sentence
shorter.

---

## Architecture

```
frontend/          React 19 + Vite + Tailwind v4. Design is finished; do not redesign.
  src/lib/api/     generated types, typed client, adapters, TanStack Query hooks
backend/
  app/core/        PURE. No I/O, no DB, no clock. kernels, spice, horizon,
                   visibility, intervals, metrics, timeline, projections
  app/data/        LOLA access, site resolution, tile rendering
  app/db/          SQLAlchemy 2.x models + one repository per aggregate
  app/services/    policy. Never imports FastAPI, so the worker and the agent
                   tools call exactly the same code the routes do
  app/api/v1/      routes + pydantic schemas only
  app/agents/      four agents, six tools, the grounding guard
  app/workers/     precompute: masks and reference metrics
docs/              conventions, system design, six ADRs, test plan, API, runbook
```

**The layering rule is enforced, not trusted.** `make contracts` runs
import-linter over eight contracts: `core/` imports no I/O, routes import
neither the ORM nor the data layer, services import no FastAPI, `spiceypy` is
reachable only through `core/spice.py`, and agents reach the domain only through
`agents/tools.py`.

**The expensive step is precomputed by construction.** Ray-casting a site's
skyline is ~45 ms against real terrain and depends on nothing but the site;
after it, a site *is* 1,440 numbers and everything the date slider touches is a
lookup plus one vectorised `spkpos`. A 708-hour timeline at 900 s (2,836
samples) costs about 15 ms cold and about 4 ms warm over HTTP, measured on this
build (Apple M3, 24 September 2026).

---

## The AI layer

Four agents over the same numbers, reachable only through six declared tools:

- **A1 Site Explainer** — one plain paragraph about what a site is like.
- **A2 Trade-off Advisor** — ranks sites against a stated requirement, and must
  say plainly when nothing qualifies.
- **A3 Audience Writer** — the same facts as a planner memo, a lesson plan and a
  public explainer, from one generation so they cannot disagree.
- **A4 Question Answerer** — natural language over the site database.

**Every numeric claim must trace to a tool result.** A response containing a
number that is not in the tool outputs is rejected, the model is told which
number and what was actually available, and it gets one retry. Fail twice and
the answer is discarded and replaced by a deterministic summary built from the
measurements — which is also what happens if the model times out or is not
configured at all. The four numbers never depend on an API key.

A *correct* derived number is still rejected: the guard cannot tell correct
arithmetic from lucky arithmetic, so derivations belong in tools. Every run,
including every rejection, is recorded in `agent_runs` and served at
`GET /api/v1/agents/runs`.

---

## Tests

```bash
make test-fast   # unit + property + synthetic golden. No services, < 20 s
make test        # everything: unit, integration and golden (292 tests)
make test-fe     # frontend unit and component tests (129)
cd frontend && npm run e2e   # browser tests, axe included; API on :8000
make lint        # ruff, mypy --strict, import-linter
```

- **Property tests** over `core/intervals.py` with hypothesis: partition,
  alternation, contiguity, inversion symmetry, concatenation, monotonicity.
  Off-by-one errors in longest-run detection are the most likely silent bug in
  this project, and they produce a plausible number rather than an exception.
- **Golden fixtures** for three sites chosen to exercise different physics,
  pinned with stated tolerances and a manifest recording the kernels, the DEM
  and the reason they were last regenerated. `make golden-update` refuses
  without `GOLDEN_UPDATE_REASON`.
- **A synthetic golden set** runs the same code paths with no kernels and no
  database, so the safety net survives on a laptop.
- **The ray-march is tested against analytic surfaces** whose horizon can be
  derived by hand: a plane, a cone, a wall, a ramp and a crater bowl. The
  numba-compiled selection is pinned to its plain-Python twin.
- **No test reaches the real Gemini API.** An autouse fixture blocks the
  transport, so a forgotten mock fails loudly.

---

## What is still a placeholder

Named, rather than quietly left:

- `SURVIVAL_LIMIT_H = 120` in the frontend is a stand-in. The backend returns
  durations and refuses to return verdicts, because a verdict needs a thermal
  model this system does not have.
- The map's terminator is drawn from a mean-element model, not SPICE. It is a
  schematic overlay; every *number* comes from the API.
- The `illumination` and `psr` tile layers are approximations from a ring-based
  horizon proxy, labelled as such in the response headers. They are right about
  which craters are dark; they are not published products.
- DEM vertical error is a per-tier constant — 2 m for the 20 m product, 4 m for
  the 80 m one — and each bearing carries the tier that actually set it. It is
  still not a per-pixel figure: wire the LDEC count products and every
  uncertainty in the app follows automatically.
- No screen-reader user has tested the arc-list announcements.

---

## Keyboard

```
[  ]        step the date by 6 h        ⇧[ ⇧]  by one day
1 2 3       switch audience face        T      read the chart as a table
Tab         nav → filters → map → card → rail
```

---

## Data and credits

Every number in this product traces to a public source, listed in full in
`docs/data-sources.md`:

- **Terrain:** LOLA polar digital elevation models `LDEM_80S_20M` and
  `LDEM_80S_80M`, from the LOLA team via the PDS Geosciences Node.
- **Ephemeris and frames:** NAIF SPICE kernels `de440`, `moon_pa_de440_200625`,
  `moon_de440_250416`, `pck00011` and `naif0012`, from NAIF / JPL.
- **CLPS missions:** NASA Science CLPS delivery pages, NASA news releases, and
  LROC landing-site images (NASA/GSFC/Arizona State University), with a source
  and an access date on every record in `data/missions.json`.
- **Feature names and centres:** the IAU Gazetteer of Planetary Nomenclature
  (USGS Astrogeology) and the LPI Lunar South Pole Atlas.

## License

Apache License 2.0; see `LICENSE`.

---

**This is not a NASA product and is not endorsed by NASA** or by any other
space agency. It was built for the NASA International Space Apps Challenge.
Data product and mission names are the public identifiers of the sources
above, used to cite them; no agency logo or insignia appears anywhere in it.
