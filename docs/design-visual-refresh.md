# Design: the visual refresh

## 2026-10-02 · Audit and plan

**Brief.** The dashboard is correct, complete and accessible, and it reads as
dull. The owner asked for a plan that makes it interesting and fun for a
project manager to read, with a visual design to match, without losing what
the product is careful about. This document is that plan: what is wrong with
the look, the direction, the system that carries it, what changes screen by
screen, the motion, the decisions the owner has to make, and the slices to
build it in.

**Preview.** `docs/design/visual-refresh-preview.html` draws three screens in
the proposed system with the app's own numbers from the saved copy of 30
September 2026 (a mission's home, a site page, a comparison) and the type,
surface and control system behind them. Open it in a browser; the half-disc in
the floating header flips the theme. It is a direction, not a component
library: the real parts are listed under *Components* below.

**One line in `conventions.md` has to change.** It says the frontend's design
"is finished — do not redesign it". This plan is a redesign of the look, not of
the product, and every invariant there except the radius rule (invariant 6)
survives unchanged. The line should be replaced with a pointer to this file
once the owner agrees to the direction.

---

### Audit

Every route, both widths (1440 and 375), both themes, from the offline copy.

*What is right, and stays*

- The structure: a question, one sentence that answers it, at most four
  numbers in a fixed order, one chart with a table twin, everything else in
  closed rows. A reader learns it once.
- The semantics: amber is sunlight, cyan is Earth contact, magenta is over the
  battery limit, and nothing else uses them; blocked and uncertain are hatched
  in opposite directions; every status is a glyph and words; no red/green
  pair; no score, no verdict.
- The words, the margins on every number, the sources on request, the four
  states of every data component, the reduced-motion branches, the two
  self-hosted faces (Archivo, IBM Plex Mono), real elements with 48 px
  targets, axe clean.
- The map and the rings. The south pole from above on the LOLA relief and the
  two-ring clock are the two pictures a visitor remembers.

*Why it reads flat*

1. **Everything is the same box.** 131 uses of `border-line`, 53 of
   `border-line-strong`, 69 of `bg-inset`, across 46 files; 7 uses of any
   shadow in the whole app. A tile, a chart, a closed row, the mission's
   record, a filter group and the list of missions are all a 1 px #232a31
   hairline on #12161a with square corners and the same padding. There is no
   figure and ground, so the eye has nowhere to land.
2. **No light in the tonal range.** Canvas #0a0c0e against panel #12161a is a
   step of a few percent; hairlines are painted grey rather than light caught
   on an edge; the only highlight is on hover. The whole page is one dark
   sheet with lines drawn on it.
3. **Type has one voice.** Nearly everything is Archivo 400–600 between 13 and
   28 px. The page title is 28 px, the answer sentence 20 px; the key figure
   at 44 px is the one moment of scale, and it is the same on every tile,
   including a tile that reads `0 h`. Eyebrows, section labels and captions
   are not told apart.
4. **The tiles are half empty.** On Launch a tile is 220 px tall for a 44 px
   figure and three lines of footnote. On a phone the four stack 2 × 2 and the
   labels wrap to three lines above small figures.
5. **The header stack.** Logo bar, saved-copy banner, the Landing-sites sub
   bar, the page header and the date bar come to about 270 px before content
   on Map and Site. On a phone that is four rows plus a 64 px tab bar.
6. **The six steps do not read as a journey.** They are a 3 × 2 grid of six
   identical cards that each say "● Available" in 12 px grey. A project
   manager's first three questions (where is the mission, what is next, what
   is at risk) are not answered at a glance, although the data to answer them
   is on the page.
7. **Status is nearly invisible, except where it is not.** The one visual
   event on the Site page is the magenta tile for the 122 h night over the
   120 h limit, and it works. That proves the point: the page lacks contrast
   of weight everywhere else, so the one thing with weight carries it all.
8. **The map is the hero and is framed as a widget.** The south pole view sits
   inside a hairline panel under a sub-heading and a segmented control, with
   a legend row and a sidebar either side.
