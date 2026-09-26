# ADR-15: Radiation numbers are screening estimates, and say where to confirm them

**Status:** Accepted
**Date:** 2026-09-26

## Decision

1. Computed with open models only: trapped belts from AE8/AP8 through IRBEM
   (SpacePy), cosmic rays from a published closed-form model with the dose
   anchored to measurements (LRO CRaTER in orbit, Chang'e-4 LND on the
   surface), solar particle events from GOES proton data (NOAA SWPC) and NASA's
   OMNI and DONKI records.
2. Every fluence carries a multiplicative margin (ADR-9 `factor`), about 2 for
   the belt models.
3. Dose behind shielding, dose at a design confidence level, single-event
   rates and displacement damage are labelled "screening only: confirm in
   SPENVIS, OLTARIS or CREME-MC". AE9/AP9 is not used: it is distributed as a
   Windows program whose source may not be redistributed.
4. SpacePy is imported only by `core/belts.py`, which serialises it like SPICE.
