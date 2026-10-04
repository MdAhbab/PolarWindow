"""SLDEM2015 global digital elevation model: tile geometry, range reads, and terrain sampler.

SLDEM2015 is a combined LOLA + SELENE Terrain Camera digital elevation model
covering latitudes equatorward of +/- 60 degrees at 512 pixels per degree
(~59.2 m/px at the equator). It is published by the PDS Geosciences Node as
headerless 32-bit little-endian float rasters with detached PDS3 labels.
Heights are in kilometres relative to a 1737.4 km reference sphere.

Vertical accuracy:
    Barker et al. 2016, Icarus 273, 346-355: vertical accuracy of SLDEM2015
    is ~3 to 4 m (3.5 m nominal).

Like LOLA polar DEMs, tiles are fixed-record binary files (RECORD_BYTES = 92160,
23040 samples x 4 bytes), allowing local windows to be fetched with HTTP range
requests without downloading the 1.4 GB tile files.
"""

from __future__ import annotations

import asyncio
import logging
import math
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import httpx
import numpy as np
import numpy.typing as npt

from app.core.projections import R_MOON_M
from app.data.lola import DemUnavailable, _parse_multipart_ranges

log = logging.getLogger(__name__)

FloatArray = npt.NDArray[np.float64]

PDS_SLDEM_BASE: Final[str] = (
    "https://pds-geosciences.wustl.edu/lro/lro-l-lola-3-rdr-v1/"
    "lrolol_1xxx/data/sldem2015/tiles/float_img"
)

SLDEM_PRODUCT_NAME: Final[str] = "SLDEM2015 (LOLA + SELENE TC), 59 m"
SLDEM_VERTICAL_ERROR_M: Final[float] = 3.5
SLDEM_SCALE_M: Final[float] = 59.225


@dataclass(frozen=True, slots=True)
class SldemTileInfo:
    """One SLDEM2015 tile geometry and metadata from its PDS3 label."""

    name: str
    filename: str
    min_lat_deg: float
    max_lat_deg: float
    min_lon_deg: float
    max_lon_deg: float
    lines: int = 15360
    samples: int = 23040
    record_bytes: int = 92160  # 23040 * 4 bytes
    line_projection_offset: float = 15359.5
    sample_projection_offset: float = 69119.5
    center_lon_deg: float = 180.0
    map_resolution_ppd: float = 512.0
    vertical_error_m: float = SLDEM_VERTICAL_ERROR_M
    scale_m: float = SLDEM_SCALE_M

    @property
    def url(self) -> str:
        return f"{PDS_SLDEM_BASE}/{self.filename}"

    def lat_lon_to_pixel(self, lat_deg: float, lon_deg: float) -> tuple[float, float]:
        """(lat, lon) in degrees -> fractional (line, sample)."""
        line = self.line_projection_offset - lat_deg * self.map_resolution_ppd
        sample = (
            (lon_deg % 360.0) - self.center_lon_deg
        ) * self.map_resolution_ppd + self.sample_projection_offset
        return line, sample

    def pixel_to_lat_lon(self, line: float, sample: float) -> tuple[float, float]:
        """Fractional (line, sample) -> (lat, lon) in degrees."""
        lat_deg = (self.line_projection_offset - line) / self.map_resolution_ppd
        lon_deg = (
            sample - self.sample_projection_offset
        ) / self.map_resolution_ppd + self.center_lon_deg
        return lat_deg, lon_deg % 360.0


#: Predefined tiles covering mission targets between 60°S and 60°N
SLDEM_TILES: Final[dict[str, SldemTileInfo]] = {
    # Blue Ghost 1 (18.5623 N, 61.8103 E)
    "sldem2015_512_00n_30n_045_090_float": SldemTileInfo(
        name="sldem2015_512_00n_30n_045_090_float",
        filename="sldem2015_512_00n_30n_045_090_float.img",
        min_lat_deg=0.0,
        max_lat_deg=30.0,
        min_lon_deg=45.0,
        max_lon_deg=90.0,
        line_projection_offset=15359.5,
        sample_projection_offset=69119.5,
    ),
    # Peregrine M1 (35.25 N, 319.01 E)
    "sldem2015_512_30n_60n_315_360_float": SldemTileInfo(
        name="sldem2015_512_30n_60n_315_360_float",
        filename="sldem2015_512_30n_60n_315_360_float.img",
        min_lat_deg=30.0,
        max_lat_deg=60.0,
        min_lon_deg=315.0,
        max_lon_deg=360.0,
        line_projection_offset=30719.5,
        sample_projection_offset=-69120.5,
    ),
    # IM-3 (7.39 N, 301.04 E)
    "sldem2015_512_00n_30n_270_315_float": SldemTileInfo(
        name="sldem2015_512_00n_30n_270_315_float",
        filename="sldem2015_512_00n_30n_270_315_float.img",
        min_lat_deg=0.0,
        max_lat_deg=30.0,
        min_lon_deg=270.0,
        max_lon_deg=315.0,
        line_projection_offset=15359.5,
        sample_projection_offset=-46080.5,
    ),
}