9. **Motion is correct and shy.** Content rises 6 px in 220 ms; the rings turn
   once; the Sun's sweep around the pole, the one animation that teaches the
   product's idea, is behind a 48 px play button on the date bar that nothing
   invites you to press.
10. **The front page and the dashboard are two products.** The front page has
    a 3D Moon, display type at 64 px and a horizon story. The dashboard
    inherits none of its atmosphere; the hand-over is a cliff.
11. **Light theme is competent and generic**: white boxes on a light grey
    field.
12. **One invariant is already bent.** The front page's primary button is
    amber; invariant 6 says primary buttons are ink. There is no data on that
    page, so it may stand as the written exception (decision D5 below).

*Palette check.* The four marks (sun, earth, alert, neutral) were run through
a categorical palette validator as part of this audit. They are a status
palette, not a categorical one: lightness is tuned for text on dark, and the
magenta against the neutral grey is weak under protan vision (ΔE 5.3; the
floor is 8). The app already carries the difference in shape (the triangle, the
words, the hatch), which is why the refresh keeps every glyph and every hatch
exactly where it is. Colour was never doing that work alone and must not start.

---

### Direction

**An instrument, lit from the horizon.** The dashboard keeps its deep-space
black, but its surfaces become machined layers rather than outlined boxes: a
hairline tray with a lit core, soft diffuse shadow, translucent edges that read
as light rather than paint, and a 3% film grain on a fixed layer so the black
has texture. The two semantic hues stay the only chroma on the page and are
allowed to glow only where they mean what they mean: the sun tile, the Sun's
arc, the terminator. The light theme is warm paper with white cards and soft
shadows, the same system with the light inverted.

Three archetypes, used by role:

- **The journey** for a mission: six steps on a line, in order, with where the
  mission got to. This is the one new picture the refresh adds, and it answers
  the project manager's first three questions in one glance.
- **The answer hero** for every step page and site page: the question as an
  eyebrow, the answer sentence as the biggest text on the page, the four
  numbers as a strip with their bars, the chart in one card, the rows in one
  grouped list.
- **The asymmetric bento** for a mission's home and the Plan page: a few cards
  of unequal size, the biggest for the thing the page is opened for (the
  record; the working-alone packet).

Seven rules decide the rest:

1. One hero per page. Everything else steps back by one level of weight.
2. Light, not lines. Hierarchy comes from tone, highlight and shadow; a
   hairline is translucent and marks an edge, never a region.
