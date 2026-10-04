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
from pathlib import Path

import numpy as np

from app.config import get_settings
from app.core.projections import geographic_to_polar
from app.data.lola import (
    LDEM_60S_60M,
    LDEM_80S_20M,
    LDEM_80S_80M,
    DemTile,
    DemUnavailable,
    fetch_full,
    fetch_window_async,
)
from app.data.sldem import SldemTile, fetch_sldem_window_async, find_sldem_tile

log = logging.getLogger("ingest_lola")


def load_dem_tile(path: Path) -> DemTile | SldemTile:
    """Load either a polar stereographic DemTile or a simple cylindrical SldemTile."""
    with np.load(path, allow_pickle=False) as z:
        if "origin_lat_deg" in z:
            return SldemTile.load(path)
        return DemTile.load(path)


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


async def ensure_fine_dem(
    site_id: str, lat_deg: float, lon_deg: float
) -> DemTile | SldemTile | None:
    """The elevation window around a site, fetched if absent.

    Supports polar 20 m (LDEM_80S_20M), polar 60 m (LDEM_60S_60M), and SLDEM2015.
    Returns ``None`` when it cannot be had.
    """
    s = get_settings()
    path = s.fine_dem_path(site_id)
    if path.exists():
        return load_dem_tile(path)
    if s.offline:
        log.warning("  %s: OFFLINE=1 and no DEM window on disk", site_id)
        return None

    if lat_deg <= -80.0:
        x, y = geographic_to_polar(np.array([lon_deg]), np.array([lat_deg]))
        try:
            await fetch_window_async(
                LDEM_80S_20M, float(x[0]), float(y[0]), s.fine_dem_radius_m, path
            )
        except DemUnavailable as exc:
            log.warning("  %s: fine DEM unavailable (%s); falling back to 80 m", site_id, exc)
            return None
        return load_dem_tile(path)
    elif -80.0 < lat_deg <= -60.0:
        x, y = geographic_to_polar(np.array([lon_deg]), np.array([lat_deg]))
        try:
            await fetch_window_async(
                LDEM_60S_60M, float(x[0]), float(y[0]), s.fine_dem_radius_m, path
            )
        except DemUnavailable as exc:
            log.warning("  %s: 60S DEM unavailable (%s)", site_id, exc)
            return None
        return load_dem_tile(path)
    elif -60.0 < lat_deg < 60.0:
        tile_info = find_sldem_tile(lat_deg, lon_deg)
        if tile_info is None:
            return None
        try:
            await fetch_sldem_window_async(tile_info, lat_deg, lon_deg, s.fine_dem_radius_m, path)
        except DemUnavailable as exc:
            log.warning("  %s: SLDEM unavailable (%s)", site_id, exc)

            return None
        return load_dem_tile(path)
    return None


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
