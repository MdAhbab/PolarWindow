# ADR-2: TanStack Query for frontend data fetching

**Status:** Accepted
**Date:** 2026-09-18
**Deciders:** backend lead, with the frontend's existing store as a fixed constraint
**Relates to:** §6 of `docs/system-design.md`, N1

## Context

The frontend already has a working data layer, and it is not a naive one. In
`frontend/src/lib/store.ts` a zustand store owns a job-counter-versioned Web
Worker: `recompute()` increments `jobCounter`, posts one job, and the message
handler drops any response whose `jobId` is stale. Results stream in per site and
the store tracks `{status, done, total, currentSiteId}` so `LoadingPanel` can show
a real progress bar rather than a spinner. That is already a hand-rolled solution
to exactly the problem TanStack Query solves.

So the question is not "how do we fetch data" from nothing. It is: **the compute
moves from a Worker to HTTP; what replaces the worker's job-versioning, and does
the existing store survive?**

The workload is unusual in three ways:

1. **Overlapping bursts.** The date slider (M1: 708 h in 14 s, linear) emits a
   window change every ~200 ms, and each one fans out to 7 sites × up to 3
   endpoints. Peak ~100 in-flight requests, of which all but 7 are already stale.
2. **The values repeat.** A user drags right, overshoots, drags back. Server-side
   quantisation (§6) means the return trip hits keys already fetched. A cache
   keyed on the same quantised tuple turns that into zero requests.
3. **Partial results must render.** `LoadingPanel` and the compare screen both
   show sites as they arrive. A design that awaits `Promise.all` across 7 sites
   regresses the existing UX.

Constraints: React 19, no existing query library, hackathon budget, and a
`conventions.md` invariant that every data-bound component has loading / empty /
error / **uncertain** states — so whatever we pick must expose enough state to
distinguish "loading" from "loaded but coarse" from "loaded but the mask is
missing". That fourth state is the one most fetching wrappers flatten away.

## Decision

**TanStack Query v5**, with:

- **One query per (site, window, endpoint)**, not one per screen. `queryKey:
  ['timeline', siteId, startISO, endISO, stepS]`. Seven sites = seven queries
  that resolve independently, which preserves the streaming render for free —
  `useQueries` gives per-item status without any coordination code.
- **`placeholderData: keepPreviousData`.** During a drag the previous window's
  numbers stay on screen, dimmed, instead of flashing to skeletons 5× a second.
  The existing `useCountUp` (M4, 600 ms) then animates between real values rather
  than from zero.
- **`signal` threaded into `fetch`.** Superseded queries abort at the client. Per
  §6 the server deliberately completes and caches the work anyway; the abort is
  about not decoding 230 KB of JSON we are about to discard, and not about
  saving server CPU.
- **`staleTime: 5 min` for timelines/windows/metrics, `Infinity` for
  `/sites/{id}/horizon`.** A horizon mask is immutable for an engine version, so
  it should be fetched exactly once per session — this is the single biggest
  request-count win, because `HorizonProfile` and `PolarMap` both want it.
- **A `select` adapter per query** that converts the wire format (ISO strings,
  seconds, snake_case, parallel arrays) into the existing `SiteMetrics` /
  `Arc` / `TrackSample` camelCase shapes. One place, typed, generated types in,
  hand-written types out. No component changes.
- **zustand keeps UI state only** — `siteId`, `compareIds`, `windowStartH`,
  `cursorH`, `face`, `theme`, `motion`, `rankBy`, `playing`. It loses `metrics`
  and `compute`, which become derived from query state. This is the right split
  and the store is already close to it.

`retry: 1` with no exponential backoff on user-driven queries: a slider that
silently retries three times over 8 seconds looks broken, and the error state is
informative.

## Options Considered

### Option A: Plain `fetch` + a reducer (extend what exists)

| Dimension | Assessment |
|-----------|------------|
| Complexity | Low to write, **high to finish** |
| Bundle cost | 0 KB |
| Team familiarity | Total — the pattern is already in `store.ts` |
| Fit for the slider | Poor without re-implementing a cache |

**Pros:** no dependency; the `jobCounter` versioning already works and could be
carried over almost verbatim; zero bundle cost, which matters for a page that
must load fast on conference wifi.
**Cons:** the honest cost is not the fetch, it is everything after it. To match
the requirement we would hand-write: a keyed cache with TTL, request
deduplication (7 components asking for the same horizon), abort plumbing,
keep-previous-data, per-key status, and retry. That is roughly the TanStack
Query feature list, written under time pressure, untested, in the component
that is hardest to test. The `jobCounter` pattern also does not generalise: it
versions *one* job, and we now have N independent per-site queries that must be
individually stale-able.

### Option B: SWR

