# ADR-22: A landing ellipse is sampled, and slope and illumination are read at every sample

**Status:** Accepted
**Date:** 2026-11-11

## Decision

1. **The ellipse is a distribution.** `POST /sites/{site_id}/dispersion` takes the entered
   3-sigma ellipse (semi-major, semi-minor, azimuth of the major axis from true north) and
   draws `samples` points (default 1000, at most 2000) from the bivariate normal cut at
   3 sigma. The draw is a Halton sequence through the inverse normal CDF with a seeded shift,
   so the same inputs give the same points and nothing depends on a global random state.
   `app/core/dispersion.py` and `app/core/hazards.py` are pure.
2. **A slope carries its baseline.** Slope is Horn's 3x3 gradient on the elevation posts, so
   its baseline is three posts (15 m on the 5 m tiles, 60 m on the 20 m DEM). Every slope in
   the response says its baseline, and slopes from different baselines are never put in one
   statistic. Its uncertainty is the elevation error propagated through the stencil
   (independent post errors, so the larger figure) and the arctangent.
3. **Source, in order.** PGDA 5 m LOLA (elevation, uncertainty) when one tile covers the whole
   ellipse and its projection matches the app's; otherwise the app's own DEM (20 m fine tile,
   else 80 m regional). The response says which, and why it fell back. No tile means a 422.
4. **Static tip-over.** `theta_tip = atan(D / (2 h_CG))` from the entered footprint diameter and
   centre-of-gravity height. The slope limit is entered too. All three are required.
5. **Shares, never a score.** The response gives the share of points above the entered limit and
   above `theta_tip`, each with its exact 95 % interval for that many points, and a sensitivity
   share with every slope one sigma higher. No index, no rating, no go/no-go.
6. **Illumination is a long-term average.** Average Sun and Earth visibility and the permanent
   shadow share come from the PGDA maps (product 69), labelled as the product's average and
   not as hours in the chosen dates. Scaling is read from each file's own scale/offset tags:
   visibility is `DN * 4e-5` (a fraction, 25000 = 1); permanent shadow is
   `DN * 2.5e-5 + 0.5`, where 1 marks shadow (checked: it is 1 where the average Sun is
   exactly 0). Epoch: LOLA data 2009-07-13 to 2013-07-18, product 2016-08.
7. **Nothing is stored.** Computed on the request, like `/energy`.

## Not modelled

Rocks and craters below the DEM's resolution; touchdown dynamics; plume effects; hours of
sunlight per point for the chosen dates; antenna pointing at a resting tilt; dynamic tip-over.

## Consequences

The PGDA rasters (`data/external/pgda_lola_5m`, `pgda_illumination`) are now read at request
time. Their entries in `backend/app/data/registry.py` are still to be added; this change does
not touch the registry. The share interval covers only the number of points drawn, not the
slope's own error; the sensitivity share shows how much that error could matter.