def find_sldem_tile(lat_deg: float, lon_deg: float) -> SldemTileInfo | None:
    """Find the SLDEM2015 tile covering a given lunar coordinate."""
    lon = lon_deg % 360.0
    for tile in SLDEM_TILES.values():
        if (
            tile.min_lat_deg <= lat_deg <= tile.max_lat_deg
            and tile.min_lon_deg <= lon <= tile.max_lon_deg
        ):
            return tile
    return None


def is_sldem_covered(lat_deg: float, lon_deg: float) -> bool:
    """True if coordinate is covered by one of our registered SLDEM tiles."""
    return find_sldem_tile(lat_deg, lon_deg) is not None


def is_terrain_covered(lat_deg: float, lon_deg: float) -> bool:
    """Check if a site has real terrain model coverage (LOLA south polar or SLDEM)."""
    if lat_deg <= -60.0:
        return True  # South polar: LOLA 80S (80S-90S) or LOLA 60S (60S-80S)
    return is_sldem_covered(lat_deg, lon_deg)


# ---------------------------------------------------------------------------
# Sampling and Local Frame
# ---------------------------------------------------------------------------


def destination_spherical(
    site_lat_deg: float,
    site_lon_deg: float,
    x_east_m: FloatArray,
    y_north_m: FloatArray,
) -> tuple[FloatArray, FloatArray]:
    """Map local ENU metres (true-north referenced) to selenographic (lat, lon) degrees.

    Uses the spherical destination formula on the 1737.4 km reference sphere:
    bearing = atan2(x_east, y_north), distance = hypot(x_east, y_north).
    """
    x = np.asarray(x_east_m, dtype=np.float64)
    y = np.asarray(y_north_m, dtype=np.float64)
    dist_m = np.hypot(x, y)
    bearing_rad = np.arctan2(x, y)
    d = dist_m / R_MOON_M

    lat1 = math.radians(site_lat_deg)
    lon1 = math.radians(site_lon_deg)
    sin_lat1 = math.sin(lat1)
    cos_lat1 = math.cos(lat1)
    sin_d = np.sin(d)
    cos_d = np.cos(d)

    sin_lat2 = sin_lat1 * cos_d + cos_lat1 * sin_d * np.cos(bearing_rad)
    lat2 = np.arcsin(np.clip(sin_lat2, -1.0, 1.0))
    y_term = np.sin(bearing_rad) * sin_d * cos_lat1
    x_term = cos_d - sin_lat1 * sin_lat2
    lon2 = lon1 + np.arctan2(y_term, x_term)

    return np.degrees(lat2), np.degrees(lon2) % 360.0


