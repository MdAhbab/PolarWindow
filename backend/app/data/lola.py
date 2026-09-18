"""LOLA polar DEM access: product definitions, windowed fetch, terrain sampler.

This is the I/O half of the terrain story. ``core/horizon.py`` holds the pure
ray-march and takes a callable; this module is what produces that callable from
real data, which is why it lives in ``data/`` and why ``core`` is forbidden from
importing rasterio.

The products
------------
LOLA gridded polar DEMs are published by the PDS Geosciences node as headerless
little-endian int16 rasters with a detached PDS3 label. Heights are
``DN * 0.5`` metres relative to a 1737.4 km reference sphere, in polar
stereographic with scale true **at the pole**.

Because the files are headerless with a fixed record length, the byte offset of
any pixel is arithmetic:

    offset(line, sample) = line * RECORD_BYTES + sample * 2

which means a 50 km window around a site can be pulled with HTTP range requests
instead of downloading 1.85 GB. That is the difference between a 40-minute
setup and a 40-second one, and it is the only reason a 20 m DEM is practical
for this build at all.

Two tiers, and why
------------------
* **Fine (20 m) within 20 km** of each site, fetched per-site. This is where
  blockers actually live: at these sites the ridge that decides the answer is
  1-3 km away.
* **Coarse (80 m) from 20 km to 50 km**, one 115 MB file covering the whole
  region. Beyond 20 km the curvature drop (115 m at 20 km, 720 m at 50 km)
  exceeds nearly all polar relief above a site, so terrain out there rarely sets
  the skyline -- and when it does, an 80 m post subtends 0.09 deg at 50 km,
  which is the same order as the mask's own tolerance.

The tiering is a stated approximation, carried into ``meta.uncertainty`` rather
than hidden.
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

from app.core.projections import R_MOON_M, local_frame

log = logging.getLogger(__name__)

FloatArray = npt.NDArray[np.float64]

PDS_BASE: Final[str] = (
    "https://pds-geosciences.wustl.edu/lro/lro-l-lola-3-rdr-v1/"
    "lrolol_1xxx/data/lola_gdr/polar/img"
)


@dataclass(frozen=True, slots=True)
class LolaProduct:
    """One LOLA gridded polar DEM, described from its PDS label.

    Every field here was read out of the published label rather than assumed.
    ``projection_offset_px`` in particular is the PDS
    ``LINE/SAMPLE_PROJECTION_OFFSET``: the pixel coordinate of the projection
    origin, which is half-integer for an even-sized grid.
    """

    name: str
    filename: str
    size_px: int
    scale_m: float
    projection_offset_px: float
    scaling_factor: float = 0.5
    reference_radius_m: float = R_MOON_M
    vertical_error_m: float = 2.0

    @property
    def url(self) -> str:
        return f"{PDS_BASE}/{self.filename}"

    @property
    def record_bytes(self) -> int:
        return self.size_px * 2

    @property
    def total_bytes(self) -> int:
        return self.record_bytes * self.size_px

    @property
    def half_extent_m(self) -> float:
        return self.size_px * self.scale_m / 2.0

    def world_to_pixel(self, x_m: FloatArray, y_m: FloatArray) -> tuple[FloatArray, FloatArray]:
        """Polar stereographic metres -> fractional (sample, line).

        ``y`` increases north; ``line`` increases south, hence the sign flip.
        """
        sample = x_m / self.scale_m + self.projection_offset_px
        line = self.projection_offset_px - y_m / self.scale_m
        return sample, line

    def pixel_to_world(self, sample: FloatArray, line: FloatArray) -> tuple[FloatArray, FloatArray]:
        x = (sample - self.projection_offset_px) * self.scale_m
        y = (self.projection_offset_px - line) * self.scale_m
        return x, y


#: 20 m/px, 80S-90S. 1.85 GB -- never downloaded whole; windowed by range request.
LDEM_80S_20M: Final[LolaProduct] = LolaProduct(
    name="LOLA_LDEM_80S_20M",
    filename="ldem_80s_20m.img",
    size_px=30400,
    scale_m=20.0,
    projection_offset_px=15199.5,
)

#: 80 m/px, 80S-90S. 115 MB -- small enough to hold entirely.
LDEM_80S_80M: Final[LolaProduct] = LolaProduct(
    name="LOLA_LDEM_80S_80M",
    filename="ldem_80s_80m.img",
    size_px=7600,
    scale_m=80.0,
    projection_offset_px=3799.5,
    vertical_error_m=4.0,
)


class DemUnavailable(RuntimeError):
    """The DEM subset this site needs is not on disk.

    Distinct from a network error: this means the seed step has not run. The
    caller turns it into a partial-coverage mask and a stated uncertainty, never
    into a flat horizon presented as terrain.
    """


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------


def _parse_multipart_ranges(body: bytes, content_type: str) -> list[tuple[int, bytes]]:
    """Parse a ``multipart/byteranges`` body into ``(start_offset, data)`` pairs.

    Parts are keyed by the byte offset from their own ``Content-Range`` header
    rather than by their position in the response. RFC 9110 lets a server
    coalesce, reorder or merge ranges, and a parser that assumes request order
    silently transposes rows of the DEM when it does -- which would look like
    terrain, not like a bug.
    """
    marker = "boundary="
    if marker not in content_type:
        raise DemUnavailable(f"expected multipart/byteranges, got: {content_type!r}")
    boundary = content_type.split(marker, 1)[1].strip().strip('"')
    sep = b"--" + boundary.encode("ascii")

    out: list[tuple[int, bytes]] = []
    for chunk in body.split(sep):
        if not chunk or chunk.startswith(b"--"):
            continue
        head, _, data = chunk.partition(b"\r\n\r\n")
        if not _:
            continue
        start: int | None = None
        for line in head.split(b"\r\n"):
            if line.lower().startswith(b"content-range:"):
                spec = line.split(b":", 1)[1].strip()
                spec = spec.split(b"/", 1)[0].strip()
                if spec.lower().startswith(b"bytes"):
                    spec = spec[5:].strip()
                start = int(spec.split(b"-", 1)[0])
                break
        if start is None:
            continue
        # Each part's payload is terminated by the CRLF preceding the boundary.
        out.append((start, data[:-2] if data.endswith(b"\r\n") else data))
    if not out:
        raise DemUnavailable("multipart/byteranges response contained no parts")
    return out


async def _fetch_rows_async(
    product: LolaProduct,
    line0: int,
    line1: int,
    sample0: int,
    sample1: int,
    *,
    rows_per_request: int = 64,
    concurrency: int = 8,
    timeout: float = 120.0,
) -> npt.NDArray[np.int16]:
    """Range-read a rectangular window using batched, concurrent requests.

    Two measurements shaped this, taken against the live PDS server:

    * One range per request costs ~1.6 s of round-trip regardless of size, so a
      2,001-row window would take 50 minutes. The server supports
      ``multipart/byteranges``, so 64 rows go in one request.
    * A single connection tops out near 200 KB/s; eight concurrent connections
      reach ~680 KB/s. Beyond eight the server stops rewarding it and large
      multipart requests (512 ranges) actually get *slower*, so the batch size
      is 64 rather than as large as possible.

    Together those take a 20 km window at 20 m from ~50 minutes to ~12 seconds.
    """
    width = sample1 - sample0
    height = line1 - line0
    out = np.zeros((height, width), dtype="<i2")
    filled = np.zeros(height, dtype=bool)
    row_bytes = width * 2

    batches = [(b, min(b + rows_per_request, line1)) for b in range(line0, line1, rows_per_request)]
    sem = asyncio.Semaphore(concurrency)
    done = 0

    def offset_of(line: int) -> int:
        return line * product.record_bytes + sample0 * 2

    async def fetch_batch(client: httpx.AsyncClient, b0: int, b1: int) -> None:
        nonlocal done
        spec = ",".join(f"{offset_of(ln)}-{offset_of(ln) + row_bytes - 1}" for ln in range(b0, b1))
        async with sem:
            resp = await client.get(product.url, headers={"Range": f"bytes={spec}"})
        if resp.status_code not in (200, 206):
            raise DemUnavailable(
                f"PDS range request failed for {product.filename} "
                f"lines {b0}-{b1}: HTTP {resp.status_code}"
            )
        ctype = resp.headers.get("content-type", "")
        if "multipart/byteranges" in ctype:
            parts = _parse_multipart_ranges(resp.content, ctype)
        else:
            # A single-range request (or a server that coalesced) returns the
            # bytes directly; recover the offset from Content-Range.
            cr = resp.headers.get("content-range", "")
            start = int(cr.split()[-1].split("/")[0].split("-")[0]) if cr else offset_of(b0)
            parts = [(start, resp.content)]

        for start, data in parts:
            line = (start - sample0 * 2) // product.record_bytes
            idx = line - line0
            if not (0 <= idx < height):
                continue
            if len(data) < row_bytes:
                raise DemUnavailable(
                    f"Short part from {product.filename} line {line}: "
                    f"{len(data)} of {row_bytes} bytes"
                )
            out[idx] = np.frombuffer(data, dtype="<i2", count=width)
            filled[idx] = True
        done += b1 - b0
        if done % 512 < rows_per_request:
            log.info("    %s: %d/%d rows", product.name, done, height)

    limits = httpx.Limits(max_connections=concurrency, max_keepalive_connections=concurrency)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, limits=limits) as client:
        await asyncio.gather(*(fetch_batch(client, b0, b1) for b0, b1 in batches))

    if not filled.all():
        missing_rows = int((~filled).sum())
        raise DemUnavailable(
            f"{missing_rows} of {height} DEM rows were not returned by the "
            f"server for {product.filename}. Re-run the fetch; a partially "
            f"filled window would read as flat ground and block nothing."
        )
    return out


async def fetch_window_async(
    product: LolaProduct,
    centre_x_m: float,
    centre_y_m: float,
    radius_m: float,
    out_path: Path,
    *,
    timeout: float = 60.0,
) -> dict[str, object]:
    """Fetch a square window around a point and save it as a .npz tile.

    Async because the precompute worker is async; ``fetch_window`` below is the
    synchronous entry point for scripts. Having the sync wrapper call
    ``asyncio.run`` from inside a running loop is exactly the bug this split
    fixes -- the worker hit it on its first site.

    Saved as compressed numpy rather than GeoTIFF on purpose: the consumer is
    ``sampler_from_tile`` below, which wants a plain array and four numbers.
    Writing a GeoTIFF would mean carrying a rasterio dependency into the read
    path for no benefit -- and ``core/`` is forbidden from importing rasterio.
    """
    half_px = int(math.ceil(radius_m / product.scale_m))
    cs, cl = product.world_to_pixel(np.array([centre_x_m]), np.array([centre_y_m]))
    sample_c, line_c = int(round(float(cs[0]))), int(round(float(cl[0])))

    sample0 = max(0, sample_c - half_px)
    sample1 = min(product.size_px, sample_c + half_px + 1)
    line0 = max(0, line_c - half_px)
    line1 = min(product.size_px, line_c + half_px + 1)

    if sample1 <= sample0 or line1 <= line0:
        raise DemUnavailable(
            f"Requested window is entirely outside {product.name}: "
            f"centre pixel ({sample_c}, {line_c}) in a {product.size_px}^2 grid."
        )

    clipped = (
        sample0 != sample_c - half_px
        or sample1 != sample_c + half_px + 1
        or line0 != line_c - half_px
        or line1 != line_c + half_px + 1
    )

    log.info(
        "  %s window: samples %d-%d, lines %d-%d (%d x %d px)%s",
        product.name,
        sample0,
        sample1,
        line0,
        line1,
        sample1 - sample0,
        line1 - line0,
        " [clipped to grid edge]" if clipped else "",
    )

    dn = await _fetch_rows_async(product, line0, line1, sample0, sample1, timeout=timeout)

    heights = dn.astype(np.float32) * np.float32(product.scaling_factor)

    x0, y0 = product.pixel_to_world(np.array([float(sample0)]), np.array([float(line0)]))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        out_path,
        heights=heights,
        origin_x_m=np.float64(x0[0]),
        origin_y_m=np.float64(y0[0]),
        scale_m=np.float64(product.scale_m),
        product=np.str_(product.name),
        vertical_error_m=np.float64(product.vertical_error_m),
    )
    return {
        "product": product.name,
        "path": str(out_path),
        "shape": [int(heights.shape[0]), int(heights.shape[1])],
        "scale_m": product.scale_m,
        "clipped": clipped,
        "bytes": out_path.stat().st_size,
    }


def fetch_window(
    product: LolaProduct,
    centre_x_m: float,
    centre_y_m: float,
    radius_m: float,
    out_path: Path,
    *,
    timeout: float = 60.0,
) -> dict[str, object]:
    """Synchronous entry point, for scripts that are not already in a loop."""
    return asyncio.run(
        fetch_window_async(product, centre_x_m, centre_y_m, radius_m, out_path, timeout=timeout)
    )


def fetch_full(
    product: LolaProduct, out_path: Path, *, timeout: float = 1800.0
) -> dict[str, object]:
    """Download a whole product. Only sensible for the 80 m tier (115 MB)."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    raw = out_path.with_suffix(".img")
    if not raw.exists() or raw.stat().st_size != product.total_bytes:
        log.info("fetching %s (%.0f MB)", product.filename, product.total_bytes / 1e6)
        tmp = raw.with_suffix(".part")
        with (
            httpx.stream("GET", product.url, timeout=timeout, follow_redirects=True) as resp,
            tmp.open("wb") as fh,
        ):
            resp.raise_for_status()
            for chunk in resp.iter_bytes(1 << 20):
                fh.write(chunk)
        tmp.rename(raw)
    dn = np.fromfile(raw, dtype="<i2").reshape(product.size_px, product.size_px)
    heights = dn.astype(np.float32) * np.float32(product.scaling_factor)
    x0, y0 = product.pixel_to_world(np.array([0.0]), np.array([0.0]))
    np.savez_compressed(
        out_path,
        heights=heights,
        origin_x_m=np.float64(x0[0]),
        origin_y_m=np.float64(y0[0]),
        scale_m=np.float64(product.scale_m),
        product=np.str_(product.name),
        vertical_error_m=np.float64(product.vertical_error_m),
    )
    return {"product": product.name, "path": str(out_path), "bytes": out_path.stat().st_size}


