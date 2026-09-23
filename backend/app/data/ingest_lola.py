"""Fetch and prepare the LOLA polar terrain the product runs on.

    python -m app.data.ingest_lola regional   # the 80 m model, 80-90 deg S (~115 MB, once)
    python -m app.data.ingest_lola fine       # a 20 m, 20 km window per terrain site
    python -m app.data.ingest_lola tiles      # the map's pre-rendered tile pyramid (ADR-4)
    python -m app.data.ingest_lola all

The DEM is read straight from the PDS Geosciences Node by HTTP range request
(``app.data.lola``), so the 1.85 GB 20 m product is never downloaded whole and
no GDAL is needed. Under ``OFFLINE=1`` nothing is downloaded: a missing file is
a loud error naming the command that fetches it, never a silent hang.
"""

from __future__ import annotations

import argparse
import asyncio
import logging

import numpy as np

from app.config import get_settings
from app.core.projections import geographic_to_polar
from app.data.lola import (
    LDEM_80S_20M,
    LDEM_80S_80M,
    DemTile,
    DemUnavailable,
    fetch_full,
    fetch_window_async,
)

log = logging.getLogger("ingest_lola")


def ensure_regional_dem() -> DemTile:
    """The 80 m regional model, fetched once."""
    s = get_settings()
    path = s.regional_dem_path
    if not path.exists():
        if s.offline:
            raise DemUnavailable(
                f"OFFLINE=1 and the regional DEM is not on disk at {path}.\n"
                "  fix: with a network, run `make dem` (about 115 MB, once)."
            )
        log.info("fetching the regional 80 m DEM (about 115 MB, once)")
        fetch_full(LDEM_80S_80M, path)
    return DemTile.load(path)


async def ensure_fine_dem(site_id: str, lat_deg: float, lon_deg: float) -> DemTile | None:
    """The 20 m window around a site, fetched if absent.

    Returns ``None`` -- rather than raising -- when it cannot be had. A site
    without its fine window still gets a mask from the 80 m model; it is simply
    coarser, and the coverage figure and ``meta.uncertainty`` say so.
    """
    s = get_settings()
    path = s.fine_dem_path(site_id)
    if path.exists():
        return DemTile.load(path)
    if s.offline:
        log.warning(
            "  %s: OFFLINE=1 and no 20 m window on disk; using the 80 m model only", site_id
        )
        return None
    x, y = geographic_to_polar(np.array([lon_deg]), np.array([lat_deg]))
    try:
        await fetch_window_async(LDEM_80S_20M, float(x[0]), float(y[0]), s.fine_dem_radius_m, path)
    except DemUnavailable as exc:
        log.warning("  %s: fine DEM unavailable (%s); falling back to 80 m", site_id, exc)
        return None
    return DemTile.load(path)


async def _fine_for_all_sites() -> int:
    from app.db.repositories.sites import SiteRepository
    from app.db.session import dispose_engine, session_scope

    try:
        async with session_scope() as session:
            sites, _ = await SiteRepository(session).list_sites(kind=None, limit=1000)
    finally:
        await dispose_engine()
    n = 0
    for site in sites:
        if site.terrain_modelled and await ensure_fine_dem(site.id, site.lat_deg, site.lon_deg):
            n += 1
    return n


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    p = argparse.ArgumentParser(prog="ingest_lola", description=__doc__.splitlines()[0])
    p.add_argument("step", choices=("regional", "fine", "tiles", "all"))
    p.add_argument("--max-zoom", type=int, default=5, help="tile pyramid depth (ADR-4)")
    args = p.parse_args(argv)
    try:
        if args.step in ("regional", "all"):
            tile = ensure_regional_dem()
            log.info("regional DEM: %s, %d x %d posts", tile.product, *tile.heights.shape)
        if args.step in ("fine", "all"):
            log.info("fine windows on disk: %d", asyncio.run(_fine_for_all_sites()))
        if args.step in ("tiles", "all"):
            from app.data.render_tiles import render_pyramid

            counts = render_pyramid(
                ensure_regional_dem(), get_settings().tile_dir, max_zoom=args.max_zoom
            )
            log.info("tiles: %d written to %s", sum(counts.values()), get_settings().tile_dir)
    except DemUnavailable as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