@dataclass(frozen=True, slots=True)
class SldemTile:
    """A loaded window of elevation data in Simple Cylindrical."""

    heights: npt.NDArray[np.float32]  # in metres above 1737.4 km reference sphere
    origin_lat_deg: float  # lat of row 0 centre
    origin_lon_deg: float  # lon of col 0 centre
    dlat_deg: float  # latitude step (negative: line increases southward)
    dlon_deg: float  # longitude step (positive: sample increases eastward)
    product: str
    scale_m: float
    vertical_error_m: float

    @classmethod
    def load(cls, path: Path) -> SldemTile:
        if not path.exists():
            raise DemUnavailable(
                f"SLDEM tile window not found: {path}\n"
                f"  fix: make seed   (this fetches the per-site DEM windows)"
            )
        with np.load(path, allow_pickle=False) as z:
            return cls(
                heights=z["heights"],
                origin_lat_deg=float(z["origin_lat_deg"]),
                origin_lon_deg=float(z["origin_lon_deg"]),
                dlat_deg=float(z["dlat_deg"]),
                dlon_deg=float(z["dlon_deg"]),
                product=str(z["product"]),
                scale_m=float(z["scale_m"]),
                vertical_error_m=float(z["vertical_error_m"]),
            )

    def sample_local(
        self,
        site_lat_deg: float,
        site_lon_deg: float,
        x_east_m: FloatArray,
        y_north_m: FloatArray,
    ) -> FloatArray:
        """Bilinear sample at local ENU coordinates.

        Returns NaN outside the tile window.
        """
        lat_pts, lon_pts = destination_spherical(site_lat_deg, site_lon_deg, x_east_m, y_north_m)

        row = (lat_pts - self.origin_lat_deg) / self.dlat_deg
        dlon = (lon_pts - self.origin_lon_deg + 180.0) % 360.0 - 180.0
        col = dlon / self.dlon_deg

        h, w = self.heights.shape
        c0 = np.floor(col).astype(np.int64)
        r0 = np.floor(row).astype(np.int64)
        fc = col - c0
        fr = row - r0

        inside = (c0 >= 0) & (c0 < w - 1) & (r0 >= 0) & (r0 < h - 1)
        c0c = np.clip(c0, 0, w - 2)
        r0c = np.clip(r0, 0, h - 2)

        z00 = self.heights[r0c, c0c].astype(np.float64)
        z01 = self.heights[r0c, c0c + 1].astype(np.float64)
        z10 = self.heights[r0c + 1, c0c].astype(np.float64)
        z11 = self.heights[r0c + 1, c0c + 1].astype(np.float64)

        top = z00 + (z01 - z00) * fc
        bot = z10 + (z11 - z10) * fc
        z = top + (bot - top) * fr
        return np.where(inside, z, np.nan)


def make_sldem_samplers(
    lat_deg: float,
    lon_deg: float,
    tile: SldemTile,
) -> tuple[
    Callable[[FloatArray, FloatArray], FloatArray],
    Callable[[FloatArray, FloatArray], FloatArray],
]:
    """Local-ENU height and vertical-error samplers for a site backed by SLDEM2015."""
    last: list[tuple[object, object, FloatArray]] = []

    def _sample(x_east_m: FloatArray, y_north_m: FloatArray) -> FloatArray:
        if last and last[0][0] is x_east_m and last[0][1] is y_north_m:
            return last[0][2]
        out = tile.sample_local(lat_deg, lon_deg, x_east_m, y_north_m)
        last[:] = [(x_east_m, y_north_m, out)]
        return out

    def sample(x_east_m: FloatArray, y_north_m: FloatArray) -> FloatArray:
        return _sample(x_east_m, y_north_m)

    def sigma(x_east_m: FloatArray, y_north_m: FloatArray) -> FloatArray:
        z = _sample(x_east_m, y_north_m)
        return np.where(np.isfinite(z), tile.vertical_error_m, np.nan)

    return sample, sigma


# ---------------------------------------------------------------------------
# Range Fetching
# ---------------------------------------------------------------------------


async def _fetch_sldem_rows_async(
    tile_info: SldemTileInfo,
    line0: int,
    line1: int,
    sample0: int,
    sample1: int,
    *,
    rows_per_request: int = 64,
    concurrency: int = 8,
    timeout: float = 120.0,
) -> npt.NDArray[np.float32]:
    """Range-read a rectangular window of 32-bit float samples from an SLDEM tile."""
    width = sample1 - sample0
    height = line1 - line0
    bytes_per_sample = 4
    row_bytes = width * bytes_per_sample

    out = np.zeros((height, width), dtype="<f4")
    filled = np.zeros(height, dtype=bool)

    batches = [(b, min(b + rows_per_request, line1)) for b in range(line0, line1, rows_per_request)]
    sem = asyncio.Semaphore(concurrency)
    done = 0

    def offset_of(line: int) -> int:
        return line * tile_info.record_bytes + sample0 * bytes_per_sample

    async def fetch_batch(client: httpx.AsyncClient, b0: int, b1: int) -> None:
        nonlocal done
        spec = ",".join(f"{offset_of(ln)}-{offset_of(ln) + row_bytes - 1}" for ln in range(b0, b1))
        async with sem:
            resp = await client.get(tile_info.url, headers={"Range": f"bytes={spec}"})
        if resp.status_code not in (200, 206):
            raise DemUnavailable(
                f"PDS range request failed for {tile_info.filename} "
                f"lines {b0}-{b1}: HTTP {resp.status_code}"
            )
        ctype = resp.headers.get("content-type", "")
        if "multipart/byteranges" in ctype:
            parts = _parse_multipart_ranges(resp.content, ctype)
        else:
            cr = resp.headers.get("content-range", "")
            start = int(cr.split()[-1].split("/")[0].split("-")[0]) if cr else offset_of(b0)
            parts = [(start, resp.content)]

        for start, data in parts:
            line = (start - sample0 * bytes_per_sample) // tile_info.record_bytes
            idx = line - line0
            if not (0 <= idx < height):
                continue
            if len(data) < row_bytes:
                raise DemUnavailable(
                    f"Short part from {tile_info.filename} line {line}: "
                    f"{len(data)} of {row_bytes} bytes"
                )
            out[idx] = np.frombuffer(data, dtype="<f4", count=width)
            filled[idx] = True
        done += b1 - b0
        if done % 512 < rows_per_request:
            log.info("    %s: %d/%d rows", tile_info.name, done, height)

    limits = httpx.Limits(max_connections=concurrency, max_keepalive_connections=concurrency)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, limits=limits) as client:
        await asyncio.gather(*(fetch_batch(client, b0, b1) for b0, b1 in batches))

    if not filled.all():
        missing_rows = int((~filled).sum())
        raise DemUnavailable(
            f"{missing_rows} of {height} DEM rows were not returned by the "
            f"server for {tile_info.filename}."
        )
    return out


