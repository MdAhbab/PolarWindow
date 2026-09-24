# Handoff Spec: POLAR WINDOW frontend ← backend API

> **Updated 24 September 2026.** Routes are now `/site`, `/skyline` and `/plan`
> (the old `/clocks`, `/horizon` and `/blackout` redirect). There is one view
> for everyone: the Simple · Explain · Expert switch was removed, and detail
> opens on request (a key number's label, closed rows). `/states` and `/story`
> are gone (the four ideas are on the front page, `/#why`). The data contracts
> and the four states in §5 are unchanged.

Scope: what an engineer needs to wire `frontend/` to the API **without changing
a single visual decision**. The design is finished. Colours, spacing, type,
motion and layout are fixed and documented in `conventions.md`; this spec does not
revisit them.

What *is* changing is the data source: a Web Worker running a synthetic DEM and
a mean-element ephemeris becomes HTTP against real LOLA terrain and real SPICE.
So this spec is mostly a **contract**, and the sections that matter are §3
(tokens as they already exist), §5 (the four states every bound component must
have) and §6 (what each screen reads).

---

## 1. Overview

Eight screens, one primitive: *time above the local horizon*. Sun and Earth are
always drawn identically so the eye compares them without a legend.

| | route | reads |
|---|---|---|
| S1 | `/map` | site list, tiles, per-site summaries |
| S2 | `/site` | focused site's arcs + the four numbers |
| S3 | `/compare` | `POST /compare` |
| S4 | `/skyline` | `GET /sites/{id}/horizon` |
| S5 | `/plan` | `GET /sites/{id}/windows` + autonomy |
| S6 | `/report` | metrics + windows + provenance |
| S7 | `/` | the front page (static, plus `/sites` counts) |
| S9 | `/missions` | **v2, new home.** `GET /missions` (§10) |
| S10 | `/missions/:id` | **v2.** `GET /missions/{id}`, the target site's metrics, `/calendar` (§10) |

S1's tile read is aspirational: as of 2026-09-23 `PolarMap` draws schematic terrain
and never calls `/tiles` (FE-2 wires the real hillshade).

---

## 2. Layout and breakpoints

Unchanged from the existing build. Recorded here only so nobody "improves" it:

| Breakpoint | Behaviour |
|---|---|
| ≥1280 | Rail + content + detail card side by side. The intended shape. |
| 1024–1279 | Detail card drops below the visual; the visual keeps its aspect. |
| 768–1023 | Single column; the rail becomes a horizontal scroller. |
| <768 | Single column; `KeyNumbers` stacks 2×2 rather than 1×4, because the four numbers must stay visible *together* — splitting them across a scroll defeats the product. |

Minimum touch target 48×48 everywhere (invariant 7).

---

## 3. Design tokens

**Already extracted.** `frontend/src/styles/globals.css` defines every token in
a Tailwind v4 `@theme` block, with a `:root[data-theme='light']` override.
Measured contrast ratios are in the comments beside each value.

The brief asks for tokens to be extracted into `tokens.css` or `theme.ts` and
hardcoded values replaced by token references. **That work is already done** —
there is no separate `tokens.css` to create, because `@theme` *is* the token
layer in Tailwind v4, and every component consumes them as utility classes
(`text-ink-2`, `bg-panel`, `border-line`) rather than as literals.

What remains is narrower and is the actual task:

| Gap | Action |
|---|---|
| SVG `fill`/`stroke` attributes in the data visuals | Use `var(--color-sun)` etc., never a hex literal. Audit: `TwoClockRings`, `PolarMap`, `HorizonProfile`, `BlackoutTimeline`. |
| Motion durations repeated in components | Read from the M1–M6 table; a single source per id. |

Token groups, unchanged:

| Group | Tokens | Meaning |
|---|---|---|
| ground | `canvas` `panel` `raised` `inset` | Surfaces, darkest to lightest |
| lines | `line` `line-strong` | Hairlines and emphasis |
| ink | `ink` `ink-2` `ink-3` | 16.3:1 / 7.8:1 / 5.5:1 on dark |
| sun | `sun` `sun-fill` `sun-soft` `sun-deep` `on-sun` | Sunlight and power. Glow means sunlight and nothing else. |
| earth | `earth` `earth-fill` `earth-soft` `earth-deep` `on-earth` | Earth contact |
| dark | `dark-fill` `hatch` | Never an empty gap; always hatched |
| alert | `alert` `alert-deep` `alert-wash` | Magenta, never red, never paired with green |
| terrain | `terrain-high` `terrain-mid` `terrain-low` `psr` | Low chroma only |
| margin | `uncertain` | The margin we admit to |
| radius | `none` (data) `control` 2px `pill` (view switches only) | |

---

## 4. Component props that change

Only the data source changes. Component *signatures* stay as they are; the
`select` adapter in `frontend/src/lib/api/adapters.ts` converts the wire format
into the existing `SiteMetrics` / `Arc` / `TrackSample` shapes.

| Wire | Existing type | Adapter rule |
|---|---|---|
| `duration_s`, `*_s` | `hours`, `*H` | ÷ 3600, once, in the adapter |
| ISO 8601 strings | `tH` (hours from window start) | `(Date.parse(iso) - Date.parse(start)) / 3.6e6` |
| `snake_case` | `camelCase` | generated types in, hand-written types out |
| parallel arrays | `TrackSample[]` | zip in the adapter |
| `el_deg: number[]` | `Float32Array` | `new Float32Array(arr)` — `maskElevationAt` expects it |
| `state: 0\|1\|2` | *new* | 2 lit, 1 penumbral, 0 dark. See §5. |

**New capability the design already has vocabulary for.** The backend returns a
three-state visibility series, not a boolean: the Sun's disc is 0.27° wide and
Earth's is ~0.9°, so there is a band where the body is *partially* occluded.
Measured on a real site, 9.6 % of samples fall in it. The design already
distinguishes "blocked" (hatch at +45°) from "uncertain" (hatch at −45°) —
penumbral uses the uncertain hatch. No new colour, no new legend.

---

## 5. The four states, on every data-bound component

This is the part that must not be skipped. `conventions.md` invariant 2 and the API's
mandatory `meta.uncertainty` exist to make all four expressible.

| State | Trigger | What the component shows |
|---|---|---|
| **Loading** | query `isPending` | `LoadingPanel`: a real progress bar over sites resolved / total, never a spinner. Copy already says totals can only fall as more terrain is found. |
| **Empty** | filters exclude everything | `EmptyState` with the filter that excluded them and a one-click way to relax it. Never "No results." |
| **Error** | 4xx/5xx | `ErrorPanel` fed **directly** from the problem detail: `title`, `detail`, `ui.still_works`. The server writes the copy so it can be improved without a frontend deploy. |
| **Uncertain** | `meta.uncertainty.grazing` or `coverage < 1` or `summary === null` | `UncertaintyNote` plus the −45° hatch at the affected arc edges. **The number is still shown.** Uncertain does not mean hidden. |

`summary: null` on a site is the uncertain state, not the empty state, and not
zero. A zero is a measurement.

`grazing: true` ⇒ render the word, not a ± figure. `edge_timing_s` is `null` in
that case precisely so a component cannot accidentally format it.

---

## 6. What each screen reads

| Screen | Query | Key | Stale time |
|---|---|---|---|
| S1 map | `GET /sites` | `['sites', filters]` | 5 min |
| S1 map | tiles | n/a (browser cache) | immutable |
| S2 clocks | `GET /sites/{id}/windows` | `['windows', id, start, end, step, engine]` | 5 min |
| S2 clocks | `GET /sites/{id}/metrics` | `['metrics', …]` | 5 min |
| S3 compare | `POST /compare` | `['compare', ids.sort(), window, rankBy]` | 5 min |
| S4 horizon | `GET /sites/{id}/horizon` | `['horizon', id, engine]` | **Infinity** |
| S5 blackout | `GET /sites/{id}/windows` | shared with S2 | 5 min |
| S6 report | metrics + windows + `GET /sites/{id}` | shared | 5 min |

`/horizon` is `staleTime: Infinity` deliberately: a mask is immutable for an
engine version, and both `HorizonProfile` and `PolarMap` want it. It should be
fetched once per session and never again — the single biggest request-count win
available.

Every key includes `engine_version`, or a backend redeploy serves stale
geometry from the client cache. That is the worst failure available here,
because nothing looks wrong.

---

## 7. The date slider

The interaction the architecture exists for (ADR-2).

| Element | State | Behaviour |
|---|---|---|
| `DateSlider` | drag | `placeholderData: keepPreviousData`. Previous numbers stay, dimmed — never a skeleton flashing five times a second. |
| `DateSlider` | drag | Superseded fetches abort via `signal`. The server still completes and caches them: the user is dragging *through* that value and will come back. |
| `useCountUp` (M4) | new value | Animates between two real values, 600 ms. Never from zero. |
| `DateSlider` | play (M1) | 708 h in 14 s, **linear**. Easing a physical rate tells the viewer something untrue. |
| `DateSlider` | reduced motion | Play disabled, ±6 h step buttons appear. Branches in code, not only CSS. |

Server-side quantisation means a drag emits a small set of repeated cache keys
rather than a continuum. Verified: three starts 41 s apart return byte-identical
bodies and report `cache: "hit"`.

---

## 8. Edge cases

- **Long site names** — `Nobile rim 1` … `de Gerlache-Kocher massif` (25 chars).
  Truncate at the rail with a `title`, never mid-word in the detail card.
- **A site with no mask** — 409 with `ui.still_works`. The site stays visible in
  the list with `summary: null`; it is not removed.
- **A compare set where one site is unsurveyed** — `unavailable[]` is populated
  and the other sites still rank. Never blank the table.
- **Ties** — `ties: [[id, id]]` groups sites the data cannot distinguish.
  Render them at the same rank. Ordering them asserts a difference that is not
  there.
- **Slow connection** — timeline is ~210 KB uncompressed, ~35 KB gzipped.
  `keepPreviousData` covers the gap.
- **No API at all** — the error panel carries `still_works`; terrain tiles are
  static files and keep working.

---

## 9. Accessibility notes (see also the M8 audit)

- Focus order: skip link → nav → filters → visual → rail → detail card.
- Every chart has a table twin (`ArcTable`) rendered from the same array. The
  screen-reader path and the export path must not diverge from the picture.
- M3 re-order announces a sentence in a live region; the animation is not the
  only signal.
- `grazing` and `coverage < 1` must reach the accessible name, not only the
  hatch — colour and texture never carry meaning alone.
- Known gap, stated rather than papered over: no screen-reader user has tested
  the arc-list announcements.

---

## 10. CLPS v2 surfaces (2026-09-23)

**Rule for everything below: no new visual language.** Every surface is built
from the existing tokens (§3) and components (`Panel`, `SectionLabel`,
`Segmented`, `Chip`, `Button`, `IconButton`, `SearchField`, `EmptyState`,
`LoadingPanel`, `ErrorPanel`, `UncertaintyNote`, `KeyNumberRow`, `Ribbon`,
`DateSlider`, `PolarMap`, `Sources`). If a screen seems to need a new colour,
radius, shadow or type size, it is using the wrong existing one.

**Colour discipline carries over.** `sun` means sunlight and `earth` means Earth
contact, and nothing else, so **mission pins, statuses and providers are never
amber or cyan**. `alert` means "over the survival limit" and nothing else, so a
failed landing is **not** magenta. Missions are drawn in `ink` / `ink-2` /
`line-strong`, and distinguished by shape and text. `uncertain` and the −45°
hatch mean "a margin we admit to", which is exactly what an unconfirmed field
is.

### 10.1 Information architecture and navigation

| Tab (order) | Route | Icon (existing) | Notes |
|---|---|---|---|
| Missions | `/missions` | `pin` | **New home.** `/` redirects here after the first visit (U1). |
| Map | `/map` | a map or grid icon if one exists; otherwise `pin` with a different label | Candidate sites (`kind=candidate`) plus mission-target pins as a toggle layer |
| Site | `/site` | `clocks` | Renamed from "Two clocks" (critique); the old `/clocks` redirects. |
| Compare | `/compare` | `compare` | Can be seeded from a mission |
| Plan | `/plan` | `gap` | Was "Blackout"; the old `/blackout` redirects. |

- Skyline (`/skyline`) is reached from Site ("See the skyline"), and Report
  (`/report`) from Site and Mission detail ("Printable report").
- **Phone (< 768):** the bottom tab bar is `fixed inset-x-0 bottom-0 z-40
  bg-canvas`, with `pb-[env(safe-area-inset-bottom)]` and **all 5 tabs**.
  `<main>` gets `pb-16 lg:pb-0` (U3).
- **First visit:** `/` goes to `/story`. It is remembered in `localStorage`,
  wrapped in try/catch, and the default if storage fails is to show Missions.
  The story's last panel's primary button is "Browse CLPS missions" →
  `/missions`. "Start here" links to `/story` from the header on desktop and
  the settings sheet on phones.

### 10.2 S9 Missions (`/missions`)

**Overview.** Every CLPS delivery at a glance: where it went or will go, when,
what it carries, and whether it worked. The killer interaction is to select the
*Volatiles* chip: the map and timeline redraw to show only the missions
carrying volatiles instruments, and the south-polar ones stand out in the inset.

**Layout** (≥ 1280, the intended shape):

```
┌ header: h1 "CLPS missions" · count "12 of 15 missions" (live region) ─────────┐
├ filters row: instrument-type Chips (multi) · Segmented status · provider Chips ┤
├──────────────────────────────────────────┬─────────────────────────────────────┤
│ Moon view (two orthographic discs:       │ Mission list (buttons), grouped:    │
│  Near side ◐  Far side ◑)                │  Upcoming · Flown · Cancelled       │
│ + south-polar inset (PolarMap, real      │ each row: name · provider · date    │
│   hillshade in FE-2) with mission pins   │  (precision) · status text ·        │
│   and landing ellipses                   │  payload-type words                 │
├──────────────────────────────────────────┴─────────────────────────────────────┤
│ Programme timeline, 2024 → last dated mission + 1 y; one lane per provider     │
└─────────────────────────────────────────────────────────────────────────────────┘
│ Ask panel (§10.5), collapsed by default into a Button "Ask about missions"     │
```

**Moon view.** Two orthographic discs, centred on 0°E and 180°E, with a 30°
graticule in `line`, the limb in `line-strong` and the disc fill in `panel`.
Label them "Near side (faces Earth)" and "Far side". **The discs are schematic,
the positions are exact**: add a caption line "Schematic globe; positions from
published coordinates" in `text-ink-3`. The south-polar inset is `PolarMap`
with a mission layer; clicking the pole region on either disc focuses the
inset. Far side, a caption "Earth never rises here" appears only when a
far-side mission is focused, and only if its site's `earth_contact_s == 0`. The
fact comes from the API, never from the view.

**Pins.**
- Mission targets are a **diamond** (rotated square, 10 px, stroke `ink`,
  fill `panel`).
- Candidate sites keep their existing circle-and-letter.
- Selected: fill `ink`, plus the existing focus ring.
- Filtered-out missions are **removed**, not dimmed, because the count line says
  how many are hidden.
- `planned_target` coordinates get a dashed stroke; `actual_landing` is solid.
  The legend says so in words.

**Landing ellipse** (inset only): `ellipse_ring` as an SVG path, stroke
`line-strong` at 1 px, no fill. It is drawn only when not null; there is no
default ellipse.

**Programme timeline** (the `Ribbon` idiom, horizontal):
- The x-axis is years. One lane per provider, with its label left-aligned in
  `text-ink-2`.
- A mark for each landing date. Its width encodes date precision:
  - `day`: a 2 px tick in `ink`;
  - `month`, `quarter` or `year`: a bar spanning that period, filled with the
    **uncertain −45° hatch**.

  So date uncertainty uses the vocabulary the app already has.
- A status glyph after the mark is text: ✓ completed, ◐ partly successful, ✕
  landing failed or lost, ○ planned, → in transit. It always comes with a
  `title` and the accessible name. The glyph is never the only signal.
- "Today" is a vertical `line-strong` rule labelled "Today", taken from the
  client clock. This is the one place the clock is used, and it is labelled.
- Linked with the list and the map: hover or focus on one highlights the same
  mission in the other two.

**Filters.**
- Instrument types: multi-select `Chip`s with `tone="neutral"`. Selection means
  any-of, and the chip label says what it matches ("Volatiles").
- Status: `Segmented` with *All · Flown · Upcoming*.
- Provider: `Chip`s.
- All filter state lives in the URL query (shareable, back-button safe), not
  only in zustand.

**States.**

| State | Trigger | Shows |
|---|---|---|
| Loading | `useMissions` pending | `LoadingPanel` in the list column; map discs drawn empty with graticule |
| Empty | filters exclude all | `EmptyState`: title "No missions match these filters", detail names the filters, primary "Clear filters", secondary "Remove {last chip}" |
| Error | problem detail | `ErrorPanel` from `title`/`detail`/`ui.still_works` |
| Uncertain | a row has `unconfirmed_fields` | the row shows "Some details unconfirmed" in `text-uncertain`; no value is invented |

**Responsive.**

| Breakpoint | Changes |
|---|---|
| 1024–1279 | The list moves below the Moon view; the timeline stays full width |
| 768–1023 | Discs side by side above the inset; list below; the timeline scrolls horizontally inside its panel (`overflow-x-auto`, with the scroll region labelled) |
| < 768 | **List first** (it answers faster), then the Moon view, then the timeline. The filter row scrolls horizontally. |

**Accessibility.**
- Focus order: filters → list → map → timeline.
- The list is the primary accessible path. Every mission is a `<button>` or
  link named from the data in this order: "{name}, {provider}, {landing date in
  words with its precision}, {status}, carries {instrument types}".