| Dimension | Assessment |
|-----------|------------|
| Complexity | Low |
| Bundle cost | ~4 KB gz |
| Team familiarity | Comparable to TanStack |
| Fit for the slider | Good, with gaps |

**Pros:** smaller and simpler; `keepPreviousData` exists; deduplication is
built in; the mental model (a key is a URL) is very clean.
**Cons:** two concrete gaps for this app. (i) `useSWRList`-style parallel
queries over a dynamic array of sites are awkward — SWR's answer is either N
hooks (illegal for a dynamic array) or a single aggregated key, which collapses
the per-site streaming render that `LoadingPanel` depends on. TanStack's
`useQueries` takes an array natively. (ii) AbortSignal support is not
first-class; you pass your own and manage it, which is the plumbing we were
trying to avoid.

### Option C (chosen): TanStack Query v5

| Dimension | Assessment |
|-----------|------------|
| Complexity | Low at the call site, medium concepts |
| Bundle cost | ~13 KB gz |
| Team familiarity | Widely known; good docs |
| Fit for the slider | **Designed for it** |

**Pros:** `useQueries` for the dynamic site array; `placeholderData:
keepPreviousData` is one line; `signal` is injected into the query function
automatically; structural sharing means unchanged arcs keep referential identity,
so React 19 skips re-rendering the 6 compare cards whose data did not change —
which directly protects the M3 re-order animation from jank; devtools make the
cache visible during the demo, which is genuinely useful when explaining the
architecture to a judge.
**Cons:** 13 KB; concepts (stale vs inactive vs fetching) to learn; it is easy to
misuse by putting server state and UI state in the same place — avoided here by
the explicit split above.

## Trade-off Analysis

Option A's bundle-size advantage is real but small against a page that already
ships React 19, Tailwind and a geometry engine; 13 KB gz is under 1 % of the
transfer and none of the interaction budget.

The decision turns on **which code we are willing to not write**. Every feature
TanStack provides here is one we independently established as a requirement in
§6: dedup, keyed cache, cancellation, keep-previous, per-item status. Writing
five of those by hand, correctly, in the slider path, is a day we do not have and
a class of bug (a stale response overwriting a fresh one) that is nearly
invisible in manual testing and catastrophic in a demo — it shows up as numbers
that are subtly *wrong*, not as an error.

SWR loses on one specific, non-negotiable point: the dynamic per-site array.
Collapsing 7 independent queries into one aggregate key would delete the
streaming progress UI that already exists and that the loading copy explicitly
describes ("Totals shown before this finishes can only fall..."). Removing a
working, thoughtful piece of UX to accommodate a library is backwards.

Structural sharing was the tiebreaker rather than a headline: the compare screen
re-orders with a 460 ms animation, and re-rendering all cards on every poll would
visibly fight it.

## Consequences

**Easier**
- The slider gets cancellation, caching and dedup for one line of config each.
- Per-site streaming render survives the Worker→HTTP move unchanged.
- Loading/error/uncertain states read off `status` + `meta.resolution` +
  `meta.uncertainty` instead of a hand-rolled enum.
- The Worker can be deleted, and with it a whole class of
  "serialising Float32Array across postMessage" problems.

**Harder**
- Two state systems in one app. The rule is written down and must be enforced in
  review: **zustand owns what the user chose; TanStack owns what the server
  said.** Nothing derived from the server may be `set()` into zustand.
- `SiteMetrics` currently carries `Float32Array` (in `HorizonMask`). JSON gives
  plain arrays; the `select` adapter must rebuild the typed arrays or the
  interpolation helpers change. Adapter converts — components untouched.
- Query keys must include `engine_version` or a backend redeploy serves stale
  client cache. Added to the key, not just to `meta`.

**To revisit**
- If the compare screen grows past ~12 sites, per-site queries become chatty and
  `POST /compare` should become the single query with `useQueries` reserved for
  the focused site.
- Offline/PWA is out of scope; if it ever is not, TanStack's persister makes it
  nearly free, which is a point in its favour we are not counting today.

## Action Items
1. [ ] Add `@tanstack/react-query` + provider in `main.tsx`, devtools in dev only.
2. [ ] Generate `frontend/src/lib/api/types.ts` from OpenAPI (`openapi-typescript`);
       hand-write only `frontend/src/lib/api/client.ts` (thin fetch + problem-detail parsing).
3. [ ] Write `frontend/src/lib/api/adapters.ts`: wire → existing `types.ts` shapes.
4. [ ] Replace `metrics`/`compute` in `store.ts` with `useSiteMetrics()` /
       `useSiteTimeline()` hooks; delete `compute.worker.ts` and its store wiring.
5. [ ] Keep `LoadingPanel`'s `done/total` by deriving it from `useQueries` statuses.
6. [ ] Add `engine_version` to every query key.
