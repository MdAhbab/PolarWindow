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

When `/healthz` says `degraded` and its `feeds` count any out of date or
failing, one quiet line under the steps names them by provider (`GET /feeds`):
"Some live data is older than usual: {providers}." and, for a provider whose
data is still recent but whose last tries failed, "{provider} is not answering
right now; its data is still recent.", then "Each number from them says how old
it is, or why it is missing." and "See the data sources" (opens Settings). The
uncertain glyph, never the alert colour: nothing is wrong with the numbers
shown, each already carries its age.

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
  there is one. A flown mission (its one opportunity `{pad}-flown`, `basis`
  not `designed`) reads "It launched on {t0 ±} from {pad}, as worked out again
  from NASA's reconstruction of the flight. The published liftoff is {t ±}."
  (or "as published" when that is all there is). With `none_reason`, a
  refused-state panel says it and nothing else is drawn.
- **Numbers** (for the chosen opportunity; the first by default): Launch time
  ({t0} ± min) · Flight time ({days} ±) · Sun height at landing ({deg} ±) ·
  Sunlight after landing ({h} ±).
- **Chart: the launch calendar.** One row per day that has an opportunity; a
  24-hour track with each opportunity as a button at its time ("01:32 · 39A"),
  its ± drawn as the −45° hatch, a launch period (`kind: window`, with
  `window_open` and `window_close`) as a thin bar from open to close along the
  foot of the track, named in the legend and in the mark's name ("…, a launch
  period from 07:18 to 08:03 UTC"). Runs of days with none collapse into one
  line: "No opportunity for 9 days". Choosing one updates the four numbers and
  the weather row. Twin:
  day, time ±, pad, kind ("Launch period, 07:18 to 08:03 UTC" or "One
  instant"), flight days, landing time, Sun height, sunlight
  after, Earth up at landing, weather available. A flown launch shows the
  period Launch Library 2 published (Peregrine 07:18 to 08:03 UTC, Blue Ghost 1
  06:06 to 06:45 UTC; IM-1 and IM-2 one instant); a designed one shows the
  ends the service worked out from the pad's two limits on the climb, and
  says so. Dates are added when a period runs past midnight.
  The opportunity's `note` (how it was worked out, and anything unusual such
  as a coast longer than any flown one) sits under the four numbers.
- **Rows:** The flight for this opportunity (meta: how it was worked out;
  launch time, launch period (or "One instant", "(published)" for a flown
  launch), direction of the climb (with where it comes from: worked out
  from NASA's reconstruction for a flown launch, assumed for a designed one
  as the vehicle's flown lunar climbs averaged, which sets the ± on its
  time), coasting in Earth orbit, speed added
  to leave Earth for the Moon, flight time, time in orbit around the Moon
  with what is assumed, the landing and the stretch the landing rule allows)
  · Weather rules for this opportunity (meta: "{n} rules; models disagree on
  {k}; {c} checked against observations", each part only when it is more than
  none; "; no forecast for this date" when `weather` is `none`) · Official
  launch forecast · Team weather limits · Other launches from this range that
  day (with `range_note`) · Space weather now · Change the dates (up to 180
  days; not shown for a flown mission) · How sure is this? · Where does this
  come from? The landing rule the calendar is worked back from is one line
  under the calendar, not a row. The weather is asked for every opportunity,
  a flown one too: the rules and the team's limits stand where no forecast
  reaches, and each empty cell says why.