async def fetch_sldem_window_async(
    tile_info: SldemTileInfo,
    centre_lat_deg: float,
    centre_lon_deg: float,
    radius_m: float,
    out_path: Path,
    *,
    timeout: float = 120.0,
) -> dict[str, object]:
    """Fetch a square window around a point and save it as a compressed .npz tile."""
    # Half-extent in degrees
    dlat_deg = math.degrees(radius_m / R_MOON_M)
    cos_lat = max(0.1, math.cos(math.radians(centre_lat_deg)))
    dlon_deg = math.degrees(radius_m / (R_MOON_M * cos_lat))

    lat_max = centre_lat_deg + dlat_deg
    lat_min = centre_lat_deg - dlat_deg
    lon_min = centre_lon_deg - dlon_deg
    lon_max = centre_lon_deg + dlon_deg

    line_top, sample_left = tile_info.lat_lon_to_pixel(lat_max, lon_min)
    line_bottom, sample_right = tile_info.lat_lon_to_pixel(lat_min, lon_max)

    line0 = int(math.floor(line_top))
    line1 = int(math.ceil(line_bottom)) + 1
    sample0 = int(math.floor(sample_left))
    sample1 = int(math.ceil(sample_right)) + 1

    # Check tile boundaries
    if line0 < 0 or line1 > tile_info.lines or sample0 < 0 or sample1 > tile_info.samples:
        raise DemUnavailable(
            f"Requested window crosses tile bounds of {tile_info.name}: "
            f"lines {line0}-{line1} (max {tile_info.lines}), "
            f"samples {sample0}-{sample1} (max {tile_info.samples})"
        )

    log.info(
        "  %s window: samples %d-%d, lines %d-%d (%d x %d px)",
        tile_info.name,
        sample0,
        sample1,
        line0,
        line1,
        sample1 - sample0,
        line1 - line0,
    )

    dn_km = await _fetch_sldem_rows_async(
        tile_info, line0, line1, sample0, sample1, timeout=timeout
    )
    # Convert km to metres above 1737.4 km sphere
    heights_m = dn_km.astype(np.float32) * 1000.0

    origin_lat, origin_lon = tile_info.pixel_to_lat_lon(float(line0), float(sample0))
    dlat = -1.0 / tile_info.map_resolution_ppd
    dlon = 1.0 / tile_info.map_resolution_ppd

    out_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        out_path,
        heights=heights_m,
        origin_lat_deg=np.float64(origin_lat),
        origin_lon_deg=np.float64(origin_lon),
        dlat_deg=np.float64(dlat),
        dlon_deg=np.float64(dlon),
        product=np.str_(SLDEM_PRODUCT_NAME),
        scale_m=np.float64(tile_info.scale_m),
        vertical_error_m=np.float64(tile_info.vertical_error_m),
    )
    return {
        "product": SLDEM_PRODUCT_NAME,
        "path": str(out_path),
        "shape": [int(heights_m.shape[0]), int(heights_m.shape[1])],
        "scale_m": tile_info.scale_m,
        "bytes": out_path.stat().st_size,
    }
