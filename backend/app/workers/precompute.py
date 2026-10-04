"""Offline precompute: DEM windows, horizon masks, reference metrics.

This is the expensive half of ADR-1's tier 1 and tier 2, and it is deliberately
a separate process from the API. A mask build is ~100 ms of tight numpy plus a
DEM fetch of several seconds; neither can share a process with a 150 ms p95
latency budget, because CPython will not preempt a numpy loop to service the
event loop.

Idempotent throughout. ``make seed`` can be run repeatedly, and re-running it
after a partial failure resumes rather than restarting -- which matters because
the DEM fetch is the slow part and there is no reason to pay for it twice.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import time
from datetime import timedelta

import numpy as np

from app.config import ENGINE_VERSION, get_settings
from app.core import spice
from app.core.horizon import SMOOTH_SPHERE_PRODUCT, HorizonMask, build_mask, smooth_mask
from app.data.ingest_lola import ensure_fine_dem, ensure_regional_dem
from app.data.lola import DemTile, make_samplers
from app.data.sldem import SldemTile, make_sldem_samplers
from app.db.repositories.metrics import WindowMetricsRecord, WindowMetricsRepository
from app.db.repositories.sites import MaskRepository, SiteRecord, SiteRepository
from app.db.session import dispose_engine, session_scope

log = logging.getLogger("precompute")


# ---------------------------------------------------------------------------
# Step 1: DEM
# ---------------------------------------------------------------------------


# ensure_regional_dem / ensure_fine_dem live in app.data.ingest_lola, which
# also owns the offline refusal; they are imported above.


# ---------------------------------------------------------------------------
# Step 2: masks
# ---------------------------------------------------------------------------


def build_site_mask(
    lat_deg: float, lon_deg: float, fine: DemTile | SldemTile | None, coarse: DemTile
) -> tuple[HorizonMask, str, float, float]:
    """Ray-march one site and summarise which terrain products set its skyline.

    Returns ``(mask, dem_product, dem_resolution_m, dem_vertical_error_m)``.
    The product names every tier that set at least one bearing's skyline, and
    the vertical error is the *largest* among those blockers -- the figure that
    is true for every bearing -- rather than the near-field tier's by default.
    """
    s = get_settings()
    if isinstance(fine, SldemTile):
        sampler, sigma = make_sldem_samplers(lat_deg, lon_deg, fine)
        mask = build_mask(
            sampler,
            azimuth_step_deg=s.azimuth_step_deg,
            max_range_m=s.max_range_m,
            dem_post_spacing_m=fine.scale_m,
            dem_vertical_error_m=fine.vertical_error_m,
            sample_sigma=sigma,
        )
        return mask, fine.product, fine.scale_m, fine.vertical_error_m

    sampler, sigma = make_samplers(lat_deg, lon_deg, fine, coarse)
    source = fine if fine is not None else coarse
    mask = build_mask(
        sampler,
        azimuth_step_deg=s.azimuth_step_deg,
        max_range_m=s.max_range_m,
        dem_post_spacing_m=source.scale_m,
        dem_vertical_error_m=source.vertical_error_m,
        sample_sigma=sigma,
    )
    return (mask, *describe_sources(mask, fine, coarse))


def describe_sources(
    mask: HorizonMask, fine: DemTile | None, coarse: DemTile
) -> tuple[str, float, float]:
    """``(product, resolution_m, vertical_error_m)`` for the tiers that set the skyline."""
    source = fine if fine is not None else coarse
    sig = mask.blocker_sigma_m
    if fine is None or sig is None:
        return source.product, source.scale_m, source.vertical_error_m
    from_coarse = int(np.count_nonzero(sig > fine.vertical_error_m + 1e-6))
    if from_coarse == 0:
        return fine.product, fine.scale_m, fine.vertical_error_m
    log.info(
        "         terrain: %d of %d bearings set beyond the fine window, on %s",
        from_coarse,
        mask.azimuth_count,
        coarse.product,
    )
    # Short enough for the column; the per-bearing count is in the log above.
    coarse_name = coarse.product.removeprefix("LOLA_")
    return f"{fine.product} + {coarse_name}", fine.scale_m, float(np.max(sig))


# ---------------------------------------------------------------------------
# Step 3: reference metrics
# ---------------------------------------------------------------------------


async def compute_reference_metrics(
    site_id: str, lat_deg: float, lon_deg: float, elev_m: float | None, mask: HorizonMask
) -> WindowMetricsRecord:
    """The four numbers over the default reference window.

    Imported here rather than at module scope to keep the worker importable
    (and its DEM steps runnable) on a machine with no SPICE kernels.
    """
    from app.services.geometry_service import compute_window_metrics

    s = get_settings()
    start = s.reference_window_start
    end = start + timedelta(days=s.reference_window_days)
    result = await compute_window_metrics(
        site_id=site_id,
        lat_deg=lat_deg,
        lon_deg=lon_deg,
        elev_m=elev_m,
        mask=mask,
        start=start,
        end=end,
        step_s=s.default_step_s,
    )
    m = result.metrics
    # Store the window that was actually computed, not the one requested.
    #
    # `compute_window_metrics` quantises its bounds to the step grid, and the
    # reference window is 29.53 days = 2,551,392 s, which is not a multiple of
    # 900. Storing the requested bounds meant the row recorded a window nobody
    # had computed, and every lookup -- which quantises the same way -- missed
    # it, so every site's summary came back null.
    return WindowMetricsRecord(
        site_id=site_id,
        window_start=result.start,
        window_end=result.end,
        step_s=result.step_s,
        sunlit_s=m.sunlit_s,
        earth_contact_s=m.earth_contact_s,
        longest_dark_s=m.longest_dark_s,
        longest_blackout_s=m.longest_blackout_s,
        worst_compound_s=m.worst_compound_s,
        sun_fraction_up=m.sun.fraction_up,
        earth_fraction_up=m.earth.fraction_up,
        grazing=m.sun.grazing or m.earth.grazing,
        computed_at=result.computed_at,
        longest_dark_open=m.longest_dark_open,
        longest_blackout_open=m.longest_blackout_open,
    )


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


async def seed_sites() -> int:
    """Load the resolved site list into Postgres."""
    s = get_settings()
    if not s.sites_seed_path.exists():
        raise SystemExit(
            f"No site seed at {s.sites_seed_path}.\n"
            f"  fix: make sites   (resolves sites against the regional DEM)"
        )
    payload = json.loads(s.sites_seed_path.read_text())
    async with session_scope() as session:
        n = await SiteRepository(session).upsert_many(payload)
    log.info("seeded %d sites", n)
    return n


async def sites_needing_work() -> list[str]:
    """Sites with no skyline or no reference numbers for this engine version.

    What ``polar-data sync`` asks before running the worker, so a machine that
    is already seeded pays one query at start-up rather than a full rebuild.
    Seeds the site list first: a site added to ``sites.json`` or a new mission
    target is work too.
    """
    try:
        await seed_sites()
        async with session_scope() as session:
            sites, _ = await SiteRepository(session).list_sites(limit=500)
            masked = await MaskRepository(session).existing_site_ids(ENGINE_VERSION)
            measured = await WindowMetricsRepository(session).site_ids_with_rows(ENGINE_VERSION)
    finally:
        await dispose_engine()
    return sorted(x.id for x in sites if x.id not in masked or x.id not in measured)


async def precompute(
    *, only: list[str] | None = None, force: bool = False, skip_metrics: bool = False
) -> None:
    s = get_settings()
    coarse = ensure_regional_dem()

    async with session_scope() as session:
        sites, _ = await SiteRepository(session).list_sites(limit=500)
        existing = (
            set() if force else await MaskRepository(session).existing_site_ids(ENGINE_VERSION)
        )

    targets = [x for x in sites if (only is None or x.id in only)]
    log.info(
        "precompute: %d sites, engine %s, %d already built",
        len(targets),
        ENGINE_VERSION,
        len(existing & {x.id for x in targets}),
    )

    kernels_ok = True
    try:
        spice.load(s.kernel_dir)
    except Exception as exc:
        kernels_ok = False
        log.warning("SPICE kernels unavailable; masks will build, metrics will not.\n%s", exc)

    failures: list[tuple[str, str]] = []
    for i, site in enumerate(targets, 1):
        t0 = time.perf_counter()
        log.info(
            "[%2d/%d] %-28s lat %.4f lon %.4f",
            i,
            len(targets),
            site.id,
            site.lat_deg,
            site.lon_deg,
        )
        # One site failing -- a DEM window that will not download, terrain
        # outside the model -- must not cost the other fourteen. The failure is
        # collected, reported at the end, and turned into a non-zero exit, so a
        # partial seed is visible rather than silent.
        try:
            await _one_site(
                site, existing, coarse, kernels_ok=kernels_ok, skip_metrics=skip_metrics
            )
        except Exception as exc:
            log.exception("         FAILED: %s", exc)
            failures.append((site.id, f"{type(exc).__name__}: {exc}"))
            continue
        log.info("         done in %.1f s", time.perf_counter() - t0)

    if failures:
        lines = "\n".join(f"  {sid}: {why}" for sid, why in failures)
        raise SystemExit(
            f"{len(failures)} of {len(targets)} sites failed; the others are seeded.\n{lines}\n"
            "  fix: re-run `make worker` (it resumes), or --sites <id> for one site."
        )


async def _one_site(
    site: SiteRecord,
    existing: set[str],
    coarse: DemTile,
    *,
    kernels_ok: bool,
    skip_metrics: bool,
) -> None:
    s = get_settings()
    mask: HorizonMask | None = None
    # An existing mask skips the *mask build*, not the whole site. These are
    # separate pieces of work with separate costs, and conflating them meant
    # a re-run could never repair missing metrics -- which is exactly the
    # state a partial first run leaves behind.
    if site.id in existing:
        async with session_scope() as session:
            rec = await MaskRepository(session).get(site.id, ENGINE_VERSION)
        if rec is not None:
            mask = rec.mask
            log.info("         mask: reused (%d bearings)", mask.azimuth_count)

    if mask is None:
        fine = await ensure_fine_dem(site.id, site.lat_deg, site.lon_deg)
        if fine is None and not site.terrain_modelled:
            # No elevation model covers this site: a smooth-sphere skyline,
            # flagged everywhere it is used.
            mask = smooth_mask(azimuth_step_deg=s.azimuth_step_deg, max_range_m=s.max_range_m)
            async with session_scope() as session:
                await MaskRepository(session).upsert(
                    site.id,
                    ENGINE_VERSION,
                    mask,
                    dem_product=SMOOTH_SPHERE_PRODUCT,
                    dem_resolution_m=0.0,
                    dem_vertical_error_m=0.0,
                )
            log.info("         mask: smooth sphere (no terrain model covers this site)")
        else:
            mask, product, res_m, err_m = build_site_mask(site.lat_deg, site.lon_deg, fine, coarse)
        log.info(
            "         mask: max %+.3f deg @ %.2f deg, mean %+.3f, coverage %.0f%%, %.0f ms",
            mask.max_el_deg,
            mask.max_el_bearing_deg,
            float(np.mean(mask.el_deg)),
            mask.coverage * 100,
            mask.compute_ms,
        )
        log.info("         terrain: %s, blocker error up to %.1f m", product, err_m)
        async with session_scope() as session:
            await MaskRepository(session).upsert(
                site.id,
                ENGINE_VERSION,
                mask,
                dem_product=product,
                dem_resolution_m=res_m,
                dem_vertical_error_m=err_m,
            )

    if kernels_ok and not skip_metrics:
        rec_metrics = await compute_reference_metrics(
            site.id, site.lat_deg, site.lon_deg, site.elev_m, mask
        )
        async with session_scope() as session:
            await WindowMetricsRepository(session).upsert(ENGINE_VERSION, rec_metrics)
        log.info(
            "         metrics: sun %.0f h (%.0f%%)  dte %.0f h (%.0f%%)  "
            "night %s%.0f h  blackout %s%.0f h",
            rec_metrics.sunlit_s / 3600,
            rec_metrics.sun_fraction_up * 100,
            rec_metrics.earth_contact_s / 3600,
            rec_metrics.earth_fraction_up * 100,
            ">=" if rec_metrics.longest_dark_open else "",
            rec_metrics.longest_dark_s / 3600,
            ">=" if rec_metrics.longest_blackout_open else "",
            rec_metrics.longest_blackout_s / 3600,
        )


async def main_async(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Precompute horizon masks and reference metrics.")
    p.add_argument("--sites", nargs="*", help="only these site ids")
    p.add_argument("--force", action="store_true", help="rebuild masks that already exist")
    p.add_argument("--skip-metrics", action="store_true", help="masks only, no SPICE")
    p.add_argument("--seed-only", action="store_true", help="load sites into the db and stop")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    try:
        await seed_sites()
        if not args.seed_only:
            await precompute(only=args.sites, force=args.force, skip_metrics=args.skip_metrics)
    finally:
        await dispose_engine()


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