- **Team weather limits** lists each rule's limit with who entered it and
  the team's note (`limit_note`). The form offers only the rules whose limit
  is not published, one group per rule (Limit, Unit, Note): it starts from
  the limits as entered, read back with their notes (`GET
  /vehicles/{id}/limits`); the unit is a choice from `RuleRow.units` (the
  published one first), or typed when the rule takes any unit. An emptied
  field removes that limit. The service replaces the vehicle's list on each
  save, so every limit entered for a rule not in the form (another range's)
  is sent again as it stands, note and all; the form does not save until
  that list is read.
- **Official forecast** is quoted as issued: "{n}% chance the weather breaks
  a launch rule", the 45th Weather Squadron's "probability of violating
  weather constraints", with who entered it and the PDF. One per mission,
  the latest; a save answers with the forecast as stored, which the row shows
  at once (the later-entered of it and the weather answer's `official`).
  "Take back this forecast" (a sheet naming which, then `DELETE`) shows the
  one entered before it again, or "not entered", with "Taken back. …" in the
  row; the history says "Entered {n}% (…); before it: …" and "Took back {n}%
  (…); shown now: …".
- **Weather rules** row opens with the opportunity's `weather_note` (what
  the rules can show, and why there are no forecast numbers when there are
  none).
- **Weather rules** (`WeatherRuleTable`): rule rows × systems (GEFS, ECMWF
  ENS, AIFS ENS), each cell "{k} of {n} runs" with a small bar and its
  interval as a hatch; missing cells give their reason. A rule's class is in
  words: "a model can answer this", "the model sees the ingredients",
  "observation only: no forecast number". Whether the shares shown have been
  checked against observations is said in that line, once for the rule ("checked
  against observations", "not yet checked against observations", or by system
  when they differ; nothing for a rule with no share), and again for screen
  readers on each share (`share.checked`, invariant 12). "Models disagree" with
  the uncertain glyph, and under it the service's sentence
  (`disagreement_note`: who puts the wind where, against which limit or which
  runs), when a single forecast is on the other side of the limit from the
  runs or two single forecasts are on opposite sides. One forecast: each named
  in full ("National Weather Service (NWS) forecast:", "High-Resolution Rapid
  Refresh (HRRR) forecast:"), then the value with "over the limit" or "under
  the limit", never a probability; under it how the number was made (the
  Quantity's reason for having no margin: HRRR from the model's 10 m and 80 m
  winds, NWS's 10 m wind carried to the rule's height) and the forecast's own
  `note` as served (HRRR: how its 10 m wind did against the station's record;
  NWS: it keeps no archive, so it cannot be checked). Each rule links its
  source. Nothing adds them up. Under the table, "How these numbers were worked
  out" lists the weather answer's own uncertainty parts (the shares' sample and
  interval, the height, and what the check against observations found, with
  whether it passed its gate), the numbers behind every "checked". The last
  column also has what was seen ("Seen now: clear." or "Seen
  now:" with the count, for lightning within six hours; said to be now, not
  at the launch) and past years for a wind rule ("Past years (2001-2024):
  over the limit 1.0% of the time." with its source and hours counted) and
  for the lightning rules ("Past years (2019-2025): thunder could be heard at
  the pad 1.0% of the time.", GLM thunder hours, with what that does not count).
- **Space weather now** (`GET /space-weather`, answered at once, read again
  every five minutes while shown): meta "Kp {n}, {k} alerts" or "no current
  reading". Opens with one line: "Now: Kp 1, protons above 10 MeV at 0.23 pfu,
  X-ray flares class B4.7, solar wind at 456 km/s; 2 alerts in the last 24
  hours." (none recent enough: "No reading is recent enough to show: the
  newest is from {time}."). Then each reading with its age from its own
  source ("· as of 2 h ago") or why it is not shown: Kp, protons above 10 and
  100 MeV, solar wind, the Sun's field north–south (Bz), X-ray class (or
  `xray_missing_reason`), the alerts as headlines. No alert listed is "None"
  only when `alerts_missing_reason` is null (the list is current); otherwise
  the row gives that reason with a link to SWPC's alerts, and the line ends
  "SWPC's alerts of the last 24 hours are not shown here." Never "None" for no
  data. "The next three days": NOAA's outlook in one sentence,
  numbers as issued (chance of a radiation storm, S1 or greater, day by day;
  largest Kp expected), and the forecast word for word behind "NOAA's
  forecast as issued". "Newest events on the Sun (NASA DONKI)": the three
  newest clouds thrown off the Sun (coronal mass ejections; speed, Earth
  arrival if estimated), flares (class, peak) and solar particle events, each
  with its record; a kind DONKI gave more of says "· 3 newest of {n}"
  (`donki.counts`). No dose here: the service's `note` points to Trip.

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
  and every burn. Gaps in the data (between the stretches the service lists
  in `covered`; a seam under a second is not a gap) break both lines and leave both lanes empty with a dashed outline, keyed
  "No data" and listed in the twin; a gap is never counted as out of contact.
- **Rows:** Radiation on the way (meta "screening only"; below) ·
  Burns ({n}, or "none listed"; each burn is one instant with its
  `no_margin_reason` under it, and `burns_note` says what is not seen) ·
  Corrections on the way (meta "a budget: {total} in 99 of 100 runs"; the
  service's `label` first, "not a prediction"; one sentence with the runs,
  95 and 99 of 100, the interval allowing for the number of runs, the linear
  check, runs that missed the Moon, the arrival height; a table of the three
  corrections and their total, taken run by run; every assumed error; the
  plan and flown notes. None: `corrections_note`) · Where the Moon's pull wins
  (only when `moon_pull` is given) · Download the trip (flown trips only: CCSDS
  OEM and CSV, one block per stretch NASA's reconstruction covers, said in the
  row when there is more than one; SPK is not served) · How sure is this? · Where does this
  come from?
- **Radiation on the way** (`Trip.radiation`; null: `radiation_note`). One
  sentence first: "{h ×/÷2} in the radiation belts over {n} passes. Cosmic
  rays give {mGy a day ±} on the way and {…} at the landing spot, before any
  shielding." Belts not counted because NASA's reconstruction starts beyond
  them (IM-1): the sentence opens with the reason (`belt_hours.missing_reason`),
  the belt time row gives it, and the two belt fluences read "Not counted, as
  above"; never "≥0" or "0 ×/÷2". Then `screening_note` (it names where to
  confirm; `confirm_in` is added only for a tool it does not name), the
  numbers as a list (belts and passes, electrons above 1 MeV, protons above
  10 MeV in the belts, cosmic-ray dose on the way and at the landing spot with
  the share of open sky, ", assumed" when it is), `surface_note` under the
  list (a flat horizon assumed where there is no elevation data; or, with no
  surface dose, why: Peregrine was lost on the way), the solar particle events during the trip
  (`sep_note`, each with its DONKI record), "Past large events, for
  comparison" (a table: Oct 1989, Oct 2003, Aug 1972, protons above 10 and 30
  MeV per cm², each linking its measurements) and "How each was worked out"
  (every figure's `source`, each past event's measurement).
