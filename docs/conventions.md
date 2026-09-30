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
   time. Show the word, never a fake precision. The margin may also be a range
   ("3 to 7 hours through the relay, if it flies as planned") or a factor
   (a radiation fluence good to a factor of 2). `core/quantity.py` refuses a
   number with no margin and no reason (ADR-9).
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
   and nothing else: primary buttons are ink, never amber. Cyan means Earth
   contact and magenta means over the battery limit, also nothing else. Mission
   pins, statuses and providers are drawn in ink and told apart by shape and
   text, and a failed landing is not magenta.
7. **Real elements.** `<button>`, `<a href>`, `<input>` + `<label>`. Never
   `role`/`onClick` on a div. Minimum target 48×48.
8. **Every animation has a named static fallback** and branches in code, not
   only in CSS — `useReducedMotion()` combines the OS setting with the in-app
   toggle.

9. **No verdicts.** No go/no-go, "safe", readiness percentage, risk score,
   likelihood-times-consequence product, or overall chance of launch. The
   product shows the evidence rule by rule; people decide.
10. **Every number says where it came from**: computed, published (with the
    source), entered (by whom, when) or assumed. Shown on request.
11. **Every live number shows its age.** Past its staleness budget it is
    replaced by the reason there is no number (ADR-8).
12. **Every probability states its sample** ("12 of 31 model runs") and
    whether it has been checked against observations (ADR-14).
13. **Every data component has four states**: loading, empty, error and
    uncertain. Loading looks like loading, never like empty. Empty names the
    filter that excluded everything and offers one click to relax it (never
    "No results"). Error is fed straight from the problem detail (`title`,
    `detail`, `ui.still_works`) and never renders as a loader. Uncertain keeps
    the number on screen with its margin or reason: uncertain does not mean
    hidden.

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
| launch opportunity (on request: "Also called launch window") | launch window, the window |
| chance the rule is broken | probability of violation, P(no-go) |
| in Earth's shadow, in the Moon's shadow | eclipse, umbra |
| time a ground station can hear the lander | DSN coverage, view period |
| through a relay | via relay, relayed link |
| message wait | latency, end-to-end delay |
| if it flies as planned | nominal, notional |
| ready, not ready, blocked | green, red, go, no-go |
| part lost | attrition, write-off |
| booster landing zone | droneship area, LZ |
| splashdown zone | recovery area |
| the trip | cruise, transit, trans-lunar phase |
| launch period | launch window, the window (for an interval with open and close) |
| forecasts disagree | models conflict, disagreement |
| checked against observations | verified, ground-truthed |
| could see the lander | orbiter pass, relay pass (for active orbiters overhead) |
| what the rover or lander can see (line of sight) | viewshed, rover LOS |
| the space around the line of sight that the radio signal needs | first Fresnel zone, Fresnel zone clearance, RF clearance |
| NOAA’s forecast model re-run for past years | reforecast, hindcast |
| how much better than the past-years rate its calls were | Brier skill, Brier skill score, BSS |
| how close its wind speeds came | CRPS, CRPS skill, Continuous Ranked Probability Score |
| air model with solar activity | NRLMSISE-00, NRLMSIS 2.1 |
| Earth gravity model | EGM2008 |
| planned relay | speculative relay, unlaunched relay |
| launched, not working | uncommissioned relay, silent relay |

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

## Accessibility

The standard is WCAG 2.1 AA, in both themes. Each rule below came out of a real
review. Keep them.

**How it is checked.** `npm run e2e` runs axe (`@axe-core/playwright`, tags
`wcag2a wcag2aa wcag21a wcag21aa`) on every route in both themes, on the phone
layout at 375 px, with every closed row open, inside the dialogs and on the
offline copy. A serious or critical finding fails the run. Axe catches perhaps
30 % of the problems, so keyboard use and the accessibility tree are still
checked by hand.

- **Contrast.** Text needs 4.5:1. Graphics, hatches and the focus ring need 3:1.
  The measured ratios sit in the comments beside each token in
  `frontend/src/styles/globals.css`. The light theme darkens amber and cyan on
  purpose: at their dark-theme values they are 1.8:1 on light stock.
- **Names.** A control is named for its action ("Switch to the light theme") and
  the explanation goes in a tooltip. A dialog's close button says what it closes
  ("Close: AI activity log"). The data-source badge is `role="status"` and its
  label starts with the status (*Saved copy*, *Partial data*, *No data*). A chart
  is an image whose text alternative carries the numbers. Every page has one
  `h1`, and section labels are `h2`.
- **Focus.** A skip link is first in the tab order. The focus ring is never
  removed: one `:focus-visible` rule, 2 px, in `--color-focus`.
- **Keyboard.** A wide chart or table scrolls inside a named, focusable region
  (`ScrollRegion`). Dialogs keep focus inside, close on Escape and give focus
  back to the opener. The single-key shortcuts are `[` and `]` (the dates by
  6 h, with Shift by one day), `T` (the table twin) and Space (play). They can
  be switched off in Settings (WCAG 2.1.4). Alt+S starts and stops Listen.
