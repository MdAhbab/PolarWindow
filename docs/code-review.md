# Code review — POLAR WINDOW, full build

**Scope:** compute core, services, API, agent layer, frontend wiring.
**Date:** 2026-09-18. **Verdict: approve, with two known limitations recorded.**

---

## Summary

A backend that computes four numbers from real LOLA terrain and real SPICE
positions, behind an API whose layering is machine-enforced, with an agent layer
whose central guard is a pure function and is exhaustively tested. 211 backend
tests and 41 frontend units, mypy strict clean across 78 files, 8/8 import
contracts kept.

The parts most likely to be wrong — interval arithmetic, the ray-march, the
grounding guard — got the most test attention, which is the right allocation.

---

## Issues found and fixed during review

| # | File | Issue | Category |
|---|---|---|---|
| 1 | `db/repositories/sites.py` | `list_sites` ran the full query, hydrated every matching ORM row, took `len()` and discarded them, then ran the query again with `limit`/`offset`. Two round trips, one of them transferring the entire table. | Performance |

**Fix:** `select(func.count()).select_from(stmt.subquery())`. Harmless at 15
sites; quietly quadratic in transferred rows as the set grows, and exactly the
kind of thing that is invisible until it is not.

### Issues found and fixed earlier, during construction

These are recorded because each was a real defect that reached running code, and
because the way each was caught is the argument for the corresponding test:

| Defect | Caught by | Consequence if shipped |
|---|---|---|
| Polar stereographic assumed `lat_ts=-87.5`; the LOLA product is true at the **pole** | Reading the PDS label rather than assuming | Every site displaced ~0.2 % in range — metres at 20 m posts |
| Grid north treated as true north near the pole | Reasoning about the projection | Every blocker reported at the wrong bearing — 166° wrong at Shackleton, and it would have looked like terrain |
| Ray-march started at 5 m, inside the site's own pixel | A mask whose peak blocker was 10 m away | Local slope reported as a 3° skyline; hours of fictional darkness |
| Near-field DEM noise selected as a blocker | Noticing 85 % of blockers were within 100 m | A 2 m error at 40 m is 2.9° of apparent skyline — larger than most real horizons here |
| Fallback in the noise rule re-selected the loudest noise | The fix not changing the output | Same as above, silently |
| Prefetched agent facts never entered the grounding pool | An agent test on a *correct* answer | Every number in every correct explainer answer rejected as ungrounded |
| The user's own requirement rejected as ungrounded | The advisor's negative-result test | A2 could not restate the requirement it was given without failing its own guard |
| Reference window stored unquantised; every lookup missed | `/sites` returning `summary: null` for all 15 | Coarse filters and list summaries silently dead |
| `asyncio.run()` called from inside the async worker | The worker crashing on its first site | Seeding impossible |
| `respx` cannot intercept `google-genai` (it runs in a worker thread) | A test with a fake key reaching the live API and getting a 400 | Tests making real, billable API calls |

---

## Security

| Area | Assessment |
|---|---|
| SQL injection | No string interpolation into SQL anywhere. The one `text()` is a literal `SELECT 1` health probe. Search terms are bound parameters via `func.lower(...).like(param)`. |
| Path traversal | Tile paths are built from a `layer` validated against a fixed tuple and three ints bounded by `Path(ge=0, le=MAX_ZOOM)` and an explicit `x < 2**z` check. No user string reaches the filesystem. |
| SSRF | Outbound requests go to two pinned hosts (NAIF, PDS Geosciences) built from module constants. No user input contributes to a URL. |
| Agent tool arguments | Validated by pydantic models with `extra="forbid"` before anything executes. A `site_id` of `'; DROP TABLE sites;--` fails the arg model and is recorded as a tool error — tested. |
| Agent blast radius | Six read-only tools, enforced by an import contract: no agent module except `tools.py` can import a service or repository. |
| Secrets | One optional API key, read through typed settings. Nothing logged. |
| Unbounded work | Window ≤ 730 days, step ∈ [300, 7200], compare ≤ 8 sites, agents ≤ 4 rounds / 8 tool calls / 20 s. |

