# POLAR WINDOW: Test Plan

What is tested, why, and how to run it: the backend suites, the validation
runners that check the physics against flown missions (their results are in
[validation.md](validation.md)), and the frontend's unit and browser tests.

---

## 1. What can go wrong

A test plan is only as good as its threat model, so this one starts from the
failure modes, not from the pyramid.

| # | Failure | Why it is dangerous | Caught by |
|---|---|---|---|
| R1 | Longest-run or gap detection is off by one | **Silent.** It produces a plausible number: 63 h against 64 h looks fine and is wrong. | §3.3 property tests |
| R2 | A refactor quietly changes the geometry | Numbers drift with no error, until they contradict a published figure. | §4 golden tests |
| R3 | An agent invents a number | It destroys the credibility of the whole product in one sentence. | §6 guard tests |
| R4 | A kernel or DEM is missing and the system degrades silently | A flat horizon presented as terrain is worse than an error. | §3.2, §3.4, §5 |
| R5 | An ENU or azimuth convention error near the pole | `cos(lat)` goes to 0, so the textbook formula loses precision exactly where this product lives. An error of 180° in azimuth is plausible and looks like terrain. | §3.1 |
| R6 | Unit confusion (seconds and hours, degrees and radians, longitude east and west) | Classic, and this system converts at three boundaries. | §3.1, §5, §9.1 |
| R7 | A cache key collision across engine versions | It serves stale geometry that looks current. | §5, §9.1 |
| R8 | A mission fact loads without a source, or a null field is shown as a value | The screen renders it like any other fact. Only an expert judge would notice. | §3.5 |
| R9 | Ranking asserts an order that censored values do not support | "Best" looks authoritative, and the flag that contradicts it sits on another row. | §3.5 |
| R10 | A smooth-Moon mask is presented as terrain | The numbers look plausible and are wrong in exactly the way the product promises not to be. | §3.5, §4, §5 |
| R11 | Calendar buckets cut a night in two and report both halves as measured | The longest-gap column silently shrinks. | §3.5 |
| R12 | The grounding guard rejects every mission date, or grounds everything because the pool grew | In the first case the agents fall back forever. In the second the guard stops guarding. | §6 |
| R13 | A live feed fails quietly and an old number looks current | A forecast that is days old reads like a forecast for today. | §7.2 |
| R14 | A record is changed by no one, or a change skips the history | The audit trail is the evidence that the team's entries are the team's. | §7.3 |

R1, R2 and R3 get the most attention below because they are the three that fail
*quietly*. Everything else throws.

---

## 2. Running the suites

### 2.1 What runs where

| Command | Runs | Needs |
|---|---|---|
| `make test-fast` | `app/tests/unit` and `golden/test_synthetic_golden.py` | Nothing. No services, no kernels. Under 20 s. |
| `make test-int` | `app/tests/integration` | Postgres and Redis, and the test database (`make test-db`) |
| `make test-geo` | `app/tests/golden` | The SPICE kernels and the terrain subset (`make seed`); the CLPS trajectory kernels for the reconstruction tests |
| `make test` | `make test-db`, then every test | A seeded development database |
| `make test-db` | Rebuilds `polar_window_test` from the migrations plus a copy of the seeded rows | A seeded development database |
| `make test-fe` | The frontend's unit and component tests (vitest) | Nothing |
| `cd frontend && npm run e2e` | The browser tests (Playwright, with axe) | The API on :8000, seeded |
| `make lint` | ruff, mypy `--strict`, the import-linter contracts | Nothing |
| `make load-compute` | The load run of the compute queue (§7.4) | Postgres |
| `make validate-*`, `make hindcast-*` | The validation runners (§8). They are tools, not tests. | Data and, for some, the network |

`make test-fast` is the quickest way to see whether a change to the physics broke
anything. Run it before and after touching `backend/app/core/`.

There is no hosted CI. Running `make lint`, `make test`, `make test-fe` and e2e is the
gate before a merge. `make test` includes the golden tests against real inputs, so it
covers a change to `core/` or `data/` too.

### 2.2 Markers and rules

The markers are declared in `backend/pyproject.toml`. A missing input turns a
test into a **skip with a reason**, never an error, so `make test-fast` runs on a
laptop with nothing installed.

| Marker | Meaning |
|---|---|
| `requires_kernels` | Needs the SPICE kernels on disk |
| `requires_dem` | Needs the LOLA terrain subset on disk |
| `requires_db` | Needs a live Postgres |
| `requires_clps_spice` | Needs NAIF's CLPS trajectory kernels (`data/clps`) |
| `requires_feed_fixtures` | Reads the recorded feed responses in `app/tests/fixtures/feeds` |
| `requires_gravity` | Needs the GRAIL GRGM1200A gravity field (`data/gravity`) |
| `slow` | Takes more than a few seconds. None is in `make test-fast`. |

The rules that keep the suite honest (`app/tests/conftest.py`):

- **The suite has its own database and Redis index.** `polar_window_test` and
  Redis database 1 (`PW_TEST_DATABASE_URL` and `PW_TEST_REDIS_URL` override the
  names). Running the suite never changes what the development API serves. If the
  test database is unreachable the tests skip, and are never pointed at the
  development database.
