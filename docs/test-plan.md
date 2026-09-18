# POLAR WINDOW — Test Plan

Status: accepted for M1–M8.
Scope: `backend/`. Frontend coverage is limited to the API adapter, the cache
keys, the exports and the accessibility pass (§7), because the components
themselves are unchanged design.

---

## 0. What can actually go wrong here

A test plan is only as good as its threat model, so this one starts from the
failure modes rather than from the pyramid.

| # | Failure | Why it is dangerous | Caught by |
|---|---|---|---|
| R1 | Longest-run / gap detection is off by one | **Silent.** Produces a plausible number. 63 h vs 64 h looks fine and is wrong. The brief names this as the most likely silent bug and it is right. | §3 property tests |
| R2 | A refactor quietly changes the geometry | Numbers drift with no error. Nobody notices until they contradict a published figure. | §4 golden fixtures |
| R3 | An agent invents a number | Destroys the credibility of the whole product in one sentence. | §6 guard tests |
| R4 | A kernel or DEM is missing and the system degrades silently | A flat horizon presented as terrain is worse than an error. | §5 integration, §2 unit |
| R5 | ENU/azimuth convention error near the pole | `cos(lat) → 0`; the textbook formula loses precision exactly where this product lives. Off-by-180° in azimuth is entirely plausible and looks like terrain. | §2 analytic unit tests |
| R6 | Unit confusion (seconds/hours, degrees/radians, lon east/west) | Classic, and this system converts at three boundaries. | §2 + §5 contract tests |
| R7 | Cache key collision across engine versions | Serves stale geometry that looks current. | §5 integration |

R1, R2 and R3 get disproportionate attention below because they are the three
that fail *quietly*. Everything else throws.

---

## 1. Shape of the suite

```
        ┌────────────────────────┐
        │ e2e  (2)               │  docker-compose up → seed → smoke the 4 numbers
        ├────────────────────────┤
        │ integration (~35)      │  real Postgres, real Redis, mocked Gemini
        ├────────────────────────┤
        │ golden (~10)           │  pinned geometry outputs, tolerance-checked
        ├────────────────────────┤
        │ property (~12)         │  hypothesis over intervals.py and metrics.py
        ├────────────────────────┤
        │ unit (~90)             │  pure core, no DB, no network, no clock
        └────────────────────────┘
```

Targets — coverage is a floor, not a goal:

| Area | Line | Branch | Rationale |
|---|---|---|---|
| `core/intervals.py` | **100 %** | **100 %** | R1. It is 150 lines and it is the one module where a missed branch is a wrong answer. |
| `core/` (rest) | ≥ 95 % | ≥ 90 % | Pure, cheap to test, load-bearing. |
| `agents/guards.py` | **100 %** | **100 %** | R3. |
| `services/`, `repositories/` | ≥ 85 % | — | |
| `api/` routes | ≥ 80 % | — | Mostly delegation; the integration tests carry it. |
| `data/`, `workers/` | ≥ 50 % | — | Scripts. Smoke-tested, not unit-tested. |

Speed budget: `make test-fast` (unit + property + golden) **< 20 s**, no services.
`make test` (everything) **< 3 min**. Anything slower stops being run.

---

## 2. Unit tests — `tests/unit/`, pure `core/`

No database, no network, no filesystem, no `datetime.now()`. `core/` is designed
for this (system-design §2) and the test suite is the reason the design rule
exists.

### 2.1 `visibility.py` — ENU basis and look angles (R5)

The pole is where this breaks, so the cases live there.

| Test | Input | Expected | Why |
|---|---|---|---|
| `test_enu_basis_orthonormal` | 200 random (lat, lon) incl. lat ∈ {−90, −89.999} | E·N = N·U = U·E = 0, all unit, E×N = U | Catches a sign flip in the basis that would otherwise show up only as a 180° azimuth error. |
| `test_zenith_is_90` | target vector = site normal | el = 90°, az undefined-but-finite | Degenerate case must not NaN. |
| `test_horizon_is_zero` | target ⟂ normal | el = 0 ± 1e-9 | |
| `test_azimuth_cardinals` | targets due N/E/S/W of a site at −85° | az = 0/90/180/270 ± 1e-6 | The convention test. North-clockwise, as the API reports every bearing. |
| `test_pole_azimuth_stability` | site at −89.9999°, target swept 0→360° | azimuth monotonic, no jump > step | R5 directly. The spherical-trig formula fails this; the unit-vector form passes. |
| `test_matches_frontend_reference_implementation` | 400 random (site, subpoint) | agrees with an in-test transcription of the original TypeScript `lookAngles` to 1e-9 | Two independently written implementations of the same maths. The TypeScript one has since been deleted — geometry is the server's — so the transcription is kept in the test as the second opinion. |

