# Design audit, 12 November 2026

The audit behind the design pass: what was looked at, what was found, and where each finding is fixed.
Nothing here is a redesign. The product's look stays; this is the list of what stops it feeling finished.

How it was made: every route in `frontend/src/App.tsx` was captured at 1440, 1024, 768 and 390 wide, dark and
light (336 captures), then in each state that applies (503 captures: loading, working it out, needs input, no
data, error, saved copy, empty filters, long names, a full project, the lander tools, Ask, the guide, print,
reduced motion, 200% zoom). Each capture was measured for sideways scroll, console errors, tap targets under
44 px, clipped text, contrast and covered content. Seven planner journeys were then walked in the running app.

Tags: **bug**, **glitch** (alignment, spacing, overflow, clipping, jump), **jargon**, **overload**, **flow**
(unclear next step or dead end), **delight** (a missed chance to make it feel good).

The evidence (screenshots, scripts, raw data) is on the audit machine under `.local/review/audit-2026-11-12/`
and is not in git. The glossary of renamed terms is `docs/design-glossary.md`.

Status: Part 3 says which build package fixes each finding. The closing commit of the pass marks every
item done or gives the reason it stays open.

Contents: Part 1, what the screens look like (visual findings, with counts of items before scrolling).
Part 2, what the journeys feel like (flow findings). Part 3, what is shown that does not help (overload).
Part 4, where every finding lands.

---

# Part 1: Visual findings


Captured 2026-11-12 against http://127.0.0.1:5173 (web) and http://127.0.0.1:8000 (API). Chromium headless shell through Playwright; viewports 1440x900, 1024x768, 768x1024 and 390x844; dark and light. Paths below are relative to `polarwindow/.local/review/audit-2026-11-12/visual/`. Source paths are relative to `frontend/src` unless they start with `backend/`. Tags: `bug` (wrong or broken), `glitch` (looks or reads wrong), `overload` (too much at once), `delight` (works well).

### 1. What was captured, and what could not be reached

#### Captured
- Pass A: 28 routes (landing, home, missions, 6 steps for an upcoming mission, 6 for a flown one, a project's home and Ready step, project new and edit, map, site, compare, skyline, plan, report, not-found) at 4 widths and 2 themes: 224 measured captures (fold and full-page images, console, network, overflow, tap targets, clipped text, contrast, dashes, tables).
- Pass B (states): 234 measured captures: loading skeletons (page and registry), working and queued jobs, mixed step states, 17 injected error scenarios, offline and API-unreachable (first load and after), 6 mission filter states, long-name and full-field projects, the three lander tools, Ask, the guide, print (PDF and print-media), reduced motion (two kinds) and 200 percent zoom. 869 images in shots/A, shots/B and shots/C in total.
- This session: owner close-ups (owner/), a tab-order audit of the first 25 stops on 5 pages in 3 configurations (15 runs, 375 stops), re-takes of the Ask panel at 390 and of the landing-ellipse tool (shots/C, data/C), and contact sheets of the state groups that had not been viewed.
- Contact sheets viewed: all 56 route sheets, B-guide, B-zoom200, X-steps, B-errors (1440, 390), B-loading (1440, 390), and in this session D-working, D-empty, D-long, D-filters, D-offline (each at 1440 and 390), D-tools-1440, D-print and the PDF pages of the report, C-ask390, C-ellipse (1440, 390), C-bottom390 and the five owner close-ups (81 sheets exist).
- Owner close-ups: `owner/journey-curve-dark.png`, `owner/journey-curve-light.png` (1440, IM-2, arc drawn solid), `owner/journey-curve-390-dark.png` (a vertical rail, because the arc is only drawn when the journey is 56rem wide; there is no curve at 390), `owner/landing-ideas-dark.png`, `owner/landing-ideas-light.png`, and because the ideas change with scroll (the Moon re-frames behind the cards) `owner/landing-ideas-frame1.png` to `frame3.png` (dark, scroll positions for ideas 1 to 3; light variants are `owner/landing-ideas-light-scroll-N.png`). Extras: upcoming-mission variants, mid-draw frames, context shots.

#### Not reached, and why
- Reduced-motion sheets (`reduced-os-reduce.*`, `reduced-pref-reduced.*`), `mix-states.m-fl`, `long-lists.*`, `tool-power.390` and `tool-relay.390` exist as captures and measurements but no sheet of them was viewed by anyone; the dark report PDF was not viewed.
- Only Chromium (headless shell) at emulated viewport sizes: no Firefox or Safari, no real touch device, no hover or tooltip states, no WebGL on the landing page beyond what headless GPU allows (GPU notes logged).
- Error, working and offline states are injected: the 404 and 500 bodies, including their wording ("The calculation did not finish", "Nothing was saved"), are the capture script's own text (scripts/passB.cjs:196); the working text "Tracing the Sun along the horizon, 12 of 29 days done" is the script's job message (passB.cjs:154), and the same job is applied to every step. "Offline" is the browser set offline after a first load, then an in-app navigation (passB.cjs:230-258); the app's structure for these states is real, the copy in injected errors is not.
- Printing: only a Playwright PDF (A4, background graphics off) and print-media emulation, not a real print dialog. The light PDF was read; the dark PDF was not.
- Tab order: the first 25 stops per page only (header 8 stops plus the first controls); later stops, Shift+Tab, activation by keyboard, the month listbox arrow keys, and map or chart controls were not exercised.
- Hub captures in shots/B log blocked hillshade tiles (app on 127.0.0.1, API host localhost): mini-map tiles may be missing in those images. Pass A shows none.
- The API refused connections once during this session (a restart); it came back within 10 seconds and every online step was completed.

#### False positives dropped (the earlier worker's and mine)
- Landing, light theme, contrast 1.06 to 2.22 (6 rows of table 3.6): the hero text sits on the dark space picture; the script measured against the cream page colour. Dropped.
- "Content under fixed layers at the bottom of the page" (table 3.5, 22 rows): checked at the real page bottom (/missions at 390, /missions/griffin-1/return at 390, /missions/griffin-1/launch at 768, `sheets/C-bottom390.jpg`): the footnote ends 100 px or more above the nav island and the Ask button (AppShell.tsx:278-281 reserves 9.5rem). The rows count text inside closed disclosures or inner scroll frames. Not reproduced; the table is kept below as measured but is not a finding.
- Landing 1440 full page "ideas sit in the left 40 percent with an empty black area at right": the Moon is a fixed canvas that a full-page capture does not draw; frames 1 to 3 show the Moon beside each card. Dropped.
- "Journey stops float without the arc at 1440 full captures" (m-up, m-fl): a full-page capture loses the arc that has finished drawing (my own full-page clip lost it too; an element capture shows it). Dropped; the arc is correct in the owner close-ups.
- Landing count-up caught mid-count (21 against 22): the number animates; the real defect is the count including projects (rank 4). The "home says 2, 8 or 14 steps wait on you" drift is test projects being added during the run (section 4), not an app fault.
- "The same 'calculation did not finish ... Nothing was saved' wording is used when a plain list load fails": the wording is the capture script's mock body. Dropped. (The bare-500 fallback title "Something went wrong" is the app's own, client.ts:97.)
- Mission step pages showing a Sun-tracing message on Ready and Return while working: the injected job is applied to every step. Dropped.
- "Work it out is disabled for the landing ellipse" and "ask.390 button already expanded": a disabled button until six figures are typed is by design (DispersionPanel.tsx:112); the Ask retake clicked the visible round button and worked.
- 11 of 12 month tiles flagged as clickable but not focusable (site, m-fl-surface): the strip is a listbox with a roving tabindex (components/WindowPicker.tsx:250), one Tab stop and arrow keys; not a defect.

### 2. Findings

#### Ranked top 40, worst first

Fields: tag, route, width, theme, state, visible text or selector, evidence file, source file:line.

1. [bug] report | A4 print | light | print (PDF, 2 pages) | The printed Printable report carries the app chrome: header pill, Map/Site/Compare/Plan tabs, the round Ask button over the Assessment sentence ("...latitud" then the button) and the bottom nav island, on both pages; the sunlight bars print as empty frames (PDF made with background graphics off, which is also the browser default) | evidence: shots/B/print.report.light.pdf (pages 1-2); sheets/D-print.jpg (dark PDF not viewed) | src: components/AppShell.tsx:157 (header), :297-308 (Ask button), :314-316 (nav island); screens/ReportScreen.tsx:93-94 and :300 (only two blocks carry print:hidden); no print-color-adjust anywhere in src
2. [bug] project-edit | 768 and 390 | dark+light | default | Page scrolls sideways: scrollWidth 791 vs 768 (+23 px) and 433 vs 390 (+43 px); the Launch pad select ("Launch Complex 39A - SpaceX, Eastern Range, Florida") pokes past its card and the viewport; also on long-full.edit at 390 | evidence: sheets/project-edit.full.jpg; data/A/project-edit.390.dark.json; data/cross-cutting.md 3.1 | src: components/project/fields.tsx:111 (div.basis-full around the control); components/project/ProjectForm.tsx:99 (SelectField "Launch pad"); likely cause: the select button has no min-w-0/truncate for its long option text
3. [bug] m-up-ready (every mission step) | 390 | dark+light | Needs input / No data yet / Working it out | The 3x2 step bar cuts the state words to an ellipsis at a 49 px box: "Needs input" and "No data yet" in 25 captures, "Working it out" in 12 more; on a phone the state is then only the glyph | evidence: sheets/m-up-ready.fold.jpg; sheets/D-empty-390.jpg; sheets/D-working-390.jpg; data/cross-cutting.md 3.4 | src: components/lifecycle/JourneyBar.tsx:113 (span.truncate in StateLine), :216 (grid-cols-3 at 390)
4. [bug] landing | 1440 and 390 | dark+light | default | Hero count "CLPS missions" includes user projects: it read 21, 22, 24 over the captures and the API now answers total 25 (20 catalogue entries + 5 projects); the same figure feeds "N of N missions" on /missions | evidence: sheets/landing.fold.jpg; sheets/B-errors-1440.jpg (error.no-session reads 24); GET /api/v1/missions total=25 | src: screens/LandingScreen.tsx:403-411 (useMissions({}).total labelled "CLPS missions")
5. [bug] m-proj-ready; project-empty.ready | 1440, 1024, 768, 390 | dark | default | React console error "Encountered two children with the same key" logged twice per load (once at 768); the only app console error in the 224 normal captures | evidence: data/A/m-proj-ready.1440.dark.json; data/cross-cutting.md 3.2 | src: not located; not the item rows (the 9 ids from GET /missions/p-aurora-scout-1/ready are unique): check keys in screens/sections/ReadySection.tsx and components/lifecycle/Readiness.tsx
6. [glitch] every mission step, home, missions, filters | 390 | dark+light | first screen | The round Ask button floats over first-screen text: it hides "UTC" in "The published liftoff is 27 Feb 2025, 00:16 UTC" (m-fl-launch), the right end of Launch step lines, a KPI card in the working state, and on long-name step pages it sits on the "6 Return" step | evidence: shots/C/ask-open.m-fl-launch.390.dark.1-closed.png; sheets/C-ask390.jpg; sheets/D-long-390.jpg; sheets/D-working-390.jpg | src: components/AppShell.tsx:297-308 (fixed right-4, 56 px, 10 px above the nav island)
7. [glitch] offline (new page while offline) | 1440 and 390 | dark | browser offline, page not opened before | After 4.5 s the page is gray blocks only: 0 headings, 0 sentences, 0 controls in the fold; the offline banner at the top is the only message, nothing says this page cannot load | evidence: sheets/D-offline-1440.jpg; sheets/D-offline-390.jpg; data/B/offline.m-fl-surface.1440.dark.json | src: banner at components/States.tsx:360; skeleton not located
8. [glitch] loading (every route) | 390 and 1440 | dark | skeleton then content | Skeletons are far shorter than the content: home 390 2447 -> 5440 px (layout shift 0.774), report 390 844 -> 3240 (0.543), project-edit 390 844 -> 5670 (0.185), plan 390 844 -> 2034; mission steps show only gray blocks with no heading | evidence: sheets/B-loading-390.jpg; sheets/B-loading-1440.jpg; data/cross-cutting.md 3.9 | src: per-screen skeletons; no single line
9. [overload] m-up-return | 1440, 768, 390 | dark | default | The headline is one sentence of about 85 words in display type: 9 lines at 1440, 8 at 768, 12+ at 390, filling the 390 first screen and pushing the KPI cards below the fold; the date breaks as "(12 / Nov 2026 07:00 UTC)" and at 768 "IM- / 1 on Landing Zone 1" | evidence: sheets/m-up-return.fold.jpg; sheets/D-empty-390.jpg (project-empty.return, same text) | src: backend/app/services/return_service.py:309
10. [glitch] m-up-contact, m-proj-ready, m-up-ready | 1024 and 390 | dark+light | default | A number is split from its margin: "422.6 / ±0.5 h" (m-up-contact), "12:00 / ±12.0 h" (m-proj-ready), "Jan- / Jan" (m-up-ready, value reads "2026-2027 Jan-Jan"); together at 1440 and 768 | evidence: sheets/m-up-contact.fold.jpg; sheets/m-proj-ready.fold.jpg; sheets/m-up-ready.fold.jpg | src: components/KeyNumbers.tsx:181 (flex-wrap items-baseline gap-x-2); lib/format.ts:233 (Next milestone)
11. [glitch] m-up-launch | 1440, 1024, 390 | dark | default | One screen gives two dates: headline "the next is 12 November 2026, 07:00 UTC" and "Numbers for the opportunity on 11 November 2026, 07:04 UTC +/-18 min" (capture clock about 22:00 UTC on 11 Nov, so the card date is already past); the headline runs 3-4 lines and names Launch Complex 39A twice | evidence: sheets/m-up-launch.fold.jpg | src: screens/sections/LaunchSection.tsx:179 (next), :185 (opportunity)
12. [glitch] plan | 390 | dark | default | "Every time without contact" is its own scroll frame: table 720 px in a 326 px frame, only # / START / END show, "Day 18, 1 April, 00:43 UTC" is cut mid-string, LENGTH and ALSO DARK? are off-screen with no fade or shadow cue (768: 736 px in 768 also scrolls) | evidence: sheets/plan.full.jpg; data/A/plan.390.dark.json; data/cross-cutting.md 3.8 | src: screens/BlackoutScreen.tsx:184 (ScrollRegion), components/ui.tsx:524
13. [glitch] plan | 1440, 1024, 768, 390 | dark | default | The "now" marker line runs through the label "<- 38 h, the longest time dark and out of contact"; at 390 the row label "NEITHER: DARK AND OUT OF CONTA..." is cut at the right edge | evidence: sheets/plan.fold.jpg | src: components/BlackoutTimeline.tsx:140
14. [glitch] home | 1440 and 390 | dark | API unreachable at first load | Missing full stop: "Cannot reach the service that does the calculations The missions, sites and Ask still work." (title has no period, the sentence is appended) | evidence: sheets/D-offline-390.jpg (unreachable-first.home) | src: screens/HomeScreen.tsx:63; lib/api/client.ts:118 (title text)
15. [glitch] guide (home, site, steps, missions) | 390 | dark | guide open | The Guide card is about 270 px tall (a third of the 844 px screen), stacked above the nav island; it leaves 2-3 lines of Home, Site and step pages above it and the Ask button overlaps its text; at 1440 it is a 380 px bar that covers the lower rows of "Needs you" | evidence: sheets/B-guide.jpg | src: components/GuideBar.tsx:95 (fixed bottom-[calc(5.5rem...)])
16. [glitch] missions (filters, no match) | 390 | dark | no missions match | The empty-state card ("No missions match these filters", "24 missions checked against: provider ZZ Nobody.") and its "Clear filters" button start at about y 390 and sit under the Ask button and nav island at the fold; filter chips take 330 px first; chip row clipped at "Heat flow" with no scroll cue | evidence: sheets/D-filters-390.jpg | src: screens/MissionsScreen.tsx:303
17. [glitch] long names (long-long.*) | 390 | dark | long mission name | The hub title wraps to 12 lines before the step bar (the name in display weight plus the vehicle name); on step pages the breadcrumb is 3 lines but on the hub it is one line cut with an ellipsis; on Home the project name is clipped with an ellipsis at a 405 px box (18 captures) | evidence: sheets/D-long-390.jpg; sheets/D-long-1440.jpg; data/cross-cutting.md 3.4 | src: components/Page.tsx:15-45 (Breadcrumbs); components/home/ProjectCards.tsx:76 (h3.truncate)
18. [glitch] errors (mission-500, registry-500, plan-500, skyline-500, report-500) | 1440 and 390 | dark | injected 500 | The page collapses to one card (about 300 px at 1440 top-left of a black 900 px page, no heading, no mission or site name; at 390 the card fills the top 220 px of an empty 844 px screen); the address is the only clue which page failed | evidence: sheets/B-errors-1440.jpg; sheets/B-errors-390.jpg | src: components/States.tsx:141-163 (ProblemPanel)
19. [glitch] skyline | 1440 and 1024 | dark+light | default | First screen is an empty ~1000x700 plot with three cyan Earth-path streaks at the right edge and the Sun path at the bottom edge; the terrain silhouette is below the fold (at 1024 only its top shows); full page: the right card column holds two small cards (~160 px) beside ~700 px of charts, leaving a ~550 px empty column | evidence: sheets/skyline.fold.jpg; sheets/skyline.full.jpg | src: scenes/DomeCard.tsx:24; components/HorizonProfile.tsx:115
20. [overload] compare | 1440 | dark | default | Busiest first screen of any route: 44 items (4 headings, 11 sentences, 12 key numbers, 14 controls, 3 badges); "Too close to call" appears on 3 of 3 cards | evidence: sheets/compare.fold.jpg; data/fold.md | src: screens/CompareScreen.tsx:456
21. [overload] map | 1440 and 390 | dark | default | 1440 fold has 41 items (25 controls: tabs, search, filter, 15-row list, scrubber, toggles); at 768 and 390 the map circle takes the whole first screen and pushes the site list and chosen-site card out of it | evidence: sheets/map.fold.jpg; data/fold.md | src: screens/MapScreen.tsx
22. [glitch] m-fl-ready | 1440 and 390 | dark | default | Three of four KPI cards read "0" in display type (Blocked 0, Next milestone 0, Spare parts 0), "Next milestone 0" is a count where the upcoming mission shows a date; 13 identical rows follow (same bar, "Since 27 Feb 2025", "ll.thespacedevs.com", Change) and the 390 page is 4953 px | evidence: sheets/m-fl-ready.fold.jpg; sheets/m-fl-ready.full.jpg | src: lib/format.ts:233; components/lifecycle/Readiness.tsx:197, :229
23. [overload] m-fl-launch | 1440 | dark | default | The launch time is stated four times on the first screen (headline "27 Feb 2025, 00:16 UTC +/-15 s", "The published liftoff is ... +/-30 s", "Numbers for the launch on 27 February 2025 ...", the Launch time card), in two date styles; at 390 "UTC +/-15 s" starts a new line away from "00:16" | evidence: sheets/m-fl-launch.fold.jpg | src: screens/sections/LaunchSection.tsx:179-185
24. [overload] m-up-surface | 1440 | dark | default | The headline sentence repeats three of the four KPI cards under it (152 h / 21%, 423 h / 60%, >=422 h); 18 items on the first screen | evidence: sheets/m-up-surface.fold.jpg | src: screens/MissionDetailScreen.tsx:192 (SurfaceSection)
25. [glitch] project-new, project-edit | 768 and 1440 | dark+light | default | The sticky "Save project / Cancel" bar covers the first form row ("Mission") at 768 and takes the bottom of the first screen at 1440, so the first screen shows a drop zone and a button bar for a form not yet visible (full-page captures draw this bar over the Mission card heading; that part is a capture artefact and is not counted); the intro ends with the orphan "steps." | evidence: sheets/project-new.fold.jpg; sheets/project-edit.fold.jpg | src: screens/ProjectNewScreen.tsx:369 (sticky bar), :271 (intro text)
26. [glitch] m-up-launch | 390 | dark | default | The "Launch opportunities by day" chart shows 00:00-12:00 only: the second opportunity column is cut (half pills), rows such as "Wed 9 Dec" look empty, no scroll cue | evidence: sheets/m-up-launch.full.jpg | src: components/lifecycle/LaunchCalendar.tsx:81-82 (min-w-[520px] in a ScrollRegion)
27. [glitch] m-fl-trip | 390 | dark | default | Correction markers in "The trip, day by day" collide (": 4 5" jammed into one box) and the x-axis labels are cut to "27 Feb", "Day 2", "Day" at the right edge | evidence: sheets/m-fl-trip.full.jpg | src: screens/sections/TripSection.tsx:128
28. [glitch] m-up-contact, m-fl-contact, m-fl-return | all | dark+light | default | The lone dash that stands for an empty value in 34 px numbers ("Through a relay", "Waves/Wind at the booster landing zone") measures 1.87:1 dark and 1.55:1 light; on m-fl-return both KPI cards hold only a dash | evidence: data/cross-cutting.md 3.6; sheets/m-fl-return.fold.jpg | src: components/KeyNumbers.tsx:188 (text-line-strong)
29. [glitch] every page with breadcrumbs | all | dark+light | default | The "/" breadcrumb separator measures 1.75:1 dark and 1.53:1 light (decorative, aria-hidden) | evidence: data/cross-cutting.md 3.6 | src: components/Page.tsx:38 (text-line-strong)
30. [glitch] landing (idea 4 "The ice is in the dark") | 1440 | light | default | The "power" label in the drawing is rgb(232,196,137) on white, 1.66:1 (13 px); 12.5:1 in dark. The contrast script skipped SVG text, so this is not in table 3.6 | evidence: owner/landing-ideas-light.png | src: landing/Illustrations.tsx:85
31. [glitch] landing (idea 1 "The Sun never climbs") | 1440 | dark+light | default | The vertical divider (x=160) runs through the caption "grey = the ground you are standing on" | evidence: owner/landing-ideas-dark.png; owner/landing-ideas-light.png | src: landing/Illustrations.tsx:15 (divider), :23 (caption)
32. [glitch] m-up, m-proj | 1024 | dark+light | default | "Explore a scenario" pills wrap to two lines ("Explore a / scenario"); at 1440 the two pills sit at different heights | evidence: sheets/m-up.fold.jpg; sheets/m-proj.fold.jpg | src: components/lifecycle/JourneyBar.tsx:491-500
33. [glitch] home | 390 | dark+light | default | The Ask field placeholder is cut by the Ask button: "Ask about a mission, a site or a di" | evidence: sheets/home.fold.jpg | src: components/home/AskBar.tsx:33-39
34. [glitch] missions | 1440 | dark | default | The list is its own scroll frame (max 640 px) beside the map card; the last visible row is cut mid-line ("Moon Base science delivery ...") with no fade; the map circle is ~190 px inside a 360 px card | evidence: sheets/missions.full.jpg; sheets/missions.fold.jpg | src: screens/MissionsScreen.tsx:314
35. [glitch] m-fl | 1440 and 390 | dark | default | The mission record mixes two date styles ("11:30 a.m. CST March 6, 2025" in the sentence, "6 Mar 2025, 17:28:43 UTC" under it); the clamped narrative needs a 32 px "Show more" button | evidence: sheets/m-fl.full.jpg | src: screens/MissionDetailScreen.tsx:321, :329
36. [overload] m-up-ready | 1440 and 390 | dark | default | The 11-row item list repeats "Not entered yet", "Not recorded" and a dash on every row: 33 filler strings | evidence: sheets/m-up-ready.full.jpg | src: components/lifecycle/Readiness.tsx:102; components/lifecycle/ProjectPanels.tsx:473
37. [glitch] m-up-surface, site | 1440 and 390 | dark | default | "Go further with this spot": two actions are pills and the third ("Printable report") is plain text; on the Site page the three actions under the skyline are styled three ways | evidence: sheets/m-up-surface.full.jpg; sheets/site.full.jpg | src: screens/MissionDetailScreen.tsx:656-682
38. [glitch] report | 768 and 390 | dark+light | default | A rank range breaks at its en dash: "Too close to call: could be 1st- / 2nd" inside the Connecting Ridge card; the sheet title wraps to two lines at 390 | evidence: sheets/report.fold.jpg | src: screens/ReportScreen.tsx:184
39. [overload] tool-power (Power and temperature) | 1440 | dark+light | open | Opening the tool shows 27 input boxes under "Example lander" (each with an ASSUMED tag and a hatched fill behind the figure); the figures read at about 9 px in four columns | evidence: sheets/D-tools-1440.jpg | src: components/surface/EnergyPanel.tsx
40. [glitch] project-empty (ready, launch, trip) | 1440 and 390 | dark | nothing entered | Ready says "9 items are listed ... no states have been entered" but offers no first-action button on the first screen; Launch and Trip say what is missing ("Launch time") and what still works but offer only "Next step", no link to enter it | evidence: sheets/D-empty-1440.jpg; sheets/D-empty-390.jpg | src: screens/sections/LaunchSection.tsx:86; screens/sections/TripSection.tsx:70; screens/sections/ReadySection.tsx:155

