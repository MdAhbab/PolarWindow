# Handoff Spec: POLAR WINDOW frontend ← backend API

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
| S2 | `/clocks` | focused site's arcs + the four numbers |
| S3 | `/compare` | `POST /compare` |
| S4 | `/horizon` | `GET /sites/{id}/horizon` |
| S5 | `/blackout` | `GET /sites/{id}/windows` + autonomy |
| S6 | `/report` | metrics + windows + provenance |
| S7 | `/story` | static |
| S8 | `/states` | all four states, live |

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
| radius | `none` (data) `control` 2px `pill` (faces only) | |

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