- The map pins are focusable, but `aria-hidden` duplicates of the list are
  **not** allowed. Either they are real buttons with names, or the map is
  `role="img"` with a summary sentence and the list is the interaction. Choose
  the second for the discs and the first for the inset, matching `PolarMap`.
- The timeline has a table twin (a `T` toggle, as `ArcTable` does) listing
  mission, provider, date with precision, and status.
- A filter change announces "Showing 5 of 15 missions" in a polite live region.

### 10.3 S10 Mission detail (`/missions/:id`)

**Overview.** One mission, fully sourced. Then the product's question: *what
do Sun and Earth do at this target over this mission's days?*

**Layout (≥ 1280):** two columns, 5/7 split.

Left column, the **record**, in `Panel`s:
1. `h1` with the mission name and vehicle name. Beneath it, one line: provider ·
   lander · task order.
2. **Status** with the sourced `outcome_note`. Status is a text label, never
   colour-coded.
3. **Dates**: launch, landing, end of mission, each with its precision in words.
4. **Target**: name, coordinates (mono), coordinate kind ("actual landing" or
   "planned target"), and the ellipse axes when present.
5. **Payload manifest**: a real `<table>` with columns Payload · Organisation ·
   Measures (instrument-type words) · Purpose · Source. Each row's source is a
   link, with the link text being the publisher name, never "link".