- **Reflow.** No page-level horizontal scroll at 320, 375, 720, 1024 or
  1280 px, or at 1440 px with 200 % zoom.
- **Times in words.** A timestamp reads "Day 12, 26 March, 09:40 UTC" on screen
  and in `aria-valuetext`. ISO 8601 appears only in exports.
- **Detail on request.** A number's label is a button (`aria-expanded`,
  `aria-controls`) that opens one sentence on what the number means. Closed
  rows are `<details>` (`Disclosure`). "Too close to call" on Compare is a
  button that states the reason.
- **The list is the way in.** Each mission row is named from the data ("IM-2,
  Intuitive Machines, landed 6 March 2025, 17:30 UTC, Partly successful,
  carries volatiles, …") and a filter change is announced ("Showing 5 of 20
  missions"). The map is a summary sentence, and the list carries the
  interaction.
- **Settings** change the model order with *Move up* and *Move down* buttons,
  not drag and drop. Results are announced in a live region and errors use
  `role="alert"`. Sign-in is one button, *Open the dashboard*, and a failure is
  announced in words.
- **The front page** draws its 3D Moon in an `aria-hidden` canvas that carries
  nothing the text does not: every idea is real text with a drawing beside it.
  Reduced motion draws one still frame and turns off the scrolling effects and
  the pointer tilt. With no WebGL the canvas is hidden and the drawings remain.
  Below 1024 px the Moon sits behind the text and is dimmed to keep the words at
  full contrast.
- **Listen** never starts by itself, is `aria-pressed`, and stops on Escape, on
  a new screen and in a hidden tab. Where speech synthesis is missing it opens
  the transcript.
- **The guide** is a named region, not a dialog, so the page stays usable. Its
  step text is a polite live region, its buttons are 48 px, and Escape closes
  it. The element a step describes gets a dashed ink outline that is not the
  focus ring.
- **Model text is never rendered as HTML.** A component test injects markup to
  prove it.
- **Penumbral reuses the uncertain hatch.** The API returns `lit`, `penumbral`
  or `dark`. Penumbral takes the −45° hatch, so it needs no new colour and no
  new legend.

**Contrast, measured from the tokens in `globals.css`**

| Pair | Needs | Dark | Light |
|---|---|---|---|
| `ink` on `canvas` | 4.5:1 | 16.33 | 15.92 |
| `ink-2` on `panel` | 4.5:1 | 7.26 | 10.02 |
| `ink-3` on `inset` | 4.5:1 | 5.39 | 4.74 |
| `uncertain` on `inset` | 4.5:1 | 5.14 | 4.74 |
| `sun` on `panel` | 4.5:1 | 8.72 | 6.15 |
| `earth` on `panel` | 4.5:1 | 9.08 | 7.22 |
| `alert` on `alert-wash` | 4.5:1 | 6.30 | 5.81 |
| `on-sun` on `sun-fill` | 4.5:1 | 9.40 | 4.76 |
| `hatch` on `dark-fill` | 3:1 | 3.23 | 3.53 |
| `focus` on `canvas` | 3:1 | 13.98 | 6.39 |
| `sun-fill` on `dark-fill` | 3:1 | 8.56 | **2.70** |
| `earth-fill` on `dark-fill` | 3:1 | 8.90 | **2.87** |
| `line-strong` on `panel` | 3:1 | **1.62** | **1.99** |

**Still open.** The four bold values are token changes: the fix is a value in
`globals.css`.

- Light theme, month strip: the sunlight and Earth bars sit on `dark-fill` at
  2.70:1 and 2.87:1, under the 3:1 a graphic needs. Each month's values are in
  its accessible name.
- Field borders: `line-strong` on `panel` is 1.62:1 (dark) and 1.99:1 (light).
  Buttons are named by their text, but the date, search, question and
  site-picker fields rely on the border.

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
- **The ray-march starts two DEM posts out, not at 5 m.** Closer in, the samples
  land inside the site's own pixel, where interpolation returns the local slope.
  A half-metre rise over 10 m reads as 2.9° of skyline, and an open site once
  reported 2.96°.
- **Store the window that was computed, not the one requested.**
  `compute_window_metrics` snaps its bounds to the step grid. A reference window
  stored unsnapped is missed by every lookup, and every site's summary comes
  back null.
- **`asyncio.run()` inside an async worker raises.** The DEM fetcher has a sync
  and an async entry point for this reason.
- **Prefetched agent facts must enter the grounding pool**, not just the prompt.

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

- No screen-reader user has tested the arc list, the mission list or the guide.
  That is the first thing to fix. Until then, nothing here claims a pass.
- The map's hillshade and terminator are schematic and labelled as such; the
  per-site DEM covers 20 km at 20 m, the map view ~300 km at 80 m.
- The exports on S5 and S6 emit CSV and SPICE interval lists from the arcs
  already on screen (`lib/export.ts`), but nothing validates the SPICE file by
  loading it back through spiceypy.
- There is one view. Detail is on request (a number's label, a closed row);
  nothing is hidden that a claim depends on: a caveat that changes what a
  number means stays on screen as a one-line note.