- **No data:** `source: "none"` shows `none_reason`.

### Landing (`/landing`, and the hub's default)

The existing mission page: status and dates, "Sun & Earth at this target"
with the four numbers, ribbons, "Change the dates", Listen, the AI row, and
the target, payload and source rows. Only the back link and `h1` moved up
into the hub header.

### Contact (`/contact`, `GET /missions/{id}/contact`)

- **Question:** "How often can the lander talk to Earth?"
- **Answer:** "A ground station can hear it for {h} hours over these dates.
  Through {relay} ({launch status}) it could reach Earth for {lo} to {hi}
  hours, if it flies as planned; that adds {lo} to {hi} hours to direct
  contact. The longest time without contact is {h} hours directly, or {lo} to
  {hi} hours with the relay, if it flies as planned" (`direct_only` gives the
  direct waits, net-4). The relay's
  launch status stands beside its name ("not launched", "planned, not
  launched", "in orbit"); a relay that adds nothing because Earth is already
  in view says "it adds no time to direct contact" (IM-3's Altus-1); with more
  than one relay, "Through a relay … if they
  fly as planned". A planned relay whose orbit is not published is named, not
  counted: "{relay} ({status}) could relay for it, but time through it is not
  worked out yet" (the tile says why). A wait that counts the relay is a range
  and says "with the relay, if it flies as planned", in the answer and under
  its tile. With no gap at all: "A ground
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
  dates with "{lo}–{hi} h somewhere in these dates, if it flies as planned"
  (what it adds), or "Not worked out: {reason}"; since net-4 the links are
  direct only, so each relay's row comes from `relays`.
  Booked passes are outlined boxes labelled "booked". Orbiters already flying
  (LRO, Danuri, …) come last, their passes as dashed outlines captioned "could
  see the lander; not a relay": geometry only, no agreement carries a lander's
  data, so they count in no number. Only orbiters with a trajectory for these
  dates get a row (an empty row would read as never in view); where the
  trajectory stops early, the rest is a dashed grey "No trajectory recorded"
  box, in the legend and the table twin. The antennas of one Deep
  Space Network complex share a row ("Goldstone, California · Deep Space
  Network, 4 antennas"); the twin keeps each antenna. Twin: link, start, end,
  length, booked or not.
- **Rows:** Relays (`relay_note` first; each with its operator, launch status
  as glyph and words, its launch plan, what it adds to direct contact and the
  time through it as ranges or why they are not worked out, its orbit in plain
  words, each figure "published" or "assumed", `orbit_note`, `sweep_note`;
  "Added to compare" when `for_this_mission` is false) · Compare a relay
  (`GET /relays`: the catalogue's relay services that are not already the
  mission's own, a tick box each with its operator, launch status and launch
  plan, and "Its orbit is not published, so no time through it can be worked
  out" when `orbit_known` is false; at most three. Ticking works nothing out:
  "Work out the numbers with these" asks the answer again with `?relay=` for
  each, and the row comes back open with them named beside its title. The
  choice is for this mission on this page only, and the row is not offered in
  the saved copy, which has no comparisons) ·
  Orbiters that could see the lander (`Contact.orbiters`, F2: `orbiters_note`
  first; each with its operator, "{n} passes over these dates, {h} in view in
  all; the longest pass {min}, the longest wait between passes {h}", a
  trajectory that covers only part of the dates says so, one with none says
  "Not known: {reason}" (never "no pass"), its own note when it differs, and
  its JPL Horizons source with its age) · Booked ground-station
  passes · Rover and lander line of sight · More numbers (either way as a range
  "if the relay flies as planned"; the two waits directly; a missing number
  gives its reason) · Download the
  contact plan (ION, CSV: the ION file needs the data rate the team plans for,
  since the lander's is not published, so there is a field for it and the ION
  link stays off until it holds a number above zero; the spreadsheet needs none.
  With a planned or added relay whose orbit is known well enough, a tick box adds
  `?relay=` so both files list its contacts, marked planned; one that is not is said
  to have none listed) · Change the dates (the same dates as Landing) ·
  How sure is this? · Where does this come from? "Line of sight only: the
  lander's radio power is not published" changes what every number means,
  so it is a one-line note under the answer, not a row.
- **Rover and lander line of sight** (`GET /missions/{id}/contact/rover?rover=`,
  asked for when the row opens; shown only for a mission that carries a rover
  as the service lists them (payloads that move, then listed rovers: IM-2's
  Yaoki, Griffin-1's FLIP, IM-3's Lunar Vertex and CADRE); a select when there
  is more than one; a
  202 shows the working panel). Answer first: "{rover} would be out of the
  lander's sight for {share} of its drive. The longest stretch out of sight is
  {m}." When no drive is published the share is over the ground: "Within {r} m
  of the lander, {lo}–{hi}% of the ground is out of its sight; the radio path is
  not clear over {lo}–{hi}%." (ranges where uncertain cells could go either
  way), then the reason the longest stretch is missing. The served `note` (what
  clear, blocked and uncertain mean) sits under the map, and a row "Antennas,
  radio and terrain" gives the antenna heights and frequency (each "assumed"
  with its reason unless given) and the elevation model with its post spacing
  and height error. Under those, when the answer can be worked out, a form "Try
  other values" asks for how far from the lander (`radius_m`, 50 to 5,000 m),
  the two antenna heights (`lander_antenna_m`, `rover_antenna_m`, 0 to 50 m)
  and the radio frequency (`freq_mhz`, 30 to 100,000 MHz), each box with its
  limits and the value in use ("In use: 500 m, assumed."). An empty box is not
  sent, so the service assumes it and says so; a slip is told at its box in a
  sentence and nothing is asked; the button "Work it out with these" asks the
  question again and the row comes back open with the sentence, map, numbers
  and table for those values. A value the team gave reads "3 m, as you gave it"
  whatever the service calls it, the service's "Give lander_antenna_m." is
  dropped since the box is on screen, and "Back to the assumed values" (shown
  only while any is given) asks for the assumed ones. `resolvable: false` → "Cannot be said here." and the served reason,
  no map. The viewshed is a map layer around the lander, north up, rings every
  100 m, the lander an ink square: in sight filled (earth), blocked the 45°
  hatch, uncertain the −45° hatch on a light wash; each state in the legend
  with a glyph (● ✕ ?) and words. A switch shows the line of sight or the
  radio path (the first Fresnel zone needs a wider corridor). When the answer
  gives `viewshed_tile` and `lander`, the same layers are drawn over the
  terrain from the service's tiles (`/tiles/viewshed/{answer}/{z}/{x}/{y}.png`,
  `?layer=terrain|sight|radio`): the hillshade of the 20 m window the answer
  read under the answer's own layer, the picture turned to put north up (the
  polar grid's north is the site's longitude off) and shrunk by the grid's
  scale, at the zoom whose tile pixel is about a screen pixel; the legend adds
  "The ground, shaded from the terrain map" and its swatches are drawn in
  the tiles' own style; a layer that fails to load says so under the map (a map
  without its layer would read as no blockers). Without tiles (not resolvable,
  or the offline copy) the sectors above are drawn instead. Table twin, from
  the same rays: each direction ("270° (west)") with its runs in words for both
  ("In sight 25–275 m; uncertain 300 m; blocked 325–425 m; in sight 450–500 m").
  Without `viewshed` the row says there is no map.