#### Per route: items visible before scrolling, then issues worst first

The count is the number of items in view at load, dark theme (headings, sentences, key numbers, controls, badges, charts). Ranked entries carry their top-40 number.

#### landing
Before scrolling: 1440 = 10 (1 headings, 5 sentences, 2 key numbers, 2 controls, 0 badges, 0 charts); 390 = 10 (1 headings, 5 sentences, 2 key numbers, 2 controls, 0 badges, 0 charts).

- (top 40 #4) [bug] landing | 1440 and 390 | dark+light | default | Hero count "CLPS missions" includes user projects: it read 21, 22, 24 over the captures and the API now answers total 25 (20 catalogue entries + 5 projects); the same figure feeds "N of N missions" on /missions | evidence: sheets/landing.fold.jpg; sheets/B-errors-1440.jpg (error.no-session reads 24); GET /api/v1/missions total=25 | src: screens/LandingScreen.tsx:403-411 (useMissions({}).total labelled "CLPS missions")
- (top 40 #30) [glitch] landing (idea 4 "The ice is in the dark") | 1440 | light | default | The "power" label in the drawing is rgb(232,196,137) on white, 1.66:1 (13 px); 12.5:1 in dark. The contrast script skipped SVG text, so this is not in table 3.6 | evidence: owner/landing-ideas-light.png | src: landing/Illustrations.tsx:85
- (top 40 #31) [glitch] landing (idea 1 "The Sun never climbs") | 1440 | dark+light | default | The vertical divider (x=160) runs through the caption "grey = the ground you are standing on" | evidence: owner/landing-ideas-dark.png; owner/landing-ideas-light.png | src: landing/Illustrations.tsx:15 (divider), :23 (caption)
- [delight] landing | 1440 | dark+light | scroll | The four numbered ideas sit in 512 px cards (597, 630, 597, 630 px tall) while the Moon behind re-frames per idea; the drawings are clear in both themes; the cards are readable and not blank | evidence: owner/landing-ideas-dark.png; owner/landing-ideas-light.png; owner/landing-ideas-frame1.png to frame3.png; sheets/landing-ideas-scroll-dark.jpg | src: screens/LandingScreen.tsx:33-58, :329-343
- [delight] landing | 1440 | dark+light | hero | Hero scene (moon in dark, Earth over the horizon in light) | evidence: sheets/landing.fold.jpg | src: screens/LandingScreen.tsx

#### home
Before scrolling: 1440 = 28 (4 headings, 14 sentences, 1 key numbers, 8 controls, 0 badges, 1 charts); 390 = 18 (2 headings, 9 sentences, 0 key numbers, 7 controls, 0 badges, 0 charts).

- (top 40 #6) [glitch] every mission step, home, missions, filters | 390 | dark+light | first screen | The round Ask button floats over first-screen text: it hides "UTC" in "The published liftoff is 27 Feb 2025, 00:16 UTC" (m-fl-launch), the right end of Launch step lines, a KPI card in the working state, and on long-name step pages it sits on the "6 Return" step | evidence: shots/C/ask-open.m-fl-launch.390.dark.1-closed.png; sheets/C-ask390.jpg; sheets/D-long-390.jpg; sheets/D-working-390.jpg | src: components/AppShell.tsx:297-308 (fixed right-4, 56 px, 10 px above the nav island)
- (top 40 #14) [glitch] home | 1440 and 390 | dark | API unreachable at first load | Missing full stop: "Cannot reach the service that does the calculations The missions, sites and Ask still work." (title has no period, the sentence is appended) | evidence: sheets/D-offline-390.jpg (unreachable-first.home) | src: screens/HomeScreen.tsx:63; lib/api/client.ts:118 (title text)
- (top 40 #33) [glitch] home | 390 | dark+light | default | The Ask field placeholder is cut by the Ask button: "Ask about a mission, a site or a di" | evidence: sheets/home.fold.jpg | src: components/home/AskBar.tsx:33-39
- [glitch] home | 1440 | dark | default | "Your projects" row holds two cards in a 3-column grid (right third empty); "Being worked out 0" and the "Live" card end at different heights (~100 px empty under the left block); "Open activity" is indented ~10 px from the line above | evidence: sheets/home.full.jpg | src: screens/HomeScreen.tsx
- [glitch] home | 390 and 768 | dark | default | The round Ask button sits on the right end of the "Fill it in" row near the bottom of the first screen and the nav island covers the next row | evidence: sheets/home.fold.jpg | src: components/AppShell.tsx:297-308
- [delight] home | 1440 and 390 | dark | API unreachable at first load | Keeps the page and says what still works: "Your projects could not be read." and "The missions, sites and Ask still work."; a SAVED COPY banner says the answers are saved and pages not saved say so | evidence: sheets/D-offline-1440.jpg; sheets/D-offline-390.jpg | src: screens/HomeScreen.tsx:49-63

#### missions
Before scrolling: 1440 = 25 (4 headings, 5 sentences, 0 key numbers, 15 controls, 0 badges, 1 charts); 390 = 14 (3 headings, 3 sentences, 0 key numbers, 8 controls, 0 badges, 0 charts).

- (top 40 #6) [glitch] every mission step, home, missions, filters | 390 | dark+light | first screen | The round Ask button floats over first-screen text: it hides "UTC" in "The published liftoff is 27 Feb 2025, 00:16 UTC" (m-fl-launch), the right end of Launch step lines, a KPI card in the working state, and on long-name step pages it sits on the "6 Return" step | evidence: shots/C/ask-open.m-fl-launch.390.dark.1-closed.png; sheets/C-ask390.jpg; sheets/D-long-390.jpg; sheets/D-working-390.jpg | src: components/AppShell.tsx:297-308 (fixed right-4, 56 px, 10 px above the nav island)
- (top 40 #16) [glitch] missions (filters, no match) | 390 | dark | no missions match | The empty-state card ("No missions match these filters", "24 missions checked against: provider ZZ Nobody.") and its "Clear filters" button start at about y 390 and sit under the Ask button and nav island at the fold; filter chips take 330 px first; chip row clipped at "Heat flow" with no scroll cue | evidence: sheets/D-filters-390.jpg | src: screens/MissionsScreen.tsx:303
- (top 40 #34) [glitch] missions | 1440 | dark | default | The list is its own scroll frame (max 640 px) beside the map card; the last visible row is cut mid-line ("Moon Base science delivery ...") with no fade; the map circle is ~190 px inside a 360 px card | evidence: sheets/missions.full.jpg; sheets/missions.fold.jpg | src: screens/MissionsScreen.tsx:314
- [glitch] missions | 390 | dark+light | default | The round Ask button sits over the first upcoming row ("Griffin Mission One ... launch late 2026 (known to the" cut by it and the Planned badge); the map comes after all 22 rows (page 4075 px) | evidence: sheets/missions.fold.jpg; sheets/missions.full.jpg | src: components/AppShell.tsx:297-308
- [glitch] missions | 1440 and 390 | dark+light | default | Counts drift between captures: "21 of 21", "22 of 22", "24 of 24" missions while test projects were added (data effect, see section 4) | evidence: sheets/missions.fold.jpg; sheets/D-filters-390.jpg | src: see landing count
- [delight] missions (filters, no match) | 1440 | dark | no missions match | Says how many were checked and against what ("24 missions checked against: carries any of Laser retroreflector; status Flown; provider ...") and offers "Clear filters" and "Remove Laser retroreflector" | evidence: sheets/D-filters-1440.jpg | src: screens/MissionsScreen.tsx:303

#### m-up
Before scrolling: 1440 = 7 (4 headings, 2 sentences, 0 key numbers, 0 controls, 0 badges, 1 charts); 390 = 2 (2 headings, 0 sentences, 0 key numbers, 0 controls, 0 badges, 0 charts).

- (top 40 #32) [glitch] m-up, m-proj | 1024 | dark+light | default | "Explore a scenario" pills wrap to two lines ("Explore a / scenario"); at 1440 the two pills sit at different heights | evidence: sheets/m-up.fold.jpg; sheets/m-proj.fold.jpg | src: components/lifecycle/JourneyBar.tsx:491-500
- [glitch] m-up (journey close-up) | 1440 | dark+light | default | Earth end glyph (16 px) sits about 7 px lower than the step 1 disc and reads small beside the 28 px discs; the arc ends against the Moon glyph; step text under the arc ends at six different heights (ragged bottom, Launch 4-6 lines, Return 6) | evidence: owner/journey-curve-dark.png | src: components/lifecycle/JourneyBar.tsx:520-566 (Terminal)
- [glitch] m-up | 1440 | dark | default | The mission record card (440 px) leaves its right half empty beside a 310 px Target card ~1.5x taller; at 390 the Ask button covers the end of the Launch step sentence | evidence: sheets/m-up.full.jpg | src: screens/MissionDetailScreen.tsx
- [delight] m-up | 1440 and 1024 | dark+light | default | The six steps drawn along a curved line from Earth to the Moon: an arc, ink-filled discs for steps behind it, a ring for the open one; at 768 and 390 it becomes a vertical rail (the arc svg is hidden below a 56rem container); the flown mission draws the arc solid through all six stops with "Partly successful: all six steps are behind it" | evidence: owner/journey-curve-dark.png; owner/journey-curve-light.png; owner/journey-curve-390-dark.png | src: components/lifecycle/JourneyBar.tsx:346-513 (JourneyPath), :428 (@4xl:block arc)

#### m-up-ready
Before scrolling: 1440 = 11 (3 headings, 2 sentences, 1 key numbers, 5 controls, 0 badges, 0 charts); 390 = 9 (2 headings, 2 sentences, 1 key numbers, 4 controls, 0 badges, 0 charts).

- (top 40 #3) [bug] m-up-ready (every mission step) | 390 | dark+light | Needs input / No data yet / Working it out | The 3x2 step bar cuts the state words to an ellipsis at a 49 px box: "Needs input" and "No data yet" in 25 captures, "Working it out" in 12 more; on a phone the state is then only the glyph | evidence: sheets/m-up-ready.fold.jpg; sheets/D-empty-390.jpg; sheets/D-working-390.jpg; data/cross-cutting.md 3.4 | src: components/lifecycle/JourneyBar.tsx:113 (span.truncate in StateLine), :216 (grid-cols-3 at 390)
- (top 40 #6) [glitch] every mission step, home, missions, filters | 390 | dark+light | first screen | The round Ask button floats over first-screen text: it hides "UTC" in "The published liftoff is 27 Feb 2025, 00:16 UTC" (m-fl-launch), the right end of Launch step lines, a KPI card in the working state, and on long-name step pages it sits on the "6 Return" step | evidence: shots/C/ask-open.m-fl-launch.390.dark.1-closed.png; sheets/C-ask390.jpg; sheets/D-long-390.jpg; sheets/D-working-390.jpg | src: components/AppShell.tsx:297-308 (fixed right-4, 56 px, 10 px above the nav island)
- (top 40 #10) [glitch] m-up-contact, m-proj-ready, m-up-ready | 1024 and 390 | dark+light | default | A number is split from its margin: "422.6 / ±0.5 h" (m-up-contact), "12:00 / ±12.0 h" (m-proj-ready), "Jan- / Jan" (m-up-ready, value reads "2026-2027 Jan-Jan"); together at 1440 and 768 | evidence: sheets/m-up-contact.fold.jpg; sheets/m-proj-ready.fold.jpg; sheets/m-up-ready.fold.jpg | src: components/KeyNumbers.tsx:181 (flex-wrap items-baseline gap-x-2); lib/format.ts:233 (Next milestone)
- (top 40 #36) [overload] m-up-ready | 1440 and 390 | dark | default | The 11-row item list repeats "Not entered yet", "Not recorded" and a dash on every row: 33 filler strings | evidence: sheets/m-up-ready.full.jpg | src: components/lifecycle/Readiness.tsx:102; components/lifecycle/ProjectPanels.tsx:473

#### m-up-launch
Before scrolling: 1440 = 14 (2 headings, 3 sentences, 5 key numbers, 4 controls, 0 badges, 0 charts); 390 = 9 (2 headings, 3 sentences, 2 key numbers, 2 controls, 0 badges, 0 charts).

- (top 40 #11) [glitch] m-up-launch | 1440, 1024, 390 | dark | default | One screen gives two dates: headline "the next is 12 November 2026, 07:00 UTC" and "Numbers for the opportunity on 11 November 2026, 07:04 UTC +/-18 min" (capture clock about 22:00 UTC on 11 Nov, so the card date is already past); the headline runs 3-4 lines and names Launch Complex 39A twice | evidence: sheets/m-up-launch.fold.jpg | src: screens/sections/LaunchSection.tsx:179 (next), :185 (opportunity)
- (top 40 #26) [glitch] m-up-launch | 390 | dark | default | The "Launch opportunities by day" chart shows 00:00-12:00 only: the second opportunity column is cut (half pills), rows such as "Wed 9 Dec" look empty, no scroll cue | evidence: sheets/m-up-launch.full.jpg | src: components/lifecycle/LaunchCalendar.tsx:81-82 (min-w-[520px] in a ScrollRegion)
- [glitch] m-up-launch | 390 | dark | default | KPI cards are two across; "Sun height at landing" and "Sunlight after landing" labels wrap to two lines and the Launch time card is half empty; page 3521 px at 1440 holds a 41-row day chart and 9 disclosures | evidence: sheets/m-up-launch.full.jpg | src: screens/sections/LaunchSection.tsx

#### m-up-trip
Before scrolling: 1440 = 7 (4 headings, 3 sentences, 0 key numbers, 0 controls, 0 badges, 0 charts); 390 = 7 (4 headings, 3 sentences, 0 key numbers, 0 controls, 0 badges, 0 charts).

- [glitch] m-up-trip | 1440 and 1024 | dark | default | Orphan: "yet." alone on the second line ("...not worked out / yet."); the closing sentence "Assuming these would still not be enough to work this step out." reads oddly | evidence: sheets/m-up-trip.fold.jpg | src: screens/sections/TripSection.tsx:70

#### m-up-surface
Before scrolling: 1440 = 18 (2 headings, 4 sentences, 6 key numbers, 6 controls, 0 badges, 0 charts); 390 = 12 (2 headings, 4 sentences, 2 key numbers, 4 controls, 0 badges, 0 charts).

- (top 40 #24) [overload] m-up-surface | 1440 | dark | default | The headline sentence repeats three of the four KPI cards under it (152 h / 21%, 423 h / 60%, >=422 h); 18 items on the first screen | evidence: sheets/m-up-surface.fold.jpg | src: screens/MissionDetailScreen.tsx:192 (SurfaceSection)
- (top 40 #37) [glitch] m-up-surface, site | 1440 and 390 | dark | default | "Go further with this spot": two actions are pills and the third ("Printable report") is plain text; on the Site page the three actions under the skyline are styled three ways | evidence: sheets/m-up-surface.full.jpg; sheets/site.full.jpg | src: screens/MissionDetailScreen.tsx:656-682
- [glitch] m-up-surface | 390 | dark+light | default | The Ask button covers the right end of the italic note "For the centre of Mons Mouton, the landing point isn't published."; the KPI cards start below the fold; the "What if..." line is a tiny underlined link that reads as body text | evidence: sheets/m-up-surface.fold.jpg | src: screens/MissionDetailScreen.tsx
- [delight] m-up-surface | all | dark+light | default | Number, unit and margin stay together (">=422 +/-0.8 h", "286 +/-0.5 h"), a bar under each value coloured by meaning | evidence: sheets/m-up-surface.fold.jpg | src: components/KeyNumbers.tsx

#### m-up-contact
Before scrolling: 1440 = 14 (3 headings, 3 sentences, 3 key numbers, 5 controls, 0 badges, 0 charts); 390 = 8 (2 headings, 3 sentences, 1 key numbers, 2 controls, 0 badges, 0 charts).

- (top 40 #10) [glitch] m-up-contact, m-proj-ready, m-up-ready | 1024 and 390 | dark+light | default | A number is split from its margin: "422.6 / ±0.5 h" (m-up-contact), "12:00 / ±12.0 h" (m-proj-ready), "Jan- / Jan" (m-up-ready, value reads "2026-2027 Jan-Jan"); together at 1440 and 768 | evidence: sheets/m-up-contact.fold.jpg; sheets/m-proj-ready.fold.jpg; sheets/m-up-ready.fold.jpg | src: components/KeyNumbers.tsx:181 (flex-wrap items-baseline gap-x-2); lib/format.ts:233 (Next milestone)
- (top 40 #28) [glitch] m-up-contact, m-fl-contact, m-fl-return | all | dark+light | default | The lone dash that stands for an empty value in 34 px numbers ("Through a relay", "Waves/Wind at the booster landing zone") measures 1.87:1 dark and 1.55:1 light; on m-fl-return both KPI cards hold only a dash | evidence: data/cross-cutting.md 3.6; sheets/m-fl-return.fold.jpg | src: components/KeyNumbers.tsx:188 (text-line-strong)
- [glitch] m-up-contact | 390 | dark | default | The "Who can hear the lander" chart draws about 7 passes per station with axis labels at the right edge, where 1440 draws two groups of about 20 (looks cropped to the first days; not confirmed at full size) | evidence: sheets/m-up-contact.full.jpg | src: screens/sections/ContactSection.tsx
- [overload] m-up-contact | 1440 and 390 | dark | default | Two adjacent KPI cards show the same figure ("Longest time without contact 286 h" and "Longest message wait 286 h") and the headline repeats 422.6 and 286; 390 page 2974 px with 10 disclosure rows | evidence: sheets/m-up-contact.fold.jpg | src: lib/format.ts:294

#### m-up-return
Before scrolling: 1440 = 9 (2 headings, 7 sentences, 0 key numbers, 0 controls, 0 badges, 0 charts); 390 = 5 (2 headings, 3 sentences, 0 key numbers, 0 controls, 0 badges, 0 charts).

- (top 40 #9) [overload] m-up-return | 1440, 768, 390 | dark | default | The headline is one sentence of about 85 words in display type: 9 lines at 1440, 8 at 768, 12+ at 390, filling the 390 first screen and pushing the KPI cards below the fold; the date breaks as "(12 / Nov 2026 07:00 UTC)" and at 768 "IM- / 1 on Landing Zone 1" | evidence: sheets/m-up-return.fold.jpg; sheets/D-empty-390.jpg (project-empty.return, same text) | src: backend/app/services/return_service.py:309
- [glitch] m-up-return | 1440 | dark | default | Only two KPI cards (175 px) fill the left half of a four-column row; the Blue Marble globe is cut at top and bottom by its card; "Against the team's limits" shows two full-width grey bars labelled "no limit entered by the team" | evidence: sheets/m-up-return.full.jpg | src: components/lifecycle/LimitBars.tsx:50

#### m-fl
Before scrolling: 1440 = 9 (4 headings, 4 sentences, 0 key numbers, 0 controls, 0 badges, 1 charts); 390 = 2 (2 headings, 0 sentences, 0 key numbers, 0 controls, 0 badges, 0 charts).

- (top 40 #35) [glitch] m-fl | 1440 and 390 | dark | default | The mission record mixes two date styles ("11:30 a.m. CST March 6, 2025" in the sentence, "6 Mar 2025, 17:28:43 UTC" under it); the clamped narrative needs a 32 px "Show more" button | evidence: sheets/m-fl.full.jpg | src: screens/MissionDetailScreen.tsx:321, :329
- [glitch] m-fl (step bar) | 1440 and 1024 | dark | default | Step text under the arc ends at six heights (Ready 3 lines, Launch 4, Trip 3, Surface 4, Contact 4, Return 6; Launch reaches 7 at 1024) | evidence: sheets/m-fl.fold.jpg | src: components/lifecycle/JourneyBar.tsx:452-503

#### m-fl-ready
Before scrolling: 1440 = 18 (3 headings, 6 sentences, 2 key numbers, 7 controls, 0 badges, 0 charts); 390 = 10 (2 headings, 2 sentences, 2 key numbers, 4 controls, 0 badges, 0 charts).

- (top 40 #22) [glitch] m-fl-ready | 1440 and 390 | dark | default | Three of four KPI cards read "0" in display type (Blocked 0, Next milestone 0, Spare parts 0), "Next milestone 0" is a count where the upcoming mission shows a date; 13 identical rows follow (same bar, "Since 27 Feb 2025", "ll.thespacedevs.com", Change) and the 390 page is 4953 px | evidence: sheets/m-fl-ready.fold.jpg; sheets/m-fl-ready.full.jpg | src: lib/format.ts:233; components/lifecycle/Readiness.tsx:197, :229
- [glitch] m-fl-ready (table) | 768 | dark | default | Table fits (688 in 768) but 13 of 18 header cells wrap | evidence: data/cross-cutting.md 3.8 | src: components/lifecycle/Readiness.tsx:276

#### m-fl-launch
Before scrolling: 1440 = 15 (2 headings, 4 sentences, 5 key numbers, 4 controls, 0 badges, 0 charts); 390 = 10 (2 headings, 4 sentences, 2 key numbers, 2 controls, 0 badges, 0 charts).

- (top 40 #23) [overload] m-fl-launch | 1440 | dark | default | The launch time is stated four times on the first screen (headline "27 Feb 2025, 00:16 UTC +/-15 s", "The published liftoff is ... +/-30 s", "Numbers for the launch on 27 February 2025 ...", the Launch time card), in two date styles; at 390 "UTC +/-15 s" starts a new line away from "00:16" | evidence: sheets/m-fl-launch.fold.jpg | src: screens/sections/LaunchSection.tsx:179-185
- [glitch] m-fl-launch | 390 | dark | default | The "The launch (time in UTC)" chart is a 24-hour axis with one pill (00:16) in a 150 px card; the first KPI card is ~220 px tall with ~140 px blank because its neighbour carries a long note | evidence: sheets/m-fl-launch.full.jpg | src: screens/sections/LaunchSection.tsx:195

#### m-fl-trip
Before scrolling: 1440 = 13 (2 headings, 2 sentences, 4 key numbers, 5 controls, 0 badges, 0 charts); 390 = 8 (2 headings, 2 sentences, 2 key numbers, 2 controls, 0 badges, 0 charts).

- (top 40 #27) [glitch] m-fl-trip | 390 | dark | default | Correction markers in "The trip, day by day" collide (": 4 5" jammed into one box) and the x-axis labels are cut to "27 Feb", "Day 2", "Day" at the right edge | evidence: sheets/m-fl-trip.full.jpg | src: screens/sections/TripSection.tsx:128
- [glitch] m-fl-trip | 390 | dark+light | default | Orphan "it": the KPI label "Time a ground station can hear it" wraps with "it" alone on line 3; its KPI cards start at the very bottom of the first screen; two tables fit in 326 px but 6 of 6 and 6 of 7 header cells wrap | evidence: sheets/m-fl-trip.fold.jpg; data/cross-cutting.md 3.8 | src: lib/format.ts:264
- [overload] m-fl-trip | 1440 | dark | default | The headline repeats the 0.75 h and >=0.12 h values shown in the cards under it; the "path to the Moon" card is ~380 px with the drawing in the middle third and a ~9 px caption line 740 px wide | evidence: sheets/m-fl-trip.fold.jpg; sheets/m-fl-trip.full.jpg | src: screens/sections/TripSection.tsx

#### m-fl-surface
Before scrolling: 1440 = 15 (3 headings, 3 sentences, 2 key numbers, 7 controls, 0 badges, 0 charts); 390 = 10 (2 headings, 3 sentences, 1 key numbers, 4 controls, 0 badges, 0 charts).

- [glitch] m-fl-surface, m-fl-contact | 1440 | dark | default | Precision differs on one screen: headline "12.75 hours" against KPI cards "13 h" (surface) and "12.8 h" against the chart title "12.75 hours" (contact) | evidence: sheets/m-fl-surface.fold.jpg; sheets/m-fl-contact.fold.jpg | src: screens/MissionDetailScreen.tsx:192 (SurfaceSection); screens/sections/ContactSection.tsx
- [overload] m-fl-surface | 1440 | dark | default | Four KPI cards carry two distinct values (13 h, 13 h, 0 h, 0 h) that the headline already states | evidence: sheets/m-fl-surface.fold.jpg | src: screens/MissionDetailScreen.tsx:192 (SurfaceSection)

#### m-fl-contact
Before scrolling: 1440 = 14 (3 headings, 2 sentences, 3 key numbers, 5 controls, 0 badges, 1 charts); 390 = 11 (2 headings, 2 sentences, 3 key numbers, 4 controls, 0 badges, 0 charts).

- (top 40 #28) [glitch] m-up-contact, m-fl-contact, m-fl-return | all | dark+light | default | The lone dash that stands for an empty value in 34 px numbers ("Through a relay", "Waves/Wind at the booster landing zone") measures 1.87:1 dark and 1.55:1 light; on m-fl-return both KPI cards hold only a dash | evidence: data/cross-cutting.md 3.6; sheets/m-fl-return.fold.jpg | src: components/KeyNumbers.tsx:188 (text-line-strong)
- [glitch] m-fl-surface, m-fl-contact | 1440 | dark | default | Precision differs on one screen: headline "12.75 hours" against KPI cards "13 h" (surface) and "12.8 h" against the chart title "12.75 hours" (contact) | evidence: sheets/m-fl-surface.fold.jpg; sheets/m-fl-contact.fold.jpg | src: screens/MissionDetailScreen.tsx:192 (SurfaceSection); screens/sections/ContactSection.tsx
- [glitch] m-fl-contact | 390 | dark | default | First KPI label wraps to three lines ("Time a ground / station can hear / the lander"); in the pass chart the station labels take ~55 percent of the row, squeezing the bars to ~110 px | evidence: sheets/m-fl-contact.full.jpg | src: lib/format.ts:264

#### m-fl-return
Before scrolling: 1440 = 8 (2 headings, 4 sentences, 0 key numbers, 2 controls, 0 badges, 0 charts); 390 = 8 (2 headings, 4 sentences, 0 key numbers, 2 controls, 0 badges, 0 charts).

- (top 40 #28) [glitch] m-up-contact, m-fl-contact, m-fl-return | all | dark+light | default | The lone dash that stands for an empty value in 34 px numbers ("Through a relay", "Waves/Wind at the booster landing zone") measures 1.87:1 dark and 1.55:1 light; on m-fl-return both KPI cards hold only a dash | evidence: data/cross-cutting.md 3.6; sheets/m-fl-return.fold.jpg | src: components/KeyNumbers.tsx:188 (text-line-strong)
- [glitch] m-fl-return | 1440, 1024 | dark+light | default | The two biggest boxes ("Waves at the booster landing zone", "Wind at the booster landing zone") hold no number, only a dash and a note; they fill the left half of the row | evidence: sheets/m-fl-return.fold.jpg | src: components/KeyNumbers.tsx:188

#### m-proj
Before scrolling: 1440 = 6 (4 headings, 1 sentences, 0 key numbers, 0 controls, 0 badges, 1 charts); 390 = 2 (2 headings, 0 sentences, 0 key numbers, 0 controls, 0 badges, 0 charts).

- (top 40 #32) [glitch] m-up, m-proj | 1024 | dark+light | default | "Explore a scenario" pills wrap to two lines ("Explore a / scenario"); at 1440 the two pills sit at different heights | evidence: sheets/m-up.fold.jpg; sheets/m-proj.fold.jpg | src: components/lifecycle/JourneyBar.tsx:491-500
- [glitch] m-proj | 1024 | dark+light | default | Coordinate split across lines in the Surface step: "near 89.45 S, 137.3 / W." with the hemisphere letter alone | evidence: sheets/m-proj.fold.jpg | src: screens/MissionDetailScreen.tsx

#### m-proj-ready
Before scrolling: 1440 = 13 (3 headings, 2 sentences, 3 key numbers, 5 controls, 0 badges, 0 charts); 390 = 10 (2 headings, 2 sentences, 2 key numbers, 4 controls, 0 badges, 0 charts).

- (top 40 #5) [bug] m-proj-ready; project-empty.ready | 1440, 1024, 768, 390 | dark | default | React console error "Encountered two children with the same key" logged twice per load (once at 768); the only app console error in the 224 normal captures | evidence: data/A/m-proj-ready.1440.dark.json; data/cross-cutting.md 3.2 | src: not located; not the item rows (the 9 ids from GET /missions/p-aurora-scout-1/ready are unique): check keys in screens/sections/ReadySection.tsx and components/lifecycle/Readiness.tsx
- (top 40 #10) [glitch] m-up-contact, m-proj-ready, m-up-ready | 1024 and 390 | dark+light | default | A number is split from its margin: "422.6 / ±0.5 h" (m-up-contact), "12:00 / ±12.0 h" (m-proj-ready), "Jan- / Jan" (m-up-ready, value reads "2026-2027 Jan-Jan"); together at 1440 and 768 | evidence: sheets/m-up-contact.fold.jpg; sheets/m-proj-ready.fold.jpg; sheets/m-up-ready.fold.jpg | src: components/KeyNumbers.tsx:181 (flex-wrap items-baseline gap-x-2); lib/format.ts:233 (Next milestone)
- [glitch] m-proj-ready | 1440 | dark+light | default | A launch known only to the day shows "14 Mar 2028 UTC 12:00 +/-12.0 h": a clock time that looks precise | evidence: sheets/m-proj-ready.fold.jpg | src: lib/format.ts:233

#### project-new
Before scrolling: 1440 = 14 (4 headings, 7 sentences, 0 key numbers, 3 controls, 0 badges, 0 charts); 390 = 13 (3 headings, 7 sentences, 0 key numbers, 3 controls, 0 badges, 0 charts).

- (top 40 #25) [glitch] project-new, project-edit | 768 and 1440 | dark+light | default | The sticky "Save project / Cancel" bar covers the first form row ("Mission") at 768 and takes the bottom of the first screen at 1440, so the first screen shows a drop zone and a button bar for a form not yet visible (full-page captures draw this bar over the Mission card heading; that part is a capture artefact and is not counted); the intro ends with the orphan "steps." | evidence: sheets/project-new.fold.jpg; sheets/project-edit.fold.jpg | src: screens/ProjectNewScreen.tsx:369 (sticky bar), :271 (intro text)
- [glitch] project-new | 1440 | dark | default | In the "Provider / Lander" and "Spacecraft name / Task order" rows the right-hand box sits a few px lower than the left (helper line under only one of the pair; confirm at full size); page 3930 px at 1440, 5581 px at 390 for 9 cards | evidence: sheets/project-new.full.jpg | src: screens/ProjectNewScreen.tsx

#### project-edit
Before scrolling: 1440 = 14 (4 headings, 7 sentences, 0 key numbers, 3 controls, 0 badges, 0 charts); 390 = 13 (3 headings, 7 sentences, 0 key numbers, 3 controls, 0 badges, 0 charts).

- (top 40 #2) [bug] project-edit | 768 and 390 | dark+light | default | Page scrolls sideways: scrollWidth 791 vs 768 (+23 px) and 433 vs 390 (+43 px); the Launch pad select ("Launch Complex 39A - SpaceX, Eastern Range, Florida") pokes past its card and the viewport; also on long-full.edit at 390 | evidence: sheets/project-edit.full.jpg; data/A/project-edit.390.dark.json; data/cross-cutting.md 3.1 | src: components/project/fields.tsx:111 (div.basis-full around the control); components/project/ProjectForm.tsx:99 (SelectField "Launch pad"); likely cause: the select button has no min-w-0/truncate for its long option text
- (top 40 #25) [glitch] project-new, project-edit | 768 and 1440 | dark+light | default | The sticky "Save project / Cancel" bar covers the first form row ("Mission") at 768 and takes the bottom of the first screen at 1440, so the first screen shows a drop zone and a button bar for a form not yet visible (full-page captures draw this bar over the Mission card heading; that part is a capture artefact and is not counted); the intro ends with the orphan "steps." | evidence: sheets/project-new.fold.jpg; sheets/project-edit.fold.jpg | src: screens/ProjectNewScreen.tsx:369 (sticky bar), :271 (intro text)
- [glitch] project-edit | 1440 | dark | default | Repeats the New-project intro word for word and opens with the drop zone before "The project"; right-hand "Task order" sits ~9 px lower than "Spacecraft name" | evidence: sheets/project-edit.fold.jpg; sheets/project-edit.full.jpg | src: screens/ProjectNewScreen.tsx:271

#### map
Before scrolling: 1440 = 41 (3 headings, 7 sentences, 5 key numbers, 25 controls, 0 badges, 1 charts); 390 = 19 (2 headings, 0 sentences, 1 key numbers, 15 controls, 0 badges, 1 charts).

- (top 40 #21) [overload] map | 1440 and 390 | dark | default | 1440 fold has 41 items (25 controls: tabs, search, filter, 15-row list, scrubber, toggles); at 768 and 390 the map circle takes the whole first screen and pushes the site list and chosen-site card out of it | evidence: sheets/map.fold.jpg; data/fold.md | src: screens/MapScreen.tsx
- [glitch] map | 1440 and 1024 | dark | default | At 1440 the map circle and the list both run past the fold with no hint (list shows 5 of 15 rows); at 1024 the map is a ~140 px slice between list and detail card, the smallest element on the page | evidence: sheets/map.fold.jpg | src: screens/MapScreen.tsx

#### site
Before scrolling: 1440 = 17 (2 headings, 1 sentences, 7 key numbers, 7 controls, 0 badges, 0 charts); 390 = 10 (1 headings, 1 sentences, 3 key numbers, 5 controls, 0 badges, 0 charts).

- (top 40 #37) [glitch] m-up-surface, site | 1440 and 390 | dark | default | "Go further with this spot": two actions are pills and the third ("Printable report") is plain text; on the Site page the three actions under the skyline are styled three ways | evidence: sheets/m-up-surface.full.jpg; sheets/site.full.jpg | src: screens/MissionDetailScreen.tsx:656-682
- [glitch] site | 1440 and 390 | dark | default | The skyline chart has near-vertical cyan segments running off its top-right corner (the Earth path leaves the plot); the clock card ends ~90 px above the right column | evidence: sheets/site.full.jpg | src: scenes/DomeCard.tsx:24
- [overload] site | 1440 | dark | default | The headline repeats 81 percent, 61 percent and 122 hours shown in the four cards under it (17 items) | evidence: sheets/site.fold.jpg | src: screens/TwoClockScreen.tsx:36
- [delight] site | all | dark | default | Numbers keep their margins together at all widths ("122 +/-17.1 h", "278 +/-5.3 h") | evidence: sheets/site.fold.jpg | src: components/KeyNumbers.tsx

#### compare
Before scrolling: 1440 = 44 (4 headings, 11 sentences, 12 key numbers, 14 controls, 3 badges, 0 charts); 390 = 13 (2 headings, 1 sentences, 2 key numbers, 7 controls, 1 badges, 0 charts).

- (top 40 #20) [overload] compare | 1440 | dark | default | Busiest first screen of any route: 44 items (4 headings, 11 sentences, 12 key numbers, 14 controls, 3 badges); "Too close to call" appears on 3 of 3 cards | evidence: sheets/compare.fold.jpg; data/fold.md | src: screens/CompareScreen.tsx:456
- [glitch] compare | 1024 and 1440 | dark | default | Small stat captions wrap unevenly at 1024 ("Without / contact" beside one-line captions); at 1440 the three cards end at different heights; site names inside a body sentence are magenta | evidence: sheets/compare.fold.jpg; sheets/compare.full.jpg | src: screens/CompareScreen.tsx

#### skyline
Before scrolling: 1440 = 11 (3 headings, 3 sentences, 2 key numbers, 2 controls, 0 badges, 1 charts); 390 = 8 (2 headings, 3 sentences, 1 key numbers, 1 controls, 0 badges, 1 charts).

- (top 40 #19) [glitch] skyline | 1440 and 1024 | dark+light | default | First screen is an empty ~1000x700 plot with three cyan Earth-path streaks at the right edge and the Sun path at the bottom edge; the terrain silhouette is below the fold (at 1024 only its top shows); full page: the right card column holds two small cards (~160 px) beside ~700 px of charts, leaving a ~550 px empty column | evidence: sheets/skyline.fold.jpg; sheets/skyline.full.jpg | src: scenes/DomeCard.tsx:24; components/HorizonProfile.tsx:115
- [glitch] skyline | 1440 and 390 | dark | default | The label "FLAT HORIZON 0 deg: what a tool that ignores terrain draws" is drawn over the Sun path and terrain line (1440) and cut at the plot edge (390) | evidence: sheets/skyline.full.jpg | src: components/HorizonProfile.tsx:115

#### plan
Before scrolling: 1440 = 17 (3 headings, 5 sentences, 2 key numbers, 6 controls, 0 badges, 1 charts); 390 = 4 (1 headings, 0 sentences, 1 key numbers, 1 controls, 0 badges, 1 charts).

- (top 40 #12) [glitch] plan | 390 | dark | default | "Every time without contact" is its own scroll frame: table 720 px in a 326 px frame, only # / START / END show, "Day 18, 1 April, 00:43 UTC" is cut mid-string, LENGTH and ALSO DARK? are off-screen with no fade or shadow cue (768: 736 px in 768 also scrolls) | evidence: sheets/plan.full.jpg; data/A/plan.390.dark.json; data/cross-cutting.md 3.8 | src: screens/BlackoutScreen.tsx:184 (ScrollRegion), components/ui.tsx:524
- (top 40 #13) [glitch] plan | 1440, 1024, 768, 390 | dark | default | The "now" marker line runs through the label "<- 38 h, the longest time dark and out of contact"; at 390 the row label "NEITHER: DARK AND OUT OF CONTA..." is cut at the right edge | evidence: sheets/plan.fold.jpg | src: components/BlackoutTimeline.tsx:140
- [glitch] plan | 1440 and 1024 | dark+light | default | Orphan: the card title "What the lander must handle on its own" breaks as "... on its / own"; the left chart card ends ~190 px above the right card | evidence: sheets/plan.fold.jpg; sheets/plan.full.jpg | src: screens/BlackoutScreen.tsx:85

#### report
Before scrolling: 1440 = 14 (2 headings, 1 sentences, 11 key numbers, 0 controls, 0 badges, 0 charts); 390 = 4 (2 headings, 1 sentences, 1 key numbers, 0 controls, 0 badges, 0 charts).

- (top 40 #1) [bug] report | A4 print | light | print (PDF, 2 pages) | The printed Printable report carries the app chrome: header pill, Map/Site/Compare/Plan tabs, the round Ask button over the Assessment sentence ("...latitud" then the button) and the bottom nav island, on both pages; the sunlight bars print as empty frames (PDF made with background graphics off, which is also the browser default) | evidence: shots/B/print.report.light.pdf (pages 1-2); sheets/D-print.jpg (dark PDF not viewed) | src: components/AppShell.tsx:157 (header), :297-308 (Ask button), :314-316 (nav island); screens/ReportScreen.tsx:93-94 and :300 (only two blocks carry print:hidden); no print-color-adjust anywhere in src
- (top 40 #38) [glitch] report | 768 and 390 | dark+light | default | A rank range breaks at its en dash: "Too close to call: could be 1st- / 2nd" inside the Connecting Ridge card; the sheet title wraps to two lines at 390 | evidence: sheets/report.fold.jpg | src: screens/ReportScreen.tsx:184
- [delight] report | all | dark+light | default | On screen the report is a cream paper sheet in both themes with a MEASURED stamp, a page footer and the source line; a document preview | evidence: sheets/report.fold.jpg; sheets/D-print.jpg | src: screens/ReportScreen.tsx

#### notfound
Before scrolling: 1440 = 8 (1 headings, 5 sentences, 0 key numbers, 2 controls, 0 badges, 0 charts); 390 = 8 (1 headings, 5 sentences, 0 key numbers, 2 controls, 0 badges, 0 charts).

- [glitch] notfound | 390 | dark+light | default | Orphan "was." on the last line of the explanation; the footnote sits behind the round Ask button | evidence: sheets/notfound.fold.jpg | src: components/AppShell.tsx:297-308
- [delight] notfound | all | dark+light | default | Says what still works ("Nothing else is affected: every mission and every landing site is where it was") and offers two exits | evidence: sheets/notfound.fold.jpg | src: components/States.tsx:394 (NotFound)

#### State groups and cross-route items

#### guide (tour card)

- (top 40 #15) [glitch] guide (home, site, steps, missions) | 390 | dark | guide open | The Guide card is about 270 px tall (a third of the 844 px screen), stacked above the nav island; it leaves 2-3 lines of Home, Site and step pages above it and the Ask button overlaps its text; at 1440 it is a 380 px bar that covers the lower rows of "Needs you" | evidence: sheets/B-guide.jpg | src: components/GuideBar.tsx:95 (fixed bottom-[calc(5.5rem...)])
- [glitch] guide | 390 | dark | guide open | Two ways to leave ("Skip the tour" and an X); "Back" is shown dimmed on step 1; the tour on Home names test projects in its chips and says "14 steps wait on you" (test data) | evidence: sheets/B-guide.jpg | src: components/GuideBar.tsx:135

#### errors (injected 404 and 500)

- (top 40 #18) [glitch] errors (mission-500, registry-500, plan-500, skyline-500, report-500) | 1440 and 390 | dark | injected 500 | The page collapses to one card (about 300 px at 1440 top-left of a black 900 px page, no heading, no mission or site name; at 390 the card fills the top 220 px of an empty 844 px screen); the address is the only clue which page failed | evidence: sheets/B-errors-1440.jpg; sheets/B-errors-390.jpg | src: components/States.tsx:141-163 (ProblemPanel)
- [delight] errors | 1440 and 390 | dark | injected 404/500 | Every error card says what failed and what still works with a "Try again" (or "Back to missions" on 404s); the mission 404 names the bad id and says other missions are available; step errors keep the journey bar; the Home activity error keeps the page | evidence: sheets/B-errors-1440.jpg; sheets/B-errors-390.jpg | src: components/States.tsx:141-163, :241-247

#### loading (skeletons)

- (top 40 #8) [glitch] loading (every route) | 390 and 1440 | dark | skeleton then content | Skeletons are far shorter than the content: home 390 2447 -> 5440 px (layout shift 0.774), report 390 844 -> 3240 (0.543), project-edit 390 844 -> 5670 (0.185), plan 390 844 -> 2034; mission steps show only gray blocks with no heading | evidence: sheets/B-loading-390.jpg; sheets/B-loading-1440.jpg; data/cross-cutting.md 3.9 | src: per-screen skeletons; no single line

#### working (injected jobs)

- [glitch] working | 390 | dark | injected job | The Ask button sits on the right KPI skeleton card and the nav island covers the next row; all six step words read "Workin..." | evidence: sheets/D-working-390.jpg | src: components/lifecycle/JourneyBar.tsx:113
- [delight] working | 1440 and 390 | dark | injected job 42 percent / queued | The working card has a bar, "42%", a plain sentence and "This page updates itself when the answer is ready. The other steps are unaffected."; queued reads "Waiting its turn to be worked out" with "Waiting for a free worker" and an indeterminate bar; KPI skeletons keep their labels (the sentence "Tracing the Sun along the horizon, 12 of 29 days done" is the capture script's own job text) | evidence: sheets/D-working-1440.jpg; sheets/D-working-390.jpg | src: components/lifecycle/Section.tsx:255

#### project-empty (a project with nothing entered)

- (top 40 #5) [bug] m-proj-ready; project-empty.ready | 1440, 1024, 768, 390 | dark | default | React console error "Encountered two children with the same key" logged twice per load (once at 768); the only app console error in the 224 normal captures | evidence: data/A/m-proj-ready.1440.dark.json; data/cross-cutting.md 3.2 | src: not located; not the item rows (the 9 ids from GET /missions/p-aurora-scout-1/ready are unique): check keys in screens/sections/ReadySection.tsx and components/lifecycle/Readiness.tsx
- (top 40 #40) [glitch] project-empty (ready, launch, trip) | 1440 and 390 | dark | nothing entered | Ready says "9 items are listed ... no states have been entered" but offers no first-action button on the first screen; Launch and Trip say what is missing ("Launch time") and what still works but offer only "Next step", no link to enter it | evidence: sheets/D-empty-1440.jpg; sheets/D-empty-390.jpg | src: screens/sections/LaunchSection.tsx:86; screens/sections/TripSection.tsx:70; screens/sections/ReadySection.tsx:155

#### long names and full projects

- (top 40 #17) [glitch] long names (long-long.*) | 390 | dark | long mission name | The hub title wraps to 12 lines before the step bar (the name in display weight plus the vehicle name); on step pages the breadcrumb is 3 lines but on the hub it is one line cut with an ellipsis; on Home the project name is clipped with an ellipsis at a 405 px box (18 captures) | evidence: sheets/D-long-390.jpg; sheets/D-long-1440.jpg; data/cross-cutting.md 3.4 | src: components/Page.tsx:15-45 (Breadcrumbs); components/home/ProjectCards.tsx:76 (h3.truncate)
- [glitch] long (long-full) | 1440 and 390 | dark | full project | A full project mid-job shows "Working it out" and "Waiting" cards on several steps and a spinner with a count in the header (a job was running during capture); step words read "Workin..." at 390 | evidence: sheets/D-long-1440.jpg; sheets/D-long-390.jpg | src: components/lifecycle/Section.tsx:255
- [delight] long (long-long) | 1440 | dark | long mission name | The 144-character name wraps in full (4 lines on the hub, 3 on steps, 4 on the edit page) and nothing is clipped; the vehicle name wraps in a lighter weight | evidence: sheets/D-long-1440.jpg | src: screens/MissionDetailScreen.tsx

#### filters (missions)

- (top 40 #6) [glitch] every mission step, home, missions, filters | 390 | dark+light | first screen | The round Ask button floats over first-screen text: it hides "UTC" in "The published liftoff is 27 Feb 2025, 00:16 UTC" (m-fl-launch), the right end of Launch step lines, a KPI card in the working state, and on long-name step pages it sits on the "6 Return" step | evidence: shots/C/ask-open.m-fl-launch.390.dark.1-closed.png; sheets/C-ask390.jpg; sheets/D-long-390.jpg; sheets/D-working-390.jpg | src: components/AppShell.tsx:297-308 (fixed right-4, 56 px, 10 px above the nav island)
- (top 40 #16) [glitch] missions (filters, no match) | 390 | dark | no missions match | The empty-state card ("No missions match these filters", "24 missions checked against: provider ZZ Nobody.") and its "Clear filters" button start at about y 390 and sit under the Ask button and nav island at the fold; filter chips take 330 px first; chip row clipped at "Heat flow" with no scroll cue | evidence: sheets/D-filters-390.jpg | src: screens/MissionsScreen.tsx:303
- [delight] missions (filters, no match) | 1440 | dark | no missions match | Says how many were checked and against what ("24 missions checked against: carries any of Laser retroreflector; status Flown; provider ...") and offers "Clear filters" and "Remove Laser retroreflector" | evidence: sheets/D-filters-1440.jpg | src: screens/MissionsScreen.tsx:303

#### offline and unreachable

- (top 40 #7) [glitch] offline (new page while offline) | 1440 and 390 | dark | browser offline, page not opened before | After 4.5 s the page is gray blocks only: 0 headings, 0 sentences, 0 controls in the fold; the offline banner at the top is the only message, nothing says this page cannot load | evidence: sheets/D-offline-1440.jpg; sheets/D-offline-390.jpg; data/B/offline.m-fl-surface.1440.dark.json | src: banner at components/States.tsx:360; skeleton not located
- [glitch] offline | 390 | dark | browser offline | offline.site shows KPI skeletons with a stray unit "h" beside an empty block | evidence: sheets/D-offline-390.jpg | src: screens/TwoClockScreen.tsx:36
- [delight] offline | 1440 and 390 | dark | browser offline, page already opened | A banner says "You are offline. Pages already opened still work; new ones come from the saved copy where it has them."; the page keeps its numbers (unreachable-after and offline.site/home/missions) | evidence: sheets/D-offline-1440.jpg; sheets/D-offline-390.jpg | src: components/States.tsx:360

#### lander tools (power, ellipse, relay)

- (top 40 #39) [overload] tool-power (Power and temperature) | 1440 | dark+light | open | Opening the tool shows 27 input boxes under "Example lander" (each with an ASSUMED tag and a hatched fill behind the figure); the figures read at about 9 px in four columns | evidence: sheets/D-tools-1440.jpg | src: components/surface/EnergyPanel.tsx
- [glitch] tool-ellipse | 390 | dark | empty | The six figures wrap as 2+1 then 2+1: "Long axis bearing from north" breaks over two lines and "Slope limit" sits alone in its row; the result text is about 10 px mono | evidence: sheets/C-ellipse-390.jpg | src: components/surface/DispersionPanel.tsx:85
- [glitch] tool-ellipse | 1440 | dark | working | At 0.5 s after pressing "Work it out" the result is already drawn while the button is greyed and still reads "Work it out" (not "Working it out...") | evidence: shots/C/ellipse.1440.dark.3-working.png | src: components/surface/DispersionPanel.tsx:112
- [glitch] tool-relay (Rovers relaying) | 1440 | dark+light | open | Three nodes with 6-8 prefilled ASSUMED boxes each and a long form before any result; the "computed" micro tag measures 4.45:1 dark and 3.75:1 light (needs 4.5) | evidence: sheets/D-tools-1440.jpg; data/cross-cutting.md 3.6 | src: components/surface/MeshPanel.tsx
- [delight] tool-ellipse (Landing ellipse and slope) | 1440 and 390 | dark+light | empty, filled, result | Six empty boxes marked "needed", a disabled "Work it out" and "6 of 6 figures still to type."; when all six are typed the button enables ("Around Connecting Ridge. Slope does not depend on the dates."); the result (map, 10th/median/90th percentile, tip-over share) arrives in about 1.2-1.4 s and is single-column at 390 | evidence: sheets/C-ellipse-1440.jpg; sheets/C-ellipse-390.jpg | src: components/surface/DispersionPanel.tsx:14-28, :112

#### Ask panel

- [glitch] ask | 390 | dark+light | open | The Ask panel is a full-screen sheet: it covers the whole page, the nav island and the round button (the button is hidden while it is open); Escape closes it and returns focus to the button; closed, the button sits 10 px above the island and over content | evidence: sheets/C-ask390.jpg; data/C/ask-open.m-fl-launch.390.dark.json | src: components/ask/AskDock.tsx:155-157; components/AppShell.tsx:297-308

#### print

- [glitch] print (compare, m-fl, site) | A4 print emulation | light | print media | The print-media screenshots of Compare, a mission page and Site still show the dark app: header pill, tabs, charts, island and Ask button, and none is laid out as a document | evidence: sheets/D-print.jpg | src: components/AppShell.tsx:157, :297-316

#### all routes

- (top 40 #29) [glitch] every page with breadcrumbs | all | dark+light | default | The "/" breadcrumb separator measures 1.75:1 dark and 1.53:1 light (decorative, aria-hidden) | evidence: data/cross-cutting.md 3.6 | src: components/Page.tsx:38 (text-line-strong)

### 3. Cross-cutting tables

Copied from data/cross-cutting.md (generated by scripts/aggregate2.cjs; deduplicated across A and B), plus the tab-order results. The first generation of that file was garbled by a bug in its text clean-up (a regex that replaced every character); it was fixed and regenerated this session.

Totals: 3.1 overflow 3 rows (A 4 of 224 captures, B 1 of 192); 3.2 console 7 classes, 4 unexpected signatures, 4025 aborted requests; 3.3 tap targets 304 instances in 18 groups on 25 routes; 3.4 clipped text 10 groups; 3.5 under fixed layers 22 rows (not reproduced); 3.6 contrast 3 dark and 11 light distinct failing items (534 raw failing samples of 37932; 6 light landing rows dropped); 3.7 dashes 55 strings on 33 pages; 3.8 narrow tables 13 rows; 3.9 skeleton 30 rows.

#### 3.1 Horizontal page overflow

| page | set | width | themes | scrollWidth vs clientWidth | offending element (text) |
| --- | --- | --- | --- | --- | --- |
| project-edit | A | 768 | dark+light | 791 vs 768 (+23px) | rid.gap-x-5.gap-y-5 > div.flex.flex-wrap.items-center > div.basis-full "Launch Complex 39A · SpaceX, Eastern Range, Florid" |
| project-edit | A | 390 | dark+light | 433 vs 390 (+43px) | rid.gap-x-5.gap-y-5 > div.flex.flex-wrap.items-center > div.basis-full "Launch Complex 39A · SpaceX, Eastern Range, Florid" |
| long-full.edit | B | 390 | dark | 433 vs 390 (+43px) | rid.gap-x-5.gap-y-5 > div.flex.flex-wrap.items-center > div.basis-full "Launch Complex 39A · SpaceX, Eastern Range, Florid" |

Captures with horizontal page overflow: A 4 of 224; B 1 of 192 that carry the measurement. Rows above: 3.

#### 3.2 Console errors, page errors and failed requests

| class | message / request | distinct signatures | captures | pages |
| --- | --- | --- | --- | --- |
| test setup: tile images blocked (app on 127.0.0.1, API host localhost) | error: Access to image at '<tile url>' from origin 'http:/ | 1 | 15 | long-full.hub, long-long.hub, project-empty.hub, reduced-os-reduce.m-fl, reduced-pref-reduced.m-fl, zoom200.m-fl |
| test setup: tile images blocked (app on 127.0.0.1, API host localhost) | error: Failed to load resource: net::ERR_FAILED | 1 | 15 | long-full.hub, long-long.hub, project-empty.hub, reduced-os-reduce.m-fl, reduced-pref-reduced.m-fl, zoom200.m-fl |
| test setup: tile images blocked (app on 127.0.0.1, API host localhost) | request failed net::ERR_FAILED: /api/v1/tiles/hillshade/z/x/y.png | 1 | 15 | long-full.hub, long-long.hub, project-empty.hub, reduced-os-reduce.m-fl, reduced-pref-reduced.m-fl, zoom200.m-fl |
| APP BUG: React duplicate-key warning | error: Encountered two children with the same key, `%s`. Keys should be unique so that components main | 1 | 10 | m-proj-ready, project-empty.ready |
| headless GPU note (not an app fault) | warning: [WebGL]GL Driver Message (OpenGL, Performance, GL_CLOSE_PATH_NV, High): GPU sta | 1 | 6 | landing, guide.site, loading-page.m-fl |
| injected: server answered 404 or 500 on purpose | (many, see per-scenario logs in data/B) | 64 | 36 | error.compare-500, error.home-activity-500, error.map-500, error.mission-404, error.mission-500, error.missions-500 (+10) |
| injected: API stopped or offline on purpose | (many, see per-scenario logs in data/B) | 21 | 14 | unreachable-after.m-fl-surface, unreachable-after.missions, unreachable-after.site, unreachable-first.home, unreachable-first.m-fl-surface, unreachable-first.missions (+1) |

Aborted requests (net::ERR_ABORTED, cancelled by navigation or by map tiles leaving view; not faults): 4025 across all captures. In the 224 normal captures (A) the only console error is the duplicate-key warning on m-proj-ready; the only warnings are the landing page GPU notes.

#### 3.3 Tap targets under 44 px at 390 wide

| pages | element | text | size (w x h px) | where |
| --- | --- | --- | --- | --- |
| 20 | a | Missions / Griffin Mission One (+5 more) | 61x32, 120x32 | m-up, m-up-ready, m-up-launch, m-up-trip (+16) |
| 11 | a | TO20A Science Payloads (page updated Aug 19, 2026) / NASA Provides Updates on Moon Base Cargo Landers, (+29 more) | 326x40, 326x20 | m-up, m-up-ready, m-up-launch, m-up-contact (+7) |
| 3 | a | IAU / USGS Astrogeology, source for the coordinate / LROC / Arizona State University, source for the co (+1 more) | 159x15, 197x15 | m-up, m-fl, m-proj |
| 2 | a | NASA, source for LRA / NASA, source for TRIDENT (+1 more) | 36x14 | m-up, m-fl |
| 2 | a (inside a sentence) | nasa.gov | 49x14 | m-up-launch, m-fl-launch |
| 2 | summary | NOAA’s forecast as issued | 326x19.5 | m-up-launch, m-fl-launch |
| 2 | a (inside a sentence) | record | 37x14 | m-up-launch, m-fl-launch |
| 2 | a | naif.jpl.nasa.gov: src_230924_230924_230930_od383a | 320x34 | m-up-return, m-fl-return |
| 2 | input | Search by name or place | 256x21 | project-new, project-edit |
| 1 | a | Evidence for Export control review (ITAR / EAR): l / Evidence for FAA launch licence (14 CFR Part 450), (+11 more) | 326x19.5 | m-fl-ready |
| 1 | a (inside a sentence) | JPL Horizons trajectory (LRO_merged) / JPL Horizons trajectory (KPLO_merged) (+2 more) | 223x14, 231x14 | m-fl-contact |
| 1 | a (inside a sentence) | ESO/S. Brunier | 82x14 | landing |
| 1 | a | Map | 24x18 | missions |
| 1 | button | Show more | 67x32 | m-fl |
| 1 | summary | How each was worked out | 326x19.5 | m-fl-trip |
| 1 | input | Site, crater or lat, lon | 296x21 | map |
| 1 | a | See it on the skyline → | 133x19.5 | site |
| 1 | button | Too close to call | 114x32 | compare |

Totals at 390: 304 small-target instances over both themes, 18 distinct selector groups, 14 not inside a sentence, on 25 of 28 routes. Targets are counted when a link or control is shorter than 44 px in either direction; links inside running text are labelled.

#### 3.4 Clipped or truncated text

| kind | text | box w px | selector | captures | first captures |
| --- | --- | --- | --- | --- | --- |
| ellipsis | "Needs input" | 49 | ex > span.flex.flex-col.gap-0.5 > span.flex.items-center.gap-1.5 > span.truncate | 25 | m-up-ready@390, m-up-launch@390, m-up-trip@390, m-up-surface@390 ... |
| ellipsis | "No data yet" | 49 | ex > span.flex.flex-col.gap-0.5 > span.flex.items-center.gap-1.5 > span.truncate | 25 | m-up-ready@390, m-up-launch@390, m-up-trip@390, m-up-surface@390 ... |
| ellipsis | "ZZ audit Extremely Long Mission Name for the Lunar South Pol" | 405 | rd-link.relative > div.flex.flex-col.gap-1 > h3.pw-display.truncate.text-subhead | 18 | home@1440, home@1024, home@768, home@390 ... |
| text-partly-hidden | "ZZ audit Extremely Long Mission Name for the Lunar South Pol" |  | 3.pw-display.truncate.text-subhead > a.no-underline.after:absolute.after:inset-0 | 17 | home@1440, home@1024, home@768, home@390 ... |
| line-clamp | "Touched down at Mons Mouton at about 11:30 a.m. CST March 6," | 568 | flex.flex-col > div.flex.flex-col.items-start > p.text-lede.leading-7.text-ink-2 | 15 | m-fl@1440, m-fl@1024, m-fl@768, m-fl@390 ... |
| ellipsis | "Working it out" | 49 | ex > span.flex.flex-col.gap-0.5 > span.flex.items-center.gap-1.5 > span.truncate | 12 | long-full.contact.390@390, long-full.launch.390@390, long-full.ready.390@390, long-full.return.390@390 ... |
| text-partly-hidden | "yes, part of it is dark too" |  | rder-line.bg-alert-wash > td.px-4.py-3.text-small > span.flex.items-center.gap-2 | 1 | plan@1024 |
| text-partly-hidden | "Day 18, 1 April, 00:43 UTC" |  | t-left > tbody > tr.border-t.border-line.bg-alert-wash > td.px-4.py-3.text-small | 1 | plan@390 |
| ellipsis | "How much sunlight and contact with Earth does it get on the " | 324 |  > div.pw-dock.is-docked > div.pw-island.mx-auto.flex > span.pw-eyebrow.truncate | 1 | long-long.surface.390@390 |
| line-clamp | "Over these 12 days the Sun is up 49% of the time and Earth i" | 324 | k.is-docked > div.pw-island.mx-auto.flex > span.line-clamp-2.text-body.leading-5 | 1 | long-long.surface.390@390 |

#### 3.5 Content under fixed layers when scrolled to the bottom (768 and 390)

| page | width | themes | last text under a layer | last link/button under a layer | layer (box overlaps text) |
| --- | --- | --- | --- | --- | --- |
| missions | 768 | dark+light | "2024" ; "2025" ; "2026" |  | nav.pw-island.fixed.bottom-[calc(0.75rem |
| missions | 390 | dark+light | "2024" ; "2025" |  | nav.pw-island.fixed.bottom-[calc(0.75rem |
| m-up-launch | 768 | dark+light | "What the Sun is doing now, as NOAA SWPC " ; "The limit is not published; the team can" |  | nav.pw-island.fixed.bottom-[calc(0.75rem |
| m-up-launch | 390 | dark+light | "10 November 2026, 02:00 UTC, 803 km/s; n" ; "·" |  | nav.pw-island.fixed.bottom-[calc(0.75rem |
| m-up-return | 768 | dark+light | "src_230924_230924_230930_od383a_v1.bsp" ; "Where the entry state and the landing ar" | naif.jpl.nasa.gov: src_230924_230924_230 | nav.pw-island.fixed.bottom-[calc(0.75rem |
| m-up-return | 390 | dark+light | "NRLMSIS 2.1, the U.S. Naval Research Lab" |  | button.pw-press.fixed.right-4 ; nav.pw-island.fixed.bottom-[calc(0.75rem |
| m-fl-launch | 390 | dark+light | "Lightning seen from space (GOES lightnin" |  | nav.pw-island.fixed.bottom-[calc(0.75rem |
| m-fl-trip | 390 | dark+light | "1.7 × 10¹⁰" ; "7.9 × 10⁹" ; "August 1972" |  | nav.pw-island.fixed.bottom-[calc(0.75rem |
| m-fl-return | 768 | dark+light | "src_230924_230924_230930_od383a_v1.bsp" ; "Where the entry state and the landing ar" | naif.jpl.nasa.gov: src_230924_230924_230 | nav.pw-island.fixed.bottom-[calc(0.75rem |
| m-fl-return | 390 | dark+light | "NRLMSIS 2.1, the U.S. Naval Research Lab" |  | button.pw-press.fixed.right-4 ; nav.pw-island.fixed.bottom-[calc(0.75rem |
| project-new | 390 | dark+light | "The downlink budget on the Contact step " ; "entered" ; "." |  | button.pw-press.fixed.right-4 ; nav.pw-island.fixed.bottom-[calc(0.75rem |
| filters.all-filters-on.390 | 390 | dark | "✓ completed · ◐ partly successful · ✕ fa" |  | button.pw-press.fixed.right-4 |
| filters.flown.390 | 390 | dark | "✓ completed · ◐ partly successful · ✕ fa" |  | button.pw-press.fixed.right-4 |
| filters.upcoming-flown-type.390 | 390 | dark | "known only to the month, quarter or year" ; "date known to the day" ; "2024" |  | nav.pw-island.fixed.bottom-[calc(0.75rem |
| filters.upcoming.390 | 390 | dark | "2024" ; "2025" |  | nav.pw-island.fixed.bottom-[calc(0.75rem |
| guide.missions.390 | 390 | dark | "Not on the timeline, because no landing " ; "✓ completed · ◐ partly successful · ✕ fa" |  | nav.pw-island.fixed.bottom-[calc(0.75rem ; div.pw-card.pw-card-raised.fixed |
| long-full.hub.390 | 390 | dark+light | "Purpose" |  | nav.pw-island.fixed.bottom-[calc(0.75rem |
| long-full.return.390 | 390 | dark | "NRLMSIS 2.1, the U.S. Naval Research Lab" |  | button.pw-press.fixed.right-4 ; nav.pw-island.fixed.bottom-[calc(0.75rem |
| long-lists.missions.390 | 390 | dark | "ZZ audit International Aerospace and Lun" ; "ZZ audit Extremely Long Mission Name for" ; "Blue Origin" |  | nav.pw-island.fixed.bottom-[calc(0.75rem |
| project-empty.return.390 | 390 | dark | "NRLMSIS 2.1, the U.S. Naval Research Lab" |  | button.pw-press.fixed.right-4 ; nav.pw-island.fixed.bottom-[calc(0.75rem |
| unreachable-first.missions.390 | 390 | dark | "2024" ; "2025" |  | nav.pw-island.fixed.bottom-[calc(0.75rem |
| zoom200.missions.720x450 | 720 | dark | "ZZ audit International Aerospace and Lun" ; "ZZ audit Extremely Long Mission Name for" |  | nav.pw-island.fixed.bottom-[calc(0.75rem |

Rows: 22. Only text whose box sits inside the viewport at the bottom of the page and overlaps a fixed layer with its own background is listed. NOT REPRODUCED: spot checks at the real page bottom (sheets/C-bottom390.jpg) show the footnote 100 px or more clear of the nav island and the Ask button; treat this table as measured but not as a finding.

#### 3.6 Text contrast failures (worst 15 per theme, deduplicated)

**dark theme** - 3 distinct failing items.

| ratio | needs | text | selector | colour on backdrop | pages |
| --- | --- | --- | --- | --- | --- |
| 1.75 | 4.5 | "/" | ap.items-center > li.flex.items-center.gap-1.5 > span.text-line-strong | rgb(57,58,60) on rgb(7,9,11) | 63: m-up, m-up-ready, m-up-launch |
| 1.87 | 3 | "-" | flex-wrap.items-baseline > span.pw-figure.text-line-strong.text-[34px] | rgb(65,69,73) on rgb(17,22,27) | 7: m-up-contact, m-fl-contact, m-fl-return |
| 4.45 | 4.5 | "computed" |  div.flex.flex-col.gap-1 > dd > span.inline-block.font-mono.text-micro | rgb(116,127,137) on rgb(17,22,27) | 2: tool-relay.1440, tool-relay.390 |

**light theme** - 11 distinct failing items (the six landing rows at 1.06 and 2.22 are false positives: the text is on the dark space picture).

| ratio | needs | text | selector | colour on backdrop | pages |
| --- | --- | --- | --- | --- | --- |
| 1.06 | 3 | "Plan a landing where the Sun barely rise" | 4 > div.flex.flex-col.gap-7 > h1.pw-display.text-[40px].leading-[1.02] | rgb(230,235,240) on rgb(243,241,236) | 1: landing |
| 1.06 | 3 | "22" |  > div.flex.flex-col-reverse > dd.pw-figure.text-[34px].leading-[38px] | rgb(230,235,240) on rgb(243,241,236) | 1: landing |
| 1.06 | 3 | "15" |  > div.flex.flex-col-reverse > dd.pw-figure.text-[34px].leading-[38px] | rgb(230,235,240) on rgb(243,241,236) | 1: landing |
| 1.53 | 4.5 | "/" | ap.items-center > li.flex.items-center.gap-1.5 > span.text-line-strong | rgb(195,198,198) on rgb(243,241,236) | 26: m-up, m-up-ready, m-up-launch |
| 1.55 | 3 | "-" | flex-wrap.items-baseline > span.pw-figure.text-line-strong.text-[34px] | rgb(204,208,212) on rgb(255,255,255) | 3: m-up-contact, m-fl-contact, m-fl-return |
| 2.22 | 4.5 | "NASA CLPS missions · the Moon’s south po" | lex.flex-col.px-4 > div.flex.flex-col.gap-7 > p.pw-eyebrow.!text-ink-2 | rgb(154,165,177) on rgb(243,241,236) | 1: landing |
| 2.22 | 4.5 | "For every NASA CLPS mission and a set of" | col.px-4 > div.flex.flex-col.gap-7 > p.text-large.leading-8.text-ink-2 | rgb(154,165,177) on rgb(243,241,236) | 1: landing |
| 2.22 | 4.5 | "CLPS missions" | -10 > div.flex.flex-col-reverse > dt.text-small.font-medium.text-ink-2 | rgb(154,165,177) on rgb(243,241,236) | 1: landing |
| 2.22 | 4.5 | "candidate landing sites" | -10 > div.flex.flex-col-reverse > dt.text-small.font-medium.text-ink-2 | rgb(154,165,177) on rgb(243,241,236) | 1: landing |
| 2.22 | 4.5 | "No account needed: the button signs you " | > div.flex.flex-col.gap-7 > p.text-caption.leading-caption.font-medium | rgb(154,165,177) on rgb(243,241,236) | 1: landing |
| 3.75 | 4.5 | "computed" |  div.flex.flex-col.gap-1 > dd > span.inline-block.font-mono.text-micro | rgb(126,133,141) on rgb(255,255,255) | 1: tool-relay.1440 |

Text samples measured across all captures: 37932; samples whose backdrop could not be resolved (image, gradient, canvas) and were skipped: 5280; raw failing samples before deduplication: 534.

#### 3.7 Visible em or en dashes in page text

| page | char | where | string ([EM] = em dash, [EN] = en dash) | captures |
| --- | --- | --- | --- | --- |
| m-up-ready | em dash | visible text | "[EM]" | 66 |
| m-up-launch | em dash | visible text | "[EM]" | 16 |
| m-up-contact | em dash | visible text | "[EM]" | 8 |
| m-fl-launch | em dash | visible text | "[EM]" | 24 |
| m-fl-contact | em dash | visible text | "[EM]" | 8 |
| m-fl-return | em dash | visible text | "[EM]" | 16 |
| m-proj-ready | em dash | visible text | "[EM]" | 54 |
| ask | em dash | visible text | "[EM]" | 6 |
| error.mission-404 | em dash | title | "Polar Window [EM] landing site planning for the Moon's south pole" | 2 |
| error.mission-500 | em dash | title | "Polar Window [EM] landing site planning for the Moon's south pole" | 4 |
| long-full.ready | em dash | visible text | "[EM]" | 18 |
| long-full.return | em dash | visible text | "[EM]" | 6 |
| long-long.contact | em dash | visible text | "[EM]" | 2 |
| long-long.ready | em dash | visible text | "[EM]" | 9 |
| project-empty.contact | em dash | visible text | "[EM]" | 2 |
| project-empty.ready | em dash | visible text | "[EM]" | 9 |
| project-empty.return | em dash | visible text | "[EM]" | 4 |
| m-up-ready | en dash | visible text | "2026[EN]2027" | 8 |
| m-up-ready | en dash | visible text | "Jan[EN]Jan" | 8 |
| m-up-launch | en dash | visible text | "Magnetic field from the Sun, north[EN]south (Bz)" | 8 |
| m-fl-launch | en dash | visible text | "Magnetic field from the Sun, north[EN]south (Bz)" | 8 |
| m-fl-trip | en dash | visible text | "1[EN]7" | 8 |
| m-fl-trip | en dash | visible text | "(80[EN]94.7 m/s, allowing for the number of ru" | 8 |
| m-fl-trip | en dash | visible text | ", and 99.7[EN]104 km in 98 of 100" | 8 |
| m-fl-surface | en dash | visible text | "6 March 2025, 17:28 UTC [EN] 7 March 2025, 06:15 UTC, as flown" | 8 |
| compare | en dash | visible text | "g Ridge can't be ranked; it could be 1st[EN]2nd: about 122 hours. Mala" | 8 |
| compare | en dash | visible text | "[EN]" | 24 |
| report | en dash | visible text | "[EN]" | 24 |
| report | en dash | visible text | "Too close to call: could be 1st[EN]2nd" | 8 |
| report | en dash | visible text | "Too close to call: could be 2nd[EN]3rd" | 8 |
| report | en dash | visible text | "Too close to call: could be 1st[EN]3rd" | 8 |
| report | en dash | attr:title | "could be 1st[EN]2nd" | 8 |
| report | en dash | attr:title | "could be 2nd[EN]3rd" | 8 |
| report | en dash | attr:title | "could be 1st[EN]3rd" | 8 |
| ask | en dash | visible text | "Magnetic field from the Sun, north[EN]south (Bz)" | 2 |
| error.compare-500 | en dash | visible text | "[EN]" | 6 |
| guide.m-fl-surface | en dash | visible text | "6 March 2025, 17:28 UTC [EN] 7 March 2025, 06:15 UTC, as flown" | 2 |
| long-full.surface | en dash | visible text | "17 June 2029, 14:30 UTC [EN] 2 July 2029, as flown" | 2 |
| long-long.surface | en dash | visible text | "21 February 2029 [EN] 5 March 2029, planned" | 2 |
| print.report | en dash | visible text | "[EN]" | 6 |
| print.report | en dash | visible text | "Too close to call: could be 1st[EN]2nd" | 2 |
| print.report | en dash | visible text | "Too close to call: could be 2nd[EN]3rd" | 2 |
| print.report | en dash | visible text | "Too close to call: could be 1st[EN]3rd" | 2 |
| print.report | en dash | attr:title | "could be 1st[EN]2nd" | 2 |
| print.report | en dash | attr:title | "could be 2nd[EN]3rd" | 2 |
| print.report | en dash | attr:title | "could be 1st[EN]3rd" | 2 |
| project-empty.surface | en dash | visible text | "21 March 2028 [EN] 31 March 2028, planned" | 2 |
| tool-power | en dash | visible text | "0[EN]1" | 30 |
| unreachable-after.m-fl-surface | en dash | visible text | "6 March 2025, 17:28 UTC [EN] 7 March 2025, 06:15 UTC, as flown" | 2 |
| unreachable-first.m-fl-surface | en dash | visible text | "6 March 2025, 17:28 UTC [EN] 7 March 2025, 06:15 UTC, as flown" | 2 |
| zoom200.compare | en dash | visible text | "g Ridge can't be ranked; it could be 1st[EN]2nd: about 122 hours. Mala" | 1 |
| zoom200.compare | en dash | visible text | "[EN]" | 3 |
| zoom200.m-fl-surface | en dash | visible text | "6 March 2025, 17:28 UTC [EN] 7 March 2025, 06:15 UTC, as flown" | 1 |
| zoom200.m-up-ready | en dash | visible text | "2026[EN]2027" | 1 |
| zoom200.m-up-ready | en dash | visible text | "Jan[EN]Jan" | 1 |

Totals: 55 distinct strings on 33 pages; 17 em-dash strings, 38 en-dash strings. A lone em dash is the empty-value placeholder; the en dashes are ranges.

#### 3.8 Tables at 390 and 768 wide

| page | width | mode | table px in viewport px | header cols | headers wrapping | headers broken mid-word | table |
| --- | --- | --- | --- | --- | --- | --- | --- |
| m-up | 768 | own-scroll | 696 in 768 | 6 | 1 | 0 | ow-x-auto > table.w-full.border-collapse.text-left |
| m-up-ready | 768 | fits | 688 in 768 | 16 | 11 | 0 | iv.hidden > table.w-full.border-collapse.text-left |
| m-up-launch | 768 | own-scroll | 860 in 768 | 15 | 15 | 0 | to.border > table.w-full.border-collapse.text-left |
| m-fl | 768 | own-scroll | 696 in 768 | 8 | 3 | 0 | ow-x-auto > table.w-full.border-collapse.text-left |
| m-fl-ready | 768 | fits | 688 in 768 | 18 | 13 | 0 | iv.hidden > table.w-full.border-collapse.text-left |
| m-fl-launch | 768 | own-scroll | 860 in 768 | 17 | 17 | 0 | to.border > table.w-full.border-collapse.text-left |
| m-fl-trip | 768 | fits | 696 in 768 | 6 | 6 | 0 | -col.gap-1.5 > table.w-full.border-collapse.border |
| m-fl-trip | 768 | fits | 696 in 768 | 7 | 3 | 0 | lex.flex-col > table.w-full.border-collapse.border |
| m-fl-trip | 390 | fits | 326 in 390 | 6 | 6 | 0 | -col.gap-1.5 > table.w-full.border-collapse.border |
| m-fl-trip | 390 | fits | 326 in 390 | 7 | 6 | 0 | lex.flex-col > table.w-full.border-collapse.border |
| m-proj-ready | 768 | fits | 688 in 768 | 14 | 9 | 0 | iv.hidden > table.w-full.border-collapse.text-left |
| plan | 768 | own-scroll | 736 in 768 | 5 | 0 | 0 | ow-x-auto > table.w-full.border-collapse.text-left |
| plan | 390 | own-scroll | 720 in 390 | 5 | 0 | 0 | ow-x-auto > table.w-full.border-collapse.text-left |

#### 3.9 Skeleton size against loaded size (loading-page captures)

| capture | skeleton page height px | loaded page height px | growth px | skeleton blocks | layout shift when content arrives |
| --- | --- | --- | --- | --- | --- |
| loading-page.compare.1440 | 900 | 1352 | 452 | 0 | 0.036 |
| loading-page.compare.390 | 916 | 2778 | 1862 | 0 | 0.165 |
| loading-page.home.1440 | 1489 | 2685 | 1196 | 4 | 0.293 |
| loading-page.home.390 | 2447 | 5440 | 2993 | 4 | 0.774 |
| loading-page.m-fl-contact.1440 | 957 | 2443 | 1486 | 12 | 0.008 |
| loading-page.m-fl-contact.390 | 1277 | 3189 | 1912 | 12 | 0.000 |
| loading-page.m-fl-surface.1440 | 900 | 2217 | 1317 | 4 | 0.150 |
| loading-page.m-fl-surface.390 | 1331 | 3054 | 1723 | 12 | 0.097 |
| loading-page.m-fl.1440 | 927 | 1558 | 631 | 11 | 0.087 |
| loading-page.m-fl.390 | 1597 | 3032 | 1435 | 11 | 0.000 |
| loading-page.m-up-launch.1440 | 1011 | 3521 | 2510 | 12 | 0.044 |
| loading-page.m-up-launch.390 | 1277 | 4229 | 2952 | 12 | 0.000 |
| loading-page.m-up-trip.1440 | 1011 | 1000 | -11 | 12 | 0.086 |
| loading-page.m-up-trip.390 | 1277 | 1410 | 133 | 12 | 0.051 |
| loading-page.map.1440 | 1383 | 1383 | 0 | 0 | 0.010 |
| loading-page.map.390 | 2816 | 3142 | 326 | 0 | 0.000 |
| loading-page.missions.1440 | 1284 | 1311 | 27 | 0 | 0.034 |
| loading-page.missions.390 | 1722 | 4581 | 2859 | 0 | 0.181 |
| loading-page.plan.1440 | 900 | 1264 | 364 | 0 | 0.029 |
| loading-page.plan.390 | 844 | 2034 | 1190 | 0 | 0.165 |
| loading-page.project-edit.1440 | 900 | 4036 | 3136 | 2 | 0.116 |
| loading-page.project-edit.390 | 844 | 5670 | 4826 | 2 | 0.185 |
| loading-page.project-new.1440 | 3739 | 3930 | 191 | 0 | 0.001 |
| loading-page.project-new.390 | 5087 | 5581 | 494 | 0 | 0.020 |
| loading-page.report.1440 | 900 | 1762 | 862 | 0 | 0.200 |
| loading-page.report.390 | 844 | 3240 | 2396 | 0 | 0.543 |
| loading-page.site.1440 | 1631 | 2265 | 634 | 6 | 0.061 |
| loading-page.site.390 | 2109 | 3006 | 897 | 6 | 0.039 |
| loading-page.skyline.1440 | 900 | 1891 | 991 | 0 | 0.110 |
| loading-page.skyline.390 | 844 | 2157 | 1313 | 0 | 0.174 |


#### 3.10 Tab order: the first 25 stops (home, site, a flown mission's Surface step, compare, an upcoming mission's Ready step)

| config | page | stops | no visible focus style | focus traps | stops with no outline (ring on wrapper) | lowest outline contrast | clickable but not tab-reachable |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1440 dark | home | 25 | 0 | 0 | 9: Ask about a mission, a s | 12.98 | 0 |
| 1440 dark | site | 25 | 0 | 0 | none | 12.98 | 20 (month tiles of the date strip, roving tabindex: not a defect) |
| 1440 dark | m-fl-surface | 25 | 0 | 0 | none | 12.98 | 20 (month tiles of the date strip, roving tabindex: not a defect) |
| 1440 dark | compare | 25 | 0 | 0 | none | 12.98 | 0 |
| 1440 dark | m-up-ready | 25 | 0 | 0 | none | 12.98 | 0 |
| 1440 light | home | 25 | 0 | 0 | 9: Ask about a mission, a s | 6.39 | 0 |
| 1440 light | site | 25 | 0 | 0 | none | 5.73 | 20 (month tiles of the date strip, roving tabindex: not a defect) |
| 1440 light | m-fl-surface | 25 | 0 | 0 | none | 6.39 | 20 (month tiles of the date strip, roving tabindex: not a defect) |
| 1440 light | compare | 25 | 0 | 0 | none | 5.73 | 0 |
| 1440 light | m-up-ready | 25 | 0 | 0 | none | 6.39 | 0 |
| 390 dark | home | 25 | 0 | 0 | 5: Ask about a mission, a s | 12.98 | 0 |
| 390 dark | site | 25 | 0 | 0 | none | 12.98 | 20 (month tiles of the date strip, roving tabindex: not a defect) |
| 390 dark | m-fl-surface | 25 | 0 | 0 | none | 12.98 | 20 (month tiles of the date strip, roving tabindex: not a defect) |
| 390 dark | compare | 25 | 0 | 0 | none | 12.98 | 0 |
| 390 dark | m-up-ready | 25 | 0 | 0 | none | 12.98 | 0 |

Totals: 375 stops tabbed in 15 runs; stops with no visible focus style: 0; focus traps: 0. Every stop gets a 2 px solid outline (lowest outline contrast against its backdrop: 12.98 in dark, 5.73 in light) except the Ask text field on Home, whose focus ring is on its wrapper (ring changes, checked). The skip link is the first stop on every page. Eight stops (skip link, logo, Home, Missions, Sites, Ask, Activity, Guide and settings) come before page content, and on Site and Compare four more (Map, Site, Compare, Plan) before the page's own controls. On Home at 1440 stops 15 to 25 are eleven "Fill it in" or "Explore a scenario" links named after test projects, so 11 of the first 25 stops are repeated project actions (test data). At 390 the header is shorter (stop 5 is already the Ask field).

Not tab-reachable: nothing measured except the date-strip month tiles (11 of 12 have tabindex -1 by design, one is the Tab stop and the rest take arrow keys; components/WindowPicker.tsx:250). Controls whose focus style could not be shown: none. Screenshots of any stop lacking a style would be in shots/focus; none were needed.

### 4. Test data that exists

Listed through the API on 2026-11-12 (`POST /api/v1/auth/demo` with `{"name":"Review"}`, then `GET /api/v1/projects`). Nothing was deleted or added in this session. `GET /api/v1/missions` answers total 25 (20 catalogue entries plus these 5 projects).

| id | name | entered by | launch |
| --- | --- | --- | --- |
| p-zz-flow-project-g | ZZ flow project g | ZZ flow audit | none |
| p-zz-audit-full-fields | ZZ audit Full Fields | Review | 2029-06-10T08:15:00Z |
| p-zz-audit-extremely-long-mission-name-for-the-lunar-south | ZZ audit Extremely Long Mission Name for the Lunar South Pol... (144 characters) | Review | 2029-02-14 |
| p-zz-flow-project | ZZ flow project | ZZ flow audit | none |
| p-aurora-scout-1 | Aurora Scout 1 (seeded, not test data) | Test Manager | 2028-03-14 |

- "ZZ audit Extremely Long Mission Name ..." and "ZZ audit Full Fields" were created by scripts/createProjects.cjs (ids in data/test-projects.json). "ZZ flow project" and "ZZ flow project g" (entered by "ZZ flow audit") were created by another worker's flow test and are not from this audit's scripts.
- Effects on the app that showed up in captures: the Missions and landing counts (21, 22, 24, now 25), "steps wait on you" on Home (2, 8, 14), the home question chips ("What does ZZ audit Full Fields still need?"), and background jobs for the full project (spinner counts in the header on long-full captures).
- Demo sessions named "Review" and "ZZ flow audit" exist; each capture signs in again with POST /api/v1/auth/demo.


---

# Part 2: Journeys


Sources: `walk-1440.txt`, `walk-390.txt`, `labels.txt`, `journey-b.txt`, `journey-e.txt` (earlier worker), `journey-a.txt` (first pass, stopped at the report step). Second pass, 12 Nov 05:00 UTC, both servers up: `verify-r1-r2.txt`, `verify-best.txt`, `verify-best2.txt`, `journey-a2.txt` (carry-over), `journey-c.txt` (compare), `journey-d.txt` (what-if), `journey-f.txt` (report), `journey-g.txt` (project form and browser Back). Screenshots in `shots/`.

Test data: demo sessions named `ZZ flow audit` (lib.cjs `session()`, one per script run); project `ZZ flow project` (earlier worker); project `ZZ flow project g` (id `p-zz-flow-project-g`, created by `journey-g-project.cjs` in this pass; its Provider edit was never saved). Nothing else was created or changed; the global parameter `battery_limit_h` was only read, never written. Home also lists `ZZ audit ...` projects made by the visual worker.

Quoted screen text keeps its words; its en dashes are written as hyphens here.

Columns: **Where** = says where I am; **What** = says what it is telling me; **Next** = one visible next action above the fold (yes/no, visible text).

### (a) Pick a site and dates, check sunlight and contact with Earth

| Screen | Where | What | Next |
|---|---|---|---|
| /home | yes: date, h1 "2 steps wait on you; nothing is being worked out." | yes | no: the one ink button is "Ask"; the waiting steps are rows below it |
| /map | yes: h1 "Candidate landing sites", tab "Map" | yes: "Spots near the south pole, measured for sunlight and contact with Earth. Choose one on the map or in the list." | yes once a site is chosen: "Open the site page" |
| /site | partly: the site name is a select at display size; no page name except the tab "Site" | yes: question, sentence, four numbers | no: "Plan for time without contact" is after the rings and rows, below the fold |
| /site, Change the dates | yes: bar reads "1 Jun 2027 → 30 Jun 2027" | yes: sentence and numbers update | n/a |
| /plan | yes: eyebrow "Plan for time without contact", site name | yes: "1 time without contact and 8 nights in 29.5 days" | no: "Download as a spreadsheet (CSV)" below the fold |

### (b) An upcoming mission (IM-3) through its six steps, then a flown one (IM-2)

| Screen | Where | What | Next |
|---|---|---|---|
| /missions | yes: h1 "CLPS missions", eyebrow spells out the acronym | yes | yes: "New project" (but the planner's next act is opening a mission) |
| /missions/im-3 | yes: breadcrumb, name, "Planned: getting ready" | yes: six stops each with a one-line answer | no: four equal "Explore a scenario" chips; no single action, the "Now" step (Ready) is not offered |
| im-3/ready | yes: breadcrumb, journey ring on 1 | yes: "14 items are listed from the mission record; no states have been entered for them yet." | no: "Change" per row, no one action; "Next step" below the fold |
| im-3/launch | yes | yes: "No launch to show yet" | yes: "Explore a scenario" |
| im-3/trip | yes | yes | yes: "Next step 4 · Surface" |
| im-3/surface | yes | contradicts: bar says "No data yet", page says "Over these 30 days the Sun is up 50%…" | no |
| im-3/contact | yes | yes | no ("What if…" is quiet text) |
| im-3/return | yes | yes: "No data yet" | yes: "Explore a scenario"; footer has only "All six steps" |
| im-3 scenario (launch → trip → surface) | yes: "Scenario · ready-made" band | yes, but the journey still shows the record's "No data yet" on every step | yes: "Next step" keeps `?scenario=` |
| /missions/im-2 | yes: "Partly successful: all six steps are behind it" | yes: record narrative | no action at all |
| im-2 steps | yes | yes: e.g. "A ground station can hear it for all 12.8 h of these dates." | "What if…" on all five steps of a flown mission |

### (c) Compare three sites

| Screen | Where | What | Next |
|---|---|---|---|
| /compare | yes: h1 "Compare sites" | yes: "The same dates at each site, side by side. Nothing is combined into a score: rank by one number at a time." | no: no primary; 0 links to the report (live, `journey-c.txt`) |
| /compare, rank by Time in sunlight | yes | breaks a rule: card label "best", spoken "Peak near Shackleton is best: about 516 hours." (`verify-best2.txt`) | n/a |

### (d) A what-if

| Screen | Where | What | Next |
|---|---|---|---|
| step with an answer | yes | yes | "What if…" text link, mid-page on Surface, low on others |
| builder `?scenario=new` (h=2749) | yes: "Scenario · When and from where can it launch?" | yes: one paragraph on what a scenario is | no: "Read it" is a plain button; "Work it out" is far below the fold |
| ready-made scenario | yes: "Scenario · ready-made" | yes, with 9 assumptions and their sources | yes: "Edit assumptions", "Leave the scenario" (two equal) |

### (e) Ask: from the header, from Home, at 390 wide

| Entry | Where | What | Next |
|---|---|---|---|
| Header "Ask /" (1440) | yes: chip "About IM-2 · Surface" | yes: three suggestions | yes: field has focus |
| Home Ask bar | chip "About any mission or site" | answer arrives in the dock | yes |
| Missions "Ask about missions and sites" disclosure | a second, older Ask with its own answer card | | |
| Phone: 56 px ink circle over the bottom bar | sheet opens, field focused | | the circle covers page text ("13h", `journey-e.txt` E5) |

### (f) Produce the report

| Screen | Where | What | Next |
|---|---|---|---|
| /report | yes: h1 "Printable report · one page", crumbs "Landing sites / Compare / Printable report" | yes: "3 candidate sites, 29.5 days" | yes: "Print or save as PDF" (also "Download as CSV") |
| ways in (live, `journey-f.txt`) | "Printable report" on /site and /missions/im-2/surface only; none on /map, /compare, /plan, /skyline, /home | | |
| /report body | | breaks a rule: "Assessment: No candidate in this set survives its longest night on its battery alone. What limits them is latitude, not terrain …" | |

### (g) Create a project, edit it, leave with unsaved work

| Screen | Where | What | Next |
|---|---|---|---|
| /projects/new | yes: h1 "New project" | yes: "Only the name is needed. A field you leave …" | two ink buttons: "Choose a file" and "Save project" |
| saved project hub | yes | yes | no "Edit project" anywhere: 0 links to `/edit` on the hub, Missions and Home (live) |
| /projects/:id/edit | yes | yes | "Save changes", "Cancel", "Not saved yet" |
| leave by a link | guard bar "Leave without saving? What you entered here will be lost." | | focus stays on the link pressed |
| leave by browser Back | no guard; the edits are gone (live: Back went to /home with no dialog; Forward showed Provider empty, `journey-g.txt`) | | |
| fresh project hub (live) | yes | "Provider not published", "The launch date is not published." on the team's own project | five "Explore a scenario" chips; no "Edit project", no "Add it" |

### Findings

Rule breaches first (B), then by journey. Sev 1 blocks the journey, 2 misleads or hides the next step, 3 polish.

| # | Tag | Sev | Visible text | Source | Fix |
|---|---|---|---|---|---|
| R1 | bug | 1 | Plan chart axis "14 Mar · 21 Mar · 28 Mar · 5 Apr · 12 Apr" under a bar reading "1 Jun 2027 → 30 Jun 2027" (`journey-a.txt` a3) | `frontend/src/components/BlackoutTimeline.tsx:166,178-180`; cause `lib/api/adapters.ts:276` (`windowStartH = 0`) | date the ticks from `metrics.windowStartIso`, as `ArcTable.tsx:20` already does. **Live: confirmed** (below) |
| R2 | bug | 2 | "56 h inside the 120 h battery limit", "236 h over the 120 h battery limit" | `frontend/src/lib/geometry/metrics.ts:12` (constant), `components/KeyNumbers.tsx:373-376`, `lib/summaryScript.ts:97-102` | the backend has `battery_limit_h` as an entered parameter "not published" (`backend/app/services/parameters_service.py:33-38`); use it, say "assumed" with the hatch when it is the default. **Live: confirmed** (below) |
| R3 | bug | 2 | Ask: "the sun fraction up is 0.543443 … sunlit time is 105645.317 seconds … longest dark period is 88754.683 seconds" (no ±, raw field names) | `backend/app/agents/tools.py:492-520` (seconds only), prompt `backend/app/agents/chatter.py` SYSTEM ("Durations … are SECONDS") | tools also return hours rounded with their ± (`edge_timing_s` is there); prompt: every number in hours with its ± |
| R4 | bug | 2 | Scenario Surface tiles with no margin (tolerance forced to 0) and no chart | `frontend/src/screens/MissionDetailScreen.tsx:222,255-256` | see `known-gaps.md` #1 |
| a1 | flow | 2 | Compare opens on "Connecting Ridge, Malapert massif, Faustini rim" after the reader chose "Peak near Shackleton" on Site | `screens/CompareScreen.tsx:75-89`; `screens/TwoClockScreen.tsx:128-139` has no "Add to Compare" | "Add to Compare" secondary pill on Site; or Compare adds the open site as the first column with a removable chip |
| a2 | flow | 2 | Opening a mission silently replaces the dates and site picked on Sites | `screens/MissionHub.tsx:67-72`, `screens/MissionDetailScreen.tsx:546` | say it once on the Sites date bar: "Dates set by IM-2. Back to 1 Jun 2027 → 30 Jun 2027" |
| a3 | flow | 3 | Site: next step "Plan for time without contact" sits under rings and rows | `screens/TwoClockScreen.tsx:128-139` | move the three onward pills under the four numbers |
| a4 | flow | 3 | Home's one ink button is "Ask" while the headline says "2 steps wait on you" | `screens/HomeScreen.tsx:67`, `components/home/AskBar.tsx` submit | make the first "Needs you" row's action the ink pill; Ask's button secondary |
| b1 | flow | 2 | Hub IM-3: four equal "Explore a scenario" chips, Ready marked "Now" is not offered; IM-2 hub has no action | `components/lifecycle/JourneyBar.tsx:490-501`, `screens/MissionHub.tsx:149-168` | one primary under the journey: "Open step 1, Ready: 14 items need a state" (planned) / "Read step 4, Surface" (flown) |
| b2 | bug | 2 | Bar: "Surface · No data yet. The landing date is known only as 'in 2026'"; page: "Over these 30 days the Sun is up 50% … longest night is 356 hours" (Sites' dates, unnamed) | `screens/MissionHub.tsx:67-72` (no window, keeps old dates), `screens/MissionDetailScreen.tsx:557` | answer names the dates and that they are chosen, with the hatch: "For 30 days you chose from 14 Mar 2027 …" |
| b3 | bug | 2 | "Named defaults: … landing 1 Jan 2026", "A month later: landing 1 Feb 2026" (both past on 12 Nov 2026) | `backend/app/workers/presets.py:41-72` (landing from `scenario_service.resolve_all`) | year-only landing resolves to the first day not yet past in the published period |
| b4 | flow | 2 | In a scenario the journey still reads "2 Launch · No data yet. The launch date is not published." | `components/lifecycle/JourneyBar.tsx:240,248` | with a scenario open, show each step's scenario phase state, hatched, "in this scenario" |
| b5 | flow | 2 | "What if…" on all five steps of flown IM-2 | `components/scenario/ScenarioEntry.tsx:112-125` | see `known-gaps.md` #2 |
| b6 | flow | 3 | Step 6 footer offers only "All six steps" | `screens/MissionHub.tsx:194-217` | last step: "Printable report" or "Back to the step that needs you" as the ink pill |
| b7 | jargon | 3 | "What still works: Surface, Contact and the other steps do not depend on the launch and work as usual." (Trip and Return do depend on it) | `screens/sections/LaunchSection.tsx:88` | "Contact works as usual. Trip and Return wait for a launch time." |
| b8 | overload | 3 | Flown IM-2 Ready: "All 13 items flew" yet 13 "Change" buttons, "Add a risk", "Add a part" | `screens/sections/ReadySection.tsx` | on a flown mission fold edits behind one "Correct the record" disclosure |
| c1 | flow | 2 | Compare has no link to the report; the report's crumbs say it belongs to Compare | `screens/CompareScreen.tsx:283`, `screens/ReportScreen.tsx:97` | "Printable report" pill at the foot of Compare |
| c2 | flow | 3 | Report always orders by longest night, whatever Compare was ranked by | `screens/ReportScreen.tsx:38` | carry `rank` from Compare |
| c3 | jargon | 3 | Compare card: "Sunlight · Contact · Without contact" vs Site tiles "Time in sunlight · Time in contact with Earth · Longest time without contact" | `screens/CompareScreen.tsx:418-421` | use the tile labels (short form "Longest without contact") |
| d1 | overload | 2 | Builder: explanation, prompt, four chips, "Read it", then the form; "Work it out" far below (page 2749 px) | `components/scenario/ScenarioBuilder.tsx` | sticky action bar with "Work it out" as on the project form |
| d2 | jargon | 3 | "Named defaults", "Next precedent" as preset titles | `backend/app/workers/presets.py:51,63` | "Defaults from past flights", "As the next flight of this lander" |
| e1 | bug | 2 | Answer link "Open · mission-im-2" | `backend/app/agents/chatter.py:420-423` | name from the site catalogue; never show an id |
| e2 | flow | 2 | Home chip "What is a scenario, and what does it assume?" gets "Nothing in the question or on this page matched…" without a model; no tool explains scenarios | `components/home/model.ts:155`, `backend/app/agents/chatter.py:332-345` | replace with "Which steps of {project} have no data yet?" (`get_mission_sections`) |
| e3 | overload | 2 | Missions page has a second Ask ("Ask about missions and sites") with another agent and answer card | `screens/MissionsScreen.tsx:421`, `components/Agents.tsx:434-463` | the row opens the dock with the question |
| e4 | flow | 2 | Phone Ask is an ink circle over the content above the bar, styled as the page's primary | `components/AppShell.tsx:297-309` | keep the floating button (recorded, `decisions.md` C-1): a glass pill with the word Ask, never ink, page padded by `--pw-ask-h` |
| e5 | jargon | 3 | "When can the Deep Space Network hear IM-2?"; model follow-ups "What is the longest blackout…", "What are the uncertainty details…" | `components/ask/store.ts:149`, `backend/app/agents/chatter.py:367`, SYSTEM | glossary words in the prompt; "When can NASA's deep-space dishes (Deep Space Network) hear IM-2?" |
| e6 | flow | 3 | "Space weather now" answer link goes to Home, where it is below the fold | `backend/app/agents/chatter.py:419` | link to the open mission's Launch row "Space weather now", or `/home#live` |
| f1 | flow | 3 | Report memo is for the Site page's site, the table for the Compare list: they can differ | `screens/ReportScreen.tsx:36,301` | memo picker limited to the compared sites |
| g1 | flow | 1 | No "Edit project" on the project's hub, card or list row; only Home's "Needs you" links to `/projects/:id/edit` | `components/home/model.ts:52`; `screens/MissionHub.tsx:107-124`; `screens/MissionsScreen.tsx:472` | "Edit project" secondary pill in the hub header for `origin: 'project'`, and on its Missions row and Home card |
| g2 | bug | 1 | Browser Back with unsaved edits leaves without a word; the edits are lost | `screens/ProjectNewScreen.tsx:143-165`, `main.tsx:39` | see `known-gaps.md` #3 |
| g3 | bug | 2 | "Leave without saving?" appears in the sticky bar but focus stays on the link pressed | `screens/ProjectNewScreen.tsx:370-385` | focus "Stay" when it opens; Esc means Stay |
| g4 | overload | 3 | Two ink buttons above the fold: "Choose a file", "Save project" | `screens/ProjectNewScreen.tsx:388`, `components/project/FileDrop.tsx` | "Choose a file" secondary |
| n1 | jargon | 3 | "Sites" (nav) / "Candidate landing sites" (h1) / "Landing sites" (crumbs, guide) / "Map" (tab) | `components/AppShell.tsx:46,51`, `screens/MapScreen.tsx:121`, `screens/ReportScreen.tsx:97`, `lib/guide.ts:36` | one name: "Landing sites" (nav may stay "Sites") |
| n2 | jargon | 3 | "project" is both a mission you add and the Settings tab "Project" (sign-in, team) | `components/SettingsSheet.tsx:18`, `lib/guide.ts:57` | Settings tab "Team" |
| n3 | jargon | 3 | Guide: "Press Guide at the top any time"; the control is "Guide and settings" | `lib/guide.ts:57` | "Open Guide and settings at the top any time" |
| n4 | bug | 3 | Plan and Site share the same h1 (the site name); Plan's page name is only an eyebrow | `screens/BlackoutScreen.tsx:56-57`, `components/SitePicker.tsx:21` | `SiteTitle prefix` or sr-only "Plan for time without contact:" in the h1 |
| x1 | delight | 3 | Mission journey "Next step" keeps the scenario and lands focus on the step bar | `screens/MissionHub.tsx:55-61` | keep |
| x2 | delight | 3 | Site answer: "Over these 29.5 days the Sun is up 73% of the time and Earth is in view 63% of the time; the longest night is 64 hours." | `screens/TwoClockScreen.tsx:70` | the model for every page |

### Live checks of R1 and R2 (12 Nov, 05:00 UTC, 1440 x 900, dark, script `verify-r1-r2.cjs`, output `verify-r1-r2.txt`)

#### R1, the Plan chart's dates: CONFIRMED
Steps: /map; press "Peak near Shackleton" in the list; "Open the site page"; tab "Plan"; tab "Site"; "Change the dates"; type 2027-06-01 in "Start (UTC)"; tab "Plan".
- Default dates: bar "14 Mar 2027 → 12 Apr 2027", axis "14 Mar, 21 Mar, 28 Mar, 5 Apr, 12 Apr". Right only because the default dates start at the model epoch (14 Mar 2027, `lib/format.ts:74`).
- After the change: bar "1 Jun 2027 → 30 Jun 2027 · Day 0 of 30 · 1 June, 00:00 UTC"; axis still "14 Mar, 21 Mar, 28 Mar, 5 Apr, 12 Apr". On the same screen the side panel says "9 h from Day 8, 9 June, 23:23 UTC" and the table "Day 20, 21 June, 03:45 UTC" (those use `windowStartIso`, so they are right). Screenshot `shots/r1-plan-after-change-1440.png`.
- Same result by in-app links only (`journey-a2.txt`: "PLAN SVG TEXTS: 14 Mar, 21 Mar, 28 Mar, 5 Apr, 12 Apr" under "1 Jun 2027 → 30 Jun 2027").
- Same root, second place: every `Ribbon` tells screen readers "These dates start at hour 0 and last 709 hours." (Compare, Report, mission Surface; `components/Ribbon.tsx:96-98`, fed `metrics.windowStartH`, always 0). Listed as R1b.

#### R2, the "120 h battery limit": CONFIRMED
Steps: as above, default dates; then /compare (Connecting Ridge, Malapert massif, Faustini rim); then `GET /api/v1/parameters` with the demo session's token (read only).
- Site tile: "Longest night · 56 h inside the 120 h battery limit"; Listen text: "That is 56 hours inside the 120 hour battery limit." No "assumed", no hatch.
- Compare: "2 h past the 120 h battery limit" (Connecting Ridge, 122 h), "At least 168 h past …", "486 h past …"; footer "… run past the 120 h battery limit on these dates". Report header: "battery limit 120 h of continuous darkness".
- API: `battery_limit_h` value `null`, provenance "entered", missing_reason "The lander's battery limit is not published; enter the one from its power budget."
- Network: 0 of 173 API calls made on /map, /site, /plan and /compare ask for `/parameters`, so a value the team enters in Settings changes nothing on these pages (not tried by writing: it is a shared global value).
- Worse than first written: the over/under call ignores the margin. Connecting Ridge is "2 h past" the limit while the Report says its longest night's start and end carry "±17.09 h" (`components/KeyNumbers.tsx:313-316` handles only open lower bounds). And the Report turns the constant into a survival verdict (R6).

### Findings from the journeys run in the second pass

Same columns. Rows that only confirm an earlier finding are marked in that journey's table above, not repeated.

| # | Tag | Sev | Visible text | Source | Fix |
|---|---|---|---|---|---|
| R1b | bug | 3 | screen reader: "These dates start at hour 0 and last 709 hours." under every sunlight and contact ribbon | `components/Ribbon.tsx:96-98`; callers `CompareScreen.tsx:511,522`, `ReportScreen.tsx:215`, `MissionDetailScreen.tsx:607,618` | "These dates run from 1 Jun 2027 to 30 Jun 2027, 709 hours." from `windowStartIso` |
| R5 | rule | 1 | Compare ranked by Time in sunlight (Peak near Shackleton, Amundsen rim, Faustini rim): card label "best"; Listen: "Peak near Shackleton is best: about 516 hours." (`verify-best2.txt`) | `lib/rank.ts:77` (`kind: 'best', text: 'best'`), `screens/CompareScreen.tsx:466`, `lib/summaryScript.ts:173-175`, `screens/ReportScreen.tsx:171` | rank 1 reads "1st" like every other place; spoken "is 1st"; rename kind `best` to `first`; a banned-words test over rendered text |
| R6 | rule | 1 | Report "Assessment: No candidate in this set survives its longest night on its battery alone. What limits them is latitude, not terrain: every site here except those within about a degree of the pole has a real seasonal night." (fixed text, printed for any set; Connecting Ridge is within a degree of the pole). Other branch: "{X} is the only one whose worst night fits inside the 120 h limit … pays for that with Earth contact". Compare footer: "Every site here stays inside the battery limit, so the choice comes down to what the payload needs." | `screens/ReportScreen.tsx:237-258`, `screens/CompareScreen.tsx:374-383`, `lib/rank.ts:73` ("1st, over the limit") | heading "Against the battery limit"; one counted sentence: "2 of 3 sites have a night longer than the 120 h battery limit (assumed) on these dates; 1 is within the margin." with the hatch on "assumed"; delete the latitude sentence and the "choice comes down to" clause; rank 1 over the limit reads "1st" and the night figure carries "past the limit" |
| a5 | flow | 2 | After opening the IM-2 hub from the Missions list (not a step), Sites shows "Dates: 12.75 hours 6 Mar 2025 → 7 Mar 2025" with "Peak near Shackleton" still chosen; nothing says why (`journey-a2.txt`) | `screens/MissionHub.tsx:67-72` | with a2: the hub does not set app dates; a step that shows dates sets them, and the Sites bar says "Dates set by IM-2 · Back to 1 Jun 2027 → 30 Jun 2027" |
| a6 | flow | 3 | Dates lost on reload or a shared link: /compare and /report by address read "29.5 days from 14 March 2027" after the reader chose 1 Jun 2027; the URL carries `sites` and `rank` only | `screens/CompareScreen.tsx:75-89`; store `windowStartH` not in the URL | add `from` and `days` to the URL of the four site pages and the report |
| c4 | jargon | 3 | "Faustini rim can't be ranked; it could be 1st-3rd: about 606 hours" beside Peak near Shackleton's 64 h (`verify-best.txt`) | `lib/rank.ts:61-69` (`rangeWords`), reason `grazing` | when the range covers every place, give only the reason: "can't be placed: the Sun skims the skyline at the start or end of this night" |
| e7 | bug | 2 | Ask chip "About IM-3 · Launch, in the scenario open" (hatched) but the answer is about the record | `components/ask/AskDock.tsx:377-378`; `backend/app/agents/chatter.py` never reads `scenario_id` | `get_scenario` tool (approved, `ask-spec.md`); until then the chip says "about the record" |
| g5 | jargon | 2 | Team's own project hub: "Provider not published", "The launch date is not published.", "No landing spot is published, so contact cannot be worked out."; the only actions are five "Explore a scenario" chips | `screens/MissionHub.tsx:122`; `backend/app/services/sections_service.py:130,221,250` (same strings for catalogue and project) | for `origin: 'project'`: "not entered yet" and an "Add it" link to `/projects/:id/edit#<section>`; the scenario chip second |
| g6 | bug | 3 | Edit page tab title "POLAR WINDOW · POLAR WINDOW" | `components/AppShell.tsx:87` (no `TITLES` entry for `/projects/:id/edit`) | "Edit {name} · POLAR WINDOW", set by `ProjectEditor` |
| d3 | flow | 3 | "What if…" at y 2238 of a 2554 px page (IM-3 Contact) and y 2187 of 2503 on flown IM-2 (`journey-d.txt`) | `screens/sections/ContactSection.tsx:97` | with known gap #2: planned missions only, and placed under the answer (`overload.md`) |

### All findings, by severity

Package IDs from `work-packages.md`. Sev 1 blocks the journey or breaks a rule that never bends; 2 misleads or hides the next step; 3 polish.

| Sev | # | Tag | Finding | Live | Package |
|---|---|---|---|---|---|
| 1 | R1 | bug | Plan chart axis keeps the default dates after the reader changes them | confirmed | O2 |
| 1 | R5 | rule | Compare labels a site "best" and says "is best" aloud | confirmed | O2 |
| 1 | R6 | rule | Report "Assessment" gives a survival verdict against an unlabelled limit, with a fixed latitude claim | confirmed | O2 |
| 1 | g1 | flow | No way to edit a project except typing its address | confirmed | O3 |
| 1 | g2 | bug | Browser Back loses unsaved project edits with no warning | confirmed | O3 |
| 2 | R2 | bug | "120 h battery limit" stated as fact; the entered parameter is never read; over/under ignores the margin | confirmed | O2 |
| 2 | R3 | bug | Ask quotes raw seconds and field names with no margin | earlier run | O1 |
| 2 | R4 | bug | A scenario's Surface tiles show no margin and no chart | code | O3 |
| 2 | a1 | flow | Compare ignores the site open on Site; Site has no "Add to Compare" | earlier run | S4 |
| 2 | a2 | flow | Opening a mission silently replaces the Sites dates | confirmed | O3 |
| 2 | a5 | flow | Even the hub alone (no step) changes the Sites dates to the mission's 12.75 hours | confirmed | O3 |
| 2 | b1 | flow | Hub: four equal scenario chips, the "Now" step not offered; flown hub has no action | earlier run | O4 |
| 2 | b2 | bug | Surface answer uses unnamed dates the reader chose elsewhere | earlier run | O3 |
| 2 | b3 | bug | Ready-made scenarios land on dates already past | earlier run | O3 |
| 2 | b4 | flow | In a scenario the journey still shows the record's "No data yet" | confirmed | O4 |
| 2 | b5 | flow | "What if…" on a flown mission | confirmed | O3 |
| 2 | c1 | flow | No link from Compare to the report it feeds | confirmed | S4 |
| 2 | d1 | overload | Builder: "Work it out" far below explanation, chips and form | earlier run | O4 |
| 2 | e1 | bug | Ask link labelled with an id ("mission-im-2") | earlier run | O1 |
| 2 | e2 | flow | Home chip "What is a scenario…" has no tool to answer it | earlier run | O5 |
| 2 | e3 | overload | A second, older Ask on Missions | earlier run | O5 |
| 2 | e4 | flow | Phone Ask is an ink circle over the content | earlier run | O5 (C-1) |
| 2 | e7 | bug | Ask chip says "in the scenario open" but answers about the record | code | O1 + O5 |
| 2 | g3 | bug | "Leave without saving?" opens without taking focus | confirmed | O3 |
| 2 | g5 | jargon | The team's own project says "not published" and offers only scenarios | confirmed | O3 + O4 + S3 |
| 3 | R1b | bug | Screen readers hear "These dates start at hour 0" on every ribbon | confirmed | O2 |
| 3 | a3 | flow | Site's next steps sit under the rings, below the fold | earlier run | S4 |
| 3 | a4 | flow | Home's one ink button is Ask, not the waiting step | confirmed | O5 + S6 |
| 3 | a6 | flow | Dates lost on reload or a shared link | confirmed | O5 |
| 3 | b6 | flow | Step 6 offers only "All six steps" | earlier run | O3 |
| 3 | b7 | jargon | Launch's "what still works" claims Trip and Return do not depend on it | code | S1 |
| 3 | b8 | overload | Flown Ready shows 13 "Change" buttons and add controls | earlier run | S3 |
| 3 | c2 | flow | Report ignores Compare's rank | code | S4 |
| 3 | c3 | jargon | Compare's card labels differ from the Site tiles | earlier run | S1 |
| 3 | c4 | jargon | "could be 1st-3rd" for a 606 h night beside a 64 h one | confirmed | O2 |
| 3 | d2 | jargon | "Named defaults", "Next precedent" as preset titles | earlier run | S1 |
| 3 | d3 | flow | "What if…" sits at the foot of long pages | confirmed | S3 (Surface O3) |
| 3 | e5 | jargon | "Deep Space Network", "blackout", "uncertainty details" in Ask | earlier run | O1 + O5 |
| 3 | e6 | flow | "Space weather now" link lands below the fold on Home | earlier run | O1 |
| 3 | f1 | flow | Report memo and table can be about different sites | confirmed | S4 |
| 3 | g4 | overload | Two ink buttons on the new-project form | confirmed | S5 |
| 3 | g6 | bug | Edit page title "POLAR WINDOW · POLAR WINDOW" | confirmed | O3 |
| 3 | n1 | jargon | Four names for the landing-site area | earlier run | S1 |
| 3 | n2 | jargon | "Project" is both a mission and a Settings tab | code | S1 |
| 3 | n3 | jargon | Guide says "Press Guide"; the control is "Guide and settings" | code | O5 |
| 3 | n4 | bug | Plan and Site share the same h1 | earlier run | S4 |
| 3 | x1 | delight | "Next step" keeps the scenario and lands focus on the step bar | earlier run | keep |
| 3 | x2 | delight | Site's one-sentence answer is the model | confirmed | keep |

---

# Part 3: Overload


Counts are items visible before scrolling, dark theme, from `../visual/data/fold.md` (1440 / 390). Visible text from `walk-1440.txt`, `walk-390.txt` and the visual notes (`../visual/PROGRESS.md`, cited as V:line). Action: **remove**, **behind** (a closed row or disclosure), **down** (below the answer), **merge**. The pattern every screen is held to: a question, one sentence of answer, at most four key numbers, then closed rows; one visible next action.

### Per route

| Route | Fold 1440 / 390 | The decision on this screen | Not helping it, visible before scrolling | Action | Source |
|---|---|---|---|---|---|
| /home | 28 / 18 | what needs me today | four Ask chips, one of which fails without a model ("What is a scenario, and what does it assume?", `journeys.md` e2); Ask's ink button outranks the waiting step (a4); map caption of two sentences "Shade where the Sun is below a flat horizon at 21:55 UTC. Ridges and craters cast no shadow on this map; each site's skyline does. Diamonds: your project targets." | chips: **remove** to two (the first waiting project's question, one about sites); caption: **behind** an "About this map" info button, keep "Diamonds: your project targets" as the legend; first Needs-you action becomes the ink pill | `components/home/model.ts:155`, `components/home/AskBar.tsx`, `components/home/NowOnTheMoon.tsx:46,51` |
| /missions | 25 / 14 | which mission to open | ink "New project" (the planner opens a mission first); a second Ask row "Ask about missions and sites" with its own agent (e3) | "New project" **secondary**; second Ask **remove** (the row opens the dock) | `screens/MissionsScreen.tsx:222,421` |
| hub, planned (m-up) | 7 / 2 | which step to open | at 390 nothing but the title and "Six steps": the rail is 1205 px; four equal hatched "Explore a scenario" pills compete, and the step marked Now has no action (b1) | **add** one primary under the journey ("Open step 1, Ready: 14 items need a state"); pills stay (recorded D-14, `decisions.md` C-8) but on the stop's own row; rail tightened (`journey-and-sequence-spec.md` §2) | `components/lifecycle/JourneyBar.tsx:440-501`, `screens/MissionHub.tsx:149-168` |
| hub, flown (m-fl) | 9 / 2 | read what happened | no action at all; "What if…" reachable on every step (b5) | primary "Read step 4, Surface"; no scenario entries (known gap 2) | `screens/MissionHub.tsx:149-168` |
| Ready, planned | 11 / 9 | what is holding it up | 33 filler strings in the item rows ("Not entered yet", "Not recorded", a dash) (V51); "Next milestone" reads "2026-2027 Jan-Jan" (V47) | **merge** a row's empties into "Nothing entered yet"; milestone tile shows the published words ("in 2026") with no fake range | `screens/sections/ReadySection.tsx` |
| Ready, flown | 18 / 10 | did it fly ready | 13 "Change" buttons, "Add a risk", "Add a part" (b8); tiles 13 / 0 / 0 / 0 incl. "Next milestone 0" (V83) | edits **behind** one "Correct the record" disclosure; **remove** the milestone tile on a flown mission (3 tiles) | `screens/sections/ReadySection.tsx` |
| Launch, planned | 14 / 9 | when can it launch | headline of 3 to 4 lines naming "Launch Complex 39A" twice (V54); headline's "12 Nov 07:00" against the tile's "11 Nov 07:04 ± 18 min" (V53, a bug) | one sentence: "The next possible launch time is {date} ± {m} min, from {pad}." | `screens/sections/LaunchSection.tsx`; backend launch answer |
| Launch, flown | 15 / 10 | when did it launch | the launch time four times: headline, "The published liftoff is … ± 30 s", "Numbers for the launch on …", the tile (V87) | **behind**: the published-liftoff line into About these numbers; "Numbers for the launch on" **remove** (the tile caption says it) | `screens/sections/LaunchSection.tsx:165` |
| Trip, planned | 7 / 7 | what is missing | "Assuming these would still not be enough to work this step out." and no button to the missing input (V60) | empty-state rule (`journey-and-sequence-spec.md` §4) | `screens/sections/TripSection.tsx` |
| Surface, planned | 18 / 12 | sunlight and contact at the landing spot | two caveat lines above the tiles ("For the centre of Reiner Gamma; the landing point isn't published." "Terrain data covers only 85% of the directions…") push the tiles below the fold at 390 (V63); three tool sections as h2 under the answer | caveats **merge** into one line under the tiles, "Assumed" hatched; tools **behind** one disclosure "Tools for a lander you describe" (three closed rows) | `screens/MissionDetailScreen.tsx:275,301-311`, `components/surface/SurfaceTools.tsx:21-45` |
| Contact, planned | 14 / 8 | how often can it talk to Earth | two tiles with the same figure, "Longest time without contact 286 h" and "Longest message wait 286 h" (V68); "Through a relay" tile with a lone dash (V69) | with no relay: **merge** into one tile and the line "No relay is planned, so the wait is the same"; the relay tile **remove** | `screens/sections/ContactSection.tsx` |
| Return, planned | 9 / 5 | where the booster comes down | the answer is one 85-word sentence in display type, 12+ lines at 390, numbers below the fold (V73) | answer ≤ 30 words: "Where the Falcon 9 booster lands is not published for this launch; past CLPS boosters landed on a ship at sea or back at the Cape."; the flown-launch list and the sea note **behind** rows "On past CLPS launches", "The sea there" | `backend/app/services/return_service.py:307-331` (note), `screens/sections/ReturnSection.tsx:156-163` |
| Return, flown | 8 / 8 | where it came down | two tiles holding only a dash (V102) | no number, no tile: **remove** both; one sentence with the reason | `screens/sections/ReturnSection.tsx:167-173` |
| Surface and Contact, flown | 15 / 10, 14 / 11 | what it got | headline "12.75 hours" beside tiles "13 h", chart "12.8 h" (V96, V98) | one precision per screen (the tile's) | `lib/format.ts`, section answers |
| /projects/new | 14 / 13 | name it, save it | two ink buttons, "Choose a file" and "Save project" (g4); the sticky Save bar sits over the first card at 768 (V110) | "Choose a file" **secondary**; the sticky bar appears once the form is in view | `screens/ProjectNewScreen.tsx:388`, `components/project/FileDrop.tsx` |
| /projects/:id/edit | 14 / 13 | change a field | the New-project intro word for word and the drop zone before the form (V114) | intro **remove** on edit; drop zone **behind** "Fill empty fields from a file" under the form | `screens/ProjectNewScreen.tsx:270-290` |
| /map | 41 / 19 | which site to open | the four filter controls open beside the list; the play bar before any site is chosen; at 390 the map fills the screen and pushes list and chosen-site card out (V121) | filters **behind** (closed, meta "2 on"); at 390 map height capped at 60vh so the first list rows show | `screens/MapScreen.tsx:132-165` |
| /site | 17 / 10 | is this site good enough on these dates | the three onward actions sit under the rings, below the fold (a3) | **down** the rings, **up** the onward pills under the four numbers | `screens/TwoClockScreen.tsx:128-139` |
| /compare | 44 / 13 | how do these sites differ on one number | "Too close to call" on all three cards at once (V128); Listen / Read it before the cards | when every card is unranked: **merge** into one line above the cards, no per-card badge; Listen **into** the header row | `screens/CompareScreen.tsx:440-470` |
| /skyline | 11 / 8 | what blocks the Sun and Earth | the first screen is the empty upper part of the plot; the terrain line is below the fold (V131) | plot's vertical range cropped to the data plus 2 degrees | `screens/HorizonScreen.tsx` |
| /plan | 17 / 4 | what must the lander do alone | at 390 the chart card fills the screen and the hero number is below it | at < 640 px the packet ("46 hours working alone") **first**, timeline after | `screens/BlackoutScreen.tsx` |
| /report | 14 / 4 | print it | (paper; fine) | none | |
| landing | 10 / 10 | enter | the stat "CLPS missions" counts the team's projects (V147, 21 → 24) | count `origin !== 'project'` only (a bug, not overload) | `screens/LandingScreen.tsx` |

### Pages that break the pattern

| Page | Break | Fix |
|---|---|---|
| Return, planned | one sentence of 85 words (V73) | the row above |
| Launch, planned | 3 to 4 line sentence with the pad twice; two different "next" times | the row above |
| Plan | no question; the hero is "1 time without contact and 8 nights in 29.5 days" | eyebrow "What must the lander do while out of contact?"; the number stays the hero (recorded: "Plan · the hours working alone") |
| Compare | the question is implicit | eyebrow "How do these sites compare on {rank-by}?" (never "best") |
| Ready, flown | four tiles, three of them 0; the answer is a count | three tiles; the count is the sentence |
| Contact, planned | five figures (two equal) | four, as above |
| Surface in a scenario | four tiles with no margin (R4) | known gap 1 |
| Missions | no question | accepted: a list page; its hero is the map (recorded) |
| Map | no question | eyebrow "Where near the pole could a lander land?" over h1 "Landing sites" |
| Report | paper | exempt |

Kept on purpose: the Site and Surface answer sentences restate three of the four tiles (V62, V122). The answer hero is recorded that way (`docs/design-visual-refresh.md` Direction, "The answer hero"): the sentence is read, the tiles carry the margins.

---

# Part 4: Where every finding lands

Rounds: 1 Ask backend (O1) and glossary renames (S1). 2 numbers and verdicts (O2) and cross-cutting fixes (S2).
3 known gaps and the project flow (O3) and step pages trimmed (S3). 4 the stage line (O4) and landing-site pages (S4).
5 Ask, phone shell, guide, dates in the URL (O5) and the project form and wrapping (S5). 6 moments (O6) and
loading placeholders (S6). 7 cleanup, gates and screenshots (O7, S7).


**journeys.md**: R1 O2 · R1b O2 · R2 O2 · R3 O1 · R4 O3 · R5 O2 · R6 O2 · a1 S4 · a2 O3 · a3 S4 · a4 O5 + S6 · a5 O3 · a6 O5 · b1 O4 · b2 O3 · b3 O3 · b4 O4 · b5 O3 + O4 · b6 O3 · b7 S1 · b8 S3 · c1 S4 · c2 S4 · c3 S1 · c4 O2 · d1 O4 · d2 S1 · d3 S3 (Surface: O3) · e1 O1 · e2 O5 · e3 O5 · e4 O5 (C-1) · e5 O1 + O5 · e6 O1 · e7 O1 + O5 · f1 S4 · g1 O3 · g2 O3 · g3 O3 · g4 S5 · g5 O3 + O4 + S3 · g6 O3 · n1 S1 · n2 S1 · n3 O5 · n4 S4 · x1, x2 kept.

**jargon.md**: rows 1 to 49 S1 · 50, 51 O5 · 52 to 56 O1 · 57 O5 (chip) + O1 (`chatter.py:367`) · 58 to 61 S1 · "same thing, named differently" S1, except "Mission sections" → "Mission steps" O4 (C-4).

**Visual** (`../visual/PROGRESS.md`): V:12 list 1 S2, 2 O4, 3 S2, 4 S3, 5 S2, 6 S2, 7 O5, 8 S4 + S2, 9 S6 + O6, 10 O2 · V:13 S2 · V30 S2 · V31 O5 · V33 S6 · V34 S6 · V36 O5 · V37 S4 · V39 S4 · V40 O4 · V41 O4 · V44 O4 · V45 S5 · V46 O4 + O5 · V47 S3 · V48 O4 · V50 S3 · V51 S3 · V53 O2 · V54 S3 · V56 S3 + S2 · V57 S2 · V58 S3 · V59 S5 + S3 · V60 S3 · V63 O3 + O5 · V65 S2 · V66 O3 · V67 S2 · V68 S3 · V69 S2 + S3 · V71 S3 · V73 S3 · V74 S2 + S3 · V76 S3 + S5 · V77 O5 · V78 O4 · V81 O4 · V82 S5 · V83 S3 · V85 S3 · V87 S3 · V88 S2 · V89 S3 · V90 S5 · V91 S1 + S2 · V93 S3 · V94 S3 · V96 S2 · V98 S2 · V99 S2 + S3 · V101 S3 · V102 S3 · V104 S2 + O4 · V106 S2 · V107 S3 · V108 S2 · V109 S5 · V110 S5 · V112 S5 · V114 S5 · V115 S5 · V116 S2 · V117 S5 · V119 S4 · V120 S4 · V121 S4 · V124 S4 · V125 S4 · V126 S4 · V127 S4 · V128 S4 · V129 S4 + O2 · V131 S4 · V133 S4 · V134 S4 + S5 · V135 O2 · V137 S4 · V138 S4 + S2 · V139 S4 · V140 O2 · V143 S5 + O5 · V144 O5 · V145 O5 · V147 S2 · V149 O6 + S6 · V150 O6 + S6 · V152 O2 · V153 O6 + S6. Lines tagged note, delight or table-fits (27, 28, 32, 38, 42, 43, 49, 52, 55, 61, 64, 70, 75, 79, 80, 84, 86, 100, 103, 105, 111, 118, 123, 130, 132, 136, 142, 148, 151, 154) record what works or a count; nothing to build. Cross-cutting: `overflow` S2 · `logs` duplicate key S2 · `tap` S2 (+ V82 S5) · `clip` step bar O4, long project name S5 · `covered` O5 · `contrast` S2 · `dashes` S2 (+ S1 in labels) · `tables` S2 + S4 · `skeleton` S6 + O6.

### Not doing, because

| Item | Because |
|---|---|
| V24 light-theme contrast fails on the landing hero | false positives: the text sits on the dark space picture |
| V25, V29, V35, V146 counts and lists differing between captures | test projects appearing mid-run; S7 deletes them (V147, the real counting bug, is S2's) |
| V26 empty right side of the landing in full-page captures | the Moon is a fixed scene that full-page captures do not include; O7 checks a viewport shot |
| V44, V81 stops floating without the arc | captures taken mid-draw; O4 still makes stops wait for the line |
| V62, V92, V97, V122 the answer sentence restates the tiles | recorded answer hero (D-10): the sentence is read, the tiles carry the margins |
| V72 many closed rows on Contact at 390 | closed rows are the pattern |
| V82 two date styles in a flown mission's narrative | the narrative quotes its source word for word |
| V95 table headers wrapping at 390 | the tables fit; wrapping headers is the intended fallback |
| V113 the project form's length | the form is the content; S5 fixes what covers it |
| V141 the report's title wrapping at 390 | a preview of a printed page |
| V:14 CORS errors on hillshade tiles in some captures | test setup (app on 127.0.0.1, API on localhost) |
| Links inside sentences under 44 px (`tap`: nasa.gov, record, ESO/S. Brunier) | WCAG 2.5.8 inline exception |
| `clip`: the Ask answer dock's clamp at 390; the flown narrative's clamp | a copy of the visible answer; "Show more" is the design |
| `logs`: headless GPU warning | not an app fault |
| x1, x2 | they are the model; keep |
| Ask as a floating button on phones (kept by `decisions.md` C-1) | reversed by the lead (L-1): the brief for this pass puts Ask in the bottom navigation, so O5 builds it as the fourth bar item |
| Scenarios for cancelled or reassigned missions | `known-gaps.md` #2 step 4: owner's call; default no |