3. Scale is hierarchy. Four type sizes a page apart: display, heading, body,
   caption. The key figures get their own voice (Archivo's width axis), so a
   number is recognisably a number from across the room.
4. The two hues are sacred. Amber and cyan appear only as sunlight and Earth,
   and glow only there. Interaction is ink.
5. Motion tells the Sun's story. Arrivals are staggered and settle; bars and
   the journey line grow from their origin; the Sun's sweep is invited, not
   hidden. Words move and never fade.
6. Fun is precision with warmth: plain sentences the app already writes,
   drawings from the front page used as empty states, one playful moment per
   page (the journey drawing itself, the day counter, the ring turning into
   place), never a mascot.
7. Nothing semantic moves. Invariants 1–5 and 7–13, the Words table, every
   glyph, every hatch, every table twin, every reduced-motion branch, every
   route and every test selector (`role`, `summary`, `data-guide`,
   `data-testid`) stay as they are.

---

### The system

*Colour.* The hues do not change. The grounds and lines do.

| Token | Dark now | Dark proposed | Light now | Light proposed |
|---|---|---|---|---|
| canvas | #0a0c0e | #06080a | #f2f1ed | #f3f1ec |
| panel (a card's core) | #12161a | #0e1216 | #ffffff | #ffffff |
| raised | #171b20 | #141a1f | #ffffff | #ffffff |
| inset | #1e242a | #1a2127 | #e9e8e3 | #ebe9e3 |
| tray (new: a card's shell) | — | white 3.5% | — | ink 4.5% |
| line | #232a31 | white 7% | #dad9d3 | ink 8% |
| line-strong | #333c45 | white 15% | #b9b8b1 | ink 17% |
| highlight (new: a core's top edge) | — | white 7% | — | white 90% |
| glass (new: the island and the dock) | — | panel at 72% | — | white at 76% |
| glow-sun (new) | — | amber 32%, 56 px, sun semantics only | — | amber 22% |

Text and the hues keep their measured contrast ratios. Translucent hairlines
are never the only boundary of a control: controls keep `line-strong` (3:1
against both canvases is re-measured in slice 1, and the value raised if it
falls short).

*Surfaces: the double bezel.* A card is a tray (the tray tint, a hairline, 4 px
padding, 16 px radius, the raised shadow) holding a core (the panel, 12 px
radius, a 1 px highlight along the top). The data inside it (bars, arcs,
hatches, tables, pins, the rings, the map) keeps square corners: those are the
data surfaces invariant 6 protects. The tray is what makes a card look like a
part rather than an outline; it costs one wrapper element in `Panel`.

*Radius.* Decision D1. Proposed: 16 px tray / 12 px core on cards; 20 px on
sheets and toasts; 10 px on fields and small controls; pill on buttons, chips,
segmented controls, tags, the island and the dock; 0 on everything that draws
data.

*Type.* Archivo stays, as one variable file (`@fontsource-variable/archivo`,
with its width axis) instead of four static weights. Roles:

| Role | Face | Size / leading | Use |
|---|---|---|---|
| Display | Archivo wdth 118, 600, −0.03 em | 36–72 px, 1.02 | page titles, the answer sentence, the front page |
| Figure | Archivo wdth 112, 600, −0.035 em, tabular | 34–56 px, 0.95 | key numbers; 26 px on the day counter |
| Heading | Archivo 600, −0.015 em | 22 / 28 | card titles, record headings |
| Title | Archivo 600 | 17 / 22 | row titles, list titles |
| Body | Archivo 400 | 15 / 24 | running text (ink-2 for secondary) |
| Caption | Archivo 400 | 12 / 17 | footnotes, legends |
| Eyebrow | Archivo 600, caps, 0.16 em | 11 | questions, section labels, group titles |
| Data | IBM Plex Mono 400 | 12–13 | stamps, coordinates, axes, step numbers |

The present scale tokens (`--text-*`) stay for the sizes they already name;
the display and figure roles gain `font-stretch`. The front page may add
Instrument Serif italic for its editorial lines only (decision D4); the
dashboard does not.

*Space.* Section padding doubles on the front page (96–160 px). In the
dashboard the gutter stays 16 / 32 px; blocks inside a page go from 24 to
28–36 px apart; cards keep 20–22 px inside their core; tiles 18–22 px.

*Elevation.* Three steps, as now, with softer, longer shadows: raised
(`0 10px 30px -10px` black 55%), lift on hover (`0 22px 44px -14px` black
65%), overlay for sheets. The light theme uses the same shapes at 14–20% of
ink.

*Motion.* The two curves stay (`--ease-settle` for things arriving,
`--ease-move` for things moving across). Durations lengthen for arrivals only:
quick 160 ms, base 320 ms, slow 640 ms, arrive 820 ms. Arrivals are staggered
60 ms per item (tiles, cards, rows). Rules that do not change: transform and
opacity only; words move and never fade; the blanket reduced-motion floor and
the in-code branch; no motion library.

---

### Components (`frontend/src/components/ui.tsx` and friends)

- **Panel → Card.** Gains the tray/core structure (one wrapper), `radius`,
  `quiet` (no shadow, for grouped lists), `link` (lift on hover) and `sunlit`
  (the amber glow, allowed only on a Sun tile or the Sun's chart). Keeps
  `as`, `guide`, `elevated`.
- **Button.** Pills. Primary stays ink; gains an optional trailing arrow in
  its own 32 px circle (the "button in a button") that travels 2 px on hover;
  press scales to .98. Secondary is a hairline on the tray tint; ghost is
  unchanged. Heights stay 48 / 40 (targets unchanged).
- **IconButton.** A 44 px circle.
- **Chip, Segmented.** Pills; the selected segment is ink; the selected chip
  keeps its tick.
- **SectionLabel.** Becomes the eyebrow (11 px caps tracked) for section
  groups and questions; keeps `h2`/`h3`/`div`.
- **Disclosure, RowGroup.** Rows live inside one quiet card as a list with
  inset dividers (18 px in from each edge), hover fill, a chevron that turns.
  The `details`/`summary` elements, `data-guide` and `onOpen` are unchanged.
- **PageHeader, Breadcrumbs.** The title moves to display scale; `titleExtra`
  is regular weight at normal width; the lede sits under it; actions become
  pills.
- **KeyNumberTile / QuantityTile / NumberRow.** A tile is a card; the label
  stays 13 px; the figure moves to the Figure role (34 px on a phone, 56 px
  from 1024 px); the bar stays 4 px and square; the footnote stays 12 px. The
  alert tile's hairline is magenta at 55%, its label, figure and bar magenta,
  its triangle and words unchanged. The Sun tile may carry the glow. Subgrid
  alignment stays.
- **DateSlider.** Becomes a control bar in a quiet card: a round play button,
  the track with a filled portion and a 3 px thumb with a halo, the dates
  label, and the day counter at Figure 26 px ("Day 12 of 30") with the stamp in
  mono under it. The play button gets a label that says what it does.
- **JourneyBar → the journey.** A line through six nodes (28 px discs with
  the step number in mono), the open step's node in ink and its name bold, the
  mark that slides between steps kept (the view transition name moves to the
  node). Each node keeps its state glyph and words. On a phone the line runs
  vertically down the left.
- **StepCards.** Replaced on the mission's home by the journey plus the
  summaries under each node; the six links, their questions and summaries are
  the same text.
- **Sheet, Toast.** 20 px radius; the sheet keeps its slide; toasts arrive in
  a pill-ended card.
- **States.** `EmptyState` gains the front page's drawings (`SunPathArt`,
  `RidgeArt`, `EarthArt`, `IceArt`) by context; `LoadingPanel`,
  `WorkingPanel`, `ErrorPanel` and `StatePanel` become cards; skeletons keep
  the page's shape.
- **AppShell.** The island (below) replaces the full-width header and the
  Landing-sites sub bar; the saved-copy banner becomes one pill under the
  island; the phone's bottom bar becomes a floating dock.
- **GuideBar.** A card docked to the bottom with the same five steps; the
  dashed outline on the element it points at stays.

---

### Screens

*Shell.* A floating island, sticky at 12 px from the top: the mark and
wordmark, the two views (the open one with a dot and an inset fill), Guide and
Settings. Blur is applied to the island and the dock only. The saved-copy /
offline / partial-data line is a pill under the island, in the same words.
Inside Landing sites, Map · Site · Compare · Plan become a segmented pill in
the page header rather than a second bar. On a phone the island holds the mark
and the two icons; the two views sit in a floating dock at the bottom, clear
of the home indicator. Decision D3.

*Front page.* Keep the Moon, the four ideas and the one button. Display type
moves to the width axis; the four idea cards and the feature cards become
bezelled cards; sections breathe at 96–160 px; the "How it works ↓" link and
the enter button become pills (the enter button's amber stays, D5). The
reveal animations become the same settle curve as the dashboard at 820 ms.

*Missions.* The page header at display scale with the count as a tag. Filters
as pills in one row. The map card is the hero: it loses its sub-heading,
gains the South pole / Whole Moon pill in its top corner over the picture,
and its legend becomes one caption. The list is a quiet card with group
eyebrows and rows that light on hover; the status glyph and words stay. The
Timeline and Ask rows stay as rows.

*A mission's home.* Breadcrumb; the name at display scale with the vehicle in
regular weight; the outcome as glyph and words beside it. The journey. Then a
bento: the record (seven columns, the narrative as a heading, the dates as a
definition list), the target (five columns, the mission's pin on a small
polar map drawn with the existing `PolarMap`), what it carries, and the
Sources row. A planned mission's journey shows solid nodes behind it and
outlined nodes ahead, with a "Next" tag over the next step; a flown mission's
line is fully drawn.

*A step page (all six).* The journey in place of the step bar, the open step
marked. The question as an eyebrow, the answer at display size, the age and
Listen beside it. The four tiles. The chart card. The rows in two groups,
Details and About these numbers. The foot: "All six steps" and the "Next
step" card as a primary pill with the arrow orb. Nothing in `SectionLayout`'s
contract changes; `data-guide="section-answer"` stays on the answer block.

*Map.* The date bar becomes the control card. The map is full-bleed inside its
card with the two-view pill over its corner and the terminator sweep as the
page's one playful moment; the chosen site's card sits to the right as a
bezelled card with its four numbers as small figures and one primary pill.
The filter rail is a quiet card.

*Site.* The answer hero is added, built from the four numbers (the preview
shows the sentence). The rings keep their size and gain the glow on the Sun
ring only; the rows sit in one list; the three onward links become one
primary, one secondary and one ghost pill.

*Compare.* The rank-by control is a segmented pill; each site is a card whose
hero figure is the measure chosen for ranking, with the other three as small
figures and the two tracks under them. The columns keep their slide (M3). The
sentence under the cards stays, in the same words.

*Plan.* A bento: the hour-by-hour timeline (eight columns), the working-alone
packet (four columns, the big number at Figure 64 px, the five rows in a
list), the table of every time without contact under both. The download
button is the primary pill.

*Skyline.* The chart card is the hero, with the blocker card and "How sure is
this?" at its side; the dashed flat-horizon line, the Sun's path and Earth's
loop are unchanged.

*Report.* Unchanged on paper; its screen frame takes the card system.

*Settings, Run log.* The sheet takes the radius and the tab pills; the six
tabs and their content do not change.

---

### Motion choreography

- **A page arriving.** The header moves first; cards and tiles rise 18 px into
  place on the settle curve over 820 ms, staggered 60 ms in reading order;
  bars inside them grow from the left 120 ms after their card; the chart's
  arcs grow from the left. Text moves with its container and never fades.
- **The journey.** The line draws from the first node to where the mission
  got to over 1.2 s; nodes behind the mission are solid at rest, nodes ahead
  outlined. Changing step slides the ink node along the line (the existing
  `pw-step-mark` view transition, re-pointed).
- **Hover and press.** A link card lifts 2 px and its hairline brightens; a
  primary pill's arrow orb travels 2 px up and right and scales to 1.06; the
  button scales to .98 on press. 160 ms each.
- **The Sun's sweep.** The play button is labelled and sits where the eye
  arrives; the sweep itself stays linear (the Sun moves at a constant rate).
  The Sun tile's glow is static; nothing pulses.
- **Sheets, toasts, disclosures, skeletons, the rings, the number settle.**
  As now, with the longer arrival durations.
- **Guardrails.** Transform and opacity only; `will-change` on nothing that
  is not animating; blur on the island and the dock only; grain on a fixed
  layer with `pointer-events: none`; every animation has its reduced-motion
  branch in code and the CSS floor behind it; axe runs mid-animation in the
  tests as it does now.

---

### Decisions the owner has to make

| # | Decision | Recommendation |
|---|---|---|
| D1 | Radius on containers. Invariant 6 says 0 on data surfaces, 2 px on controls. | Keep 0 on everything that draws data (bars, arcs, hatches, tables, pins, rings, the map). Allow 16 / 12 px on cards, 20 px on sheets, 10 px on fields. Rewrite invariant 6 to say "data surfaces" means the data, not the card around it. |
| D2 | Pills on buttons, chips and segmented controls. Invariant 6 allows the pill only on a view switch. | Allow pills on all controls; the pill no longer means "view switch", the position in the header does. Primary buttons stay ink. |
| D3 | The floating island and dock in place of the full-width header, sub bar and bottom bar. | Yes. It removes two rows of chrome and gives the pages their first 100 px back. Fallback if the owner prefers a full-width bar: keep the bar, give it the glass treatment, keep the sub-pages as a segmented pill in the page header. |
| D4 | Fonts: Archivo variable with the width axis instead of four static files; Instrument Serif italic as an accent on the front page only. | Yes to the variable file (the bundle stays within a few kilobytes of today's four weights). The serif is optional; try it on the front page's four ideas and keep it only if it earns its place. |
| D5 | The front page's amber button. | Keep it as the one written exception: the page shows no data, and amber on the front page is the product's horizon. Everywhere else, primary is ink. |
| D6 | A small 3D Moon on a mission's home, turned to its landing spot. | Defer. It would load three.js (180 kB) into the dashboard. Revisit after slice 7 as an idle-time, motion-on, desktop-only extra. |
| D7 | The "design is finished" line in `conventions.md`. | Replace it with a pointer to this document once D1–D3 are agreed. |

The plan below proceeds on the recommendations. Where a decision goes the
other way, the slice it affects is marked.

---

### Slices

Each slice is checked at 1440 and 375, dark and light, with motion on and
reduced, axe clean, `npm run check` and `npm test` green, the Playwright
suite green, and the screens under `e2e/__screens__` and the offline copy
re-recorded before it is committed.

1. **Tokens and parts** (M). The colour, radius, elevation and motion tokens
   above in `globals.css`; the variable font in `main.tsx`; `Panel` → card
   with the tray and core; pills on `Button`, `IconButton`, `Chip`,
   `Segmented`; `SectionLabel` as the eyebrow; `Disclosure` and `RowGroup`
   as a grouped list; `PageHeader` at display scale; `KeyNumberTile` at the
   Figure role; `Sheet` and `Toast` radius; the grain layer. Decisions D1,
   D2, D4. Every screen changes at once here, so this slice is the one to
   review on every route before moving on.
2. **Shell** (M). The island, the saved-copy pill, the segmented sub-pages,
   the phone dock, the guide card. Decision D3. Route focus, skip link,
   `aria-current`, the `--pw-guide-h` variable and the page padding under the
   dock are the things to re-test.
3. **The journey and a mission's home** (M). `JourneyBar` as the line with
   nodes, the step mark re-pointed, the bento with the record, the target map
   and the payloads; the planned-mission variant. `StepCards` retired; its
   text moves into the nodes.
4. **Step pages** (M). The answer hero, the tile strip, the chart card, the
   grouped rows, the primary "Next step" pill, across all six sections and
   Surface. `SectionLayout`, `Answer`, `ChartPanel`, `Rows` carry the change
   so each section file changes little.
5. **Landing sites** (L). The date bar as a control card; Map with the map as
   hero and the chosen site's card; Site with its answer sentence and the
   Sun ring's glow; Compare's hero figure per card; Plan's bento; Skyline's
   card. `DateSlider` is shared by four of them and goes first.
6. **Front page** (S). Display type on the width axis, bezelled idea and
   feature cards, pill buttons, section spacing, the settle curve on the
   reveals. The Moon scene is untouched.
7. **Motion and polish** (M). The staggered arrivals, the journey draw, hover
   and press physics, the labelled play button, the illustrated empty states,
   the light theme pass, a performance pass (no blur on scrolling content, no
   layout-triggering animation, frame times on a phone), the final axe run
   in both themes, screens and offline copy re-recorded, `conventions.md`
   updated (D7) and this document's *Built* section written.

Sizes: S under a day, M one to two days, L two to three days, for one person
who knows the codebase.

---

### What does not change

The API and every number on screen. The routes and the old addresses that
redirect. The Words table. Invariants 1–5 and 7–13 of `conventions.md`, and
invariant 6 except as D1 and D2 amend it. Every status glyph and hatch. Every
table twin. Every reduced-motion branch. The unit tests and the Playwright
suite, which select by role, `summary`, `data-guide` and `data-testid`, none
of which move; only the recorded screens change.

### Risks

- **Contrast on translucent hairlines.** A 7% white line is decoration; a
  control's border must still meet 3:1, so controls keep `line-strong` and
  slice 1 measures it against both canvases.
- **Blur on low-end phones.** Blur is confined to two small fixed elements;
  slice 7 measures frame times with the Sun's sweep playing.
- **The variable font's weight.** One file with the width axis is larger than
  one static weight and about the size of the four static weights shipped
  now; slice 1 records the bundle delta in its commit message.
- **Review load.** Slice 1 touches every screen. The screens recorded before
  it are the baseline to compare against; keep them until slice 7 replaces
  them.
