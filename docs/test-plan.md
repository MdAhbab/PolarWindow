# POLAR WINDOW — Test Plan

Status: accepted for M1–M8; **extended 2026-09-23 for the CLPS v2 scope (§10)**.
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
        │ e2e  (0 today → 2, §10)│  Playwright + axe over the demo path
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
| `connecting-ridge` (−89.44°) | Near-polar, high and open: terrain decides, not season. |
| `malapert-massif` (−85.99°) | Far enough out that the Sun genuinely sets; seasonal, not terrain-driven. Catches an ephemeris error a polar site would mask. |
| `faustini-rim` (−86.64°) | Sheltered and low: a long night no single ridge is responsible for. |

(Corrected 2026-09-23, D32: an earlier draft named Shackleton rim and
"de Gerlache ridge"; the committed fixtures have always been the three above.)

**Fixtures committed** (`tests/golden/data/`):
- `{site}.horizon.npz` — the 1440-entry `el_deg`, `range_m`, `tol_deg`.
- `{site}.timeline.npz` — az/el/margin for both bodies over a fixed window
  (2027-03-14T00:00Z + 708.734 h, 900 s step).
- `{site}.metrics.json` — the four numbers, arcs, compound events.
- `MANIFEST.json` — engine version, kernel names and byte counts, per-site DEM
  product and coverage, tolerances and the regeneration reason. **Kernel
  SHA256s and the generating command are not recorded yet (D15); §10.6 adds
  them.**

**Tolerances** (from system-design N5, and each justified):

| Quantity | Tolerance | Why this value |
|---|---|---|
| horizon `el_deg` | ±0.05° | Below the DEM's own contribution (±2 m at 1.4 km ⇒ ±0.08°), so it catches drift without failing on float noise. |
| az/el | ±0.01° | An order below the horizon tolerance. |
| arc edge times | ±72 s | Bisection converges to ~1 s; 72 s allows a step-schedule tweak but not a logic change. |
| the four numbers | ±360 s absolute **or** ±0.1 % relative, whichever is larger | A 300 h night and a 4 h arc need different scales. |
| `worst_compound_s` | ±180 s | Tighter: it is an intersection, so errors compound and a loose bound would hide them. |

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
- **Accessibility**: a manual WCAG 2.1 AA review at M8, plus an automated
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

---

## 10. CLPS v2 and gap closure (2026-09-23)

**Baseline** (`make test`, 2026-09-23): 211 passed in 6.0 s. That is unit 143,
integration 52 and golden 16 after parametrisation. The frontend has 41 Vitest
tests.

This section adds what v2 needs, and names each test the plan above promised
but the suite does not have. Every row below is a test to write, not one that
exists.

### 10.1 New risks

| # | Risk | Why it is quiet |
|---|---|---|
| R8 | A mission fact loads without a source, or a null field is shown as a value | The UI renders it like any other fact. An expert judge finds it; nobody else does. |
| R9 | Ranking asserts an order that censored values don't support (D20) | "Best" looks authoritative, and the flag that contradicts it sits on another row. |
| R10 | A smooth-Moon mask is presented as terrain | The numbers look plausible and are wrong in exactly the way the product promises not to be. |
| R11 | Calendar buckets cut a night in two and report both halves as measured | The longest-gap column silently shrinks. |
| R12 | The grounding guard rejects every mission date, or grounds everything because the pool grew | In the first case the agents fall back forever; in the second the guard stops guarding (D23). |

### 10.2 Mission data (R8): `tests/unit/test_missions_data.py`

These are pure and run against the committed `data/missions.json`.

| Test | Asserts |
|---|---|
| `test_every_record_validates` | The pydantic contract loads every record. Unknown `status`, `instrument_types` or `*_precision` values fail with the record id. |
| `test_every_record_has_a_source` | `len(sources) ≥ 1`, and every URL is https and parses. |
| `test_every_payload_has_a_source_url` | Every payload row has one. |
| `test_null_means_unconfirmed` | Every nullable field that is null appears in `unconfirmed_fields`, and every name in `unconfirmed_fields` is a real field. |
| `test_coordinates_in_range` | lat ∈ [−90, 90], lon ∈ [0, 360); `coordinate_kind` is set iff a coordinate is. |
| `test_dates_are_ordered` | launch ≤ landing ≤ end_of_mission wherever all are day-precision. |
| `test_ids_are_unique_and_slugs` | ids are unique and kebab-case; payload ids are prefixed with their mission. |
| `test_ingest_rejects_partial_file` | A fixture with one bad record loads **nothing** (the ingest is transactional). |

