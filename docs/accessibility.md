# Accessibility audit — POLAR WINDOW

**Standard:** WCAG 2.1 AA · **Date:** 2026-09-18 · **Scope:** the surfaces that
changed when the frontend was wired to the API. The existing design system was
built to these rules and is not re-litigated here.

Method: read the rendered accessibility tree in a real browser, plus keyboard
traversal. Automated tooling catches perhaps 30 % of issues, so this is a floor.

---

## Summary

**Found: 4 · Critical: 0 · Major: 3 · Minor: 1 · All three Major fixed.**

## Findings

### Robust

| # | Issue | Criterion | Severity | Status |
|---|---|---|---|---|
| 1 | The provenance badge announced only its `title` — "Terrain from the LOLA lunar polar elevation model…" — and the word carrying the status (*Measured* / *Partial data* / *No data*) was lost entirely. This is the one element on screen that tells a user how much to trust every other number. | 4.1.2 Name, Role, Value | 🟡 Major | **Fixed.** `role="status"` plus an `aria-label` that leads with the status and then explains it. Visual treatment unchanged. |
| 2 | The theme and motion buttons announced a sentence instead of an action: "Both themes pass contrast. The light one is for print and projection." A user heard an essay, not a button. | 4.1.2 Name, Role, Value | 🟡 Major | **Fixed.** Explicit `aria-label` ("Switch to the light theme"), sentence retained as a tooltip. |

### Perceivable

| # | Issue | Criterion | Severity | Status |
|---|---|---|---|---|
| 3 | Each nav link contained the same label twice, in a `hidden lg:inline` / `lg:hidden` pair, so it announced "Map Map". The second span was dead markup: the whole `<nav>` is `hidden lg:flex`, so it could never render. | 1.3.1 Info and Relationships | 🟡 Major | **Fixed.** One label; the small-screen icon is now `aria-hidden`. |
| 4 | The arc-edge tolerance renders as "±17.1" with the unit in an adjacent element, so it can be announced without "hours". | 1.3.1 | 🟢 Minor | **Open.** Reading order currently supplies the unit; worth an `aria-label` if a screen-reader user reports it. |

---

## What was verified as passing

| Check | Result |
|---|---|
| Skip link, first in tab order, visible on focus | ✅ `Skip to the content` → `#pw-main` |
| Landmarks | ✅ `banner`, `navigation[aria-label="Views"]`, `main`, `complementary` |
| Heading present and meaningful | ✅ `heading "Connecting Ridge"` |
| Range input has a real label | ✅ `textbox "Mission window — one lunar day, 709 h"` |
| Chart has a text alternative that carries the data | ✅ `img "Two clock rings over 709 hours. Outer amber ring: the Sun is above the local skyline for about 574 h…"` |
| Every chart has a table twin | ✅ `ArcTable`, from the same array — the screen-reader path and the export path cannot diverge from the picture |
| Focus ring, never removed | ✅ one `:focus-visible` rule, 2 px, `--color-focus` |
| Touch targets | ✅ controls are `h-12` (48 px) |
| Colour never alone | ✅ blocked hatches at +45°, uncertain at −45°, over-limit adds a glyph *and* the words "2 h over the 120 h limit" |
| Motion has a static fallback | ✅ `useReducedMotion()` combines the OS setting with the in-app toggle and branches in code, not only CSS |

### Contrast

Measured on the dark canvas `#0A0C0E`, unchanged from the existing system:

| Element | Ratio | Required | |
|---|---|---|---|
| Body `--color-ink` | 16.3:1 | 4.5:1 | ✅ |
| Secondary `--color-ink-2` | 7.8:1 | 4.5:1 | ✅ |
| Captions `--color-ink-3` | 5.5:1 | 4.5:1 | ✅ |
| Sun amber | 9.4:1 | 3:1 (graphic) | ✅ |
| Earth cyan | 9.8:1 | 3:1 | ✅ |
| Alert magenta | 6.8:1 | 4.5:1 | ✅ |

The light theme darkens amber and cyan deliberately: at their dark-theme values
they sit at 1.8:1 on light stock and fail the 3:1 a non-text mark needs.

---

## The new three-state visibility

