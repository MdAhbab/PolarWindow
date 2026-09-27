# Design: the mission lifecycle screens

**Status:** built to this plan on branch `featured` · **Date:** 2026-09-27
**Builds on:** `docs/lifecycle-api.md` (the contract), `docs/conventions.md`
(invariants 1–12, Words), `docs/design-handoff.md` (tokens, states),
ADR-2, 7, 9, 14, 16, 17.

The product gains six sections per mission: **Ready · Launch · Trip · Landing ·
Contact · Return**. The users are a project manager and mission scientists;
judges must read every screen without training. Three rules decide every
choice below:

1. **Learn one section, know all six.** Every section has the same shape.
2. **Answer first.** The first thing on a section is one sentence that answers
   its question. Nothing above it but the question.
3. **Less on screen.** A number or control that does not answer the section's
   question goes into a closed row, or is dropped.

Nothing here redesigns an existing screen. The five tabs stay (e2e asserts
five). The Landing section is the existing mission page, unchanged apart from
its header moving up into the hub.

---

## 1. The mission hub

`/missions/:id` is the hub. It shows the mission's header, the six steps, and
one section at a time.

```
← All CLPS missions
IM-2 · Athena                                        h1 (unchanged style)
Intuitive Machines · Nova-C · NASA task order …      one line
┌──────────┬──────────┬──────────┬──────────┬──────────┬──────────┐
│1 READY   │2 LAUNCH  │3 TRIP    │4 LANDING │5 CONTACT │6 RETURN  │  nav "Mission sections"
│○ No data │● Avail.  │◔ Working │● Avail.  │● Avail.  │– Does not│  glyph + words
│yet       │14 oppor- │it out    │Sun 574 h,│Stations  │apply     │  summary (2 lines max)
└──────────┴──────────┴──────────┴──────────┴──────────┴──────────┘
[the section]
```

| Route | Shows |
|---|---|
| `/missions/:id` | the hub with **Landing** open (the existing page; every current link and test keeps working) |
| `/missions/:id/landing` | the same |
| `/missions/:id/ready` · `launch` · `trip` · `contact` · `return` | the hub with that section open |
| `/missions/:id/anything-else` | redirects to `/missions/:id` |

**The step bar** (`JourneyBar`, `components/lifecycle/JourneyBar.tsx`)

- A `<nav aria-label="Mission sections">` of six real links, in the order a
  mission lives them. The open one has `aria-current="page"`, a 3 px ink bar on
  top, the panel background and ink text. Ink, not amber: amber means sunlight.
- Each step shows its number and name, its state as **glyph and words**, and
  `SectionStatus.summary` from `GET /missions/{id}/sections`. Nothing else.
- States, never colour alone:

  | `state` | Glyph | Words |
  |---|---|---|
  | `available` | ● filled dot | Available |
  | `computing` | ◔ quarter dot | Working it out |
  | `needs_input` | ✎ pencil | Needs input |
  | `not_applicable` | – dash | Does not apply |
  | `no_data` | ○ ring | No data yet |

- Each link's accessible name is the whole cell: "Ready: No data yet. No
  readiness items entered yet."
- Loading: names only, with a static "…" (no shimmer: motion is for data). If
  `/sections` fails, the bar still navigates and one caption line under it says
  the summaries are not available and why.
- Widths: six columns from 1024 px; three by two below it. Below 768 px the
  summary is kept for screen readers only (the section repeats it as its
  answer), so each cell is name + state and stays 48 px tall.
- Moving between sections keeps focus on the link that was pressed (a
  tab-like move inside one page), and the document title becomes
  "IM-2, Trip · POLAR WINDOW". Leaving the mission moves focus to `main` as
  today.

---

## 2. One template for every section

`SectionLayout` (`components/lifecycle/Section.tsx`) is the only way a section
is drawn. Top to bottom:

1. **The question**, as the section's `h2`, and under it **one plain sentence
   that answers it**, built from the data (counts and quantities, never a
   verdict). Under that, one caption: how old the answer is ("Worked out
   2 hours ago"), with "some inputs are out of date" and the uncertain glyph
   when `meta.stale`.
2. **A fixed row of at most four key numbers** (`QuantityTile`, §3). Same row,
   same place, every section.
3. **One primary chart** in a `ChartPanel`: title, the chart, a one-line key,
   and "Read the chart as a table" (also the T key, as on Site). The table
   twin renders from the same array as the chart.
4. **Everything else in closed rows** (`Disclosure`), in this order: the
   section's own rows, then "How sure is this?" (the composite uncertainty
   parts), then "Where does this come from?" (sources with issue time, fetch
   time, licence; engine versions; when it was worked out).

No verdicts, no scores, no percent ready: counts, quantities and per-rule
evidence only (invariant 9).

**States.** Every section has all of these, drawn by `SectionLayout` so each
looks the same everywhere. Each non-answer state has a "What still works" box.

| State | Trigger | Shows |
|---|---|---|
| Loading | query pending | the question; tiles in their computing state ("——"); no chart |
| Working it out | 202 `JobRef` | the question; a progress bar from `progress` (or "queued") and `message`; "This page updates itself when the answer is ready. The other sections are unaffected." Polls `GET /jobs/{id}` every `poll_after_s` |
| Needs input | status `needs_input`, or no entries | the question; what is missing in one sentence; the entry button if signed in with a name |
| Does not apply | status `not_applicable`, or `applicable: false` | the question; why, in the server's words |
| Stale | `meta.stale` | the answer as usual, plus an uncertain note under the sentence; a number past its budget arrives as `missing_reason` and is shown as such |
| No data | `source: "none"`, 404, or status `no_data` | the question; the server's reason; what still works |
| Error | any other failure | `ProblemPanel` with the server's title, detail and what still works |

---

## 3. One number shape on screen: `QuantityTile`

`KeyNumberTile` gains a preformatted figure and margin, a range bar, an age
line and a provenance line, and `QuantityTile` feeds it a `Quantity`
(`lib/lifecycle/quantity.ts` converts; one place, tested).

| `Quantity` | Figure | Beside it | Bar under it |
|---|---|---|---|
| `pm` | `12` | `±2` in the uncertain ink, then the unit (`4.1° ±0.3°` for a unit written against the number); a margin from 1 to 3 keeps one decimal | solid to the value |
| `lo`/`hi` | `3–7` | unit; the caller's footnote says "if it flies as planned" | solid to `lo`, −45° hatch from `lo` to `hi` |
| `factor` | `4.1 × 10⁹` | `×/÷2` | solid |
| `open` | `≥288` | as above | solid |
| `no_margin_reason` | `12` | nothing | solid; footnote "No margin: {reason}" |
| `value: null` | `—` in the line ink | unit | empty; footnote is the `missing_reason` |
| time (`s since epoch`) | `01:32`, with "27 Feb 2025 · UTC" above; known only to days, `8 Oct` with the year above | `±4 min`, `±3 days` | none |

- The label is a button, as today: it opens what the number means, its
  professional name, and **where it comes from** (invariant 10):
  "Worked out by POLAR WINDOW", "Published: {source link}", "Entered by
  {name}", "Assumed: {source}".
- A live number (weather, sea, space weather) shows its age on the tile
  itself ("as of 40 min ago", invariant 11).
- Spoken form: "about 12 hours, plus or minus 2 hours"; "3 to 7 hours, if it
  flies as planned"; "not available: {reason}".
- A probability is never a tile. It is a `Share` line: "12 of 31 model runs
  (95 % range 23 to 56 %), not yet checked against observations"
  (invariant 12), drawn in the weather table.

---

## 4. The six sections

Each: its question, the answer sentence, its four numbers, its chart, and its
rows. Copy in quotes is the on-screen text; `{}` is data.

### Ready (`/ready`, `GET /missions/{id}/ready`)

- **Question:** "What is ready, and what is holding it up?"
- **Answer:** "{ready} of {total} items are ready; {blocked} blocked: {names}."
  With nothing entered: "No readiness items have been entered yet."