### 2.2 `horizon.py` — ray-march (R2, R4)

Tested against surfaces whose horizon is known **analytically**, which is the
only way to test a ray-marcher without testing it against itself:

| Surface | Analytic horizon | Test |
|---|---|---|
| Flat plane, h=0 everywhere | `θ(A) = −atan(sqrt(2·h_eye/R))` ≈ 0⁻ for h_eye=0 — i.e. slightly **below** level from curvature alone | `test_flat_plane_horizon_is_slightly_negative`: every bearing equal, negative, matching `−√(2d/R)` at the range where curvature dominates. Asserts we do **not** clamp at zero. |
| Single cone of height H at range D, narrow | `atan((H − D²/2R)/D)` at the cone's bearing, flat elsewhere | `test_single_blocker_elevation_and_bearing`: peak value and `max_el_bearing_deg` both correct ±0.02°. |
| Infinite wall at azimuth band [a,b] | constant inside the band | `test_blocker_angular_extent`: the ±0.25° edges land in the right bins. |
| Linear ramp rising at slope s | `atan(s)` asymptotically, reduced by curvature | `test_ramp_converges_to_slope` |
| Site on a crater rim, floor below | horizon below level toward the floor | `test_crater_floor_lowers_horizon` |

Plus:
- `test_curvature_drop_applied`: same surface with `R_MOON = ∞` vs real; the
  difference at 20 km must equal `d²/2R` = 115.1 m to 0.1 m. A dropped curvature
  term is otherwise invisible for near blockers.
- `test_step_schedule_does_not_miss_a_thin_ridge`: a 6 m-wide ridge at 300 m
  range, where the step is 5 m. Regression guard for a coarsening bug.
- `test_numba_and_python_agree`: the jitted and fallback implementations on the
  same surface, to 1e-6. Non-optional — an `@njit` that silently changes
  semantics (integer division, float32 accumulation) is a real risk.

### 2.3 `intervals.py` — see §3. Unit tests here cover only the named edge cases;
the interesting coverage is property-based.

### 2.4 `metrics.py`

- `test_four_numbers_from_known_arcs`: hand-built arc lists, asserted totals.
- `test_compound_is_intersection`: sun-down ∩ earth-down, including the
  touching-but-not-overlapping case (`end == start` ⇒ no event).
- `test_no_composite_score_field`: asserts the response model has no `score`
  attribute. A guard-rail test for a `conventions.md` invariant — cheap, and it makes
  the rule executable rather than aspirational.
- `test_autonomy_inside_dark`: compound fully inside a dark arc ⇒
  `survival_needed_s` is the whole night, not the blackout.

### 2.5 `spice.py` / `kernels.py` (R4, R6)

`spice.py` is the only spiceypy importer, so it is tested with the real kernels
when present and skipped with a **loud** marker otherwise
(`pytest.mark.requires_kernels`; CI runs them, `make test-fast` does not).

- `test_utc_to_et_roundtrip` including a leap second boundary.
- `test_sun_vector_magnitude`: |SUN−MOON| ∈ [1.47e8, 1.53e8] km. Catches a frame
  or observer mix-up instantly.
- `test_earth_vector_magnitude`: ∈ [3.5e5, 4.1e5] km.
- `test_moon_me_vs_moon_pa_differ`: the two frames must **not** be identical.
  Silently furnshing only the PA frame and calling it ME is a real and
  documented trap; this asserts the difference is the expected ~arcminutes.
- `test_missing_kernel_raises_with_path_and_url`: the error message must contain
  the filename and the NAIF URL. Asserted on the string, because that message is
  the product's main defence against its most common failure.
- `test_kernel_checksum_mismatch_refuses`: a truncated cached kernel must fail
  loudly, not furnsh partially.

---

## 3. Property tests — `tests/unit/test_intervals_properties.py` (R1)