6. **Sources**: the mission's `sources[]`, each with its accessed date.
7. The `data_version` in `text-ink-3`.

Right column, **Sun & Earth at this target** (sticky at ≥ 1280):
1. The **surface window** line, with its basis in words:
   - *published*: "{start}–{end}, as flown";
   - *planned*: "{start}–{end}, planned";
   - *assumed*: "one lunar day from landing (duration not published)";
   - *none*: "Landing known only to the month; choose a date below".
2. `UncertaintyNote` when `terrain_modelled == false`: "Terrain is not modelled
   outside 80°S. Sun and Earth are computed against a smooth Moon, so real hills
   could block more." The four numbers still render, in the uncertain variant.
3. `KeyNumberRow`: the same four numbers, in the same order and colours as
   everywhere (critique: same anchors everywhere).
4. Two `Ribbon`s (sun, earth) over the window, with the `DateSlider` cursor.
5. The **window picker** (§10.4).
6. Actions, as `Button` secondary:
   - "Open the site page" → `/site` with this site and window;
   - "Compare with nearby candidates" → `/compare` seeded with the target and
     the 3 nearest candidates by great-circle distance (computed client-side from
     coordinates, and labelled "nearest by distance");
   - "Printable report" → `/report`.
7. **Explain** (A1, §10.5) as a collapsed disclosure: "What is it like at this
   site?".