### 10.3 Ranking (R9): `tests/unit/test_rank_properties.py`, hypothesis

The generators produce 2–8 items, each with a value, an uncertainty ≥ 0 and a
censored flag.

| Property | Statement |
|---|---|
| `censored_never_beats` | A censored item beats nothing, for a "smaller is better" metric. |
| `range_is_well_formed` | `1 ≤ rank_min ≤ rank_max ≤ n` for every item. |
| `order_invariant` | Permuting the input permutes the output and changes no range. |
| `definite_rank_is_consistent` | If every item has `rank_min == rank_max`, the ranks are a permutation of 1..n after ties are merged. |
| `removal_never_widens` | Removing any item never widens another item's range. |
| `no_best_under_censoring` | An item gets `rank == 1` only if nothing it is incomparable with is censored. |
| `mirror_symmetry` | Ranking a "larger is better" metric equals ranking the negated values as "smaller is better". |

Named cases: the D20 reproduction (Connecting Ridge 122 ± 17 h; de Gerlache rim
≥ 112 h censored; Malapert ≥ 288 h censored) gives ranges [1,2], [1,3] and [2,3].
The integration test in §10.8 asserts the same through `POST /compare`.

### 10.4 Calendar (R11): `tests/unit/test_calendar.py`

| Test | Asserts |
|---|---|
| `test_bucket_partition` | Bucket spans tile `[start, end)` exactly, with no overlaps; the last bucket is clipped. |
| `test_edge_run_is_open` | A dark run crossing a bucket edge is split, and **both** halves report `longest_dark_open = true`. |
| `test_interior_run_is_closed` | A run strictly inside a bucket reports `open = false`, and its length equals the v1 `intervals` result. |
| `test_fraction_matches_v1` | Over one bucket equal to a v1 window, the fractions match `/metrics` within the golden metric tolerance. |
| Hypothesis `calendar_sums` | For random boolean series and bucket edges, the sum of per-bucket up-time equals the whole-span up-time. |

### 10.5 Smooth mask and `terrain_modelled` (R10)

| Test | Where | Asserts |
|---|---|---|
| `test_smooth_mask_is_zero` | unit | `smooth_mask(1440)` gives el = 0, tol = 0 and the product string "none (smooth sphere)". |
| `test_far_side_has_no_earth` | golden-geo | A far-side target (a synthetic site at 0°N, 180°E) has Earth elevation < 0 for a whole year, so `earth_contact_s == 0`. |
| `test_terrain_flag_propagates` | integration | Every site-scoped endpoint for a `terrain_modelled = false` site carries the flag and a note in `meta.uncertainty`. |
| `test_candidate_goldens_unchanged` | golden | The migration's defaults leave the three golden sites byte-identical. |

### 10.6 Gap closure: tests the plan promised

| Test | Where | Closes |
|---|---|---|
| `test_blocker_angular_extent` (a wall) | unit, `test_horizon.py` | D31 |
| `test_ramp_converges_to_slope` | unit | D31 |
| `test_crater_rim_encloses_a_floor_site` | unit | D31 |
| `test_numba_and_python_agree` | unit | D10. Max bearing difference ≤ 1e-4° on the cone, the wall and a real fine window. |
| `test_resolve_all_matches_sites_json` | golden | C5. `ingest_sites` is removed from the coverage `omit` list. |
| `test_kernel_sha256` | unit | D14. Every `KernelSpec` has a pinned digest, and the cached files match it. |
| `test_manifest_records_digests_and_command` | golden | D15 |
| `test_source_note_states_the_rule` | unit | C4. The served sentence names "most open sky" and "top elevation decile". |
| `test_list_provenance_is_deduplicated` | integration | C6 |
| `test_memo_hit_is_labelled` | integration | C7. `cache == "memo"` and `compute_ms == 0`. |