This is the highest-value block in the plan. `intervals.py` deliberately knows
nothing about astronomy — it takes `(t: float64[n], value: bool[n])` or a margin
array and returns runs — which is what makes universally-quantified properties
possible.

Strategy: `hypothesis` with `st.lists(st.booleans(), min_size=0, max_size=400)`
and a monotonic time array, plus explicit `@example`s for every degenerate shape.

**The properties:**

1. **Partition.** `sum(run.duration for run in runs) == t[-1] - t[0]`, exactly
   (to 1e-9). No time is lost or double-counted. This single property kills most
   off-by-one bugs.
2. **Alternation.** `runs[i].value != runs[i+1].value` for all i. No two
   adjacent runs share a value.
3. **Contiguity.** `runs[i].end == runs[i+1].start`. No gaps, no overlaps.
4. **Longest is a member.** `longest_run(v) ∈ {r.duration for r in runs if r.value == v}`
   and `>= every` such duration. Stated both ways deliberately: `max()` over the
   wrong filtered set passes the second half alone.
5. **Inversion symmetry.** `runs(~a)` equals `runs(a)` with values flipped.
   Catches asymmetric handling of the first/last run, which is where off-by-ones
   live.
6. **Concatenation.** For `a + b` where `a[-1] != b[0]`,
   `len(runs(a+b)) == len(runs(a)) + len(runs(b))`; where `a[-1] == b[0]`, it is
   one fewer and the joining run's duration is the sum. This is the property
   that catches a boundary bug at a chunk edge.
7. **Idempotence of merge.** `merge_short_gaps(merge_short_gaps(r, ε), ε) == merge_short_gaps(r, ε)`.
8. **Monotonicity in ε.** `longest_run` after merging gaps < ε is non-decreasing
   in ε.
9. **Threshold monotonicity.** For a margin array, `up_time(threshold)` is
   non-increasing as the threshold rises. Catches a flipped comparison.
10. **Bisection bracket.** If `refine_crossing` is given a bracket where the
    margin changes sign, the returned t is inside the bracket and
    `|margin(t)| < tol`. With `@example` for a bracket whose endpoints are both
    ~0 (a graze).

**Explicit `@example` cases** (these are the ones that break implementations):
`[]`, `[True]`, `[False]`, `[True]*n`, `[False]*n`, `[True, False]`,
`[False, True]`, alternating every sample, and a single `True` at index 0 and at
index n−1. Runs at the very first and very last sample are where the classic
off-by-one hides, so they are pinned rather than left to the generator.

**Metrics-level properties** (a smaller set, on `metrics.py`):
- `sunlit_s + dark_s == window_s`
- `longest_dark_s <= dark_s`
- `worst_compound_s <= min(longest_dark_s, longest_blackout_s)` — a true
  invariant of an intersection, and a sharp test of the compound logic.
