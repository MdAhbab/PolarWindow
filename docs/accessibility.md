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