- **Dates:** the hub sets the dates to the mission's time on the surface
  when the mission is first opened, whichever step comes first, so Contact
  and Landing always answer for the same dates.

### Return (`/return`, `GET /missions/{id}/return`)

- **Question:** "Where do the booster and any capsule come down, and what is
  the sea like there?"
- **Answer:** the service's own words for where the booster comes down
  (`booster.note`: "The booster came back to Landing Zone 1", or the vehicle's
  practice and the flown CLPS landings when not yet published), then the sea:
  "Waves there are forecast at {v ± m} against the team's limit of {limit}.",
  or the one reason every measure shares ("This launch is in the past; the sea
  and wind then were not recorded."). Adds the capsule's `reason` ("Nothing
  comes back to Earth on this mission.") when not applicable. No booster: a
  cancelled delivery or a vehicle not published is the step's state panel with
  its summary. The note does not name its source; "Where does this come
  from?" does (Launch Library 2's landing records or upcoming launches, and
  GFS-Wave with its run and fetch when the sea is forecast), and "Worked out"
  is the newest input's time.
- **Numbers:** Waves at the booster landing zone · Wind at the booster
  landing zone · Waves at the splashdown zone · Wind at the splashdown zone
  (the last two only with a capsule; without one the row has two tiles). On
  land there are no waves: that tile says so and has no bar.
