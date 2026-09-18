"""Render the three raster layers into a static PNG pyramid.

ADR-4 chose pre-rendering over dynamic rio-tiler, for one reason that dominates
everything else: the output space is small enough to enumerate. The extent is
fixed (one polar scene, +-304 km), the data is static, and the whole pyramid is
a few hundred MB -- less than the SPICE kernels. Enumerating it converts a
latency-and-reliability problem into a storage problem, and storage is the
cheapest thing here.

Tile scheme
-----------
A plain quadtree over the DEM's own extent, in the same lunar south polar
stereographic projection the data ships in. z0 is one tile covering +-304 km;
each level doubles. ``x`` increases with grid east, ``y`` increases with grid
south, matching the usual slippy-map convention so the frontend does not need a
special case.

Deliberately *not* a Web Mercator scheme: there is no lunar basemap service to
align with, and reprojecting a polar dataset into Mercator to serve a polar map
would add distortion and a dependency for no benefit.

The three layers
----------------
* ``hillshade`` -- relief from the DEM. Schematic, low-chroma, matching the
  product's visual language.
* ``illumination`` -- approximate average sunlit fraction over a year.
* ``psr`` -- approximate permanently shadowed regions.

The last two are **approximations and are labelled as such** everywhere they
appear. A true illumination map needs a full horizon computation per pixel; what
is computed here is the ring-based horizon proxy compared against the Sun's
elevation envelope at that latitude. That is a genuine first-order calculation,
it is right about which craters are dark, and it is not a published PSR product.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np
import numpy.typing as npt
from scipy.ndimage import maximum_filter

from app.core.projections import R_MOON_M
from app.data.lola import DemTile

log = logging.getLogger(__name__)

TILE_PX: Final[int] = 256
LAYERS: Final[tuple[str, ...]] = ("hillshade", "illumination", "psr")

#: The Moon's axial tilt to the ecliptic. The reason the poles are strange: the
#: Sun never rises more than this above the horizontal at the pole itself.
OBLIQUITY_DEG: Final[float] = 1.5424


@dataclass(frozen=True, slots=True)
class TileGrid:
    """A quadtree over a square extent centred on the pole."""

    half_extent_m: float

    def tile_size_m(self, z: int) -> float:
        return float(2.0 * self.half_extent_m / (2**z))

    def bounds(self, z: int, x: int, y: int) -> tuple[float, float, float, float]:
        """(x_min, y_min, x_max, y_max) in projected metres."""
        size = self.tile_size_m(z)
        x_min = -self.half_extent_m + x * size
        y_max = self.half_extent_m - y * size
        return x_min, y_max - size, x_min + size, y_max

    def in_range(self, z: int, x: int, y: int) -> bool:
        n = 2**z
        return bool(0 <= x < n and 0 <= y < n)


def _hillshade(
    z_m: npt.NDArray[np.float64], res_m: float, az_deg: float = 315.0, alt_deg: float = 25.0
) -> npt.NDArray[np.uint8]:
    """Standard Horn hillshade.

    A low sun altitude (25 deg) is used rather than the usual 45 deg because at
    the south pole the interesting relief is subtle and low-angle lighting is
    what the terrain actually looks like there.
    """
    gy, gx = np.gradient(z_m, res_m)
    slope = np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(-gx, gy)
    az = np.radians(360.0 - az_deg + 90.0)
    alt = np.radians(alt_deg)
    shade = np.sin(alt) * np.cos(slope) + np.cos(alt) * np.sin(slope) * np.cos(az - aspect)
    return np.asarray((np.clip(shade, 0, 1) * 255).astype(np.uint8), dtype=np.uint8)


def _horizon_proxy_deg(
    z_m: npt.NDArray[np.float64],
    res_m: float,
    radii_m: tuple[float, ...] = (500.0, 1500.0, 4000.0, 10000.0, 25000.0),
) -> npt.NDArray[np.float64]:
    """Ring-based skyline approximation, as in ``ingest_sites``."""
    worst = np.full(z_m.shape, -90.0)
    for r in radii_m:
        size = max(3, int(round(2.0 * r / res_m)) | 1)
        local_max = maximum_filter(z_m, size=size, mode="nearest")
        drop = r * r / (2.0 * R_MOON_M)
        worst = np.maximum(worst, np.degrees(np.arctan2(local_max - z_m - drop, r)))
    return worst


def _max_sun_elevation_deg(lat_deg: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    """Highest the Sun's centre ever reaches at a latitude, ignoring terrain.

    At latitude phi (negative south) the sub-solar latitude oscillates over
    +-OBLIQUITY across a year, so the Sun's maximum elevation on a smooth sphere
    is ``90 - |phi| + OBLIQUITY`` in the southern summer -- which at -89 deg is
    about 2.5 deg, and at the pole itself 1.54 deg.
    """
    return 90.0 - np.abs(lat_deg) + OBLIQUITY_DEG


def render_layer(
    layer: str, tile: DemTile, bounds: tuple[float, float, float, float], size_px: int = TILE_PX
) -> npt.NDArray[np.uint8] | None:
    """Render one tile as an RGBA array, or None if it has no data."""
    x_min, y_min, x_max, y_max = bounds
    xs = np.linspace(x_min, x_max, size_px)
    ys = np.linspace(y_max, y_min, size_px)
    xx, yy = np.meshgrid(xs, ys)
    z = tile.sample_grid(xx, yy)
    if not np.isfinite(z).any():
        return None
    res_m = (x_max - x_min) / size_px
    z_filled = np.where(np.isfinite(z), z, np.nanmin(z[np.isfinite(z)]))

    rgba = np.zeros((size_px, size_px, 4), dtype=np.uint8)

    if layer == "hillshade":
        shade = _hillshade(z_filled, res_m)
        # Low-chroma grey, matching the product's terrain palette.
        rgba[..., 0] = (shade * 0.62).astype(np.uint8)
        rgba[..., 1] = (shade * 0.66).astype(np.uint8)
        rgba[..., 2] = (shade * 0.72).astype(np.uint8)
        rgba[..., 3] = 255
    elif layer in ("illumination", "psr"):
        horizon = _horizon_proxy_deg(z_filled, res_m)
        r = np.hypot(xx, yy)
        lat = -(90.0 - np.degrees(r / R_MOON_M))
        max_sun = _max_sun_elevation_deg(lat)
        if layer == "illumination":
            # Fraction of the Sun's annual elevation range that clears the
            # local skyline. Crude, monotonic in the right direction, and
            # labelled approximate wherever it is drawn.
            span = 2.0 * OBLIQUITY_DEG
            frac = np.clip((max_sun - horizon) / max(span, 1e-6), 0.0, 1.0)
            rgba[..., 0] = (242 * frac).astype(np.uint8)
            rgba[..., 1] = (163 * frac).astype(np.uint8)
            rgba[..., 2] = (60 * frac).astype(np.uint8)
            rgba[..., 3] = (200 * frac).astype(np.uint8)
        else:
            shadowed = horizon > max_sun
            rgba[..., 0] = 14
            rgba[..., 1] = 17
            rgba[..., 2] = 20
            rgba[..., 3] = np.where(shadowed, 210, 0).astype(np.uint8)
    else:
        raise ValueError(f"unknown layer {layer!r}")

    z_missing = ~np.isfinite(z)
    if z_missing.any():
        rgba[z_missing, 3] = 0
    return rgba


def write_png(path: Path, rgba: npt.NDArray[np.uint8]) -> None:
    """Write RGBA to PNG with no extra dependency.

    zlib + a hand-rolled PNG chunk writer, because pulling Pillow in for one
    function would add an image stack to a service that otherwise has none.
    """
    import struct
    import zlib

    h, w, _ = rgba.shape
    raw = b"".join(b"\x00" + rgba[i].tobytes() for i in range(h))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 6))
        + chunk(b"IEND", b"")
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)


def render_pyramid(
    tile: DemTile, out_dir: Path, *, max_zoom: int = 5, layers: tuple[str, ...] = LAYERS
) -> dict[str, int]:
    """Render every tile of every layer up to ``max_zoom``."""
    grid = TileGrid(half_extent_m=abs(tile.origin_x_m))
    counts: dict[str, int] = {}
    for layer in layers:
        written = 0
        for z in range(max_zoom + 1):
            for x in range(2**z):
                for y in range(2**z):
                    rgba = render_layer(layer, tile, grid.bounds(z, x, y))
                    if rgba is None:
                        continue
                    write_png(out_dir / layer / str(z) / str(x) / f"{y}.png", rgba)
                    written += 1
            log.info("  %s z%d done (%d tiles so far)", layer, z, written)
        counts[layer] = written
        log.info("%s: %d tiles", layer, written)
    return counts


def main() -> None:
    import sys

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    from app.config import get_settings

    s = get_settings()
    max_zoom = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    tile = DemTile.load(s.regional_dem_path)
    counts = render_pyramid(tile, s.tile_dir, max_zoom=max_zoom)
    log.info("wrote %d tiles to %s", sum(counts.values()), s.tile_dir)


if __name__ == "__main__":
    main()
