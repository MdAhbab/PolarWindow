"""The ``site_build`` job: the skyline (and reference numbers) of a project's coordinate.

A seeded site gets its horizon mask from ``precompute``; a coordinate a team enters
gets it here, through the same functions (``build_and_store_mask`` and
``store_reference_metrics``), so the two cannot drift apart. Params: ``{site_id}``.
"""

from __future__ import annotations

import asyncio
import logging

import numpy as np

from app.config import ENGINE_VERSION, get_settings
from app.core import spice
from app.core.projections import geographic_to_polar
from app.data.ingest_lola import ensure_regional_dem
from app.db.repositories.sites import MaskRepository, SiteRecord, SiteRepository
from app.db.session import session_scope
from app.workers import precompute
from app.workers.compute import HandlerResult, JobContext, handler

log = logging.getLogger("polar_window.site_build")

#: Where the regional 80 m product stops: poleward of this the grid has no posts for it.
REGIONAL_LIMIT_LAT_DEG = -80.0


class OutsideCoverage(ValueError):
    """The coordinate lies where no elevation model reaches."""


def _check_covered(site: SiteRecord, coarse_covers: bool) -> None:
    if not site.terrain_modelled:
        raise OutsideCoverage(
            f"No elevation model covers {site.lat_deg:.3f} deg, {site.lon_deg:.3f} deg E. "
            "The terrain models reach the lunar south pole (LOLA 80 m, 20 m and 60S) and the "
            "mid-latitude SLDEM2015 tiles; a skyline cannot be built here without inventing it."
        )
    if site.lat_deg <= REGIONAL_LIMIT_LAT_DEG and not coarse_covers:
        raise OutsideCoverage(
            f"The south-polar elevation model has no posts at {site.lat_deg:.3f} deg, "
            f"{site.lon_deg:.3f} deg E, so a skyline cannot be built there."
        )


@handler("site_build")
async def run(ctx: JobContext) -> HandlerResult:
    site_id = str(ctx.job.params["site_id"])
    ctx.progress(0.02, "Looking up the site.")
    async with session_scope() as s:
        site = await SiteRepository(s).get(site_id)
    if site is None:
        raise ValueError("the site is gone")

    ctx.progress(0.05, "Loading the south-polar elevation model.")
    coarse = await asyncio.to_thread(ensure_regional_dem)
    x, y = geographic_to_polar(np.array([site.lon_deg]), np.array([site.lat_deg]))
    sample = coarse.sample_grid(np.array([x[0]]), np.array([y[0]]))
    _check_covered(site, bool(np.all(np.isfinite(sample))))

    phases = {
        "Fetching the elevation window around the spot.": 0.1,
        "Tracing the skyline in every direction.": 0.3,
    }
    mask = await precompute.build_and_store_mask(
        site, coarse, lambda msg: ctx.progress(phases.get(msg, 0.3), msg)
    )
    ctx.progress(0.8, "Skyline stored; working out sunlight and Earth contact.")
    metrics = False
    try:
        spice.load(get_settings().kernel_dir)
        await precompute.store_reference_metrics(site, mask)
        metrics = True
    except Exception as exc:  # the skyline is the job; the numbers can be had on demand
        log.warning("site_build %s: reference numbers not stored: %s", site_id, exc)
    async with session_scope() as s:
        stored = await MaskRepository(s).get(site_id, ENGINE_VERSION)
    ctx.progress(1.0, "Done.")
    out = {
        "site_id": site_id,
        "dem_product": stored.dem_product if stored else None,
        "max_el_deg": round(mask.max_el_deg, 3),
        "coverage": round(mask.coverage, 3),
        "reference_numbers": metrics,
    }
    return HandlerResult(result=out, message="The skyline is built.")