- **Chart: against the team's limits.** One row per measure: the value as a
  bar with its ± hatched, the team's limit as an ink rule. Over the limit is
  magenta, a triangle and the words "{x} over the team's limit" (invariant 4).
  No limit entered: the bar alone and "No limit entered by the team". Twin:
  measure, value, ±, limit, who entered it, over or not. Nothing to draw (no
  forecast and no limit, as for every flown launch): no chart; the tiles say
  why.
- **Team limits form:** starts from the limits entered (the PUT replaces both
  parts, so a part not shown is sent as it stands); a field left empty is no
  limit; its history is `entity=limits&id=return:{mission}`.
- **Booster landing zone** not published yet (a mission still to fly): the
  row's meta stays "not published yet" and the body says where the sea is
  read ("The sea is read near {lat} {lon}."), since that point is chosen, not
  a published zone.
- **The capsule model, checked against a real landing** (`capsule.model_check`,
  shown whenever it is served, capsule or not): meta "{d} km from it; the limit
  is {l} km"; the body is the service's `note` first, then the case, the
  distance with its range over the published drag range, the limit, the
  mission's own simulation, the 99 % landing area and whether it holds the real
  point, when it was checked, and its sources (a URL as a link by its host).
  Over the limit: "{x} km over the limit." with the triangle (invariant 4).
  With a capsule and no check served, the splashdown zone says "The capsule
  model has not been checked against a real landing here."
- **Rows:** Booster landing zone · Splashdown zone · The capsule model, checked
  against a real landing · Team limits · How sure is this? · Where does this
  come from?

---

## 5. Entering records (the project manager)

Every write is one small form in a `Sheet`, opened by a secondary button next
to what it changes. The browser's own checks are off (`noValidate`), so each
message is ours and sits under the field it is about. Forms share `Field` (visible label, hint, error),
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
- Model disagreement: the uncertain glyph and the words "Models disagree",
  then the service's sentence. "Checked against observations" / "not yet
  checked": one phrase in each rule's line, and spoken on every share.

## 9. Words

All labels follow the Words table. New words this design uses, proposed for
`docs/conventions.md` (owned by the backend):

| Say | Not |
|---|---|
| launch time (on request: "Also called T-0") | T-0, liftoff epoch |
| speed added to leave Earth for the Moon | TLI Δv, C3 |
| direction of the climb (compass heading) | launch azimuth |
| time in orbit around the Moon before landing | loiter, phasing orbit time |
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