- **Numbers:** Items ready ({k} of {n}) · Blocked ({count}; footnote names the
  first) · Next milestone ({date ± days}, footnote its name) · Spare parts
  ({spares}; footnote "{lost} lost, {damaged} damaged, {failed} failed").
- **Chart: the readiness list.** One row per item, blocked first, then the
  least advanced. Each row: glyph and state words, name, kind and
  organisation, since when and by whom, evidence link, and a ladder of eight
  steps (not started … ready) filled up to its state. The ladder is a position
  in a fixed sequence, not a score, and carries no number. Blocked rows add
  the triangle glyph, the word "Blocked" and the reason, in ink: magenta
  stays reserved for "over a limit". Twin: the same
  rows as a table (item, kind, organisation, state, since, by, evidence,
  tests). A signed-in manager gets "Change" on each row.
- **Rows:** Risks ({n}, {rising} rising) · Parts ({total}; {spares} spares) ·
  Milestones · Landing history and lessons ({adopted} of {available} lessons
  adopted) · Add an item · How sure is this? · Where does this come from?

### Launch (`/launch`, `GET /missions/{id}/launch`, `/launch/weather`)

- **Question:** "When and from where can it launch?"
- **Answer:** "{n} launch opportunities from {pads} between {from} and {to}.
  The next is {date, time} from {pad}." Adds the published launch time when
  there is one.
- **Numbers** (for the chosen opportunity; the first by default): Launch time
  ({t0} ± min) · Flight time ({days} ±) · Sun height at landing ({deg} ±) ·
  Sunlight after landing ({h} ±).
- **Chart: the launch calendar.** One row per day that has an opportunity; a
  24-hour track with each opportunity as a button at its time ("01:32 · 39A"),
  its ± drawn as the −45° hatch, a launch period as a thin bar from open to
  close. Runs of days with none collapse into one line: "No opportunity for 9
  days". Choosing one updates the four numbers and the weather row. Twin:
  day, time ±, pad, kind, flight days, landing time, Sun height, sunlight
  after, Earth up at landing, weather available.
