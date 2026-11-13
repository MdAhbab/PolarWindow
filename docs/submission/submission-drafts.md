# Space Apps 2026 submission: drafts

Drafts for the NASA project page and the two videos. Fill every `[ ... ]`. Check every number against the
running app or the report before it goes on the page: nothing here is a substitute for reading it off the screen.

Files in this folder:

| File | For |
|---|---|
| `video-240s.md`, `video-240s.srt` | The long video: master plan, whole script, subtitles |
| `video-30s.md`, `video-30s.srt` | The short video: plan and subtitles |
| `task_wali.md`, `task_ryan.md`, `task_mehrab.md`, `task_tanjamul.md` | Each speaker's words and how to record |
| `task_ahbab.md` | Ahbab's words, the demo voice and the six screen recordings |
| `task_mehedi.md` | Mehedi's words, the film clips, the twelve figure prompts and the full edit |
| `demo-files/` | Example mission briefs to drop into New project during the demo |

Team name: **Sagittarius A\***. In file names, write `SagittariusA` (a `*` is not allowed there).

| Member | Role on the Members tab | Name caption (two or three words) |
|---|---|---|
| Md Ahbab Hamid Khan | Frontend, backend, planning, content, deliverables and deployment | Ahbab · Build and deploy |
| Wali | Backend help and planning | Wali · Backend and planning |
| Tanjamul | Backend and frontend help | Tanjamul · Backend and frontend |
| Ryan | Planning and user survey | Ryan · Planning and survey |
| Mehedi | Deliverables and planning | Mehedi · Deliverables |
| Mehrab | Advised on design | Mehrab · Design advice |

Team: Wali, Ryan, Ahbab, Mehrab, Tanjamul, Mehedi. Speaking order in the long video: Wali (hook), Ryan
(problem), Ahbab (solution and demo), Mehrab (NASA data), Tanjamul (why to trust it), Mehedi (close and
final edit).

Deadlines (Asia/Dhaka), from the Participants Guide:

| What | Limit | Due | Where |
|---|---|---|---|
| Video 2, local judging | under 240 s (aim for 230) | Fri 13 Nov, 6:00 PM (the guide's table says 6:30 PM; the team works to 6:00). Team's own times: final cut 3:00 PM, uploaded 4:00 PM, form filled 5:00 PM | YouTube link in the Google Form, file in the Local Lead's Drive folder |
| Video 3, global judging | under 30 s | Sat 14 Nov, 12:00 PM | YouTube or Vimeo, link in the Google Form and on the NASA project page |
| NASA project page | every field, then Submit | Sat 14 Nov, close of the local event | spaceappschallenge.org |

Both videos must contain: the team name, every member by name, the problem and the challenge, the solution with
a demo of it working, and the NASA data said out loud. English subtitles. No recognisable person under 18.
Credit every generated or third-party asset.

## NASA project page

### High-Level Summary

PolarWindow is a mission browser and planner for NASA's commercial Moon landings (CLPS), built for the challenge
*Lunar Landing Site Navigator*. It answers the question a lander team asks first: is this landing site, on these
dates, workable for my lander? Near the Moon's south pole the Sun and Earth stay close to the horizon, so one
ridge can cut off power and contact for days. PolarWindow takes NASA's laser height map of the pole and NASA's
navigation data, works out hour by hour when the Sun and Earth are above each site's own skyline, and shows four
numbers for any site and dates: time in sunlight, time in contact with Earth, the longest night, and the longest
time without contact. It follows every CLPS delivery through six steps (Ready, Launch, Trip, Surface, Contact,
Return), lets a team add its own mission and try what-ifs, and answers questions in plain words. Every number
says where it came from and how far it could be off. The tool never gives a score or picks a "best" site: it
shows what was worked out and what was not modelled, and the planner decides.

- Live: https://polarwindow.ahbab.tech
- Code: https://github.com/MdAhbab/PolarWindow
- 240-second video: [YouTube link]
- Report: `docs/report/report.pdf` in the repository

### Project Details, block 1: the why, the what, the how

- **Why.** CLPS data is public but scattered: trajectories in NASA's SPICE archive, terrain in the LRO archives,
  ground-station limits in a DSN handbook, mission facts in press kits. A planner has to join them by hand to
  learn what a lander goes through.
- **What.** One browser for every CLPS delivery, flown and planned, with each fact linked to its source and
  "not published" said where that is the truth; and a planner that works out sunlight, contact, launch
  opportunities, the trip, radiation on the way, ground-station passes, relays, and where the booster comes down.
- **How.** A height map becomes a skyline for each site (the outline of hills in every direction). NASA's SPICE
  toolkit gives the Sun's and Earth's positions. Comparing the two, step by step, gives the four numbers, each
  with a margin from the terrain map's error and the time step. Flown missions are checked against their own
  reconstructed trajectories. See the report for each method and its validation.
- **Datasets used**: see "NASA data sources" below.

### Project Details, block 2: community involvement

- **Who benefits.** CLPS provider teams and payload teams choosing sites and dates; students and the public
  who want to follow a lunar delivery without a specialist's tools.
- **Highlighted features.** Six steps for every mission on one line from Earth to the Moon; four numbers with
  margins; marks on every mission that say what each step has (from the record, a worked example, or needs
  input); a worked example for every planned mission, built from named past flights; compare sites one measure
  at a time, with ties shown as ties; assumed values always marked with stripes; an assistant that may state only numbers its tools returned, with a log of how it got each
  one; a printable report and downloads for navigation software.
- **What to know.** Screening-level models, stated as such. Assumed inputs are hatched on screen. Nothing is
  hidden behind a single score.

### Project Details, block 3: tools and technologies

Python (FastAPI, SQLAlchemy, NumPy, SpiceyPy on NASA's SPICE toolkit), PostgreSQL, Redis; React, TypeScript,
Vite, Tailwind CSS, three.js; Playwright and Vitest for tests; Docker Compose; Google Cloud for hosting.
Test counts measured on `main` on 13 Nov, final run: 1,005 backend unit tests (2 skipped), 184 backend integration
tests, 546 frontend unit and component tests, 62 browser tests. 1,797 in all, every one passing.

### Use of AI (every tool, with why and how)

| Tool | Used for | How it is kept honest |
|---|---|---|
| Google Gemini, inside the app ("Ask") | Answering questions about missions and sites in plain words | The model can call only the app's own read-only tools; a guard rejects any answer containing a number or date that a tool did not return; "How the AI got this" shows every tool call. Without a key the app answers from fixed rules. |
| Google Gemini video generation [name the exact tool and version used] | Five short illustrative clips, on the landing page and in the videos (low Sun over the pole, a hill's shadow crossing a lander, Earth setting behind a hill, a crater rim, a descent) | Labelled on the page and in the videos as "Illustration, generated". Prompts: [paste the prompts used]. No data or result comes from them. |
| Google Gemini image generation | Twelve simple line figures shown beside the speakers in the video | Labelled "Illustration, generated". All words on them were added by hand. Prompts are in `task_mehedi.md`. No data or result comes from them. |
| Real-ESRGAN | Upscaling the first set of clips from 720p for large screens [delete this row if the page no longer uses any upscaled clip] | Picture quality only. |
| Claude Code (Anthropic) | Development help: code, tests, review, documentation drafts | Every change is covered by the test suite and the physical models are validated against flown missions (see the report). The team reviewed and owns the code. |

[List anything else used: image tools, music, transcription.]

### NASA data sources used (say these in the videos)

| Dataset | From | Used for |
|---|---|---|
| LOLA south-pole elevation models (80 m, 20 m, 60 m) and SLDEM2015 | NASA LRO, PDS Geosciences | The skyline around every landing site: the core of every sunlight and contact number |
| LOLA 5 m site terrain (PGDA product 78), LROC NAC terrain | NASA GSFC PGDA, LROC | Slope and landing-area checks; rover line of sight |
| Sunlight, Earth visibility and permanent-shadow maps (PGDA product 69) | NASA GSFC PGDA | Cross-checks and the map |
| SPICE generic kernels (DE440 ephemeris, lunar orientation, leap seconds, Earth stations) | NASA JPL NAIF | Where the Sun, Earth, Moon and DSN antennas are at any instant |
| CLPS SPICE archive: reconstructed trajectories of IM-1, IM-2, Blue Ghost Mission 1, Peregrine Mission One | NASA JPL NAIF / PDS | The flown trip of each mission, and validation of the trip model |
| LRO reconstructed orbit | NASA JPL NAIF / PDS | Validation of orbit and relay geometry |
| GRAIL lunar gravity field GRGM1200A | NASA PDS | Orbits near the Moon |
| DSN 810-005 module 301 horizon masks | NASA JPL Deep Space Network | When a ground station can see the Moon |
| DONKI space weather (through CCMC) and OMNI hourly solar wind | NASA GSFC | Space weather now, and radiation on the way |
| Diviner polar temperatures | NASA LRO, PDS | Bounds on lander temperature at a site |
| OSIRIS-REx capsule trajectory, TIMED/SABER | NASA | Validation of the capsule return model |
| KSC field mill network, GLM thunder hours | NASA | Launch weather rules |

Other open data: NOAA GEFS, GEFS reforecast and HRRR winds; ASOS station winds (Iowa Environmental Mesonet);
Goldstone radar elevation model. The full list with links and sizes is in `README.md`.

### References

The bibliography of `docs/report/report.pdf` (`docs/report/ref.bib`) and the dataset table in `README.md`.

### Before pressing Submit

- [ ] All six members on the Members tab with photo and role; team photo added
- [ ] Challenge named: Lunar Landing Site Navigator
- [ ] 30-second video link opens in a private window; so do the GitHub link and the live link
- [ ] Use of AI, NASA data sources and References filled in
- [ ] English subtitles on both videos; generated clips credited in the description
- [ ] Submit pressed

## Video credits line (for both video descriptions)

Film clips and drawn figures generated with Google Gemini; illustration only, not mission footage.
Music: [track and artist], YouTube Audio Library. Data: NASA LRO/LOLA, NASA JPL NAIF SPICE and the CLPS SPICE archive, NASA JPL
Deep Space Network, NASA GSFC DONKI and OMNI, NASA GRAIL, NASA Diviner; NOAA.
