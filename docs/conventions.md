# POLAR WINDOW — conventions and invariants

Landing site planning for the Moon's south pole. NASA Space Apps 2026, challenge
"CLPS Lunar Mission Browser".

**Two halves.** `backend/` is FastAPI + Postgres + Redis over SPICE and the LOLA
polar DEM. `frontend/` is Vite + React 19 + TypeScript + Tailwind v4 and its
design is finished — do not redesign it.

```
make install       # both halves
make seed          # kernels, terrain, sites, horizon masks. ~10 min, once.
make dev           # services + api on :8000 + frontend on :5173
make test          # every backend test: unit, integration, golden
make test-fe       # frontend units: the adapter, the cache keys, the exports
make lint          # ruff, mypy --strict, 8 import contracts
make test-fast     # unit + property + synthetic golden. No services, < 20 s.
```

`make test-fast` is the fastest way to see whether a change to the physics broke
anything. Run it before and after touching `backend/app/core/`.

**The geometry moved to the backend.** The frontend no longer computes anything:
`src/lib/geometry/` retains the four-number constants and a mean-element
sub-solar point used *solely* for the schematic terminator overlay on the map.
Every number on screen comes from the API.

---

## The one idea

Every screen draws the same primitive: **time above the local horizon**. A
filled arc, a filled bar, a filled ring segment — Sun and Earth always drawn
identically so the eye compares them without being taught a legend first. If a
new view needs a different metaphor, that is a strong signal it is answering a
question this product does not ask.

Four numbers decide a mission and they always appear together, in this order:

1. hours of sunlight in the window
2. hours of Earth contact in the window
3. longest unbroken dark gap
4. longest unbroken comms blackout

Never average them into a score. A score hides which corner you gave up, and
the whole point of the tool is to show the trade.

---

## Architecture

```
backend/app/
  core/            PURE. No I/O, no DB, no clock. This is what makes it testable.
    kernels.py     SPICE kernel download, verify, metakernel. Fails loudly.
    spice.py       the ONLY importer of spiceypy. One dedicated thread.
    horizon.py     1440-ray march. Takes a sampler callable, not a raster.
    visibility.py  ENU basis, az/el, three-state lit/penumbral/dark
    intervals.py   boolean series -> runs. Knows nothing about astronomy.
    metrics.py     the four numbers. No composite score, ever.
    timeline.py    composes mask + ephemeris into arcs
  data/            LOLA access (HTTP range reads), site resolution, tiles
  db/              models + one repository per aggregate
  services/        policy. Never imports fastapi.
  api/v1/          routes + pydantic schemas only
  agents/          four agents, six tools, the grounding guard
  workers/         precompute: masks and reference metrics

frontend/src/
  lib/api/         schema.ts (GENERATED), client.ts, adapters.ts, queries.ts
  lib/store.ts     zustand: UI state ONLY
  lib/mission.ts   the bridge: useFocusedMetrics, useMetricsFor, window params
  components/      design system + the data visuals
  screens/         S1–S8
```

**Data flow.** zustand owns what the user chose; TanStack Query owns what the
server said. Nothing derived from the server is ever `set()` into zustand. Each
screen's queries fetch what that screen needs; `useQueries` over a dynamic site
array preserves the per-site streaming render. Ranking is the server's too: S3
posts to `/compare` and draws the ranks and ties it is given, because two
implementations of "which site is best" is one more than this product can
defend.

**The expensive step is precomputed by construction.** Ray-casting a site's
skyline is ~45 ms against real terrain and depends on nothing but the site.
After it, a site *is* 1,440 numbers and everything the date slider touches is a
lookup plus one vectorised `spkpos`. Never move the ray-cast onto a request path.

**Window quantisation is why the slider is fast.** `start`/`end` snap to the
`step_s` grid before anything else, so a drag collapses onto a small set of
cache keys. Do not remove it.

**The layering rule is enforced.** `make contracts` runs import-linter over
eight contracts. `core/` imports no I/O; routes import neither the ORM nor the
data layer; services import no FastAPI; `spiceypy` is reachable only through
`core/spice.py`; agents reach the domain only through `agents/tools.py`.

---

## Invariants — please keep these

1. **No hardcoded metric.** Every number on screen is derived from
   `SiteMetrics`. If you find yourself typing `61` into JSX, something upstream
   is missing. The only literals are `SURVIVAL_LIMIT_H` and
   `DEM_VERTICAL_ERROR_M`, both flagged as placeholders.
2. **Every number carries its ±, or says why it cannot.** `crossingTolerance`
   returns `grazing: true` when the body crosses the skyline too shallowly to
   time. Show the word, never a fake precision.
3. **Every value is an estimate, and says so once per screen** (the footer line,
   `format.ts` `ESTIMATES`); "≥" marks a value the dates cut short and "±" a
   timing margin. Every response carries `meta.uncertainty`, which is never
   null. The data-source badge reads from `/healthz` and appears only when the
   data is not live (*Saved copy*, *Partial data*, *No data*) — it is never a
   hardcoded label.
4. **Colour never carries meaning alone.** Sun is amber *and* the outer ring
   *and* labelled; blocked is hatched at 45°; uncertain is hatched at −45°;
   over-limit is magenta *and* a triangle glyph *and* the words. No red/green
   pair exists anywhere.
