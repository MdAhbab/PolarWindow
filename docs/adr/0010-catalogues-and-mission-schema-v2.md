# ADR-10: Cited catalogues, and mission schema v2

**Status:** Accepted
**Date:** 2026-09-26
**Relates to:** ADR-5 (the cited mission list), ADR-6 (targets as sites)

## Context

Launch planning needs pads, vehicles and their limits; contact needs ground
stations and relays; recovery needs zones; readiness needs the history of
lunar landings and their causes. The mission record has no launch vehicle, pad,
launch time, transfer type, radio, rovers or return.

## Decision

1. **Every catalogue is a cited JSON file under `data/catalogues/`**, validated
   like `missions.json`: `extra="forbid"`, every value either sourced or listed
   in `unconfirmed_fields`, and a null field must be listed. Loaded at seed
   time into typed tables. Catalogues: launch sites, vehicles, ground stations
   (with horizon masks), relays, recovery zones, lunar landing attempts,
   lessons, weather rules.
2. **Mission schema v2** adds `launch` (vehicle, pad, T-0 with precision),
   `transfer` (direct, phasing loops, low energy, unknown; flight days; days in
   lunar orbit), `descent` (Sun elevation band, Earth required at landing),
   `comms` (bands, EIRP, G/T, ground stations, relays), `spacecraft` (mass,
   area, reflectivity), `rovers[]` and `returns` (none, sample capsule, crew).
   Unpublished values stay null and listed; the product shows "not published"
   rather than a guess.
3. **Sources widen for engineering facts**: vehicle user guides, FAA
   environmental assessments, range documents, the DSN 810-005 handbook and
   agency fact sheets are accepted as sources for vehicle, pad and station
   facts. Provider press releases are still never the only source for a
   mission outcome.

## Consequences

- Every lifecycle number can be traced to a file, a field and a URL.
- Missing engineering facts are visible as missing, and a project manager can
  enter them (ADR-17), which marks them *entered* rather than *published*.
