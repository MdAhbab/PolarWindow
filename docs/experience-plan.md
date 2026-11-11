# The experience release: plan

10 November 2026. Five things, built together:

1. **Ask**, on every dashboard page: a quick chat for short answers.
2. **Projects**: the project manager adds their own mission, by hand or by
   dropping a file the AI reads into the form.
3. **Scenarios**: where a mission has no published data for a step, the manager
   says or sets what to assume, watches it being worked out, and reads the
   answer, labelled as a scenario.
4. **Presets**: likely scenarios worked out ahead of time, so vague or repeated
   prompts answer at once.
5. **A dashboard that is an experience**: a home, a simpler shell, the mission
   as a journey, live things that move.

The wire contract is `frontend/src/lib/api/experience.types.ts`. It is the
source of truth for every shape below; the backend's Pydantic schemas mirror it.

## What is wrong today (the audit)

- **There is no home.** The dashboard opens on a filtered list of 20 missions.
  Nothing says what is being worked out, what needs the manager, or what is
  live right now.
- **It is a report, not a tool.** Every page is read-only prose and closed rows.
  The manager cannot add a mission; everything shown was fed in from
  `data/missions.json`.
- **The AI is hidden.** Ask is a closed row at the bottom of Missions; Explain
  and Advise are closed rows elsewhere. No page has a way to ask about what is
  on it.
- **Dead ends.** A planned mission with no pad, vehicle or date says "not
  published" on Launch, Trip and Contact and stops. Most upcoming missions are
  mostly dead ends.
- **Six equal cards.** The mission hub gives six text cards the same weight. The
  mission is a journey from Earth to the Moon; nothing draws it.
- **Nothing moves.** The front page has a 3D Moon; past the sign-in the product
  is static. The live data (Sun on the Moon now, space weather, DSN) is in
  closed rows.
- **Navigation is thin and deep at once.** Two top-level views, then four site
  tabs, then six steps, then closed rows. Guide and Settings take a third of
  the header.

## Product rules that do not change

These are the product's invariants (README, ADR-3, ADR-5, ADR-17). The new work
keeps every one of them.

- **No invented numbers.** A number on screen comes from a calculation or a
  source. The AI computes nothing; the grounding guard stays on every AI answer,
  chat included.
- **A mission's record is never filled in.** A scenario's assumed values live in
  the scenario. They are never written to the mission, and a scenario's answer
  is never shown without its *Scenario* label and its list of assumptions with
  the basis of each: **you** (typed or said), **published** (the record),
  **live** (fetched for this scenario, with source and time), **default** (a
  named precedent or catalogue value).
- **No verdicts.** No score, no go/no-go, no "likely". "Most likely values"
  means *named defaults from precedent*, shown as defaults.
- **Entered data has a name on it.** Every project write needs a named session
  and goes to the audit log.
- **Only the feeds worker and the compute worker fetch.** The API never touches
  the network (import contract, ADR-8). A scenario's live values are fetched in
  the compute worker.
- **Everything degrades.** No model key: files are read by rules, prompts are
  read by rules, chat answers from the measurements. Each says so.
- Accessibility (WCAG 2.1 AA, keyboard, reduced motion, both themes) and the
  layering contracts (`lint-imports`), `mypy --strict`, `ruff` stay green.

## The design

### Shell

`Home · Missions · Sites` in the island, then **Ask** (opens the dock; also
`/` or Ctrl/Cmd+K), **activity** (a ring that fills while anything is being
worked out; opens the tray), and one menu for Guide and Settings. The brand
goes to Home. On a phone: three views in the bottom bar and Ask as a floating
button above it.

### Home (`/home`, where sign-in lands)

Answers "what needs me today" in one screen:

- **Now on the Moon**: the south pole with the real terminator for this minute
  (`useSubSolar`), the manager's project targets pinned, a UTC clock.
- **Your projects**: a card each (name, next dated event with a countdown, the
  six steps as a small journey strip coloured by state), and **New project**.
  Empty state: the two ways to start (drop a file, fill the form) and three
  CLPS missions to explore.
- **Being worked out**: live from `/activity`, with progress.
- **Needs you**: steps in `needs_input` or `no_data` across the manager's
  projects, each one click from the form or a scenario.
- **Live**: space weather now and the feeds' ages, one line each.
- **Ask** bar with suggestion chips, front and centre.

### Ask dock (every page)

A panel from the right (a sheet on a phone). Conversation with history for the
session, context chip ("About IM-3 · Launch"), suggestion chips, follow-up
chips, action links into the app, and *How the AI got this* on every answer.
`POST /agents/chat`. Answers are two to four sentences on the light model
chain; the guard applies; without a model it answers from rules and the
measurements and says so.

### Projects (`/projects/new`, `/projects/:id/edit`)

One page, two ways in:

- **Drop a file** (PDF, DOCX, TXT, MD, CSV, JSON; 8 MB). Staged progress
  (reading, finding the facts, filling the form). The form arrives filled;
  each field shows *from the file* with the quoted evidence and page on hover
  or focus, *worked out* for inferences, or stays empty. Nothing is saved
  until the manager presses Save.
- **Fill it in**: the same form, empty. Grouped as the journey: Mission,
  Landing spot (pick a surveyed site on the map or type coordinates), Dates,
  Launch (vehicle and pad from the catalogues), Spacecraft and radio, Payloads.
  Only the name is required; an unknown field stays unknown and the step that
  needs it offers a scenario.

A saved project is a mission (`origin: 'project'`): it opens in the same hub
with the same six steps, is listed first on Missions under *Your projects*,
and survives a re-seed of the CLPS records. A new coordinate gets its skyline
built as a job (`site_build`) with progress.

### Scenarios (inside a mission's step)

Where a step is `no_data`, the panel no longer stops at "not published". It
offers **Explore a scenario**:

1. Presets as cards ("Most likely: Falcon 9 from LC-39A, landing Q4 2027"),
   opening at once.
2. A prompt ("launch on Falcon Heavy in March, 10 days on the surface") read
   into the assumption form by `POST …/scenarios/interpret`; the reading is
   shown back and every field stays editable. Or the form alone.
3. **Work it out**: phases with real progress (*Checking live sources* →
   *Launch opportunities* → *Trip* → *Contact*), and a line that says the other
   pages are free to use meanwhile. The activity ring shows it everywhere and
   a toast links back when it is done.
4. The answer in the step's normal layout under a **Scenario** band naming the
   assumptions and their bases, with *Edit assumptions* and *Save as…*.

### The mission hub as a journey

The six cards become one drawn path from Earth to the Moon with six stops.
Each stop shows its state by shape and words (not colour alone), its one-line
answer, and where data is missing, *Explore a scenario*. The record and target
stay below.

### Motion and feel

Arrivals, the journey drawing itself, numbers counting up to their value once,
the terminator moving, the activity ring. All through the existing motion
tokens, each with a reduced-motion branch. Amber still means sunlight and cyan
Earth; scenario gets its own treatment (a dashed outline and a hatch, never a
new hue that could read as a state).

## Backend

| Endpoint | Auth | What |
|---|---|---|
| `GET /projects/options` | public | Choices for the form, from the catalogues |
| `POST /projects/intake?filename=` | named | Raw file body → `IntakeDTO` (draft + evidence) |
| `GET /projects` | public | The team's projects |
| `POST /projects` · `PUT /projects/{id}` | named | Save → `ProjectSavedDTO` |
| `DELETE /projects/{id}` | named | Projects only; a catalogue record is refused |
| `GET /missions/{id}/scenarios/gaps` | public | What is missing, the fields, presets, suggestions |
| `POST /missions/{id}/scenarios/interpret` | signed in | Prompt → assumptions (no computing) |
| `POST /missions/{id}/scenarios` | named | Start (or join) → `ScenarioDTO` |
| `GET /missions/{id}/scenarios` | public | List, presets first |
| `GET /scenarios/{id}` · `DELETE /scenarios/{id}` | public · named | Progress, then results |
| `POST /agents/chat` | signed in | Quick answer → `ChatResponseDTO` |
| `GET /activity` | public | Jobs and scenarios in progress and just finished |

`MissionBrief`/`MissionDetail` gain `origin` and `owner_name`; a `Source` gains
`kind`.

**Projects** live in `missions` with `origin = 'project'`, `owner_id`,
`created_at`, `updated_at`. `MissionRepository.replace_all` replaces catalogue
rows only. Ids are `p-<slug>`; a clash gets a suffix. Migration
`f3a5c7e9b1d2` (down `e1b3d5f7a9c2`) also creates `project_intakes`.

**Intake** takes the raw body (no multipart dependency), under its own size
limit (`PW_MAX_UPLOAD_BYTES`, 8 MB; `BodyLimit` gets a per-path override). With
a model key the file goes to the model (PDFs natively) with a response schema
of the form plus evidence per field; the guard checks every extracted number
and date appears in the file's text. Without one, rules: dates, coordinates,
catalogue names (vehicles, pads, providers, landers, sites), masses.
`pypdf` is an optional import for the rules path on PDFs; when it is absent the
answer says a PDF needs the model.

**Scenarios**: table `scenarios` (migration `a7c9e1b3d5f8`, down
`f3a5c7e9b1d2`). One job kind, `scenario`, in the compute worker:

1. *inputs*: resolve each field in order you → published → live → default.
   Live: Launch Library 2 for this mission's listed launch (date, vehicle,
   pad), fetched now through `app.feeds` (rate-limited, stored as a feed
   snapshot); a failed or empty fetch falls to the default and says so.
   Defaults: the same provider's or lander's last flown mission, then the
   catalogue's most-used; each default names its precedent.
2. Build a mission record with the assumptions laid over it (never saved) and
   run the existing launch, trip, contact and return calculations on it,
   forwarding their progress. Surface is the site's four numbers over the
   assumed dates.
3. Store one assessment (kind `scenario`); its key is the hash of the
   *canonical* assumptions (dates to the day, days to 0.5, degrees to 0.5,
   ids sorted), so similar prompts share one answer.

The section services gain record-based entry points so the overlay runs the
same code as a real mission. Scenario jobs run below every real job.

**Presets**: for each upcoming mission with a gap, up to three default
scenarios (most likely; the next vehicle/pad precedent; a later landing month)
are queued at the lowest priority when the API starts and after a seed
(`python -m app.workers.presets` does the same on demand). `interpret` returns
`matches_preset` when a reading equals one.

**Chat**: a fifth agent on the asker's tools plus `list_scenarios`, in a quick
mode (light chain, three rounds, short output). The same guard, the same run
log. `actions` are built by the service from the tool calls (which mission,
which section), not by the model.

**Activity**: one query over `jobs` and `scenarios`.

## Workstreams and who owns which files

Agents work in one tree at the same time. **Edit only the files you own.** A
shared file is edited with small, surgical changes after re-reading it, never
reformatted, never reverted. No one runs `git commit`, `git stash`,
`git checkout`, `git reset` or `git clean`.

| | Owner | Files |
|---|---|---|
| A | backend: projects, intake, chat | `app/services/project_service.py`, `intake_service.py`, `chat` in `app/agents/chatter.py`, `app/agents/intake.py`, `app/api/v1/routes/projects.py`, `schemas/projects.py`, `app/db/repositories/projects.py`, `missions.py` (repo), `mission_service.py`, `schemas/missions.py`, `data/ingest_missions.py`, `app/api/limits.py`, migration `f3a5c7e9b1d2`, their tests |
| B | backend: scenarios, presets, activity | `app/services/scenario_service.py`, `activity_service.py`, `app/core/scenario.py`, `app/agents/scenario_reader.py`, `app/workers/handlers/scenario.py`, `handlers/site_build.py`, `app/workers/presets.py`, `routes/scenarios.py`, `routes/activity.py`, `schemas/scenarios.py`, `repositories/scenarios.py`, `launch_service.py`, `trip_service.py`, `contact_service.py`, `return_service.py`, `sections_service.py`, migration `a7c9e1b3d5f8`, their tests |
| C | frontend: shell, home, Ask, activity, hub journey, motion | `App.tsx`, `components/AppShell.tsx`, `screens/HomeScreen.tsx`, `components/home/*`, `components/ask/*`, `components/activity/*`, `screens/MissionHub.tsx`, `components/lifecycle/JourneyBar.tsx`, `lib/api/home.ts`, `lib/guide.ts`, `components/GuideBar.tsx`, `styles/globals.css`, `screens/LandingScreen.tsx` (sign-in target only) |
| D | frontend: projects | `screens/ProjectNewScreen.tsx` (exports `ProjectNewScreen`, `ProjectEditScreen`), `components/project/*`, `lib/api/projects.ts`, `screens/MissionsScreen.tsx`, `lib/missions.ts`, `components/Sources.tsx` |
| E | frontend: scenarios | `components/scenario/*`, `lib/api/scenarios.ts`, `screens/sections/*.tsx`, `screens/MissionDetailScreen.tsx`, `components/lifecycle/Section.tsx` |

Shared, surgical edits only: `app/db/models.py` (A adds beside `Mission`, B
appends at the end), `app/main.py` (one `include_router` line each),
`app/agents/tools.py` (append your tools), `app/config.py` (append your
settings), `backend/pyproject.toml` (the agents' import contract list),
`.env.example`, `frontend/src/lib/api/client.ts`, `components/ui.tsx`,
`components/Icon.tsx` (add, never change).

URL conventions between the frontend streams, so no stream imports another's
unfinished file: a scenario opens at `/missions/:id/<step>?scenario=<id>` and
the builder at `?scenario=new`; a new project at `/projects/new`; editing at
`/projects/:id/edit`.

## Verification

- Backend: `ruff check`, `mypy`, `lint-imports`, the unit suite
  (`pytest -m "not requires_db and not slow"`), and integration tests written
  for a database even where one is not running on the machine.
- Frontend: `npm run check`, `npm test`, and screenshots of each new screen at
  1440 and 390 wide, both themes, with the API mocked.
- Then the whole thing against a live stack: add a project from a file, open
  its hub, run a scenario from a prompt, watch the tray, ask the dock about it.