5. **Every chart has a table twin** rendered from the same arc array
   (`ArcTable`). The screen-reader path and the export path must not diverge
   from the picture.
6. **Radius 0 on data surfaces**, 2px on controls, pill only on a view switch
   (the Missions map's *South pole · Whole Moon*). Amber and glow mean sunlight
   and nothing else: primary buttons are ink, never amber.
7. **Real elements.** `<button>`, `<a href>`, `<input>` + `<label>`. Never
   `role`/`onClick` on a div. Minimum target 48×48.
8. **Every animation has a named static fallback** and branches in code, not
   only in CSS — `useReducedMotion()` combines the OS setting with the in-app
   toggle.

---

## Words

One name for each idea, in plain English, everywhere it appears. No coined
terms on screen; a technical term is spelled out where it appears. The
professional name of a key number is shown only when its label is pressed
("Also called …"). Keep to these:

| Say | Not |
|---|---|
| time in sunlight | time in the Sun, sunlit window |
| time in contact with Earth | call home, Earth link, DTE (on request: "Also called Direct-to-Earth (DTE) contact") |
| longest night | longest dark gap, dark period |
| time without contact | blackout, silence, RF blackout (on request: "Also called radio (RF) blackout") |
| dark and out of contact at once | compound event |
| the dates, these dates | the window |
| stretch | arc |
| skyline | horizon mask |
| flat ground, hills not counted | smooth Moon |
| terrain map (LOLA) | elevation model, hillshade, DEM |
| Sun and Earth positions (SPICE) | ephemeris |
| battery limit | survival limit |
| Plan (the page) | Blackout planner |
| Printable report | Hand-over report |
| Saved copy | Cached snapshot |
| landing spot | target, feature centre (say "centre of X, not a landing point") |

## Motion

| id | what | duration | easing | fallback |
|----|------|----------|--------|----------|
| M1 | terminator sweep (`PolarMap` + `DateSlider`) | 708 h in 14 s | **linear, never eased** | play disabled, ± 6 h step buttons |
| M2 | ring fill (`TwoClockRings`) | 600 ms | `cubic-bezier(.16,1,.3,1)` | mask fully open in one frame |
| M3 | compare re-order (`CompareScreen`) | 460 ms | `cubic-bezier(.2,.8,.2,1)` | instant, plus a live-region sentence |
| M4 | number roll (`useCountUp`) | 600 ms | same as M2 | value set directly |
| M5 | horizon reveal (`HorizonProfile`) | 900 ms | same as M2 | paths drawn complete |
| M6 | uncertainty band (`.breathe`) | 8 s loop | linear | static at 0.34 opacity |

M1 is linear because it represents a real rate. Easing a physical motion tells
the viewer something untrue about it.

---

## Traps, learned the hard way

Each of these reached running code. Do not reintroduce them.

- **A crater's IAU coordinate is its floor.** Shackleton's published centre is
  −2,767 m — a permanently shadowed hole. Site coordinates are *derived* from
  the DEM by `data/ingest_sites.py`. Do not "correct" them to catalogue values.
- **Grid north is not true north** in polar stereographic. It rotates with
  longitude — 166° of error at Shackleton. `local_frame()` measures it.
- **The LOLA polar products are true at the pole**, not at a standard parallel.
- **Near-field DEM noise looks exactly like a ridge.** At 40 m a 2 m error is
  2.9° of apparent skyline. The mask only counts blockers clearing their own
  noise floor. Do not "simplify" that rule away.
- **The horizon can be negative and must not be clamped.** A site 1,958 m above the
  lunar reference sphere looks *down* at −2.4°, which is the entire reason it has
  81 % sunlight while the Sun never rises above level.
- **Prefetched agent facts must enter the grounding pool**, not just the prompt.
- **respx cannot intercept google-genai** (it runs in a worker thread). Model
  calls are blocked at our own `_generate` seam.

## Still a placeholder

- `SURVIVAL_LIMIT_H = 120` in the frontend. The backend returns durations and
  refuses to return verdicts — a verdict needs a thermal model.
- DEM vertical error is a per-tier constant: 2 m on the 20 m product, 4 m on the
  80 m one, and each bearing carries whichever tier set its skyline. It is still
  not per-pixel — wire the LDEC count products and every ± follows.
- `illumination` and `psr` tiles are approximations from a ring-based horizon
  proxy, labelled in the response headers.

---

## Things that are deliberately not done yet

- No screen-reader user has tested the arc-list announcements. That is the
  first thing to fix, and the accessibility copy says so rather than claiming
  a pass.
- The map's hillshade and terminator are schematic and labelled as such; the
  per-site DEM covers 20 km at 20 m, the map view ~300 km at 80 m.
- The exports on S5 and S6 emit CSV and SPICE interval lists from the arcs
  already on screen (`lib/export.ts`), but nothing validates the SPICE file by
  loading it back through spiceypy.
- There is one view. Detail is on request (a number's label, a closed row);
  nothing is hidden that a claim depends on: a caveat that changes what a
  number means stays on screen as a one-line note.