# ---------------------------------------------------------------------------
# Sampling
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DemTile:
    """A loaded window of elevation data in the polar stereographic grid."""

    heights: npt.NDArray[np.float32]
    origin_x_m: float
    origin_y_m: float
    scale_m: float
    product: str
    vertical_error_m: float

    @classmethod
    def load(cls, path: Path) -> DemTile:
        if not path.exists():
            raise DemUnavailable(
                f"DEM tile not found: {path}\n"
                f"  fix: make seed   (this fetches the per-site DEM windows)"
            )
        with np.load(path, allow_pickle=False) as z:
            return cls(
                heights=z["heights"],
                origin_x_m=float(z["origin_x_m"]),
                origin_y_m=float(z["origin_y_m"]),
                scale_m=float(z["scale_m"]),
                product=str(z["product"]),
                vertical_error_m=float(z["vertical_error_m"]),
            )

    def sample_grid(self, x_m: FloatArray, y_m: FloatArray) -> FloatArray:
        """Bilinear sample at polar stereographic coordinates.

        Returns NaN outside the tile. NaN rather than an edge clamp, because a
        clamp fabricates terrain at the boundary -- it would extend the last
        row of pixels outward forever, which near a crater rim invents a plateau
        that blocks the Sun. NaN propagates into ``coverage`` and gets reported.
        """
        col = (np.asarray(x_m, dtype=np.float64) - self.origin_x_m) / self.scale_m
        row = (self.origin_y_m - np.asarray(y_m, dtype=np.float64)) / self.scale_m

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


