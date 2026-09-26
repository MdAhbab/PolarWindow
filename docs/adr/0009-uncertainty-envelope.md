# ADR-9: One number shape, and an uncertainty envelope for every kind of answer

**Status:** Accepted
**Date:** 2026-09-26
**Relates to:** invariants 2, 3, 10, 11, 12 in `docs/conventions.md`

## Context

`meta.uncertainty` is required on every response and is terrain-specific
(DEM error, skyline error, penumbra). Weather shares, trajectory dispersions,
radiation factors and numbers a person entered have margins of other kinds,
and would otherwise each invent a format, and the frontend would render each
differently.

## Decision

1. **`Quantity`** (`app/core/quantity.py`, mirrored in the API schema and
   rendered by one frontend component): `value`, `unit`, a margin in exactly
   one form (`pm`, `lo`/`hi`, or a multiplicative `factor`) or a
   `no_margin_reason`, `open` (a lower bound), `provenance`
   (computed, published, entered, assumed) and `source` (who entered it, or
   the URL it was published at). A missing value carries `missing_reason`.
   The constructor refuses a number without a margin or a reason.
2. **`Share`** for probabilities: `k` of `n` model runs, an exact
   (Clopper-Pearson) 95 % interval, and `checked` (has this rule been
   verified against observations). Exact rather than Jeffreys because a rare
   launch rule is exactly where Jeffreys under-covers (about 0.89 at 51 runs,
   p = 0.05); the coverage is pinned in `test_quantity.py`.
3. **`meta.uncertainty` becomes a tagged union** on `kind`: `terrain` (today's
   fields, unchanged, so existing clients keep working) or `composite` with a
   list of parts, one per source of error in the answer.
4. `meta.engines` names the engine versions an answer depends on (ADR-13);
   `meta.engine_version` stays for the surface answers.

## Consequences

- The surface API is unchanged on the wire apart from a `kind: "terrain"` tag.
- A new margin kind is a schema change in one place.
