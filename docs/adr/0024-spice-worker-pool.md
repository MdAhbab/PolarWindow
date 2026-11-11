# ADR-24: SPICE reads can run in an opt-in process pool; kernel changes stay on one thread

**Status:** Accepted
**Date:** 2026-11-11

## Decision

1. **Pool.** `app/core/spice_pool.py` runs N worker processes (`ProcessPoolExecutor`, `spawn`
   context, so it behaves the same on Windows and Linux). Each worker furnshes the pinned
   metakernel once in its initializer and computes a fingerprint (kernel count plus the
   metakernel's SHA-256, see ADR-18). A worker whose fingerprint differs from the parent's
   raises and never serves. The pool is warmed at start, so a bad kernel set fails at start-up.
2. **Opt-in.** `PW_SPICE_WORKERS` defaults to 0, which is exactly the single-thread behaviour
   of today. From 2 up, `spice.ephemeris_async` goes to the pool. The pool starts in the API
   lifespan and in the compute worker's `main`, after `spice.load`, and stops with them. A pool
   that fails to start, or breaks later, logs a warning and the call runs on the single thread.
3. **Dispatched.** Pure-in, pure-out reads against the pinned kernels: the ephemeris sweep
   (`ephemeris_async`) and `positions` (ET array in, array out).
4. **Not dispatched.** Everything that changes kernel state (`load_extra`, `unload_extra`,
   `write_spk13`), `run_async` and every other call, and any call that needs extra kernels
   loaded in the parent (`eligible(needs_extra=True)` is false): workers hold only the pinned set.
5. **Health.** `spice.describe()` carries `pool: {workers, started, tasks_served}`.

## Why opt-in

The single thread is correct, cheap and deterministic. A pool costs about 1.3 s to start and
memory per worker (each process holds its own CSPICE, numpy, scipy and the mapped kernels; a
few hundred MB is the planning figure, not measured here). It only pays off under concurrent
load, which a one-user laptop never sees. `app/core/spice.py` already does kernel file I/O, so a
process pool beside it keeps the layering: spiceypy is still reached only through `core.spice`.

## Measured

Windows 11 dev machine, 900 s step, K concurrent sweeps, best of 3 (`backend/scripts/bench_spice_pool.py`).
Pooled results were asserted bit-identical to the single thread in every run.

| K x window | 1 thread | pool of 2 | pool of 4 |
|---|---|---|---|
| 8 x 1 d | 0.012 s | 0.006 s (1.9x) | 0.005 s (2.3x) |
| 2 x 30 d | 0.035 s | 0.018 s (1.9x) | 0.018 s (1.9x) |
| 8 x 30 d | 0.144 s | 0.083 s (1.7x) | 0.038 s (3.8x) |
| 8 x 365 d | 1.623 s | 0.851 s (1.9x) | 0.454 s (3.6x) |

Start-up was 1.2 to 1.6 s. Once warm, speed-up is near-linear in workers up to the core count,
and no size tried was slower. Single sweeps do not get faster (one call still runs in one
process); the gain is throughput under concurrency. The 1.3 s start-up is paid once per
process lifetime, so it is only worth paying for a long-running API that sees overlapping
requests, not for a short script.

## Consequences

Results are bit-identical, so caches and golden tests are unaffected. Worker processes do not
see kernels added with `load_extra`; those calls must opt out, and a future caller that forgets
would get an answer without the extra body, so new dispatched functions are listed here.