The API now returns `lit | penumbral | dark` rather than a boolean, because the
Sun's disc is 0.27° across and Earth's is ~0.97°, so ~10 % of samples fall in a
partially-occluded band.

This needed **no new colour and no new legend**. The design already
distinguishes two hatches — blocked at +45°, uncertain at −45° — and penumbral
takes the uncertain hatch. Adding a third colour would have broken the rule that
colour never carries meaning alone, for a state that is genuinely "we cannot say
precisely".

---

## Known gap, stated rather than papered over

**No screen-reader user has tested the arc-list announcements.** The `ArcTable`
is structurally correct and the alt text carries the numbers, but "structurally
correct" and "usable" are different claims and only one of them has been
verified. This is the first thing to fix, and the accessibility copy in the app
says so rather than claiming a pass.

---

## 2026-09-24 review: the CLPS v2 screens (WCAG 2.1 AA)

Scope: every route (Missions, Mission detail, Map, Site, Compare, Horizon,
Blackout, Report, Story, States), both themes, the Simple and Expert faces,
at 1440, 1280, 1024, 720 (1440 at 200 % zoom), 375 and 320 px, with reduced
motion on and off.

### How it was checked

- **axe** (`@axe-core/playwright`, tags `wcag2a wcag2aa wcag21a wcag21aa`) on
  every route in both themes and both faces, on the phone layout, inside the
  run-log and settings dialogs, and on the offline copy: **zero serious or
  critical violations**. This runs in `npm run e2e` and fails the build.
- **Keyboard**: the e2e suite drives the demo path by keyboard where it
  matters: the month strip (arrows, Home, End, Enter), the table twin (T and
  its button), the shortcut switch, Escape out of every dialog with focus
  returned to the opener, and Tab held inside a dialog.
- **Reflow**: no page-level horizontal scroll on any route at 320, 375, 720,
  1024 or 1280 px. Wide charts and tables scroll inside a named, focusable
  region instead.
- **Contrast**: computed from the tokens in `frontend/src/styles/globals.css`
  (table below).

### Fixed in this pass

| Issue | WCAG | Fix |
|---|---|---|
| Horizontal scroll regions (Horizon chart, Blackout timeline and ledger, arc table, "Numbers used") could not be reached by keyboard | 2.1.1 | `ScrollRegion`: a named `region` with `tabIndex=0` |
| Timing margins printed in `earth-soft` failed 4.5:1 in the light theme, and used Earth's colour for something that is not Earth contact | 1.4.3, 1.4.1 | ink |
| Tab could walk out of the run-log and settings dialogs into the browser's own controls | 2.4.3 | focus wraps inside `Sheet` |
| The close buttons of the dialogs were named "Close ai activity log" | 4.1.2 | "Close: AI activity log" |
| Compare and Map had no page heading | 1.3.1, 2.4.6 | an `h1` each |
| The Listen button changed width between "Listen" and "Stop", moving what sat beside it | advisory | both words share one grid cell |
| Pins near the pole overlapped, so letters were unreadable and targets overlapped | 1.4.3, 2.5.5 (advisory) | clusters, and a pole close-up where they separate |
| Dates shown as raw source phrases with square brackets | 3.1.5 (advisory) | dates in words; the source phrase is the tooltip |
| The face switcher asked "who are you" | advisory (U15) | fixed then; the switch itself was removed on 24 September (see below) |

### Verified as passing

- U1 first visit goes to the story, which ends on "Browse CLPS missions"; U2
  the four numbers sit above the ring on every face; U3 the phone tab bar is
  fixed with all five tabs and nothing is hidden under it; U5 the Map's night
  filter starts at "Any"; U8 single-key shortcuts can be switched off and the
  choice is remembered; U9 section labels are `h2`; U10 timestamps read "Day
  12, 26 March, 09:40 UTC" on screen and in `aria-valuetext`; U12 one
  provenance badge per screen; U15 face targets are 44 px; U16 the Listen
  control never auto-plays, is `aria-pressed`, stops on Escape, on a new
  screen and in a hidden tab, toggles with Alt+S, and opens its transcript
  where speech synthesis is missing.
- Reduced motion branches in code: play is disabled and the ±6 h step buttons
  appear; the sheets appear without sliding; numbers are set, not rolled.
