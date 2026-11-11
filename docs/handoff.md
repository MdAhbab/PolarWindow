# Handoff: the "experience" work

State on disk as of 2026-11-11, 00:40 (Asia/Dhaka). Everything below was checked by running
the commands shown, not taken from agent reports. **Nothing is committed**: all of it is
uncommitted changes on top of the last commit.

The plan is `docs/experience-plan.md`. The wire contract between frontend and backend is
`frontend/src/lib/api/experience.types.ts`. Read those two before continuing.

## What was asked for

1. Find what is wrong with `run.py`.
2. Make the frontend simpler, and make it feel like an experience.
3. An AI Ask/chat on the dashboard.
4. Let the project manager add a project by file or by hand, with the AI filling the form from a file.
5. For missions with missing data, run a "what if" scenario from a setup or plain words, with a
   progress bar, live values where a source has them, and precomputed common cases.

## Where each part stands

| Part | State | Evidence |
|---|---|---|
| `run.py` fix | Done, not run end to end by me | Compiles; 7 runner tests pass. `.local/tools/pgsql` now exists, so the PostgreSQL bootstrap ran at least once. |
| Plan and contract | Done | `docs/experience-plan.md`, `experience.types.ts` |
| Frontend: add/edit project, fill from file | Built, never seen in a browser | 312 frontend tests pass |
| Frontend: scenario builder, progress, results | Built, never seen in a browser | Same test run |
| Backend: projects, file intake, chat | Code written; tests written (42 pass) | See "Broken right now" |
| Backend: scenarios, presets, activity | Code written; **no tests** | Type-checks; never executed |
| Frontend: shell, Home, Ask dock, activity tray, hub redesign | **Not started.** Only `lib/api/home.ts` exists, and it does not compile | This is the "make it an experience" part |
| Design review from screenshots | Not started | Needs the row above first |
| Live run against a database | Never done | No `.env`; nothing has been run against PostgreSQL |
| Datasets | Mostly downloaded | See the last section |

In short: four of the five build streams have their code on disk, and the one that changes how
the app looks and feels has not been built. No new feature has been exercised end to end.

## Broken right now

Fix these first; each is small.

1. **Frontend type-check fails.** `frontend/src/lib/api/home.ts(49,25)`: `unknown` passed where
   `ActivityDTO | undefined` is expected. Tests still pass (312).
2. **One backend test fails.** `test_request_limits.py::test_every_change_needs_a_named_project_manager`:
   `POST /missions/{id}/scenarios/interpret` is signed-in only by design, so it needs an entry in
   that test's `NOT_A_CHANGE` table (the same way the other AI endpoints are listed).
3. **mypy: 13 errors, all in the new test files** (`test_intake.py`, `test_chat.py`,
   `test_projects.py`). They patch attributes such as `intake_service.get_settings` that the
   module does not export. `app/` itself is clean.
4. **ruff: 6 errors.** Three Yoda conditions in `test_intake.py` (auto-fixable), long lines in
   `test_chat.py:117` and `workers/presets.py:115`, and one old one in `agents/advisor.py:23`.

Passing: the 10 import-layer contracts, and a scan of every changed file for power-cut damage
(none found).

## What is left, in order

1. Fix the four items above.
2. **Backend scenario tests** (none exist): assumption order `you → published → live → default`,
   a missing basis being a gap, canonical keys matching for near-equal inputs, `matches_preset`,
   a scenario never writing to the mission record, presets at lowest priority, the activity summary.
3. **Contract check** of the scenario, activity, project, intake and chat schemas against
   `experience.types.ts`. Not done. The frontend also relies on four things the contract does
   not spell out:
   - a refused project save returns 422 with `detail.errors: [{field, message}]`;
   - `IntakeDTO.fields` uses dotted keys such as `target.lat_deg`, `launch.date`, `lifecycle.*`;
   - an `entered` or `file` source has the person's name in `publisher`, the file name in `title`, and an empty URL;
   - a scenario's contact result always carries `start` and `end`.
4. **Build stream C** (plan, section C): shell with `Home · Missions · Sites` plus Ask and the
   activity ring; Home at `/home`; Ask dock on `POST /agents/chat`; activity tray on
   `GET /activity`; the hub as an Earth→Moon journey; motion. It must also:
   - add routes `/projects/new` and `/projects/:id/edit` in `App.tsx` (the screens exist, nothing links to them yet);
   - add a `.pw-scenario` class in `globals.css` (the scenario UI falls back to a dashed outline without it);
   - keep `?scenario=<id>` on step links, reading `components/scenario/store.ts`.
5. **Run it for real.** `python run.py` from `polarwindow/`, then `alembic upgrade head`
   (new migrations `f3a5c7e9b1d2` then `a7c9e1b3d5f8`). Add `PW_GEMINI_API_KEY` to `.env` or
   every AI feature runs in its rule-based fallback. Then walk the path: add a project from a
   file, open its hub, run a scenario from a prompt, watch the tray, ask the dock.
6. **Design review** from screenshots at 1440 and 390 wide, both themes, and polish.
7. Regenerate `docs/openapi.json` and the frontend `schema.ts`; update the README.
8. Commit, when you say so.

Known gaps left by the finished streams:
- A scenario's Surface step shows four numbers and a sentence, no day-by-day chart (the contract carries no arcs).
- The quiet "What if…" link shows on every available step, including flown missions.
- The unsaved-work guard on the project form does not cover the browser Back button.
- The project form's map and site picker are covered by type-check only.

## Rules to keep

- No Claude co-author or attribution on commits, PRs or pushes.
- At most one Opus and one or two Sonnet agents at a time (Pro plan). Never resume a stopped
  agent; start a fresh one with a short prompt that names the files to read.
- Product rules: no invented numbers, no verdicts or scores, scenario values always labelled
  You / Published / Live / Default and never written to the mission record, every write needs a
  named session, only workers import `app.feeds`.

## How to check the state yourself

```
# frontend/
npm run check
npx vitest run

# backend/
.venv\Scripts\python.exe -m ruff check app
.venv\Scripts\python.exe -m mypy app
.venv\Scripts\lint-imports.exe
.venv\Scripts\python.exe -m pytest app/tests/unit/test_projects.py app/tests/unit/test_intake.py app/tests/unit/test_chat.py app/tests/unit/test_request_limits.py -q
```

## Datasets

In `data/external/` (not in git). `data/external/SOURCES.md` lists each one with its source and
intended use. Nothing in the app reads them yet.

Downloaded and intact: Diviner polar temperature and ice depth (south), CLPS LISTER, CLPS LRA,
JPL periodic orbits (9 families), USAspending CLPS contracts (16 awards), NASA image records
(130), CGI Moon Kit, Robbins crater catalogue, the Barker paper, the Artemis III abstract, and
7 of the 10 PGDA illumination maps.

Still to download (the run was cut off):
- PGDA illumination: `AVGVISIB_65S_240M_201608_EARTH.TIF`, `LPSR_65S_240M_201608.TIF`, `SKYV_65S_240M.TIF`.
- PGDA 5 m site terrain, all nine sites, about 1.6 GB. None fetched yet.

To finish, from `polarwindow/` in Git Bash (finished files are skipped):

```
bash data/external/_tools/fetch_external.sh data/external
```

Not obtainable: Artemis III region coordinates (NASA published names and a map image only) and
the NASA LSP vehicle performance data (a web form, no file or API).

`data/external/_probe` is an empty leftover folder; delete it.