def make_samplers(
    lat_deg: float,
    lon_deg: float,
    fine: DemTile | None,
    coarse: DemTile | None = None,
) -> tuple[
    Callable[[FloatArray, FloatArray], FloatArray],
    Callable[[FloatArray, FloatArray], FloatArray],
]:
    """Local-ENU height and vertical-error samplers for a site.

    Handles the part that is easy to get catastrophically wrong: near the south
    pole, **grid north in a polar stereographic projection is not true north**.
    It rotates with longitude. Marching a ray along grid +y and calling it
    bearing 0 would put every blocker at the wrong azimuth by an amount equal to
    the site's longitude -- 166 deg at Shackleton, which would not look like a
    bug, it would look like different terrain. ``local_frame`` measures the
    convergence (and the projection's scale factor) and ``local_to_grid``
    applies both.

    Fine and coarse tiers are combined by preferring fine wherever it has data.
    The error sampler follows the same choice, so a blocker found on the 80 m
    regional model carries the regional model's error, not the 20 m one's.
    """
    frame = local_frame(lon_deg, lat_deg)
    Tiers = tuple[FloatArray, FloatArray, npt.NDArray[np.bool_]]
    last: list[tuple[object, object, Tiers]] = []

    def _tiers(x_east_m: FloatArray, y_north_m: FloatArray) -> Tiers:
        # The ray-march asks for heights and then errors along the *same* ray
        # arrays. Remembering the last lookup by identity halves the bilinear
        # work -- without it the per-tier error doubled the mask build time.
        if last and last[0][0] is x_east_m and last[0][1] is y_north_m:
            return last[0][2]
        gx, gy = frame.local_to_grid(
            np.asarray(x_east_m, dtype=np.float64), np.asarray(y_north_m, dtype=np.float64)
        )
        zc = coarse.sample_grid(gx, gy) if coarse is not None else np.full(gx.shape, np.nan)
        zf = fine.sample_grid(gx, gy) if fine is not None else np.full(gx.shape, np.nan)
        out = (zf, zc, np.isfinite(zf))
        last[:] = [(x_east_m, y_north_m, out)]
        return out

    def sample(x_east_m: FloatArray, y_north_m: FloatArray) -> FloatArray:
        zf, zc, use_fine = _tiers(x_east_m, y_north_m)
        return np.where(use_fine, zf, zc)

    def sigma(x_east_m: FloatArray, y_north_m: FloatArray) -> FloatArray:
        _zf, zc, use_fine = _tiers(x_east_m, y_north_m)
        fine_err = fine.vertical_error_m if fine is not None else np.nan
        coarse_err = coarse.vertical_error_m if coarse is not None else np.nan
        return np.where(use_fine, fine_err, np.where(np.isfinite(zc), coarse_err, np.nan))

    return sample, sigma


def make_sampler(
    lat_deg: float,
    lon_deg: float,
    fine: DemTile | None,
    coarse: DemTile | None = None,
) -> Callable[[FloatArray, FloatArray], FloatArray]:
    """The height sampler alone; see ``make_samplers``."""
    return make_samplers(lat_deg, lon_deg, fine, coarse)[0]