- The mission list is the primary accessible path: each row's name is built
  from the data ("IM-2, Intuitive Machines, landed 6 March 2025, 17:30 UTC,
  Partly successful, carries volatiles, …"), and a filter change is announced
  as "Showing 5 of 20 missions".
- Model text is never rendered as HTML (a component test injects markup).

### Contrast, measured from the tokens

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

### Still open

- **Light theme, month strip.** Its sunlight and Earth bars stand on
  `dark-fill` at 2.70:1 and 2.87:1, under the 3:1 a graphic needs. Each month's
  values are in its accessible name, but a sighted user reading the bars in the
  light theme gets less than AA. The fix is a token value (`sun-fill` and
  `earth-fill` in the light theme, or the well's colour), which this pass was
  not allowed to change.
- **Input borders.** `line-strong` against `panel` is 1.62:1 (dark) and 1.99:1
  (light). Buttons are identified by their text, but the date, search and
  question fields rely on their border. Same constraint: a token change.
- The known gap above still stands: no screen-reader user has tested the arc
  list, and none has tested the mission list either.

## 2026-09-24 (later): the front page, the guide and the project settings

What was added, and how each part meets WCAG 2.1 AA. Checked with axe in the
browser tests (front page, the dashboard with the guide open, the Settings
sheet, and a 375 px phone with the guide open) with zero serious or critical
findings, and by keyboard.

| Part | How it is accessible |
|---|---|
| Front page 3D Moon | The canvas is `aria-hidden` and carries nothing the text does not. Every idea is real text with a drawing beside it. Reduced motion (the system setting or the app's own) draws one still frame and turns off scrolling effects and the pointer tilt; with no WebGL the canvas is hidden and the drawings remain. Below 1024 px the Moon sits behind the text, so it is dimmed to keep the words at full contrast. A skip link leads to the content. |
| Sign-in | One real button, named *Open the dashboard*. A failure is announced (`role="alert"`) in words. No user name or password, so nothing to mistype. |
| Guide bar | A named region (`Guide`), not a dialog, so the page stays usable while it is open. The step text is a polite live region. Back, Next and Close are real buttons at 48 px; Esc closes it. The element a step describes gets a dashed ink outline, distinct from the focus ring, and is scrolled into view (instantly under reduced motion). On a phone it sits above the tab bar, and the page leaves room for it, which the phone test measures. |
| Settings, Project | Grouped under headings. The AI switch is a labelled button group. Model order is changed with *Move … up/down* buttons, not drag and drop. The two clears need a second step whose explanation is in a named group; results are announced in a live region; errors use `role="alert"`. |
| Site picker, Add a site | Native `<select>` elements with visible labels. |

### Still open from this pass

- The new selects use the `line-strong` border, so they share the input-border
  contrast gap listed above (a token change).
- The guide's step order was tried by keyboard and screen reader in the
  browser's accessibility tree only; no screen-reader user has tried it.

---

## 2026-09-24 (evening): one view, detail on request

The Simple · Explain · Expert switch was removed: every visitor gets the one
plain-English view. What the other two added is now reached from the content
itself, and each path was checked with axe (both themes) and by keyboard:

- **A number's label is a button** (`aria-expanded`, `aria-controls`) that opens
  one sentence on what the number means and, where there is one, its
  professional name ("Also called Direct-to-Earth (DTE) contact").
- **Closed rows** (`<details>`/`<summary>`, the `Disclosure` component) hold what
  used to be the Expert sidebar and the Explain panels: what blocks the Sun and
  Earth, how sure the numbers are, the sources and the table, other dates, a
  mission's target, payloads and sources. A browser test opens every row on
  Mission detail, Site, Skyline and Plan and runs axe with them open.
- **"Too close to call"** on Compare is a button that states the reason and the
  places the site could take; the reason is also in the live ranking sentence.
- The **1 2 3 shortcuts** went with the switch. The remaining single keys
  (T, [ ], Space) can still be switched off in Settings (2.1.4).
- The data-source badge appears only when the data is not live, so the status
  that matters (*Saved copy*, *Partial data*, *No data*) is never lost among
  a badge that always says the same thing.
- Routes were renamed to plain words (`/site`, `/plan`, `/skyline`); the old
  addresses redirect.