Container runs non-root. No authentication, by design — read-only public data on
a demo host, stated in the API docs rather than omitted.

---

## Correctness

**Strong.** The compute core is pure functions over arrays, which is what makes
the following possible:

- `intervals.py` is property-tested over arbitrary boolean arrays for partition,
  alternation, contiguity, inversion symmetry, concatenation, idempotence and
  monotonicity. The degenerate shapes (`[]`, `[True]`, a lone `True` at either
  end) are pinned as explicit examples rather than left to the generator.
- The ray-march is tested against surfaces whose horizon is derivable by hand —
  a plane, a cone, a wall, a ramp — not against its own previous output.
- The pole is tested directly: azimuth is swept a full turn at −89.9999° and
  must not jump, which is exactly where the textbook formula fails.
- The Python ENU projection is checked against a transcription of the frontend's
  TypeScript to 1e-9. Two independent implementations agreeing is real evidence.
- Golden fixtures carry a manifest with the kernel set, the DEM product and the
  reason they were last regenerated, and `make golden-update` refuses without
  one.

---

## Known limitations

Two, stated rather than papered over.

### 1. The grounding guard weakens as the tool-result pool grows

An integer claim matches any tool value within ±0.5, under any of five unit
conversions. With three tool calls returning ~30 numeric leaves each, roughly 90
values are in the pool and an integer between 0 and a few hundred has a
meaningful chance of coincidentally matching one.

This is a deliberate trade. Tightening it would reject legitimate rounding
("80 %" for 0.7983) and push the model toward writing raw seconds. The
mitigations in place are that the pool is *trimmed* before the model sees it —
tools return finished numbers rather than raw sample arrays, precisely so there
is nothing to divide — and that provenance records which field each claim was
matched against, so a coincidental match is visible on inspection rather than
merely trusted.

**Worth revisiting** if an agent ever gains a tool that returns a large array.

### 2. The map terminator is not SPICE

`frontend/src/lib/geometry/ephemeris.ts` retains a mean-element model for one
purpose: the schematic terminator overlay needs a sub-solar longitude for the
whole globe rather than a look angle at one site, and the API does not expose
one. The file carries a comment saying exactly this and that the right fix is a
sub-solar point on the timeline response, not a better model on the client.

Every *number* in the product comes from the API. This affects a drawn line.

---

## What looks good

- **The layering rule is executable.** Seven import-linter contracts, not a
  convention in a README. Routes cannot import SQLAlchemy — `deps.Session` is a
  deliberately opaque alias so they cannot even name it.
- **`core/` is genuinely pure**, which is why the test suite is fast and why the
  same code runs in the worker, the API and the agent tools without divergence.
- **Uncertainty is structural, not decorative.** `meta.uncertainty` is
  mandatory, `edge_timing_s: null` with `grazing: true` is a stronger and more
  honest claim than a large number, and a parameterised test enforces presence
  across every endpoint.
- **The absence of a score is tested.** `test_metrics_has_no_composite_score`
  asserts the response model has no `score`, `rating`, `overall`, `grade` or
  `index` field. A product rule made executable.
- **Every agent exit path persists a row**, including timeouts and outages, and
  a parameterised test asserts it. The run log is demo evidence, and a missing
  row for a failure would make it evidence of something else.
- **The degraded path is real.** With no API key at all, every agent returns a
  correct paragraph assembled from tool results. The four numbers never depend
  on a model being reachable.
- **Error copy carries `still_works`** from the server, so no failure renders as
  a shrug and the wording can improve without a frontend deploy.

---

## Verdict

**Approve.** The two limitations above are documented in code and here, and
neither affects a reported number. The one performance defect found during
review is fixed.
