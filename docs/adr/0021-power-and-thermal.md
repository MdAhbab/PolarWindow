# ADR-21: Battery charge and bus temperature are one coupled model, run over a range of ground temperatures

**Status:** Accepted
**Date:** 2026-11-11

## Decision

1. **Physical quantities, never a score.** `POST /sites/{site_id}/energy` returns a
   time series (at most 600 points) and key quantities: energy generated (Wh),
   lowest state of charge, the time the battery empties, lowest bus temperature,
   hours below the operational threshold, the time the survival threshold is crossed.
   Each is a `Quantity` with a `lo`/`hi`, or says why it has none. No verdict.
   `app/core/power.py` and `app/core/thermal.py` are pure.
2. **Generation.** `P_gen = eta * A_eff(az, el) * S * lit * (1 - dust)`. `S` is 1361 W/m2
   (published, Kopp and Lean 2011) scaled by the inverse square of the Sun distance taken
   from the track. `lit` comes from the track's lit arcs; the track carries no partial-disc
   fraction. Geometries: `vertical_faces`, `top_deck_flat`, `sun_tracking`.
3. **One node, coupled.** `C dT/dt = Q_solar + Q_regolith + P_dissipated - Q_space`, with
   the state of charge, integrated together by RK4 (sub-step at most 120 s, shorter if the
   bus is fast). The heater is a thermostat drawing from the battery and dissipating in the
   bus; an empty battery dissipates nothing beyond what the arrays generate.
4. **Ground temperature is a range.** The only data is the Diviner Polar Resource Product,
   an annual average and an annual maximum per triangle (`app/data/diviner.py`, indexed once
   into `index.npz`, not in git). While the Sun is up the ground is at radiative equilibrium,
   capped at the maximum; in the dark it is anywhere from the temperature of space (cold end)
   to the annual average (warm end). Both ends are run. The spread of the triangles within the
   radius widens each end (minimum maximum and minimum average for the cold run, maxima for the
   warm). The central curve is the midpoint of the two, not a best estimate. Outside coverage
   only the cold end runs, and the answer says so.
5. **Every lander figure is an input.** No defaults. A missing one is a 422 naming it.
   Inputs are echoed with provenance. `data/catalogues/lander_examples.json` holds one example
   whose figures are all `assumed`, each with how it was derived.

## Not modelled

Panel temperature and degradation; multi-node gradients; multi-layer insulation detail; heat
through the legs; light reflected from sunlit terrain; shading of one face by another; battery
efficiency and ageing; the ground's temperature through the lunar day.

## Consequences

The envelope on temperature and charge is the ground range only: arc-edge timing is carried
into the energy generated but not into the curves, and lander figures carry no margin.