- **No test reaches a real model.** An autouse fixture blocks
  `app.agents.base._generate`, our own seam. `fake_gemini` scripts that seam.
  `gemini_http` restores the real SDK call and scripts Gemini's HTTP responses
  with `respx` (the SDK's async client speaks httpx), and every other request
  fails.
- **Tests call the app in process** through an ASGI client, with no live server.
  `client` is signed in with a name as the project manager (ADR-17).
  `anon_client` has no session.
- **Deprecation warnings raised in `app.*` are errors** (`filterwarnings`), and
  coverage leaves out `app/tests` and `app/validation`.

---

## 3. Unit and property tests (`app/tests/unit`)

Pure `core/` code: no database, no network, no clock. `core/` is designed for this
(`docs/system-design.md` §2), and the test suite is the reason the design rule
exists.

### 3.1 Look angles (`test_visibility.py`, `test_projections.py`) (R5, R6)

The pole is where this breaks, so the cases live there.

- The ENU basis is orthonormal and right-handed for random latitudes and
  longitudes, including −90° and −89.999°. A sign flip would otherwise show up
  only as a 180° azimuth error.
- The zenith is 90° with a finite azimuth. A target at right angles to the
  vertical is at elevation 0. Targets due north, east, south and west of a site
  give azimuth 0, 90, 180 and 270.
- **Pole stability.** A target swept a full turn round a site at −89.9999° never
  makes the azimuth jump by a degree. The spherical-trigonometry formula fails
  this and the unit-vector form passes.
- Subtracting the site vector matters for Earth's distance.
- The three visibility states (lit, penumbral, dark) come out right.
- `test_matches_frontend_reference_implementation` keeps a frozen transcription
  of the deleted TypeScript `lookAngles` as a second opinion, agreeing to 1e-9.

### 3.2 Skyline (`test_horizon.py`) (R2, R4)

The ray-march is tested against surfaces whose horizon is known by hand. That is
the only way to test a ray-marcher without testing it against itself.

| Surface | What must hold |
|---|---|
| Flat plane | Every bearing equal and slightly **below** level from curvature alone. This is the assertion a clamp at zero would break. |
| One cone (400 m at 3,000 m) | The peak elevation to 0.05° and its bearing to 0.5°. |
| A wall over a bearing band | The elevation to 1e-4° inside the band, and below level outside it. |
| A 10° ramp | +10° uphill and −10° downhill, to 0.1°. |
| A crater bowl (radius 5,000 m, rim 800 m) | A raised skyline all round, equal to the rim angle to 0.15°, and symmetric to 0.01°. |

Also pinned:

- Curvature: the drop is 115.1 m at 20 km and 719.5 m at 50 km, and leaving it
  out changes a far blocker.
- A thin, tall feature (60 m at 300 m) is still found, so the step schedule
  cannot skip a near ridge.
- **Noise floor.** A 1.5 m rise 45 m away, against a 2 m DEM error, does not
  become a blocker. The march starts beyond the resolvable scale (two posts out).
- Missing terrain lowers `coverage` instead of being clamped into a plateau. A
  site outside the DEM is an error, not a guess.
- A ray starting in a hole or nodata post advances to the first finite sample,
  never evaluating to minus infinity.
- **SLDEM2015 coverage and samplers** (`test_sldem.py`): label geometry parsing,
  window bounding geometry, local ENU to selenographic coordinate mapping, bilinear
  sampling with boundary-pixel clamping and nodata corner propagation, and synthetic
  cone terrain verifying elevation and azimuth accuracy.
- Downsampling takes the maximum of each group, never the mean, and a step that
  does not divide 360 is refused.
- A mask is reproducible, and the compiled and plain-Python kernels agree
  (`test_numba_and_python_agree`: elevation to 1e-4°, ranges, tolerances and
  coverage exactly).

### 3.3 Intervals and the four numbers (`test_intervals_properties.py`, `test_metrics.py`) (R1)

This is the highest-value block in the plan. `intervals.py` knows nothing about
astronomy: it takes a time array and a boolean or margin array and returns runs.
That is what makes universally quantified properties possible.

**Strategy.** `hypothesis` over arbitrary boolean arrays, plus explicit examples
for every degenerate shape.

**The properties:**

1. **Partition.** The run durations add up to the span, exactly. No time is lost
   or counted twice. This one property kills most off-by-one bugs.
2. **Alternation.** No two adjacent runs share a value.
3. **Contiguity.** Each run starts where the last one ended.
4. **The longest run is a member and maximal**, stated both ways on purpose:
   `max()` over the wrong filtered set passes the second half alone.
5. **Inversion symmetry.** The runs of the inverted series are the runs with
   their values flipped. It catches asymmetric handling of the first and last run.
6. **Concatenation.** Joining two series adds their run counts, or one fewer when
   the join continues a run, and then the joined run's duration is the sum. This
   is the boundary bug at a chunk edge.
7. **Idempotence** of merging short gaps, and **monotonicity** of the longest run
   in the merge threshold.
8. **Threshold monotonicity.** Up-time never rises as the threshold rises. It
   catches a flipped comparison.
9. **Bisection.** A refined crossing lies inside its bracket, and a bracket whose
   ends are both near zero (a graze) returns the midpoint.
10. **Set algebra.** Union, intersection, complement and clip agree with the
    pointwise logic, and a touch inside a night does not split it.

**Degenerate examples**, pinned rather than left to the generator: empty, one
sample, all true, all false, alternating every sample, and a single true at the
first and at the last index. That is where the classic off-by-one hides.

**Metrics.** For any pair of series: sunlit plus dark equals the span, each
longest gap is at most its total, and the worst compound event is at most the
shorter of the longest night and the longest blackout. Beyond that:

- The four numbers come out right from hand-built arcs. A compound event is the
  intersection of both being down, and two intervals that only touch make none.
- **Survival is the whole night, not the blackout**, when the blackout falls
  inside it, and it is the longest night even when no blackout exists.
- A night cut by the window is flagged as a lower bound, and an interior night is
  not.
- `test_metrics_has_no_composite_score` (unit and integration): neither the
  metrics model nor the `/metrics` response has a `score`, `rating`, `overall`,
  `index` or `grade` field. A product rule made executable.

### 3.4 SPICE and kernels (`test_spice.py`, `test_kernels.py`) (R4, R6)

`spice.py` is the only importer of spiceypy. It is tested with the real kernels
when present (`requires_kernels`).

- The UTC to ET round trip holds across a leap second. The Sun is about one
  astronomical unit away and Earth a lunar distance away, which catches a frame
  or observer mix-up at once.
- `MOON_ME` is not `MOON_PA`. Furnishing only the principal-axis frame and
  calling it the mean-Earth frame is a documented trap, and this asserts that
  the two differ. Rotations are proper rotations, and GM matches DE440.
- A missing kernel raises with the file name, the NAIF URL and the fix, asserted
  on the string because that message is the main defence against the most common
  failure. A truncated file and a checksum mismatch are refused before use,
  every problem is reported at once, and every required kernel has a pinned
  digest (ADR-18).

### 3.5 Missions, ranking, calendar, surface windows (R8 to R11)

- **Mission data** (`test_missions_data.py`, pure, on the committed
  `data/missions.json`). Every record validates. Every record and payload has a
  source. A null field must be listed in `unconfirmed_fields`, and a silent null
  fails. Dates are ordered, ids are unique slugs, and coordinates carry their
  kind and source. A record without a source fails the **whole** load. Feature
  centres share one site. Terrain exists only inside the polar model. The v2
  fields (launch, comms and the rest) follow the same rules, and a launch instant
  must be to the minute.
- **Ranking** (`test_rank_properties.py`, hypothesis). A censored item beats
  nothing on a smaller-is-better metric. `1 ≤ rank_min ≤ rank_max ≤ n`. Input
  order changes no range. Removing an item never widens another's range. An item
  is never "best" while something it is incomparable with is censored. Mirroring
  a larger-is-better metric is the same as negating it. The reviewed case
  (Connecting Ridge 122 ± 17 h, de Gerlache rim ≥ 112 h, Malapert ≥ 288 h) gives
  ranges [1,2], [1,3] and [2,3], and declines to call the lower bound best.
- **Calendar** (`test_calendar.py`). Bucket edges partition the window. A night
  split by a boundary is open on both sides, and a night inside a bucket is
  measured. Up-time sums across buckets.
- **Surface windows** (`test_surface_window.py`). Published, planned and assumed
  windows follow their rules, a year is not a window, and a lost mission has no
  surface time.
- **Terrain flag and coverage.** The smooth mask is flat and flagged (`test_calendar.py`),
  targets covered by fine LOLA 60S or SLDEM2015 windows report `terrain_modelled: true`
  with cited product provenance, and targets outside coverage report `terrain_modelled: false`
  (`integration/test_api.py`, `test_missions_data.py`).

### 3.6 Uncertainty, engines, registry, data sharing

- `test_quantity.py`: a number with no margin and no reason is refused, exactly
  one margin form is allowed, and a shared probability carries an exact interval
  (ADR-9).
- `test_engines.py`: the surface version is the pair of surface engines, a
  closure is order-free, and the surface cache key format is unchanged (ADR-13).
- `test_registry.py`: dataset ids are unique, every kernel is registered once,
  every download has an address, and **the README's "Required data" table matches
  the registry byte for byte**.
- `test_data_share.py`: an export comes back whole, a damaged file is not used,
  a file already present is never replaced, a manifest cannot write outside
  `data/`, and only what git ignores is exported.
- `test_offline.py`, `test_request_limits.py`, `test_auth_service.py`: offline
  mode refuses downloads and the model, request limits, and session tokens
  (§7.3).

---

## 4. Golden tests (`app/tests/golden`) (R2)

**What is pinned.** Three sites chosen to exercise different physics:

| Site | Why this one |
|---|---|
| `connecting-ridge` (−89.44°) | Near-polar, high and open: terrain decides, not season. |
| `malapert-massif` (−85.99°) | Far enough out that the Sun genuinely sets, so it is seasonal. It catches an ephemeris error a polar site would mask. |
| `faustini-rim` (−86.64°) | Sheltered and low: a long night that no single ridge is responsible for. |

**Fixtures** (`app/tests/golden/data`):

- `{site}.horizon.npz`: the 1,440-entry `el_deg`, `range_m` and `tol_deg`.
- `{site}.timeline.npz`: azimuth, elevation and margin for both bodies over a
  fixed window (2027-03-14T00:00Z plus 708.734 h, 900 s step).
- `{site}.metrics.json`: the four numbers, arcs and compound events.
- `MANIFEST.json`: the engine version, the kernel names, byte counts and SHA-256
  digests, each site's DEM product and coverage, the tolerances, the generating
  command and the reason for the last regeneration.

**Tolerances**, each justified:

| Quantity | Tolerance | Why this value |
|---|---|---|
| Horizon `el_deg` | ±0.05° | Below the DEM's own contribution (±2 m at 1.4 km is ±0.08°), so it catches drift without failing on float noise. |
| Azimuth and elevation | ±0.01° | An order below the horizon tolerance. |
| Arc edge times | ±72 s | Bisection converges to about 1 s. 72 s allows a step-schedule tweak but not a logic change. |
| The four numbers | ±360 s absolute **or** ±0.1 % relative, whichever is larger | A 300 h night and a 4 h arc need different scales. |
| `worst_compound_s` | ±180 s | Tighter: it is an intersection, so errors compound and a loose bound would hide them. |

**How a failure reports.** A golden failure never prints "arrays differ". The
comparator names the quantity, the worst offending index and where it is (an
azimuth or a timestamp), both values and the tolerance. A golden test that is
annoying to read gets updated reflexively, which destroys its value.

**Regeneration is deliberate.** `make golden-update` refuses unless
`GOLDEN_UPDATE_REASON` is set, and writes that reason into `MANIFEST.json`. A
golden diff in review is the signal that a refactor changed the physics, and it
must be impossible to produce by accident.

**The kernel and terrain problem.** The goldens depend on about 130 MB of kernels
and a terrain subset, which are not committed. So there are two layers:

- `test_geometry_golden.py` needs the real inputs (`requires_kernels`,
  `requires_dem` and `requires_db`). It rebuilds the horizon from the DEM, and
  checks the stored horizon, the timeline and metrics and the manifest.
- `test_synthetic_golden.py` runs **the same code paths** against the analytic
  surfaces of §3.2 and a stub ephemeris. It always runs, including with no
  kernels. It is what keeps the safety net alive in local development, and it
  catches most refactor drift because most refactors are not ephemeris-specific.

The other golden tests pin the reconstruction checks of §7.1 and §8
(`test_propagate_vs_clps.py`, `test_eclipse_vs_spice.py`,
`test_launch_vs_clps.py`, `test_loops_vs_clps.py`, `test_capsule_vs_orex.py`,
`test_clps_landing.py`: touchdown instant to the second, position and Sun/Earth
elevations against NAIF EDL/LS reconstructions), the Blue Ghost 1 sunset
(`test_hindcast.py`: it falls on the reported date) and the resolved candidate
sites (`test_sites_golden.py`).

---

## 5. Integration tests (`app/tests/integration`)

Real Postgres (`polar_window_test`), real Redis (database 1), the app called in
process, and Gemini scripted always. The test database holds the migrations and a
copy of the seeded rows (`make test-db`), so the tests exercise real masks and
metrics without recomputing them.

**Contract (R6, R4).**

- The OpenAPI document is emitted and complete, and `docs/openapi.json` matches
  the app (`test_openapi_document_in_docs_matches_the_app`). Run `make codegen`
  when it fails.
- The timeline, windows and metrics answers carry `meta`, and `meta.uncertainty`
  is neither absent nor null (`test_meta_is_present_and_uncertainty_is_never_null`,
  parameterised). Durations are seconds and never hours, and no field is named
  `_h`.
- A site list summary is null, not zero, when a site is unseeded. An unhandled
  failure is still a problem detail the browser can read.

**Behaviour.**

| Test | Asserts |
|---|---|
| `test_window_is_quantised_so_the_slider_hits_cache` | Starts seconds apart (41 s, 7 min 13 s, 14 min 59 s) collapse onto one window: the same `start`, the same numbers and a cached answer. This is the slider's central mechanism, and untested it would silently regress. |
| `test_step_out_of_range_explains_the_limit` | A step of 10 s gives 422, and the error says what still works. |
| `test_calendar_refuses_more_than_two_years` | A span over 730 days gives 422. |
| `test_compare_agrees_with_the_per_site_endpoint` | `/compare` and `/metrics` return identical numbers. They share a service, and this proves it stayed shared. |
| `test_compare_rejects_too_many_sites`, `test_compare_survives_one_unsurveyed_site` | More than 8 sites is 422. One unsurveyed site never blanks the comparison. |
| `test_compare_declines_to_call_a_lower_bound_best` | The reviewed case: de Gerlache rim is `censored` with `rank: null` and a range wider than one place, and no item is ranked 1 while it has an incomparable neighbour. It skips if the reference window no longer cuts that night. |
| `test_healthz_reports_every_dependency` | `/healthz` names every dependency. |
| `test_tile_out_of_extent_is_204_not_404`, `test_tile_etag_round_trip` | A tile in the grid with no data is 204. A conditional request gets 304. |
| `test_cors_allows_the_vite_dev_server` | The single most common "it works in curl" failure. |
| `test_concurrent_burst_is_consistent_and_fast` | 15 overlapping requests across three sites after a warm-up: all 200, all served from cache, averaging under 0.5 s. A loose bound, and the only timed assertion on the slider. |
| `test_missions_filter_by_payload_type`, `test_mission_detail_is_sourced_and_honest`, `test_unknown_mission_is_a_problem_detail` | Mission filters, sources and 404s as problem details. |
| `test_default_site_list_is_unchanged_by_mission_targets` | `kind=candidate` is the default and returns the original list. |
| `test_a_target_outside_the_polar_model_says_so` | `terrain_modelled: false` and a note in `meta.uncertainty`. |

The engine version is part of every cache key (R7), and a payload rebuilt from
memoised geometry says so.

---

## 6. Agent tests

**No test ever calls the real Gemini API** (§2.2). Model responses are scripted
at our own seam (`fake_gemini`) or at the HTTP layer through the real SDK
(`gemini_http`, with five cases: a grounded answer, a hallucinated number,
schema-invalid output, a timeout and an outage).

### 6.1 Guards (`unit/test_guards.py`, pure) (R3)

`guards.check` is a pure function of the parsed output and the collected tool
results, which makes this the easiest high-value block in the project.

- A grounded answer passes, and its provenance maps each claim to a tool and a
  field. An invented number is rejected and named. Rounding within the stated
  precision is allowed ("80 %" for 0.7983), and per cent and fraction are one
  claim.
- **A correct derived number is still rejected.** If the tools gave 204,120 s and
  708.7 h, "288 hours of sunlight" is a right division and is rejected anyway:
  the guard cannot tell correct arithmetic from lucky arithmetic, so derivations
  belong in tools.
- Seconds to hours and days are allowed conversions. Ordinals, years and small
  counts are exempt, so the guard is not uselessly strict.
- A number hidden in a structured field is checked, not only the prose. With no
  tools called, every number is forbidden.
- Dates: a date the tools returned is grounded, an invented one is rejected, and
  a month or a year alone is not a date claim.
- Verdict words are rejected in any answer field, even in a denial, and the
  user's own words may carry one. Evidence words are not verdicts.
- The user's threshold cannot ground a measured value.
- `insufficient_data` needs a reason. The advisor must state a negative result.

### 6.2 Orchestration (`integration/test_agents.py`, `test_agents_http.py`)

- Happy path: a run and its tool calls are recorded, with latency and tokens.
- A hallucinated answer is rejected, repaired and then passes, and the first
  rejection stays in `guard_failures`. **Two rejections degrade** to the
  deterministic summary, and the bad text is never rendered.
- Schema-invalid output is retried. A timeout degrades within the budget. A total
  outage degrades rather than answering 500, and the four numbers stay available.
- Tool arguments are validated: a site id of `'; DROP TABLE sites;--` fails the
  argument model and is recorded as a tool error. An unknown tool is refused.
- **Every exit path persists a run**, whatever the outcome. The demo shows this
  table, and a missing row would be a missing proof.
- Without a key every agent degrades into its own contract, with provenance, and
  a missing value is never printed as zero.
- `test_thought_signature_round_trip`: the second request's history carries the
  first response's content, signature part included, byte for byte.
- A model over its quota hands the run to the next in the chain, and when every
  model is over quota the run degrades without asking again.
- Agents declare **exactly ten tools** (`test_agents_declare_exactly_ten_tools`).

### 6.3 Per-agent rules

- **A2 must say so when nothing qualifies:** `satisfied: false` with a
  plain-language reason, and nothing ranked "best".
- **A3's documents share one fact set:** in the degraded answer the planner memo,
  the lesson plan and the public explainer are all present, and the memo and the
  explainer carry the same facts.
- **A4 refuses what the data does not hold** rather than improvising.
- Search rows are trimmed so the numeric pool stays small, the open flags survive
  the trimming, and `get_site` lists a site's missions with no mass or cost
  fields. Every agent response and `GET /agents/runs` carries the full `meta`.

**By hand, before a demo** (the runbook): one live call per agent with the real
key. Prompt quality is not covered by CI, and that is written into the runbook
rather than pretended away.

---

## 7. The mission lifecycle

### 7.1 What each part is checked against

Each part has unit tests (pure engines), integration tests (the API and the
stored answers) and, where a flown mission exists, a golden test. The plan's
tolerance is in the last column, and the measured result is in
[validation.md](validation.md).

| Part | Tests | Checked against |
|---|---|---|
| Propagator and shadows | `test_propagate.py`, `test_eclipse_trip.py`, `golden/test_propagate_vs_clps.py`, `golden/test_eclipse_vs_spice.py` | NASA's reconstructed CLPS trajectories and LRO: 1 km after 24 h and 5 km after 72 h; 1 m for a forward-and-back round trip |
| Launch instants and transfers | `test_launch_core.py`, `golden/test_launch_vs_clps.py`, `integration/test_launch.py` | The flown launches: liftoff worked out again from the flown TLI within 2 min (IM-1, IM-2) and 5 min (Blue Ghost); a designed launch on the right day within 10 min |
| Loops and correction budget | `test_phasing_lincov.py`, `test_lincov_guide.py`, `golden/test_loops_vs_clps.py` | The flown burns (replayed perigees and apogees within an hour, apogee radius within 1 %); the linear budget within 10 % of Monte Carlo at the 95th and 99th percentiles, and a seeded run repeated bit for bit |
| Launch weather | `test_weather_rules.py`, `test_verification.py`, `test_gefs_targeted.py`, `test_hindcast_hrrr.py`, `test_grib_*.py`, `integration/test_weather_checks.py`, `integration/test_weather_return.py` | The rules verbatim; ensembles and HRRR against the Cape's and Vandenberg's stations. Brier skill needs at least 10 cases above the threshold; intervals are Wilson and month-resampled; GRIB2 template 5.0 and 5.3 byte ranges decode against ecCodes |
| Radiation | `test_radiation.py`, `make validate-radiation` | IRBEM against SPDF (5 %), CRaTER (±30 %), NOAA's event list (10 %) |
| Contact | `test_contact_core.py`, `test_contact_relays.py`, `test_relay.py`, `test_orbiter_words.py`, `test_horizons_feed.py`, `test_viewshed.py`, `integration/test_contact.py` | DSN station kernels and horizon masks; JPL Horizons and the LRO reconstruction for orbiter passes; 36 × 36 relay sweeps; rover line of sight and the first Fresnel zone on 20 m terrain, served as zoom 12 tiles in three states |
| Capsule entry | `test_entry.py`, `test_capsule_atmosphere.py`, `test_capsule_air.py`, `golden/test_capsule_vs_orex.py`, `make validate-capsule` | The U.S. Standard Atmosphere 1976 tables; OSIRIS-REx's landing within 10 km |
| Trip gravity | `test_gravity.py`, `test_propagate.py` | EGM2008 to degree and order 8 with Earth's spin, and J2 nodal drift against the textbook rate within 2 %; the GRAIL reader stops at the requested degree. The lunar degrees and switch-on radii across perilune passes are compared by `validate_trip` (§8) |
| Readiness, parts, risks | `test_readiness.py`, `integration/test_ready.py`, `integration/test_audit_and_sign_in.py` | The state machine (one step forward, a date and evidence on every change); every write audited and hash-chained |
| Jobs | `integration/test_jobs.py`, `test_job_ref.py` | One claim per job, leases, back-off, and the waiting messages |
| Feeds | `test_feed_parsers.py`, `test_feed_http.py`, `test_feed_on_demand.py`, `test_feed_age.py`, `integration/test_feeds.py` | Recorded responses; the breaker, retries, and secrets never stored |
| Catalogues | `test_catalogues.py` | Every catalogue loads and its references resolve; weather rules verbatim and classified |
| Registry | `test_registry.py` | Unique dataset ids, addresses, and the README table |

### 7.2 Chaos (`integration/test_chaos.py`) (R13)

For a space weather feed that is **down** (connection refused), **slow** (read
timeout) or **malformed** (an HTML page): the section answers 200, the number is
missing with "the last attempt to fetch it failed", the section's other feed
(DONKI) still answers, Ready, Sections and Return are unchanged, and `/healthz`
says `degraded` (200), never `down`.

**Stale** (recorded three days ago): the number is replaced by its age and limit,
`meta.stale` is true, and `/healthz` is not degraded by it.

**No feed recorded at all:** space weather, launch weather, Return and the other
sections all answer 200, and every space weather value says that no data has been
recorded.

The first run found a real fault: DONKI's lists took their newest event's time as
their age, so a quiet Sun hid them as stale. The parsers now leave the issue time
empty, and a test covers a parser fix reaching a body that has not changed.

### 7.3 The project manager's writes (R14)

Checked on every route that is not a read (`unit/test_request_limits.py`,
`integration/test_jobs.py`, `integration/test_settings_http.py`,
`integration/test_contact.py`, `integration/test_audit_and_sign_in.py`):

- **A named session on every write.** Every non-GET route needs a named project
  manager, except signing in, the site comparison (computed on the request,
  nothing stored) and the four AI helpers (a project manager's session, no name
  needed: they read). A test walks the app's routes, so a new write without it
  fails (`test_every_change_needs_a_named_project_manager`).
- **History on every change.** Settings (the model order, its reset, the model
  retry, clearing the run log, clearing the cache) and job retries are in the
  change history (`entity=settings`, `entity=job`), in the same transaction as the
  change. The history is append-only and hash-chained. It cannot be edited or
  deleted, and a tampered entry is found by verification.
- **Input bounds.** Numbers must be finite (NaN or infinity was once accepted for
  the sea limits and stored). Sea limits, vehicle limits, forecast concerns and
  link, risk scale, ratings and links, booking station and agents' site ids have
  length or size limits. A booked pass is at most 24 hours. Request bodies over
  64 KB are refused (413) before they are read, or while they are read when sent
  without a length.
- **Rate limits.** Per address, per sliding minute: 60 sign-ins, 20 AI questions,
  60 site comparisons and 120 other changes. Past them the answer is 429 with
  `Retry-After`. Reads are not limited. The counts are per API process.
- **CORS allows every method the API has**, PATCH included. It once did not, and
  moving a readiness item failed from the dashboard.
- **Tokens travel in the `Authorization` header, not in cookies,** so a
  cross-site request carries none (no CSRF). A 500 returns a problem detail
  without the trace.
- Session tokens: a changed token, one signed with another secret, an expired
  one and an unsigned (`alg: none`) one are all refused
  (`unit/test_auth_service.py`).

### 7.4 Load on the compute queue (`make load-compute`)

`app/tests/load/load_compute.py` builds its own database (`polar_window_load`,
the migrations and the seeded rows), starts the API on :8011 and two compute
workers against it, and asks for the trip, contact and launch sections of all 20
missions at once, with six more contact windows per landed mission and twelve
more launch windows per planned one: 138 requests, 58 jobs (37 contact, 17
launch, 4 trip). It waits for the queue to empty and reads the times from the
jobs table. The result is `data/load/compute_queue.json`. Measured 2026-09-28 on
an 8-core laptop, two workers:

| | In arrival order | Cheapest first (now) |
|---|---|---|
| Queue empty after | 170 s | 180 s |
| Jobs per minute | 20.4 | 19.3 |
| Workers busy | 86 % | 86 % |
| Wait, all jobs: median / 95 % / longest | 95 / 117 / 127 s | 2.8 / 65 / 123 s |
| Wait, contact (runs 0.1 s) | median 115 s, longest 127 s | median 1.9 s, longest 3.1 s |
| Wait, launch (runs ~10 s) | median 73 s | median 21 s |
| Wait, trip (runs ~55 s) | median 1.8 s | median 71 s |

The API answered every request in the burst within 0.34 s (median 0.21 s; it only
queues), and the same 138 requests again, all stored, within 0.46 s (median
0.37 s, all at once on one API process). Two workers are the limit: throughput is
set by the four trips (a minute each), so a third worker would shorten the queue,
not the longest job.

Two findings, both fixed. Jobs were taken in arrival order, so a 0.1 s contact
plan waited two minutes behind trips (now contact before launch before trip). And
a job queued longer than two minutes said "the compute worker is not running"
while both workers were busy (now said only when nothing is ahead of it). The
queue holds at most 200 waiting jobs. Past that a section answers 503 with
`Retry-After` (`test_jobs.py::test_a_full_queue_*`), because the contact and
launch sections take any window and each new window is a new job.

---

## 8. Validation runners (`backend/app/validation`)

The runners check the engines against measurements the product did not produce:
NASA's reconstructed trajectories, JPL Horizons, flown launches, station
records, CRaTER, IRBEM against SPDF, and OSIRIS-REx's landing. They are **tools,
not tests**: they print the tables in [validation.md](validation.md), and the
golden tests of §4 and §7.1 pin the acceptance numbers so that a change is seen.
Coverage leaves them out.

| Command | Runs | Notes |
|---|---|---|
| `make validate-trip` | The propagator, shadow, launch and loop golden tests, then `validate_trip`, `validate_launch` and `validate_loops` | About 7 min with the loops |
| `make validate-radiation` | `validate_radiation` | Belts, cosmic rays and past events |
| `make validate-capsule` | `validate_capsule` (with `capsule_air` and `capsule_air_data`) | About 20 s. Writes `data/capsule/orex_check.json` |
| `make validate-orbiters` | `validate_orbiters` | Needs the network (JPL Horizons, about 30 requests). Writes `data/contact/orbiters_check.json` |
| `make validate-viewshed` | `validate_viewshed` | Rover line of sight against a brute-force line test |
| `make validate-viewshed-gdal` | `validate_viewshed_gdal` | Independent GDAL viewshed reference on matched lunar raster pixels (99% agreement gate) |
| `make validate-landing` | `validate_landing` | Touchdown instants, positions and surface geometry against NAIF CLPS EDL/LS kernels |
| `make hindcast-weather`, `hindcast-reforecast`, `hindcast-hrrr` | The wind verification in `app/feeds` | Long and cached; see the runbook |
| `make catalogues` | Validates the cited catalogues | |

---

## 9. Frontend

### 9.1 Unit and component tests (`make test-fe`, vitest)

`npm test` runs `src/**/*.test.{ts,tsx}` (jsdom for the components). It is fast
and needs no network.

- **The adapter** (`src/lib/api/adapters.test.ts`) is the one place the wire
  format becomes the shape the screens draw, so it is the frontend code whose
  mistakes are silent: a factor of 3,600 in the wrong place still renders. It
  covers seconds to hours, ISO to hours from the start, snake to camel case,
  `Float32Array` reconstruction, the three visibility states and the window-edge
  flags. The fixtures are captured responses (`src/lib/api/__fixtures__/`), and
  the first test asserts that they are the same numbers the backend pins in
  `golden/data/connecting-ridge.metrics.json`, so a physics change that skips
  the frontend fails here rather than in a demo.
- **Cache keys** (`queries.test.ts`, ADR-2, ADR-19): every key carries the engine
  version and the *quantised* window, each site's `dem_product` is folded into
  site query keys (`horizon`, `windows`, `metrics`, `timeline`, `compare`) so
  transitioning a site to real terrain invalidates cached smooth-sphere numbers,
  a drag inside one step collapses onto one key, and the same sites in either order
  are one query.
- **Exports** (`export.test.ts`): the CSV and the SPICE interval lists are built
  from the same adapted arcs the charts draw. RFC 4180 quoting, matched
  `BEGIN_WINDOW` and `END_WINDOW` blocks, increasing UTC pairs, `# open` on the
  intervals the window cut short, an empty tolerance for a graze, and no
  composite score in the comparison header.
- **Rank labels** (`rank.test.ts`): "best" only when `rank == 1` and the value is
  neither cut short nor over the limit. A tie reads "joint".
- **The lifecycle contract** (`src/lib/api/lifecycle.test.ts`): every
  `Quantity` in every fixture has exactly one margin form or a reason (ADR-9),
  every section answer carries its envelope, and every enum is one the contract
  names.
- **Components** (`States.test.tsx`, `Agents.test.tsx`, `KeyNumbers.test.tsx`,
  `MissionsScreen.test.tsx`, `lifecycle/*.test.tsx`): each data-bound component
  renders its loading, empty, error and uncertain states from fixtures, and an
  error never renders as a loader. Model text is never rendered as HTML (a test
  injects markup). Mission rows are named from the data, and a filter change is
  counted in a live region.
- Also covered: times in words (`format.test.ts`), the sub-solar point recovered
  from a site's Sun track (`subSolar.test.ts`), the guide, the session, and the
  spoken summary.

### 9.2 Browser tests (`npm run e2e`, Playwright and axe)

The tests drive the real app in Chromium (1440 × 900) against the real API on
:8000 and a dev server on :5174 (`E2E_BASE_URL` points them at another build, for
example the offline copy). They run in one worker. `returningVisitor` starts a
signed-in visitor with the guide closed, in either theme. Where the backend does
not answer a lifecycle endpoint yet, the tests marked *contract fixtures* answer
it from `src/lib/api/__fixtures__/lifecycle`, and use the live answer as soon as
there is one. The tests marked *live* always use the API.

| File | What it checks |
|---|---|
| `demo.spec.ts` | The demo path: front page, sign-in, guide, Missions, the volatiles filter, a mission, Compare, the AI run log, the Settings sheet, with no console error or warning |
| `screens.spec.ts` | Every route in **both themes**; every closed row open; the fixed tab bar and every route at **375 px**; empty states; Settings with every project row open |
| `lifecycle.spec.ts` | The six mission sections, the writes (a readiness change asks for a name, needs evidence and shows its history), the weather rules, relays, rover line of sight and the capsule model, each in both themes and at 375 px |
| `degraded.spec.ts` | The API down: the offline copy and its *Saved copy* badge |
| `speaker.spec.ts` | Listen on each page, and the transcript where speech synthesis is missing |
| `webgl-contexts.spec.ts` | Navigates across 3D scenes repeatedly, asserting active WebGL contexts never exceed 1 and each unmounted canvas context is cleanly lost via `loseContext()` |

**Accessibility.** `expectNoSeriousAxe` runs axe with the tags `wcag2a`,
`wcag2aa`, `wcag21a` and `wcag21aa`, and any serious or critical finding fails the
test. It runs on every route in both themes, at 375 px, with every closed row
open, inside the dialogs and on the offline copy. At 375 px the tests also assert
`scrollWidth ≤ 375`, so nothing runs off the side of the page. At 320 px (narrow
mobile / iPhone SE), the header island hides the wordmark to keep all navigation
controls visible without overflow. Axe catches perhaps 30 % of the problems, so it
is a floor. The rules it protects are in `docs/conventions.md`, *Accessibility*.

**No visual regression suite.** Screenshot diffing a canvas-heavy, animated UI
produces flakes, not signal. `npm run screens` retakes the screenshots for the
report.

### 9.3 By hand

Keyboard use and the accessibility tree are checked by hand, and no screen-reader
user has tested the arc list, the mission list or the guide (see the README's
*Known limits*). The pre-demo checks in the runbook cover what no test can:
reading one agent paragraph, and the offline rehearsal.

---

## 10. Coverage

Coverage is a floor, not a goal. These are targets. Nothing enforces them.

| Area | Line | Branch | Why |
|---|---|---|---|
| `core/intervals.py` | 100 % | 100 % | R1. It is the one module where a missed branch is a wrong answer. |
| `agents/guards.py` | 100 % | 100 % | R3 |
| The rank function and the calendar bucketer | 100 % | | R9, R11 |
| `core/` (the rest) | ≥ 95 % | ≥ 90 % | Pure, cheap to test, load-bearing |
| `services/`, `repositories/` and the API routes | ≥ 85 % | | Mostly delegation, and the integration tests carry it |
| `data/ingest_missions.py`, `data/ingest_sites.py` | ≥ 85 % | | Both are inside coverage |
| The frontend's `src/lib` logic | ≥ 80 % | | Components are covered through their states, not by line |

---

## 11. What is deliberately not tested

Named so that absences are decisions rather than oversights.

- **Load and performance**, beyond the one loose timed assertion of §5 and the
  compute-queue run of §7.4.
- **Failover.** The system is single-node by design.
- **Tile pixel values.** Tiles are tested for existence, content type, extent and
  ETag, not for colours. Pinning a colour ramp adds maintenance without
  protecting a behaviour anyone depends on.
- **Real Gemini responses.** By design (§2.2). Prompt quality is checked by hand
  before a demo.
- **Live end-to-end runs against the real feeds.** They are recorded responses
  here.
