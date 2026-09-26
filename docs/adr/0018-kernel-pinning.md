# ADR-18: Kernels and data files are dated and pinned

**Status:** Accepted
**Date:** 2026-09-26

## Decision

1. Every SPICE kernel is a dated file pinned by SHA-256 in `core/kernels.py`.
   NAIF's `earth_latest_high_prec.bpc` is republished daily under one name and
   cannot be pinned, so Earth orientation comes from the dated combined
   reconstruction-and-prediction kernel (`earth_1962_260806_2126_combined.bpc`,
   measured to 2026-08-06, predicted to 2126).
2. NAIF moves superseded files to `a_old_versions/`; each kernel lists that
   address as a mirror, so a pinned file stays downloadable.
3. Lifecycle kernels (GM values, Earth orientation, DSN stations) are loaded
   when present and never required by the surface engine.
4. Every other file is in `app/data/registry.py` with its URL, size floor and,
   where stable, its SHA-256; `polar-data sync` is the only downloader.
5. Replacing any pinned file is a data-version change and re-runs the goldens.
