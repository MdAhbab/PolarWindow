# ADR-19: Real terrain models for mission targets outside 80°S (LOLA 60S and SLDEM2015)

**Status:** Accepted  
**Date:** 2026-10-04  
**Deciders:** backend lead  
**Relates to:** ADR-0006, ADR-0001, ADR-0013, `docs/system-design.md` §10.4, `docs/data-sources.md`

## Context

ADR-6 point 3 established that mission targets outside the 80°S–90°S coverage of the primary LOLA south polar elevation models (`LDEM_80S_80M` and `LDEM_80S_20M`) received a curvature-only "smooth-sphere" skyline (0° on all bearings) with `terrain_modelled = false`.

While this prevented fabricating elevation where polar data was absent, several active and planned CLPS missions land outside 80°S:
- **APEX-1** (`feature-schrodinger`, 74.73°S, 132.93°E): located in the Schrödinger impact basin, surrounded by prominent rim walls and peak rings.
- **Blue Ghost 1** (`mission-blue-ghost-m1`, 18.56°N, 61.81°E): Mare Crisium basin floor.
- **Peregrine Mission 1** (`feature-sinus-viscositatis`, 35.25°N, 319.01°E): Sinus Viscositatis / Gruithuisen Domes.
- **IM-3** (`feature-reiner-gamma`, 7.39°N, 301.04°E): Reiner Gamma swirl.

Serving flat ground at these locations produces unrealistically optimistic horizon profiles and masks real topographic shadowing.

## Decision

1. **LOLA 60S for targets between 80°S and 60°S:**
   For targets between 80°S and 60°S (such as APEX-1 at Schrödinger), use the LOLA polar stereographic product `LDEM_60S_60M` (60 m/pixel resolution, scaled at 0.5 m integer, true scale at the south pole). The existing polar-stereographic range reader and sampler infrastructure are reused.

2. **SLDEM2015 for targets between 60°S and 60°N:**
   For targets between 60°S and 60°N (Blue Ghost 1, Sinus Viscositatis, Reiner Gamma), use the SLDEM2015 elevation model (Barker et al. 2016, *Icarus* 273, 346–355). SLDEM2015 combines LOLA altimetry and SELENE (Kaguya) Terrain Camera stereo imagery into 512 pixels/degree (~59.2 m/pixel) simple cylindrical tiles, with vertical accuracy of 3–4 m.

3. **HTTP Range Reads for 55 km Windows:**
   Rather than downloading multi-gigabyte global or hemispheric products, 55 km radius windows (`PW_MAX_RANGE_M` + 5 km margin) are fetched via HTTP range requests directly from PDS Geosciences Node into `data/dem/fine/<site_id>.npz`.

4. **Coverage & Metadata:**
   When a site is covered by a fine terrain window:
   - `terrain_modelled` is set to `true`.
   - `elev_m` and `slope_deg` are sampled directly from the DEM window.
   - `dem_product` names the product (e.g. `LOLA_LDEM_60S_60M` or `SLDEM2015 (LOLA + SELENE TC), 59 m`).
   - `dem_vertical_error_m` reflects cited accuracy (4.0 m for LOLA 60S; 3.5 m for SLDEM2015 per Barker et al. 2016).

5. **Client Cache Invalidation Without Engine Bump:**
   In accordance with ADR-13, candidate sites and `ENGINE_VERSION` remain unchanged. To ensure returning browsers do not serve stale smooth-sphere responses from cache, each site's `dem_product` is folded into the TanStack Query keys for `horizon`, `windows`, `metrics`, `timeline`, and `compare`.

6. **UI and Diagnostics Wording:**
   User-facing uncertainty banners and comments are updated from "No terrain data outside 80°S" to "No terrain model covers this site", correctly distinguishing coverage from latitude.

## Options Considered

### Option A: Retain smooth-sphere skylines outside 80°S
- **Pros:** No new data pipelines or readers needed.
- **Cons:** Fails to represent actual terrain obstacles at major CLPS landing sites.

### Option B: Download complete global DEM tiles (~2–4 GB)
- **Pros:** Simple local file loading.
- **Cons:** Violates download budgets and disk space limits.

### Option C: Targeted HTTP range reads from LOLA 60S and SLDEM2015 (chosen)
- **Pros:** Full topographic fidelity for all 4 non-polar CLPS targets with under 45 MB total download footprint.
- **Cons:** Requires a simple cylindrical reader and spherical destination mapping for equatorial/mid-latitude tiles.

## Consequences

- All four non-polar CLPS mission targets now have authentic skyline profiles (max elevations between 2.2° and 2.7° above the geometric horizon).
- Candidate site masks, candidate goldens, and `ENGINE_VERSION` remain untouched.
- `make test-geo` remains completely green with no golden updates required.
