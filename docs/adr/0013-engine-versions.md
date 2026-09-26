# ADR-13: A version per engine

**Status:** Accepted
**Date:** 2026-09-26

## Decision

`ENGINE_VERSION = "hz-2/vis-2"` stays exactly as it is, so the surface cache
keys, stored skylines and goldens do not move. Each lifecycle engine has its
own version (`config.ENGINES`: traj, ecl, wx, rad, link, net, los), and an
answer's cache key names the versions it depends on (its *closure*, from
`config.engine_closure`). A change to the trip propagator invalidates trip and
contact answers and nothing else. Feed-derived keys include snapshot ids, so a
new forecast is a new key without any invalidation step.