- Window subdivision: metrics over `[a,c]` relate correctly to `[a,b] + [b,c]`
  for totals (sum) and bound the longest run (≥ each part's).

---

## 4. Golden tests — `tests/golden/` (R2)

**What is pinned.** For three sites chosen to exercise different physics:

| Site | Why this one |
|---|---|
| Shackleton rim, east shoulder (−89.68°) | Single dominant blocker; terrain, not season, controls the night. The interesting case. |
| de Gerlache ridge (−88.50°) | High and open; near-flat mask. Catches an over-eager blocker. |
| Malapert massif (−86.00°) | Far enough out that the Sun genuinely sets; seasonal, not terrain-driven. Catches an ephemeris error that a polar site would mask. |

**Fixtures committed** (`tests/golden/data/`):
- `{site}.horizon.npz` — the 1440-entry `el_deg`, `range_m`, `tol_deg`.
- `{site}.timeline.npz` — az/el/margin for both bodies over a fixed window
  (2027-03-14T00:00Z + 708.734 h, 900 s step).
- `{site}.metrics.json` — the four numbers, arcs, compound events.
- `MANIFEST.json` — engine version, kernel set + SHA256s, DEM product + SHA256,
  the generating command, and the tolerances below.

**Tolerances** (from system-design N5, and each justified):

| Quantity | Tolerance | Why this value |
|---|---|---|
| horizon `el_deg` | ±0.05° | Below the DEM's own contribution (±2 m at 1.4 km ⇒ ±0.08°), so it catches drift without failing on float noise. |
| az/el | ±0.01° | An order below the horizon tolerance. |
| arc edge times | ±0.02 h (72 s) | Bisection converges to ~1 s; 72 s allows a step-schedule tweak but not a logic change. |
| the four numbers | ±0.1 h absolute **and** ±0.1 % relative, whichever is larger | A 300 h night and a 4 h arc need different scales. |
| `worst_compound_s` | ±0.05 h | Tighter: it is an intersection, so errors compound and a loose bound would hide them. |

**How a failure reports.** A golden failure must not print "arrays differ". The
comparator emits: the quantity, the worst offending index, the azimuth or
timestamp there, both values, the delta, and the tolerance — then writes the new
arrays to `tests/golden/_actual/` so they can be diffed and, if the change is
intended, promoted with `make golden-update`. A golden test that is annoying to
read gets `--update`d reflexively, which destroys its value.

**Regeneration is deliberate and reviewed.** `make golden-update` refuses unless
`GOLDEN_UPDATE_REASON` is set, and it writes that reason into `MANIFEST.json`. A
golden diff in a PR is the signal that a refactor changed the physics, and it
must be impossible to produce accidentally.

**The kernel/DEM problem.** Goldens depend on ~130 MB of kernels and a DEM
subset, which are not committed. Two layers:
- `tests/golden/test_geometry_golden.py` — needs the real inputs, marked
  `requires_kernels` + `requires_dem`, runs in CI where they are cached.
- `tests/golden/test_synthetic_golden.py` — the **same code paths** against the
  analytic surfaces from §2.2 and a stub ephemeris. Always runs, everywhere,
  including on a laptop with no kernels. This is what keeps the golden safety net
  alive during local development, and it is the one that catches most refactor
  drift because most refactors are not ephemeris-specific.

**Cross-implementation check — retired.** This was
`frontend/scripts/check-geometry.ts`, run against the Python engine on the same
synthetic terrain, and it did its job: two independently-written engines agreeing
on the four numbers is strong evidence neither has a structural error. The
frontend engine has since been deleted rather than kept in sync — every number on
screen now comes from the API, and a second implementation that nothing calls is
a liability, not a check. What survives of it is
`test_matches_frontend_reference_implementation` in §2.1, which keeps the
TypeScript look-angle formula as an in-test transcription. The replacement
evidence at the whole-pipeline level is the golden fixtures below, which are
rebuilt from the DEM rather than compared against a stored mask.

---

## 5. Integration tests — `tests/integration/`

Real Postgres (testcontainers, or a compose-provided `polar_window_test`), real
Redis, **mocked Gemini always**. `httpx.AsyncClient(transport=ASGITransport(app))`
— no live uvicorn, so tests are fast and deterministic.

Fixtures: a session-scoped migrated database, a function-scoped transaction that
rolls back, and a seeded set of 3 sites with precomputed masks loaded from the
golden `.npz` files — so integration tests exercise real geometry without
recomputing it.

### 5.1 Contract (R6)

- Every 200 response validates against its pydantic model **and** against the
  emitted OpenAPI schema. Parameterised over all endpoints — one test, full
  coverage of the contract the frontend generates from.
- `test_meta_present_everywhere`: every endpoint's 200 body has
  `meta.computed_at`, `meta.resolution`, `meta.uncertainty`, and `uncertainty` is
  neither absent nor null. Parameterised. This enforces a brief-level rule
  mechanically.
- `test_durations_are_seconds`: field names ending `_s` are seconds and plausible;
  no field is named `_h`. R6.
- `test_openapi_snapshot`: the emitted schema is committed; a diff fails CI. The
  frontend client is generated from it, so an unnoticed contract change is a
  broken frontend.

### 5.2 Behaviour

| Test | Asserts |
|---|---|
| `test_timeline_quantises_window` | Three requests with starts 41 s apart return byte-identical bodies and the 2nd/3rd report `meta.cache == "hit"`. This is ADR-1/§6's central mechanism; untested it will silently regress. |
| `test_timeline_step_bounds` | `step_s` < 300 or > 7200 ⇒ 422 with a usable message. |
| `test_window_too_long` | > 2 years ⇒ 422, not a 30 s hang. |
| `test_missing_mask_returns_uncertain_contract` | A site with no precompute ⇒ 409 problem-detail with `ui.still_works`, **never** zeros. R4. |
| `test_sites_summary_null_when_unseeded` | `summary is None`, not `0`. R4. |
| `test_compare_agrees_with_per_site_metrics` | `/compare` and N× `/metrics` return identical numbers. They share a service; this proves it stayed shared. |
| `test_compare_reports_ties` | Two sites within tolerance appear in `ties`, not silently ordered. |
| `test_compare_rejects_over_8_sites` | 422. |
| `test_engine_version_in_cache_key` | Bump the version, same request ⇒ `cache == "miss"`. R7. |
| `test_redis_down_degrades` | Redis unavailable ⇒ 200 with `meta.cache == "bypass"`, correct numbers. |
| `test_healthz_degraded_is_200` | DEM absent but kernels loaded ⇒ 200 `"degraded"`; kernels absent ⇒ 503. |
| `test_tile_out_of_extent_204` | Not 404. |
| `test_tile_etag_304` | Conditional request. |
| `test_cors_allows_frontend_origin` | The single most common "it works in curl" failure. |
| `test_concurrent_slider_burst` | 40 overlapping timeline requests across 7 sites: all correct, single-flight means the compute counter increments ≤ once per distinct key. |

---

## 6. Agent tests — `tests/integration/test_agents_*.py` (R3)

**No test ever calls the real Gemini API.** `respx` intercepts `google-genai`'s
HTTP transport. A session-scoped autouse fixture asserts no unmocked request
escapes, so forgetting a mock fails loudly rather than costing money and
flaking.

### 6.1 Guards — `tests/unit/test_guards.py`, pure, 100 % coverage required

`guards.check(parsed_output, collected_tool_results) -> Verdict` is a pure
function of two values, which makes this the easiest high-value test block in
the project.

| Test | Scenario | Expected |
|---|---|---|
| `test_grounded_passes` | Every number in the prose appears in tool output | `ok`, provenance maps each claim → (tool, field) |
| `test_invented_number_rejected` | Prose says "72 %", tools said 70 % and 80 % | `rejected`, violation names `72` |
| `test_rounding_allowed_within_tolerance` | Tool said 0.7983; prose says "80 %" | `ok`. Rounding is not invention — the guard compares against the tool value at the stated precision, with an explicit rule. |
| `test_derived_arithmetic_rejected` | Tools gave 204120 s and 708.7 h; prose says "288 h of sunlight" (a correct division!) | **`rejected`.** Deliberate and worth stating: a *correct* derived number is still ungrounded, because the guard cannot distinguish correct arithmetic from lucky arithmetic. Derivations belong in tools. |
| `test_ordinals_and_years_ignored` | "the first site", "2027", "one ridge" | `ok`. A whitelist of non-claim numerics, tested, so the guard is not uselessly strict. |
| `test_percent_vs_fraction` | Tool `0.80`, prose "80 %" | `ok` — the comparator normalises units it knows about. |
| `test_number_in_structured_field_also_checked` | A hallucinated value in `result.metrics.sunlit_h`, not the prose | `rejected`. The guard walks the whole validated object, not just free-text fields. |
| `test_insufficient_data_accepted_without_numbers` | `status=insufficient_data`, reason, no numbers | `ok` |
| `test_empty_tool_results_forbids_all_numbers` | No tools called, prose has any number | `rejected` |

### 6.2 Orchestration — `tests/integration/test_agent_loop.py`

| Test | respx script | Asserts |
|---|---|---|
| `test_happy_path` | tool call → grounded answer | 200, `status=ok`, `agent_runs` row with 2 `agent_tool_calls`, latency and tokens recorded |
| `test_guard_retry_then_success` | hallucinated → repair prompt → grounded | 200 `ok`, `attempts == 2`, `guard_failures` records the first violation |
| `test_guard_fails_twice_degrades` | hallucinated → hallucinated | 200 `status=degraded`, body is the deterministic summary, **no ungrounded text anywhere in the response** (asserted by scanning for the invented number) |
| `test_schema_invalid_retried` | malformed JSON → valid | `ok`, `attempts == 2` |
| `test_timeout_degrades` | respx delays past 20 s | `status=degraded` within ~21 s, deterministic summary returned |
| `test_total_outage_degrades` | connection error | `status=degraded`, 200 not 502 — the four numbers are still available |
| `test_round_budget_enforced` | model calls tools forever | stops at `max_rounds`, `status=insufficient_data` |
| `test_tool_args_validated` | model sends `site_id="'; DROP TABLE"` | tool rejects on the pydantic arg model; no SQL executed; run recorded with the error |
| `test_agent_cannot_reach_db_directly` | import-linter contract | `agents/*` (except `tools.py`) imports no service or repository |
| `test_every_exit_path_persists_a_run` | parameterised over all six statuses | an `agent_runs` row exists in every case. The demo shows this table; a missing row is a missing proof. |

### 6.3 Per-agent contract tests

One each for A1–A4, asserting the pydantic output shape and the agent-specific
rule:
- **A2 must say so when nothing qualifies.** Scripted tools return sites that all
  miss the requirement ⇒ response has `satisfied: false` and a plain-language
  reason, and does not rank anything as "best". This is a named requirement in
  the brief and the failure mode (ranking the least-bad site as if it passed) is
  exactly what a helpful-sounding model does.
- **A3's three documents share one fact set.** Assert the numbers in memo,
  lesson and explainer are identical, not merely consistent.
- **A4 returns `insufficient_data` for an unanswerable question** ("which site
  has the best soil") rather than improvising.

---

## 7. Frontend tests

Deliberately narrow — the components are finished design and re-testing them is
not this plan's job. `make test-fe`; 41 tests, 0.2 s, no DOM and no network.

- **Adapter unit tests** (`src/lib/api/adapters.test.ts`): wire JSON →
  `SiteMetrics`. Seconds→hours, ISO→`tH`, snake→camel, `Float32Array`
  reconstruction, the three visibility states, and the window-edge flags.
  Fed by captured responses in `src/lib/api/__fixtures__/`, asserted against the
  same seconds the backend pins in `golden/data/connecting-ridge.metrics.json`,
  so a physics change that skips the frontend fails here.
- **Query-key test** (`src/lib/api/queries.test.ts`): every key carries
  `engine_version` and the *quantised* window, a drag inside one step collapses
  onto one key, and a comparison of the same sites in either order is one query
  (ADR-2 consequence).
- **Export tests** (`src/lib/export.test.ts`): the CSV and the SPICE interval
  lists are built from the same adapted arcs the charts draw — RFC 4180
  quoting, matched `BEGIN_WINDOW`/`END_WINDOW` blocks, increasing UTC pairs,
  `# open` on the intervals the window cut short, an empty tolerance for a
  graze, and no composite score in the comparison header.
- **Accessibility**: `design:accessibility-review` at M8, plus an automated
  `axe-core` pass on the eight routes. Automated axe catches perhaps 30 % of
  issues, so it is a floor and the manual review is the actual gate — the
  existing `conventions.md` is honest that no screen-reader user has tested the arc
  announcements, and the plan does not paper over that.
- **No visual regression suite.** Screenshot diffing a canvas-heavy, animated UI
  in a hackathon produces flakes, not signal.

---

## 8. CI

```
lint      ruff check + ruff format --check + mypy --strict + import-linter
test-fast unit + property + synthetic golden          (no services, < 20 s)
test-int  integration + agents (Postgres, Redis)      (< 2 min)
test-geo  golden against real kernels + DEM           (cached; nightly + on core/ changes)
```

Kernels and the DEM subset are cached by SHA in CI. `test-geo` runs on every
change touching `backend/app/core/**` or `backend/app/data/**` and nightly
otherwise — it is the slow one and it only matters when the geometry moves.

Gates: `lint` and `test-fast` block every PR. `test-int` blocks merge. `test-geo`
blocks merge **only** when it runs, and its failure output is the golden
comparator's readable diff.

---

## 9. What is deliberately not tested

Named so that absences are decisions rather than oversights:

- **Load/performance testing.** N1 is verified by a single timed assertion in
  `test_concurrent_slider_burst` (p95 under 150 ms warm on CI hardware, generous
  bound). A real load suite is not a hackathon deliverable.
- **Chaos / failover.** N6 says single-node. There is nothing to fail over to.
- **Tile rendering pixel output.** Tested for existence, content-type, extent
  behaviour and ETag — not for pixel values. Pinning a colour ramp adds
  maintenance without protecting a behaviour anyone depends on.
- **The four screens' visual output.** Unchanged design, out of scope.
- **Real Gemini responses.** By design (§6). The consequence is that prompt
  quality is unverified by CI and must be checked by hand before the demo; this
  is written into the runbook as a manual pre-demo step rather than pretended
  away.