### 10.7 Agents (R12)

- **The transport moves to HTTP** (ADR-3 amendment). `respx` routes intercept
  `generativelanguage.googleapis.com`, with five fixtures:
  1. grounded;
  2. a hallucinated number;
  3. schema-invalid output;
  4. a timeout (respx side effect `httpx.ReadTimeout`);
  5. an outage (503).

  The autouse block on `base._generate` stays, so an unrouted call still fails
  loudly.
- `test_thought_signature_round_trip`: the second request's history contains
  the first response's `Content`, including its signature part, byte for byte.
- `test_iso_dates_are_grounded`: "landed on 2025-03-06" passes when the tool
  output contains that date, and fails when it doesn't.
- `test_search_sites_pool_is_small`: the flattened numeric pool for a 50-row
  `search_sites` stays under a stated bound. Also a regression check that a
  random two-digit integer is grounded less than 10 % of the time (D23).
- `test_tools_keep_open_flags`: `_trim` keeps `longest_dark_open` and
  `longest_blackout_open` (C2).
- `test_get_site_lists_missions`: a mission target's `get_site` returns its
  mission, with no mass or cost fields.
- `test_agent_meta_complete`: every agent response and `GET /agents/runs`
  carries computed_at, resolution and uncertainty.
- **Manual, pre-demo** (runbook): one live call per agent with the real key.
  Record run ids, latency and tokens in the demo notes.

### 10.8 Integration: an isolated database

Integration tests stop using the dev database. The session fixture:
- connects to `polar_window_test` (`PW_TEST_DATABASE_URL`);
- runs `alembic upgrade head`;
- loads `tests/fixtures/`: three sites, their masks, two missions (one polar,
  one far side) and their payloads;
- truncates between modules.

If the test database is unreachable the tests are **skipped with a reason**,
never pointed at the dev database. New HTTP tests:

- `GET /missions` filters: status, provider, `payload_type` (any-of), region,
  date range, `q`; `total` is correct under pagination.
- `GET /missions/{id}`: `surface_window.basis` for each of the four rules;
  `ellipse_ring` is null when the axes are null; 404 as problem details.
- `GET /sites?kind=candidate` is the default and returns the v1 list unchanged.
- `GET /sites/{id}/calendar`: span > 730 d gives 422; `bucket=month` gives
  calendar months in UTC.
- `POST /compare`, the D20 reproduction: de Gerlache rim `rank == null`,
  `censored == true`, and no item is labelled rank 1 unless it is definite.

### 10.9 Frontend (FE-1 / FE-2)

- **Vitest, logic**: adapters for missions and calendar; the rank-range to
  label mapping ("best" only when `rank == 1`, never when censored or over the
  limit); query keys carry `data_version`; human-readable timestamps (U10).
- **Vitest + Testing Library, components**: each data-bound component renders
  its loading, empty, error, uncertain and insufficient-data states from the
  fixtures. An error must never render as a loader.
- **e2e, Playwright** (new, two tests, against a seeded backend):
  1. **Demo path**: Missions → filter to volatiles → open a south-polar mission
     → the four numbers render → shift the date (assert exactly one live
     metrics request per site after a burst) → compare with a candidate → Ask →
     the run log shows the tool calls.
  2. **Degraded path**: API down → snapshot fallback with its badge
     (FE-2); agent with no key → the deterministic answer with its state.
- **axe-core** in both e2e tests on every route visited: zero serious or
  critical violations. It is a floor; the manual WCAG 2.1 AA review is the
  gate (§7).

### 10.10 Coverage targets

| Area | Target |
|---|---|
| `core/` | ≥ 95 % lines, 100 % of `intervals.py`, the rank function and the calendar bucketer |
| `agents/guards.py` | 100 % (unchanged) |
| `data/ingest_missions.py`, `data/ingest_sites.py` | ≥ 85 %; both are back in coverage |
| services and routes | ≥ 85 % |
| frontend logic (`lib/`) | ≥ 80 %; components through state tests, not line coverage |