**Fields that are unconfirmed.** In place of the value, the word **Unconfirmed**
in `text-uncertain`, with a `title` and accessible description "No source found
for this field as of {latest accessed date}". Never a dash, never blank, and
never a value "for illustration".

**States.**

| State | Shows |
|---|---|
| Mission loading | Record skeleton lines in `bg-inset` (static, no shimmer, because motion is reserved); the right column shows `LoadingPanel` |
| Mission 404 | `ErrorPanel` "That mission isn't in the list", `still_works` "All other missions are available", primary "Back to missions" |
| No target (`site_id == null`) | The right column is an `EmptyState`: "Target not published, so Sun and Earth can't be computed for it yet" |
| Metrics loading | `KeyNumberRow` in its `computing` state |
| Metrics error | `ErrorPanel` inside the right column only; the record stays |
| Uncertain | as for any site (grazing, coverage), plus `terrain_modelled == false` |

**Responsive:** < 1280 the right column follows the record's header block
(answer first: status and dates, then the four numbers, then the payloads).
< 768 the payload table becomes a definition list per payload (`<dl>`), keeping
the source link in each.

### 10.4 Window picker and month strip (shared by Mission detail and Site)

**Purpose:** "compare … dates quickly". It drives `setWindow(startH, hours)` in
`lib/store.ts`.

