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
surface and control system behind them. The mission's target card holds a
live Moon drawn with three.js (loaded from a CDN in the preview; bundled in
the app), turned to its south pole and lit from the horizon; the journey line
and the horizon light are scrubbed by the scroll where the browser supports
it. Open it in a browser; the half-disc in the floating header flips the
theme. It is a direction, not a component library: the real parts are listed
under *Components* below.

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
   hidden. Scrolling drives the longer stories (the journey drawing itself,
   the lander moving along its path). Words move and never fade.
5a. Depth where the page is about a place. Three dimensions are used for the
   Moon, the sky over a site and the path to the Moon, and nowhere else: a
   scene must show something the flat drawing cannot, carry the same numbers
   as its table twin, and fall back to that drawing without WebGL.
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

### Three dimensions

The front page already has a Moon (`landing/moonScene.ts`: three.js, the
real LOLA hillshade tiles wrapped on a sphere, GSAP ScrollTrigger scrubbing
its tilt and the Sun's position). The dashboard never loads it. The refresh
brings three.js into the dashboard for exactly four scenes, each on the page
that is about the place it shows.

| Scene | Page | What it shows that the flat drawing cannot | Data it draws | Fallback |
|---|---|---|---|---|
| **The target globe** | a mission's home | The Moon turned to the landing spot, lit by the Sun where it is on the chosen dates (the sub-solar point `useSubSolar` already gives the map), the landing pin, the 80°S circle the map covers. As the record scrolls, the globe tilts toward the pole. | the mission's target, the sub-solar point, the hillshade tiles the front page loads | the small `PolarMap` |
| **The skyline dome** | Site and Skyline | The 1,440-ray skyline as a wall around the viewer standing at the site; the Sun's path and Earth's loop for the dates as arcs in the sky; the Sun and Earth as discs at the slider's time. Drag to look around; the slider moves the Sun. "The ridge to the south-west blocks the Sun" becomes something you can see. | the horizon mask, the Sun and Earth tracks the two rings use | `HorizonProfile`, which stays as the table twin's picture |
| **The path to the Moon** | Trip | Earth and Moon at true distance, the lander's path from the trip's own states (the section already offers them as an orbit file), the burns as marks, the Moon's shadow, the point where the Moon's pull wins. Scrolling the page moves the lander along the path and the day-by-day chart's cursor with it. | the trip ephemeris, the burns, the shadow and hearing intervals | the day-by-day chart |
| **The landing zones** | Return | A small Earth turned to the booster landing zone and the splashdown zone, with the sea state's colour band. Lowest priority. | the zones and the sea state the section already shows | the existing map tile |

*Where 3D is not used.* The Map page keeps its 2D pole on the real relief: a
3D pole is prettier and less legible, and the map is an instrument. Compare,
Plan, Ready, Launch and Contact gain nothing from depth. The front page keeps
its scene and gains grazing light with a softer terminator and a faint
earthshine on the night side.

*How it loads.* One lazy chunk for three.js (Vite `manualChunks`), shared by
the four scenes and the front page, fetched after the page's data has arrived
and the browser is idle, and only when the scene's container is near the
viewport. The dashboard's main bundle does not grow. A scene renders at a
pixel ratio of at most 2, pauses when off-screen or when the tab is hidden,
and is disposed on route change. Under reduced motion (OS or the in-app
toggle) a scene draws one still frame and redraws on resize only. Without
WebGL it is not created and the 2D drawing stays. Every canvas is
`aria-hidden`; the numbers stay in the words and the table twin, as on the
front page today.

*Budget.* About 160 kB gzipped for the chunk, once, cached across pages; 60
frames a second on a 2020 laptop and 30 on a mid-range phone with the Sun's
sweep playing, measured in slice 9; GPU memory under 64 MB per scene.

---

### Scroll

Scroll is the second clock on every page after the Sun's. The mechanism is
the same everywhere: one-shot reveals through `IntersectionObserver`;
scrubbed effects through CSS scroll-driven animations (`animation-timeline:
view()` and `scroll()`), which Chrome, Edge and Safari 26 run and other
browsers ignore in favour of the one-shot reveal; GSAP ScrollTrigger only
inside the three.js chunk, to scrub a scene, since the front page already
pays for it there. No page adds a `scroll` listener.

| Page | What the scroll does |
|---|---|
| Front page | As now (the Moon turns to the pole, the Sun circles, Earth rises, the terrain closes in), with the four ideas pinned while the Moon does the work and the feature cards cascading in. |
| Missions | The map card's pins drop in as it enters; the list's groups cascade; the timeline draws its bars when its row opens. |
| A mission's home | The journey line draws from the first node to where the mission got to, scrubbed by the scroll; the target globe tilts toward the pole and steps closer as the record scrolls; the cards cascade. |
| Step pages | The answer never leaves: when the answer sentence scrolls off, a compact strip (the question and the answer at title size) docks under the island, scaled down by the scroll, so a reader deep in the rows still sees what the page answers. Tiles rise, bars grow, the chart draws, rows cascade, the next-step card rises last. |
| Trip | The scroll moves the lander along its path in the scene and the chart's cursor with it; the burns light as it passes them. |
| Site, Skyline | The rings turn into place; the dome's arcs draw as it enters. |
| Compare | The cards cascade; changing the rank slides the columns, as now. |
| Plan | The hour-by-hour timeline draws left to right as it enters; the packet rows cascade; the big number settles. |
| Report | Nothing: it is a page for paper. |

Guardrails: transform and opacity only; `content-visibility: auto` on long
pages so off-screen sections cost nothing; every scrubbed effect has a
resting state that is complete without it; reduced motion turns all of it
into the static page.

---

### Every page

The three screens in the preview set the standard; every route, every sheet
and every state is held to the same list before its slice is done.

1. **A hero.** One element at display scale: a sentence, a number or a picture.
2. **Surfaces.** Cards are trays with lit cores; no bare hairline box
   anywhere; at most two surface levels visible at once.
3. **Type.** Four sizes a page apart; an eyebrow above every section; figures
   in the Figure role; mono for every stamp.
4. **Controls.** Pills; the primary action carries the arrow orb; hover
   lifts, press scales.
5. **Arrival.** Nothing appears statically: reveals staggered in reading
   order, charts drawing, bars growing.
6. **One playful moment.** A scene, a scrubbed draw, a turning ring, a
   sweeping Sun. One, not three.
7. **Space.** Sections breathe; nothing touches a container's edge.
8. **States.** Loading has the page's shape; empty has a drawing; error says
   what still works; all of them in the card system.
9. **Both themes, 375 px, reduced motion, axe.** Clean.
10. **Semantics untouched.** Hues, glyphs, hatches, words, table twins.

| Page | Hero | Playful moment | Depth |
|---|---|---|---|
| Front page | the headline over the Moon | the Moon turning as you scroll | the Moon |
| Missions | the pole on the real relief | pins dropping in; the Sun's sweep | — |
| A mission's home | the record | the journey drawing itself | the target globe |
| Ready | the answer sentence; the count of what is ready | the checklist filling | — |
| Launch | the answer sentence; the launch time | the launch calendar's opportunities lighting in order | — |
| Trip | the answer sentence | the lander moving with the scroll | the path |
| Surface | the answer sentence | the date bars drawing; the Sun's sweep | — |
| Contact | the answer sentence | the ground stations' passes drawing in sequence | — |
| Return | the answer sentence | the zones' sea-state band filling | the landing zones |
| Map | the pole | the Sun's sweep across the terminator | — |
| Site | the answer sentence and the rings | the rings turning into place | the skyline dome |
| Compare | the ranked figures | the columns sliding | — |
| Plan | the hours working alone | the timeline drawing | — |
| Skyline | the skyline chart | the Sun's path drawing | the skyline dome |
| Report | the page itself | — | — |
| Settings, Run log | the sheet's title | the sheet's slide; a toast with Undo | — |
| Guide | the step's title | the dashed outline finding its element | — |
| Not found, errors, loading | the message | the drawing | — |

---

### Decisions the owner has to make

| # | Decision | Recommendation |
|---|---|---|
| D1 | Radius on containers. Invariant 6 says 0 on data surfaces, 2 px on controls. | Keep 0 on everything that draws data (bars, arcs, hatches, tables, pins, rings, the map). Allow 16 / 12 px on cards, 20 px on sheets, 10 px on fields. Rewrite invariant 6 to say "data surfaces" means the data, not the card around it. |
| D2 | Pills on buttons, chips and segmented controls. Invariant 6 allows the pill only on a view switch. | Allow pills on all controls; the pill no longer means "view switch", the position in the header does. Primary buttons stay ink. |
| D3 | The floating island and dock in place of the full-width header, sub bar and bottom bar. | Yes. It removes two rows of chrome and gives the pages their first 100 px back. Fallback if the owner prefers a full-width bar: keep the bar, give it the glass treatment, keep the sub-pages as a segmented pill in the page header. |
| D4 | Fonts: Archivo variable with the width axis instead of four static files; Instrument Serif italic as an accent on the front page only. | Yes to the variable file (the bundle stays within a few kilobytes of today's four weights). The serif is optional; try it on the front page's four ideas and keep it only if it earns its place. |
| D5 | The front page's amber button. | Keep it as the one written exception: the page shows no data, and amber on the front page is the product's horizon. Everywhere else, primary is ink. |
| D6 | Three dimensions in the dashboard: the target globe, the skyline dome, the path to the Moon, the landing zones. | Yes, as the *Three dimensions* section sets out: one lazy chunk, loaded after the page and only near the viewport, a still frame under reduced motion, the 2D drawing without WebGL. Build in the order globe, dome, path, zones; the zones may be cut. |
| D8 | Scroll choreography: CSS scroll-driven animations with one-shot reveals as the fallback, GSAP ScrollTrigger only inside the three.js chunk. | Yes. It keeps the main bundle where it is and the pages free of scroll listeners. If the owner wants scrubbed effects in every browser today, GSAP ScrollTrigger (about 13 kB gzipped on top of GSAP's 30 kB) can be loaded with the dashboard instead; the choreography does not change. |
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
   reveals, grazing light and earthshine in the Moon scene.
7. **Scroll** (M). The staggered arrivals and the one-shot reveals on every
   page; the scrubbed journey line; the docked answer strip on step pages;
   the drawing charts (date bars, contact passes, the hour-by-hour timeline,
   the launch calendar); `content-visibility` on long pages. Decision D8.
8. **Three dimensions** (L). The shared three.js chunk and its loader (idle,
   near-viewport, WebGL check, reduced-motion still frame, dispose on route
   change); the target globe (S) from `moonScene`; the skyline dome (M); the
   path to the Moon with its scroll scrub (M); the landing zones (S, may be
   cut). Each scene ships with its 2D fallback in place and its frame times
   recorded. Decision D6.
9. **Polish and performance** (M). Hover and press physics, the labelled play
   button, the illustrated empty states, the light theme pass, the *Every
   page* list walked on every route, a performance pass (no blur on
   scrolling content, no layout-triggering animation, frame times on a
   phone with a scene running and the Sun's sweep playing), the final axe
   run in both themes, screens and offline copy re-recorded,
   `conventions.md` updated (D7) and this document's *Built* section
   written.

Sizes: S under a day, M one to two days, L three to five days, for one person
who knows the codebase. Slices 7 and 8 can run in parallel with 5 once 1–4
are in.

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
  it are the baseline to compare against; keep them until slice 9 replaces
  them.
- **WebGL on phones and in meetings.** A scene that stutters is worse than
  no scene. Each scene pauses off-screen, caps its pixel ratio, draws one
  frame under reduced motion and is cut from the phone layout if slice 8's
  measurements say so; the 2D drawing is always underneath it.
- **Scroll-driven CSS is not everywhere yet.** Firefox ignores it, so every
  scrubbed effect also has a one-shot reveal and a complete resting state;
  nothing a reader needs depends on the scrub.

---

## Progress

Built on branch `visual-refresh`, one commit per slice, decisions D1–D8
taken as recommended.

| Slice | State | Commit |
|---|---|---|
| 1. Tokens and parts | done | `3f29c87` |
| 2. Shell | done | `944b00a` |
| 3. The journey and a mission's home (and the Missions page) | done | `1a221f9` |
| 4. Step pages | done | `79762a2` |
| 5. Landing sites | done | `d35d87a` |
| 6. Front page | done | `5b70b44` |
| 7. Scroll | done | `cbe2035` |
| 8. Three dimensions | done | `e60a894` |
| 9. Polish and performance | done | the commit that added the *Built* section |

Between and after the slices, at the owner's request: the logo (`07c182a`,
`7ad721b`); the real Moon, Earth and night sky on the front page (`e503803`,
`4b18998`); the light theme's Earthrise (`8ac22a9`, `cb43791`); the page's
own lists in place of native selects (`7f91391`); one set of corners
(`fd21a69`); the map's relief on its own layer (`03fe817`).

*What the slices so far added, for whoever picks up the next one.*

- **Classes** (`frontend/src/styles/globals.css`): `pw-card` is the tray
  and lit core in one element, with `-quiet`, `-raised`, `-flush`,
  `-alert`, `-sunlit` and `-link`; its tray is drawn in box-shadow, so
  siblings need at least 12 px between them. `pw-on-raised` gives cards
  inside a sheet their own context. `pw-rows` and `pw-row` make a group of
  disclosures one list in one card. `pw-display`, `pw-figure` and
  `pw-eyebrow` are the type roles; `pw-press` and `pw-orb` the pill
  controls' press and arrow; `pw-island` the shell's glass. Key-number
  tiles also carry `pw-tile`, which the unit and e2e tests select on.
- **Parts** (`frontend/src/components/ui.tsx`): `Panel` takes `quiet`,
  `flush`, `alert`; `Button` takes `arrow`; `Eyebrow` is new; every
  `Segmented` is a pill with the chosen segment drawn inset in a full
  48 px target.
- **Shell** (`AppShell.tsx`): the island, the note pill, the landing-site
  pages as a pill, the phone dock (still the fixed "Views" navigation with
  two links), the guide as a card above the dock (`--pw-guide-h` includes
  its 16 px gap).
- **Journey** (`components/lifecycle/JourneyBar.tsx`): `missionProgress()`
  maps a published status to how far the mission has got and its words;
  `JourneyBar` (a step page) and `StepCards` (the home) draw the line from
  per-step segments, each marked `data-journey-segment` and `--pw-i` for
  slice 7's scrubbed draw.
- **Step pages** (`components/lifecycle/Section.tsx`, slice 4): the
  question is an eyebrow; `.pw-answer` (globals.css) is the answer's type
  role, 22 / 28 / 36 px, the biggest text on a step page;
  `UNDER_QUESTION`, `ANSWER_TEXT` and `AnswerAge` are shared with Surface,
  whose answer is drawn in `MissionDetailScreen`. `PageHeader` takes
  `compact`, used on a step so the mission's name steps back behind the
  answer. The chart card's title is at title size and its table toggle a
  ghost pill. The foot of a step (`StepFooter` in `MissionHub`) is the
  page's one primary pill, "Next step" with the arrow orb, with the next
  step's question beside it as its description. On a phone each step in
  the step bar keeps a 48 px target (`min-h-12`), which slice 3 had let
  fall to 44 px.
- **Landing sites** (slice 5): every landing-site page is one column in
  `pw-page`: a compact header (`PageHeader compact`, or `SiteTitle`, now
  the name at display size with the real select laid over it), then the
  date control card, then the page. `DateSlider` is that card: a Play
  pill, the track with a filled part and a haloed thumb, and a day
  counter ("Day 12 of 30", the same count as the Site page's clock) with
  the time under it; `compact` keeps the bare track inside Surface's chart
  card. Map: the pole is the hero card, the chosen site a card with its
  four numbers as small figures and the one primary pill. Site: the answer
  sentence (`surfaceSentence`, moved to `lib/siteSentence.ts` and shared
  with Surface) under its question, the clock in a card with the Sun ring's
  glow (`.pw-sun-glow`, `--color-glow-sun`), the rows as Details and About
  these numbers, and the three onward links as primary, secondary and
  ghost pills (`pillClass`, `PillArrow` in ui.tsx). Compare: the ranked
  measure is each card's hero figure, the other three small, an over-limit
  card has the magenta edge, and the sentence under the cards is a quiet
  card. Plan: a bento, the hours and every time without contact on the
  left, the working-alone card (the big number at 64 px, its five rows as
  a list) on the right. Skyline: the chart card is the hero, the blocker
  card beside it. Report: the screen frame is the page's, the paper is
  unchanged.
- **Front page** (slice 6): the dashboard's island as its header, with the
  way in always in reach; display type on the width axis for the headline
  and section titles; the four ideas, the feature cards and the method
  note as cards; the amber way in as a pill with the arrow (the one
  written exception, D5) and How it works as a secondary pill; sections
  96 px apart on a phone and 144 px from lg. Reveals rise 18 px on the
  settle curve over 820 ms and no longer fade, the feature cards 60 ms
  apart. The Moon has a softer line between day and night (a second,
  weaker Sun a little behind the first) and a faint cool earthshine on
  its night side. Instrument Serif (D4) was not added: the display voice
  carried the headline without it.
- **Logo** (`components/Brand.tsx`, after slice 6): the owner's two logos,
  cropped into `frontend/src/assets/brand/` as the mark, the words and the
  full logo, light lines for a dark ground and ink for a light one. The
  version follows the nearest `data-theme` (`.pw-logo-on-dark`,
  `.pw-logo-on-light`), so the report's paper takes the ink one. Headers
  set the mark and the words side by side (`BrandName`), since the full
  logo's words are unreadable at header size; the full logo (`BrandLogo`)
  closes the front page and stands on the loading screen. Tab icons and
  the touch icon are in `frontend/public/`; the README opens with the logo.
- **Scroll and arrival** (slice 7): `hooks/useArrivals.ts`, run once by
  `AppShell`, is one IntersectionObserver (and a MutationObserver for new
  content) over the page: every card not inside another card rises 18 px
  as it comes into view (`.pw-pre`, `.pw-rise`), 60 ms after the one
  before it; a key-number tile's bar (`.pw-bar-grow`), a strip of bars
  (`.pw-draw-bar`, the Ribbon) and a chart with words in it (`.pw-draw`)
  follow 120–160 ms after their card; the pole map's pins drop in
  (`.pw-pin`). The journey's line draws itself as a mission's page opens
  (`.pw-journey-draw`, a segment every 150 ms), timed rather than scrubbed,
  since it sits in the first screen and a scrub would already be complete.
  On a step page the answer docks under the island once it has scrolled
  away (`AnswerDock` in Section.tsx, a copy hidden from assistive
  technology), and the page's scroll padding grows by its height. Not used:
  `content-visibility`, whose paint containment clipped the cards' trays,
  and a cascade inside the Missions list, which is one card. The Trip's
  scroll scrub belongs to its scene (slice 8). The e2e helper `arrived()`
  waits for the arrivals before a test measures a position.

- **The front page's picture** (after slice 7; `frontend/src/landing/`).
  The Moon is real: NASA's LRO wide-angle camera mosaic on the globe
  (`space.ts`, `moonSurface`), with the LOLA relief inside 80°S tinted to
  the photograph's tone. Dark theme: ESO's Milky Way panorama (S. Brunier,
  CC BY 4.0, credited in the footer) on a sphere behind the Moon, drawn
  through its own 72° lens first and the Moon over it. Light theme, with
  motion: the page opens on the ground at Connecting Ridge with Earth
  (NASA's Blue Marble under NASA's cloud layer) over the horizon and the
  same sky behind it, and the first scroll flies out to the whole Moon, the
  sky clearing to the page. The ground is the LOLA heights around the site
  as `backend/app/data/render_earthrise.py` samples them (a fan in front of
  the viewer, the Moon's curvature in it, the terrain's own shadows), with
  craters, rocks and grain smaller than the 80 m heights generated in
  `earthrise.ts` and lit by the same Sun. That Sun is ten degrees up, placed
  for the picture and higher than it ever stands there; the script's notes
  say so, and the footer says the Sun is placed to light the pictures.
  `SceneState.ground` (1 on the ground, 0 at the whole Moon) and `.space`
  (1 black sky, 0 the page) are what the scroll
  drives; the page's styles follow `--pw-space` and `--pw-hero`. The stars
  are fixed to Earth, so the two cross the screen together. Under reduced
  motion, or without WebGL, the light page opens on the Moon as before.
- **Lists to choose from** (`components/Select.tsx`). No native `<select>`
  is left: the operating system draws those, outside the theme. `Select` is
  a button (`role="combobox"`, named by a `<label for>`) and the page's own
  list, put in the browser's top layer (`popover`) so a sheet or a scrolling
  panel never cuts it, placed under the button or over it when the room
  below is short. Keys as the native one: arrows, Home, End, Page Up and
  Down, typing a name, Enter, Space, Tab, Esc (which closes the list and
  leaves a sheet open). Looks: `field` (the forms), `pill` (beside the
  pills), `bare` (the site's name as the page title). The forms' `Select`
  in `lifecycle/Forms.tsx` is this part; its `onChange` gives the value.
- **Corners** (`globals.css`, the radius tokens). 12 px on fields and small
  controls, 16 px on a card's core (the tray's own curve is 21 px and runs
  parallel), 24 px on sheets and floating boxes of more than one line,
  pills elsewhere; a box inside another takes the outer radius less the
  space between. The chosen segment of a pill group is a clear 4 px border
  with the fill kept inside it (`bg-clip-padding`): an inset shadow over a
  light fill left a light fringe round the curve. A row in a list is square
  (`rounded-none` on a row that is a `<button>`, since every button takes
  the control radius by default).
- **The real Moon in the dashboard** (slice 8). Missions: the whole-Moon
  view is the LRO mosaic as two orthographic discs
  (`backend/app/data/render_moon_discs.py`, the projection the pins use),
  under a faint graticule and the pins. Map: the relief is drawn a little
  crisper, as its own picture under the map's drawing (`.pw-relief`), so the
  Sun's sweep does not repaint the tiles.
- **Scenes** (slice 8; `frontend/src/scenes/`). `SceneFrame` holds a scene
  over the page's flat drawing: it is made only with WebGL, when the
  browser is idle and the frame is within a screen of the viewport; it
  draws on demand, never in a loop; under reduced motion it draws its
  resting frame; `onFail` lets a card with no flat drawing of its own take
  itself away. three.js is one chunk (`vite.config.ts`, `manualChunks`),
  shared with the front page. `targetGlobe.ts` (a mission's home): the Moon
  turned to the landing spot, with the pin and the 80°S circle.
  `skylineDome.ts` with `DomeCard` (Site, Skyline): the site's skyline as a
  wall round the viewer, the Sun's path and Earth's loop behind it, heights
  drawn six times taller (`DOME_EXAGGERATION`, said in the caption from
  `words.ts`), drag to look. `tripPath.ts` with `PathCard` (Trip): the
  flown path from the step's own orbit file, at true distance, amber in
  sunlight and grey in shadow, the burns as dots, nothing drawn across a
  gap, the lander moved along it by the scroll.

*How each slice was checked.* `npm run check` and `npm test`; then the
offline build (`npm run build:snapshot && npx vite preview`) driven by
Playwright over 19 routes at 1440 and 375 px in both themes, with the same
axe rules as `e2e/helpers.ts`, horizontal overflow and console errors, and
the phone-dock geometry from `e2e/screens.spec.ts`. Every slice so far
holds the baseline: no axe findings, no overflow, no console errors. For
slices 1–3 the e2e suite was not run (it needs the live API on :8000); its
four tile selectors were updated to `div.pw-tile`. From slice 4 it runs
against a local API and compute worker, with the feeds fetched once
(`make feeds-once`) so the weather and space-weather tests have live
data: all 60 pass after slice 5. Without fresh feeds, three of them
(launch weather, return's sea state, space weather now) fail on the
data's age, not on anything drawn.

---

## Built

All nine slices are on branch `visual-refresh`. The look this document set
out is what the dashboard and the front page now have, and the product's
rules held throughout: amber means sunlight, cyan means Earth, magenta means
over the battery limit; no score and no verdict; every status a glyph and
words; square corners on everything that draws data. *Progress*, above, is
the part-by-part record. This section says where the build differs from the
plan, what was measured, and what was left out.

**Where it differs from the plan.**

- *Corners* (D1). The plan proposed a 12 px core in a 16 px tray. Built:
  16 px core, the tray's curve 21 px, fields 12 px, sheets 24 px. With pill
  controls inside them, cards at 12 px read as boxes of another family.
- *Selects.* Not in the plan. Every native select was replaced by the page's
  own list (`components/Select.tsx`), because the native one is drawn by
  the operating system and ignores the theme.
- *The front page.* The plan kept the scene and softened its light. Built
  instead: the real Moon (LRO), the Milky Way (ESO) behind it in the dark
  theme, and in the light theme an Earthrise over the real terrain at
  Connecting Ridge that flies out to the whole Moon. The Earthrise's Sun is
  ten degrees up, which it never is there; that is a choice for the
  picture, written in `render_earthrise.py`, and the footer says the Sun
  is placed to light the pictures, not where it stands on any date.
- *The target globe.* It is lit for the picture, not by the Sun of the
  chosen dates, and it does not tilt with the scroll; its caption says the
  Surface step has the Sun for the dates.
- *The path to the Moon.* It draws the flown path, sunlight and shadow, the
  burns and the gaps. It does not mark the Moon's shadow or the point where
  the Moon's pull wins, and the day-by-day chart's cursor does not follow
  the scroll. It needs the live service: the offline copy does not hold the
  orbit file, so there the card is absent and the strip above it stands.
- *The landing zones* (Return). Not built; the plan allowed the cut.
- *Scroll* (D8). Arrivals are one-shot reveals from one
  IntersectionObserver. CSS scroll-driven animations were not used: the
  journey's line and the charts draw on a timer as they arrive, which reads
  the same and runs in every browser. The path card listens to the scroll
  (one passive listener, one measurement a frame, only while the card is
  on the page), which the plan had ruled out for pages; the front page
  uses GSAP ScrollTrigger, as before. `content-visibility` was tried and
  removed, since its paint containment cut the cards' trays.
- *Fonts* (D4). Archivo on its width axis carries the display voice;
  Instrument Serif was not added.

**Measured.**

- *Size.* The dashboard's main bundle is 186 kB gzipped. three.js is its
  own chunk, 132 kB gzipped (the budget was 160 kB), fetched only by a page
  with a scene, when idle and near the viewport. The front page's own code
  is 51 kB gzipped; its pictures are 0.6 MB (Moon), 1.8 MB (Milky Way, dark
  theme only), 0.5 MB (Earth and clouds) and 0.25 MB (the terrain, light
  theme only).
- *Frame times.* Headless Chromium at 390 × 844, two device pixels to one,
  the processor slowed four times, five seconds each. With no WebGL: 16.7 ms
  a frame, median and 95th percentile, on Missions, a mission's home and
  Surface while scrolling, and on Site and Map with the dates playing. With
  the scenes drawn in software (SwiftShader, far slower than a phone's
  graphics chip): the same medians; the 95th percentile on Site, scrolling
  with the dates playing, is 33 ms. The Map with the dates playing was 33 ms
  at the median before its relief was given its own layer, and is 16.7 ms
  after. None of this was measured on a real phone; that remains to do.
- *Accessibility.* The e2e suite's axe rules (WCAG 2.1 A and AA, serious
  and critical), sideways overflow and console errors over 19 routes at
  1440 and 375 px in both themes: 76 of 76 clean. The same rules with each
  list open, both themes: no findings. That sweep ran before the last three
  changes (the map's relief on its own layer, the solid heading on the
  Missions list, one sentence in the front page's footer); the e2e suite,
  which checks the same rules on the pages it visits, ran after the first
  two.
- *Tests.* 290 unit tests pass. The e2e suite, against a local API and
  compute worker with the feeds fetched once: 60 of 60 pass.

**Not done.**

- Frame times on a real phone (above).
- The landing-zones scene.
- A higher-zoom relief on dense screens: the map draws 1,024 source pixels
  across a picture that can be 1,400 device pixels wide. The pyramid has
  the next zoom; it is about 4 MB of tiles, so it was left out.
- Thirteen of the 58 recorded screens in `frontend/e2e/__screens__/` still
  show the old look: the phone pictures of Contact (six), Return (four),
  the launch weather forecasts and the two of Settings. The other 45,
  every desktop picture among them, were retaken with `npm run screens`.
  Retake the rest with the same command once the service's answers are
  warm (a step still being worked out makes the script wait and give up).
- The offline copy (`frontend/public/snapshot/`) was not recorded again.
  Its answers are the service's and did not change with the look; it does
  not hold the Trip's orbit file, so the path card is absent offline.
