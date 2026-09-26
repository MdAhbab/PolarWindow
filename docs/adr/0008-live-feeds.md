# ADR-8: Live feeds are fetched by one process and kept as forecasts of record

**Status:** Accepted
**Date:** 2026-09-26
**Relates to:** ADR-5 (N8: no runtime network access for curated facts), ADR-12 (jobs), ADR-13 (versions)

## Context

The lifecycle sections need data that changes by the hour: launch-pad weather
forecasts (NWS, NOAA GEFS and HRRR, ECMWF open data, NASA GEOS-FP), space
weather now (NOAA SWPC, NASA DONKI), sea state for booster recovery (NDBC,
WaveWatch III), the launch schedule (Launch Library 2) and DSN Now. ADR-5 said
the API never touches the network at run time, and that rule is what keeps a
demo alive on a bad connection and makes every answer reproducible.

A forecast cannot be reproduced later by asking again: NWS keeps no archive,
and model runs roll off the servers within days. If a launch-weather number is
to be checked against what actually happened, the forecast it came from has to
be kept.

## Decision

1. **One process fetches: `feeds`.** It is the only process with general
   outbound network access. The API reads what it stored and never fetches
   (the Gemini call from ADR-3 stays the one exception). In Docker the API
   sits on an internal network so this is enforced, not only intended.
2. **Every fetch is a `feed_snapshots` row**: provider, product, place, the
   model run or issue time, the valid range, fetch time, URL (never a secret),
   HTTP status, ETag, SHA-256 of the body, the raw body (compressed, or a file
   when large), the parsed values in SI units, the parser version, the licence
   and any problems found. Snapshots are immutable.
3. **A snapshot used for an answer is kept.** Assessments list the snapshot
   ids they used (ADR-12), and raw bodies an assessment marks *of record* are
   never garbage-collected. "Reproduce" re-runs from those ids.
4. **Adapters share one HTTP layer** (`app/feeds/http.py`): 5 s connect and
   20 s read timeouts, three retries with jitter that honour `Retry-After`,
   ETag and If-Modified-Since, a circuit breaker per provider, and a token
   bucket per provider kept in `feed_health` so a restart cannot blow a
   15-requests-an-hour limit.
5. **Every value is checked before it is stored**: schema (pydantic), physical
   range (a 200 m/s surface wind is a parse error, not a forecast), units
   converted once to SI. A body that fails is kept with status `rejected` and
   the previous good snapshot stays current.
6. **Each product has a staleness budget.** Past it the API returns no number
   and says why (invariant 11), rather than an old number that looks current.
7. **Primary sources are public-domain government data** (NOAA, NWS, NASA);
   ECMWF open data is CC-BY with attribution shown. Open-Meteo is a
   convenience fallback only: its free tier is non-commercial.

ADR-5's N8 still holds for curated facts (missions, catalogues): those are
cited files loaded at seed time.

## Consequences

- A new outbound dependency class, isolated in one process that can fail
  without taking the API down: `/healthz` reports feed problems as *degraded*,
  never *down*.
- Storage grows with snapshots; monthly partitions and raw-body GC bound it.
- Offline demos serve the last stored snapshots, labelled with their age.

## Rejected

- *Fetch on request with a cache:* a slow provider becomes a slow page, and a
  forecast used for an answer is gone once the cache expires.
- *A third-party weather API as the primary:* licence and single-vendor risk.