| Element | Component | Behaviour |
|---|---|---|
| Start date | native `<input type="date">`, styled like `SearchField` (same height, border and focus ring) | UTC dates only; the label says "Start (UTC)" |
| Duration | `Segmented` with *Mission · 14 d · 30 d · 90 d · 1 y* ("Mission" only when a surface window exists) | Maximum 730 d, which is the API limit |
| Month strip | 12 cells (one year from the start's month), each cell two thin bars (sun `bg-sun-fill`, earth `bg-earth-fill`) whose heights are that month's `sun_fraction_up` / `earth_fraction_up`; a censored longest-dark shows the uncertain hatch on the cell's bottom edge | Click or Enter sets the window to that month. Arrow keys move between cells. The strip is a `role="listbox"` with each cell `role="option"` named "{Month year}: sunlight {n} percent, Earth {m} percent", with the values from the API. |
| Window line | text | "30 days from 14 Mar 2027" in words. ISO appears only in exports (U10). |

**Requests.** Changing the window changes the query key. TanStack cancels the
superseded fetches through `signal` and keeps the previous numbers dimmed
(`keepPreviousData`). No debounce is needed: server quantisation collapses
nearby keys (§7).

### 10.5 Agents: Ask (A4), Advise (A2), Explain (A1), Brief (A3)

**Placement.**
- **Ask:** a collapsible `Panel` on Missions, with the prompt "Ask about
  missions and sites".
- **Advise:** on Compare, as "Find sites that meet a requirement". The
  requirement is a textarea, with an example as placeholder text: "200 W solar
  and at least 4 hours of Earth contact per day".
- **Explain:** on Mission detail and Site, as a disclosure.
- **Brief:** on Report, as three cards (`Panel` each): Planner memo · Lesson
  plan · Public explainer. They are one generation, so they can't disagree.

**The shared response card** (one component, used by all four):

```
┌ Panel ───────────────────────────────────────────────────────────────┐
│ status line (text-ink-3, mono): "AI answer · gemini-3.8-flash · 3.2 s"│
│ body: the validated structured output, rendered as text, never HTML  │
│ "Numbers used" (SectionLabel/h2): each claim → value → tool · field   │
│ [How the AI got this]  ← opens the run-log drawer at this run_id     │
└──────────────────────────────────────────────────────────────────────┘
```

| `status` | Card shows |
|---|---|
| `ok` | As above. |
| `insufficient_data` | `EmptyState`-style: title "Not enough data to answer", detail = `reason` from the API verbatim, primary "Rephrase", secondary "Browse missions". **No partial answer.** |
| `degraded` (timeout, outage, or no key) | `UncertaintyNote`: "The AI didn't respond, so this summary was built directly from the measurements." Then the deterministic summary. The status line reads "Summary from measurements (no AI)". |
| `guard_rejected` | `UncertaintyNote`: "The AI's answer included a number we couldn't trace to a measurement, so we replaced it with a summary built from the measurements." Then the deterministic summary. |
| loading | The status line reads "Asking… checking every number against the measurements", and the submit `Button` is disabled. No spinner. A `Cancel` button aborts the request (`signal`). |
| error (HTTP) | `ErrorPanel` from the problem detail |

Never render model text as HTML. Never show a number in the body that is not
in "Numbers used"; the server already guarantees this, so the UI must not
reformat numbers in a way that creates new ones.

### 10.6 Run-log drawer ("How the AI got this")

- A right-side drawer: a `<dialog>`, `aria-modal`, with focus trapped and
  returned to the opener on close. It opens from any response card, and from a
  header `IconButton` labelled "AI activity log".
- Content: `GET /agents/runs`, newest first. Each run is a row with agent,
  model, status, latency, tokens (in/out), attempts and time. Expanding a row
  shows its tool calls as a real `<table>`: # · tool · arguments (mono,
  wrapped, max 3 lines then "Show all") · latency · error.