- **Rows:** Weather rules for this opportunity (meta: "{n} rules; models
  disagree on {k}") · Official launch forecast · Team weather limits · Other
  launches from this range that day · Space weather now · Change the dates ·
  How sure is this? · Where does this come from? The landing rule the
  calendar is worked back from is one line under the calendar, not a row.
- **Official forecast** is quoted as issued: "{n}% chance the weather breaks
  a launch rule", the 45th Weather Squadron's "probability of violating
  weather constraints", with who entered it and the PDF.
- **Weather rules** (`WeatherRuleTable`): rule rows × systems (GEFS, ECMWF
  ENS, AIFS ENS), each cell "{k} of {n} runs" with a small bar and its
  interval as a hatch; missing cells give their reason. A rule's class is in
  words: "a model can answer this", "the model sees the ingredients",
  "observation only: no forecast number". "Models disagree" with the
  uncertain glyph when the intervals do not overlap. One forecast: "over" or
  "under", never a probability. Each rule links its source. Nothing adds them
  up.

### Trip (`/trip`, `GET /missions/{id}/trip`)

- **Question:** "What does the lander go through on the way?"
- **Answer:** "The trip takes {days} days ({as flown | as designed}). The
  longest time in shadow is {h}, and the longest time without contact is {h}."
  A zero reads "It is never in shadow" / "a ground station can hear it the
  whole time"; a stretch the dates cut short reads "at least {h}". When NASA's
  reconstruction has gaps (IM-1), the second sentence starts "In the {h} hours
  NASA's reconstruction covers, …" and `coverage_note` sits under the answer,
  since the numbers then describe only the parts with data.
- **Numbers:** Time in sunlight · Time a ground station can hear it · Longest
  time in shadow · Longest time without contact.
- **Chart: the trip strip** (schematic, no 3D). Top: distance to Earth and to
  the Moon over time, two lines labelled at their ends, burns as labelled
  ticks, and a dotted line where the Moon's pull wins. Below it two lanes on
  the same time axis: sunlight (amber lit, −45° hatch partly shadowed, +45°
  hatch in shadow) and "a ground station can hear it" (cyan heard, +45° hatch
  not heard). Twin: every shadow and not-heard stretch (start, end, length)
  and every burn. Gaps in the data (a sample step many times the usual one)
  break both lines and leave both lanes empty with a dashed outline, keyed
  "No data" and listed in the twin; a gap is never counted as out of contact.
- **Rows:** Radiation on the way (screening only, and where to confirm) ·
  Burns ({n}, or "none listed" with `burns_note`) · Where the Moon's pull wins
  (only when `moon_pull` is given) · Download the trip (flown trips only: CCSDS
  OEM and CSV, one block per stretch NASA's reconstruction covers, said in the
  row when there is more than one; SPK is not served) · How sure is this? · Where does this
  come from?
- **No data:** `source: "none"` shows `none_reason`.

### Landing (`/landing`, and the hub's default)

The existing mission page: status and dates, "Sun & Earth at this target"
with the four numbers, ribbons, "Change the dates", Listen, the AI row, and
the target, payload and source rows. Only the back link and `h1` moved up
into the hub header.

### Contact (`/contact`, `GET /missions/{id}/contact`)

- **Question:** "How often can the lander talk to Earth?"
- **Answer:** "A ground station can hear it for {h} hours over these dates.
  Through a relay it could add {lo} to {hi} hours, if it flies as planned. The
  longest time without contact is {h} hours." With no gap at all: "A ground
  station can hear it for all {h} of these dates." `window_note` shows only
  when the server used other dates than the ones asked for. A wait under a
  minute reads in seconds, one of two hours or more in hours.
- **Numbers:** Time a ground station can hear the lander · Through a relay
  ({lo}–{hi} h, "if it flies as planned") · Longest time without contact ·
  Longest message wait. (Time in contact with Earth, the geometric number,
  stays on Landing; "either way" and "dark and out of contact at once" are in
  a row.)
- **Chart: the contact chart.** One row per link (lander to each station,
  lander to each relay, relay to station), bars where the link is up. A
  planned relay has no real timeline, so its row is the −45° hatch across the
  dates with "{lo}–{hi} h somewhere in these dates, if it flies as planned".
  Booked passes are outlined boxes labelled "booked". The antennas of one Deep
  Space Network complex share a row ("Goldstone, California · Deep Space
  Network, 4 antennas"); the twin keeps each antenna. Twin: link, start, end,
  length, booked or not.
- **Rows:** Relays (each with its launch status) · Booked ground-station
  passes · Rover and lander line of sight · More numbers · Download the
  contact plan (ION, CSV) · Change the dates (the same dates as Landing) ·
  How sure is this? · Where does this come from? "Line of sight only: the
  lander's radio power is not published" changes what every number means,
  so it is a one-line note under the answer, not a row.
- **Dates:** the hub sets the dates to the mission's time on the surface
  when the mission is first opened, whichever step comes first, so Contact
  and Landing always answer for the same dates.

### Return (`/return`, `GET /missions/{id}/return`)

- **Question:** "Where do the booster and any capsule come down, and what is
  the sea like there?"
- **Answer:** "The booster lands on a droneship {lat, lon ± km}. Waves there
  are {v ± m} against the team's limit of {limit}." Adds "No capsule returns
  on this mission." when not applicable.
- **Numbers:** Waves at the booster landing zone · Wind at the booster
  landing zone · Waves at the splashdown zone · Wind at the splashdown zone
  (the last two only with a capsule; without one the row has two tiles).
- **Chart: against the team's limits.** One row per measure: the value as a
  bar with its ± hatched, the team's limit as an ink rule. Over the limit is
  magenta, a triangle and the words "{x} over the team's limit" (invariant 4).
  No limit entered: the bar alone and "No limit entered by the team". Twin:
  measure, value, ±, limit, who entered it, over or not.
- **Rows:** Booster landing zone · Splashdown zone · Team limits · How sure
  is this? · Where does this come from?

---

## 5. Entering records (the project manager)

Every write is one small form in a `Sheet`, opened by a secondary button next
to what it changes. Forms share `Field` (visible label, hint, error),
48 px controls, and one primary button ("Save"). The server's refusal is shown
as it comes (a 409 on an illegal readiness move lists the allowed next
states).

- **A name on every change.** Reading needs no name. The first time a form is
  opened by the demo session, the form starts with "Your name" and
  "Team (optional)": "Every change is recorded with your name." Saving signs in
  again with that name (`POST /auth/demo {name, team}`) and then saves.
- **Forms:** change a readiness item (state, date, evidence link, note,
  reason when blocked; its history below the form) · add a readiness item ·
  add or change a part · add or change a risk (likelihood and consequence per
  category on the scale in use; never combined) · official launch forecast
  (probability, concerns, the PDF link) · team weather and sea limits · a
  booked ground-station pass.
- **History:** each form's sheet ends with "Change history": who, when, from
  what to what, and the note, newest first.

## 6. Settings → Project

Four additions, each a group or a closed row:

- **People:** who is signed in (name, team), "Sign in with your name".
- **Data sources:** one row per feed (`GET /feeds`): provider and product,
  state as glyph and words (● Working, ◔ Out of date, ▲ Failing), last good
  fetch as an age, next run, licence, the last error; "Refresh now" for a
  signed-in manager.
- **Risk scale:** the likelihood and consequence levels in use, with their
  source and notes (read-only). When the levels have no words beyond their
  numbers (the scale as shipped: GSFC-HDBK-8005A leaves the words to a
  non-public procedure), one sentence says so instead of a table of repeats.
- **Parameters:** "n of 4 entered"; each value, or "Not entered yet" and why;
  who set it and when. A signed-in manager opens "Change" (or "Enter a value")
  in place under it: the value in its unit, a note, Save (`PUT /parameters/{id}`),
  and its change history (`GET /history?entity=parameter`), newest first
  ("120 h → 96 h"). An out-of-range value is refused in the server's words.
  The row is left out when the server has no `/parameters` (see §9).

## 7. Guide

One step is added, not two: **"Follow a mission from start to finish"**,
on `/missions/im-2/trip`, pointing at the step bar. Body: "Each mission has
six steps, from getting ready to coming home. Every step answers one
question the same way: a sentence first, up to four numbers, one chart, and
the rest in rows you open." It comes first among the mission steps, so the
guide stays ten steps and the mission steps stay last.

## 8. Visual system

- Only existing tokens are used: sun (amber) = sunlight, earth (cyan) =
  contact with Earth, alert (magenta) = over a limit, ink for everything else.
  Shadow is the existing `hatch-blocked` (+45°); partly shadowed and every
  range or margin is `hatch-uncertain` (−45°), so "if it flies as planned" is
  a hatched range.
- No new colour token is needed. A chosen item (a launch opportunity) is
  ink on canvas, as a pressed segment already is.
- Radius 0 on data surfaces, 2 px on controls; no animation is added, so each
  new chart is its own reduced-motion version (stated in code comments).
- Model disagreement: the uncertain glyph and the words "Models disagree".
  "Not yet checked": caption text on every share line.

## 9. Words

All labels follow the Words table. New words this design uses, proposed for
`docs/conventions.md` (owned by the backend):

| Say | Not |
|---|---|
| launch time (on request: "Also called T-0") | T-0, liftoff epoch |
| flight time | transfer duration, TOF |
| Sun height (at landing) | Sun elevation, solar elevation angle |
| model runs, "12 of 31 model runs" | ensemble members |
| one forecast | deterministic run |
| checked against observations, not yet checked | verified, calibrated |
| models disagree | ensemble spread conflict |
| team limit | vehicle constraint, LCC value |
| booked pass | DSN allocation, track |
| where the Moon's pull wins | sphere of influence (on request) |
| in the radiation belts | Van Allen transit |
| screening only | preliminary analysis |
| change history | audit log, audit trail |
| evidence link | artefact, proof |
| working it out, needs input, does not apply, no data yet | pending, TBD, N/A |

## 10. Contract requests

Filed under *Changes* in `docs/lifecycle-api.md`: the `Part` shape and parts
list; the risk-scale shape; team limits body; a generic change history for
parts and risks; `GET|PUT /parameters`.
