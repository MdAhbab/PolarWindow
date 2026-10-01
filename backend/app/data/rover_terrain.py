"""Native 3/4 m stereo and 5 m LOLA rover terrain, with a 20/80 m fallback.

Kept separate from the surface skyline so finer rover data never silently changes
the precomputed illumination model. No synthetic upsampling or smaller height error.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import math
from functools import lru_cache
from pathlib import Path

import numpy as np

from app.config import get_settings
from app.core.projections import geographic_to_polar, local_frame
from app.data.lola import LDEM_875S_5M, DemTile, fetch_window_async

log = logging.getLogger(__name__)
WINDOW_RADIUS_M = 6000.0  # covers the largest allowed 5 km rover neighbourhood
STEREO_PRODUCT = "LROC_NAC_DTM_NOBILE04"
STEREO_URL = (
    "https://pds.lroc.im-ldi.com/data/LRO-L-LROC-5-RDR-V1.0/LROLRC_2001/"
    "DATA/SDP/NAC_DTM/NOBILE04/NAC_DTM_NOBILE04.TIF"
)
STEREO_SOURCE = "https://data.lroc.im-ldi.com/lroc/view_rdr/NAC_DTM_NOBILE04"
# Reported precision 2.72 m and LOLA registration RMS 1.71 m. Use their sum
# as a conservative bound, rather than assuming independent Gaussian errors.
STEREO_ERROR_M = 2.72 + 1.71
NOBILE03_PRODUCT = "LROC_NAC_DTM_NOBILE03"
NOBILE03_URL = STEREO_URL.replace("NOBILE04", "NOBILE03")
NOBILE03_SOURCE = STEREO_SOURCE.replace("NOBILE04", "NOBILE03")
NOBILE03_ERROR_M = 3.70 + 0.42


@lru_cache(maxsize=32)
def _covers(path: Path, stamp: int, lat: float, lon: float, radius: float) -> bool:
    """Require the entire neighbourhood, including a bilinear interpolation border."""
    frame = local_frame(lon, lat)
    extent = radius * frame.scale_factor
    with np.load(path, allow_pickle=False) as z:
        x, y, step = (float(z[k]) for k in ("origin_x_m", "origin_y_m", "scale_m"))
        heights = z["heights"]
        height, width = heights.shape
        col = math.floor((frame.x0_m - x) / step)
        row = math.floor((y - frame.y0_m) / step)
        if not (0 <= col < width-1 and 0 <= row < height-1):
            return False
        if not np.isfinite(heights[row:row+2, col:col+2]).all():
            return False  # no antenna can be placed where the lander's own ground is unknown
    return (
        x <= frame.x0_m - extent
        and frame.x0_m + extent < x + (width - 1) * step
        and y - (height - 1) * step < frame.y0_m - extent
        and frame.y0_m + extent <= y
    )


def terrain_path(site_id: str, lat: float, lon: float, radius: float) -> Path:
    s = get_settings()
    for path in (s.rover_stereo_path(site_id), s.rover_stereo4_path(site_id),
                 s.rover_dem_path(site_id), s.fine_dem_path(site_id)):
        if path.exists() and _covers(path, path.stat().st_mtime_ns, lat, lon, radius):
            return path
    return s.regional_dem_path


@lru_cache(maxsize=32)
def _digest(path: Path, stamp: int, size: int) -> str:
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def version(path: Path) -> str:
    if not path.exists():
        return "missing"
    stat = path.stat()
    return _digest(path, stat.st_mtime_ns, stat.st_size)


async def ensure_rover_dem(site_id: str, lat: float, lon: float) -> bool:
    s = get_settings()
    if lat > -87.5:
        return False
    path = s.rover_dem_path(site_id)
    if path.exists():
        return True
    if s.offline:
        return False
    x, y = geographic_to_polar(np.array([lon]), np.array([lat]))
    staged = path.with_suffix(".pending.npz")
    await fetch_window_async(LDEM_875S_5M, float(x[0]), float(y[0]), WINDOW_RADIUS_M, staged)
    tile = DemTile.load(staged)
    staged.replace(path)
    log.info("%s: native %g m rover terrain, %s", site_id, tile.scale_m, tile.heights.shape)
    return True


def crop_stereo(
    source: str | Path, path: Path, lat: float, lon: float, *,
    product: str = STEREO_PRODUCT, error_m: float = STEREO_ERROR_M,
    post_m: float = 3.0, clip_to_footprint: bool = False,
) -> bool:
    """Read native posts only, preserve shadow/nodata gaps, and use pixel centres."""
    import rasterio
    from pyproj import Transformer
    from rasterio.windows import Window

    from app.core.projections import MOON_SOUTH_POLAR

    frame = local_frame(lon, lat)
    extent = WINDOW_RADIUS_M * frame.scale_factor
    with rasterio.Env(
        GDAL_HTTP_TIMEOUT="60", GDAL_HTTP_MAX_RETRY="2",
        GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
    ), rasterio.open(source) as src:
        if src.crs is None or not src.crs.is_projected:
            raise ValueError("Stereo terrain must use the Moon's south polar stereographic grid")
        # Equivalent lunar CRSs may have different datum names or encode scale
        # as lat_ts=-90 versus k=1. Check their mapping, rather than WKT spelling.
        points = np.array([0.0, 100000.0, -100000.0])
        tx, ty = Transformer.from_crs(src.crs, MOON_SOUTH_POLAR, always_xy=True).transform(
            points, points
        )
        if not (np.allclose(tx, points, rtol=0, atol=1e-5)
                and np.allclose(ty, points, rtol=0, atol=1e-5)):
            raise ValueError("Stereo terrain projection differs from the lunar terrain grid")
        a = src.transform
        if a.b != 0 or a.d != 0 or a.a != post_m or a.e != -post_m:
            raise ValueError(f"Expected native north-up {post_m:g} m LROC terrain")
        col, row = (frame.x0_m - a.c) / a.a, (frame.y0_m - a.f) / a.e
        if not (0 <= col < src.width and 0 <= row < src.height):
            return False
        n = math.ceil(extent / a.a) + 2
        c0, r0 = math.floor(col) - n, math.floor(row) - n
        c1, r1 = c0 + 2*n + 1, r0 + 2*n + 1
        if clip_to_footprint:
            c0, r0, c1, r1 = max(0, c0), max(0, r0), min(src.width, c1), min(src.height, r1)
        elif c0 < 0 or r0 < 0 or c1 > src.width or r1 > src.height:
            return False
        window = Window(c0, r0, c1-c0, r1-r0)
        heights = src.read(1, window=window, masked=True).astype(np.float32).filled(np.nan)
        heights[~np.isfinite(heights) | (heights < -1e20)] = np.nan
        origin_x, origin_y = a.c + (c0 + 0.5) * a.a, a.f + (r0 + 0.5) * a.e
    path.parent.mkdir(parents=True, exist_ok=True)
    staged = path.with_suffix(".pending.npz")
    np.savez_compressed(
        staged, heights=heights, origin_x_m=origin_x, origin_y_m=origin_y,
        scale_m=post_m, product=product, vertical_error_m=error_m,
    )
    staged.replace(path)
    return True


async def ensure_stereo_dem(site_id: str, lat: float, lon: float) -> bool:
    s = get_settings()
    if not (-85.38 <= lat <= -83.56 and 23.24 <= lon <= 42.11):
        return False
    path = s.rover_stereo_path(site_id)
    if path.exists():
        return True
    if s.offline:
        return False
    return await asyncio.to_thread(crop_stereo, STEREO_URL, path, lat, lon)


async def ensure_nobile03_dem(site_id: str, lat: float, lon: float) -> bool:
    """A small native 4 m footprint: useful near IM-2, never padded to a larger area."""
    s = get_settings()
    if not (-84.85 <= lat <= -84.60 and 27.90 <= lon <= 30.39):
        return False
    path = s.rover_stereo4_path(site_id)
    if path.exists():
        return True
    if s.offline:
        return False
    return await asyncio.to_thread(
        crop_stereo, NOBILE03_URL, path, lat, lon, product=NOBILE03_PRODUCT,
        error_m=NOBILE03_ERROR_M, post_m=4.0, clip_to_footprint=True,
    )


async def sync_windows() -> tuple[int, int]:
    from app.db.repositories.sites import SiteRepository
    from app.db.session import dispose_engine, session_scope

    try:
        async with session_scope() as session:
            sites, _ = await SiteRepository(session).list_sites(kind=None, limit=1000)
    finally:
        await dispose_engine()
    present, fetched = 0, 0
    for site in sites:
        for ensure, path in (
            (ensure_rover_dem, get_settings().rover_dem_path(site.id)),
            (ensure_stereo_dem, get_settings().rover_stereo_path(site.id)),
            (ensure_nobile03_dem, get_settings().rover_stereo4_path(site.id)),
        ):
            had = path.exists()
            if await ensure(site.id, site.lat_deg, site.lon_deg):
                present += 1
                fetched += int(not had)
    return present, fetched


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    print("Rover terrain windows (present, fetched):", asyncio.run(sync_windows()))