- Guard rejections are listed inside the run as "Rejected: {number} not found in
  tool results". This is the demo's proof that the guard works.
- Empty: "No AI runs yet. Ask a question to see how the answer is built."
- Width: 480 px at ≥ 768; full screen below.
- Motion: slides in with the M3 curve over 460 ms. With reduced motion it
  appears instantly.

### 10.7 Honesty rules that change existing screens

- **Compare "best"** (U11). Label an item "best" **only** when the API gives
  `rank == 1` and the item is not censored and not over the limit. When
  `rank == null`, print "cut short, can't rank" in `text-uncertain`, with the
  `rank_range` in the title ("could be 1st–3rd"). Tied items print "joint
  {rank}".
- **Map filter default** (U5): the dark-gap filter starts at "Any"
  (`Infinity`), and its maximum is the site maximum rounded up to 24 h.
- **Provenance badge** (U12): shown on every screen at every width, once.

### 10.8 Accessibility carried into v2 (from the 2026-09-23 critique)

- Change these tokens' values, and only these (U6, U7):

  | Token | Dark | Light |
  |---|---|---|
  | `--color-hatch` | `#5f6a75` | `#6b7178` |
  | `--color-ink-3` | `#8d99a5` | light value unchanged unless it measures under 4.5:1 on `inset` |
  | `--color-uncertain` | `#8a95a1` | same check |

- `SectionLabel` renders as `<h2>` with the same classes (U9).
- The single-key shortcuts get an off switch, stored in the store (default on)
  and exposed in the settings sheet (U8, WCAG 2.1.4).
- Controls are at least 44 px (U15).
- Timestamps read as "Day 12, 26 March, 09:00 UTC" on screen and in
  `aria-valuetext`; ISO stays in the exports (U10).
