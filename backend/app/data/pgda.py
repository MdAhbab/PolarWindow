"""NASA PGDA rasters read at points: 5 m LOLA site tiles and the illumination maps.

Windowed reads only (the 60 m illumination maps are 50 MB, the 5 m tiles 40 MB
each). Each raster's own transform, nodata and scale/offset tags are used;
nothing about the grid is assumed. ``crs_matches_app`` checks that a raster is
in the same south polar stereographic frame as ``core.projections`` so a point
in the app's frame can be looked up directly.

The files are not in git and are not yet in ``data/registry.py``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt
import rasterio
from pyproj import CRS, Transformer
from rasterio.windows import Window

from app.core.projections import MOON_GEOGRAPHIC, MOON_SOUTH_POLAR

FloatArray = npt.NDArray[np.float64]

LOLA_DIR = "pgda_lola_5m"
ILLUM_DIR = "pgda_illumination"
#: Illumination products, finest first, with their file stems.
ILLUM_STEMS = ("85S_060M", "75S_120M", "65S_240M")
ILLUM_EPOCH = "2016-08 release of LOLA data collected 2009-07-13 to 2013-07-18"


@dataclass(frozen=True, slots=True)
class Window2D:
    """A scaled window: NaN where the raster has no data.

    ``origin_x_m`` / ``origin_y_m`` are the outer corner of the top-left cell
    (rows run to -y). The cells are ``res_m`` square.
    """

    values: FloatArray
    origin_x_m: float
    origin_y_m: float
    res_m: float
    crs_wkt: str


@dataclass(frozen=True, slots=True)
class LolaTile:
    name: str
    surf: Path
    toterr: Path
    slp: Path
    left: float
    bottom: float
    right: float
    top: float
    res_m: float
    crs_wkt: str

    def contains(self, x0: float, y0: float, x1: float, y1: float, margin: float = 0.0) -> bool:
        return (
            x0 - margin >= self.left
            and x1 + margin <= self.right
            and y0 - margin >= self.bottom
            and y1 + margin <= self.top
        )


def crs_matches_app(crs_wkt: str, tol_m: float = 1.0) -> bool:
    """True when the raster's projection puts a lon/lat where the app's does."""
    try:
        theirs = Transformer.from_crs(MOON_GEOGRAPHIC, CRS.from_wkt(crs_wkt), always_xy=True)
        ours = Transformer.from_crs(MOON_GEOGRAPHIC, MOON_SOUTH_POLAR, always_xy=True)
        for lon, lat in ((0.0, -89.0), (131.6, -89.3), (200.0, -85.0)):
            ax, ay = theirs.transform(lon, lat)
            bx, by = ours.transform(lon, lat)
            if abs(ax - bx) > tol_m or abs(ay - by) > tol_m:
                return False
        return True
    except Exception:
        return False


def read_window(path: Path, x0: float, y0: float, x1: float, y1: float) -> Window2D | None:
    """The cells touching the box, with the raster's scale and offset applied.

    ``None`` when the box misses the raster entirely.
    """
    with rasterio.open(path) as r:
        t = r.transform
        if t.b != 0 or t.d != 0 or t.e >= 0:
            raise ValueError(f"{path.name}: rotated or south-up raster is not supported")
        res = float(t.a)
        c0 = int(np.floor((x0 - t.c) / res))
        c1 = int(np.ceil((x1 - t.c) / res))
        r0 = int(np.floor((t.f - y1) / res))
        r1 = int(np.ceil((t.f - y0) / res))
        c0, c1 = max(c0, 0), min(c1, r.width)
        r0, r1 = max(r0, 0), min(r1, r.height)
        if c1 <= c0 or r1 <= r0:
            return None
        raw = r.read(1, window=Window(c0, r0, c1 - c0, r1 - r0))
        scale = float(r.scales[0]) if r.scales else 1.0
        offset = float(r.offsets[0]) if r.offsets else 0.0
        nodata = r.nodata
        vals = raw.astype(np.float64) * scale + offset
        bad = ~np.isfinite(vals)
        if nodata is not None and not np.isnan(nodata):
            bad |= raw == nodata
        vals[bad] = np.nan
        return Window2D(vals, t.c + c0 * res, t.f - r0 * res, res, r.crs.to_wkt())


def sample_points(
    path: Path, x: FloatArray, y: FloatArray, method: str = "nearest", pad_cells: int = 2
) -> tuple[FloatArray, float, str]:
    """Raster values at polar stereographic points: ``(values, res_m, crs_wkt)``.

    ``method`` is ``"bilinear"`` (elevation, averages) or ``"nearest"`` (slope,
    categorical maps). A point outside the raster, on a no-data cell, or (bilinear)
    with a no-data neighbour is NaN.
    """
    if method not in ("bilinear", "nearest"):
        raise ValueError("method is bilinear or nearest")
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    with rasterio.open(path) as r:
        pad = pad_cells * float(r.transform.a)
    w = read_window(
        path, float(x.min()) - pad, float(y.min()) - pad, float(x.max()) + pad, float(y.max()) + pad
    )
    if w is None:
        return np.full(x.shape, np.nan), 0.0, ""
    h, wd = w.values.shape
    fc = (x - w.origin_x_m) / w.res_m
    fr = (w.origin_y_m - y) / w.res_m
    if method == "nearest":
        c = np.floor(fc).astype(np.int64)
        rr = np.floor(fr).astype(np.int64)
        ok = (c >= 0) & (c < wd) & (rr >= 0) & (rr < h)
        out = np.full(x.shape, np.nan)
        out[ok] = w.values[rr[ok], c[ok]]
        return out, w.res_m, w.crs_wkt
    gc = fc - 0.5  # cell centres sit half a cell in
    gr = fr - 0.5
    c0 = np.floor(gc).astype(np.int64)
    r0 = np.floor(gr).astype(np.int64)
    ok = (c0 >= 0) & (c0 + 1 < wd) & (r0 >= 0) & (r0 + 1 < h)
    c0 = np.clip(c0, 0, max(wd - 2, 0))
    r0 = np.clip(r0, 0, max(h - 2, 0))
    ac = np.clip(gc - c0, 0.0, 1.0)
    ar = np.clip(gr - r0, 0.0, 1.0)
    v = w.values
    top = v[r0, c0] * (1 - ac) + v[r0, c0 + 1] * ac
    bot = v[r0 + 1, c0] * (1 - ac) + v[r0 + 1, c0 + 1] * ac
    out = np.where(ok, top * (1 - ar) + bot * ar, np.nan)
    return out, w.res_m, w.crs_wkt


def lola_tiles(root: Path) -> list[LolaTile]:
    """Every 5 m site that has all three of its rasters on disk."""
    base = root / LOLA_DIR
    out: list[LolaTile] = []
    if not base.is_dir():
        return out
    for d in sorted(base.iterdir()):
        if not d.is_dir() or not re.fullmatch(r"Site\d+(v\d+)?", d.name):
            continue
        paths = {k: d / f"{d.name}_final_adj_5mpp_{k}.tif" for k in ("surf", "slp", "toterr")}
        if not all(p.is_file() for p in paths.values()):
            continue
        try:
            with rasterio.open(paths["surf"]) as r:
                b = r.bounds
                out.append(
                    LolaTile(
                        d.name,
                        paths["surf"],
                        paths["toterr"],
                        paths["slp"],
                        b.left,
                        b.bottom,
                        b.right,
                        b.top,
                        float(r.transform.a),
                        r.crs.to_wkt(),
                    )
                )
        except rasterio.RasterioIOError:
            continue  # a file that is still downloading
    return out


def covering_tile(
    root: Path, x0: float, y0: float, x1: float, y1: float, margin_m: float = 0.0
) -> LolaTile | None:
    """The 5 m tile that contains the whole box (plus margin), if any."""
    for t in lola_tiles(root):
        if t.contains(x0, y0, x1, y1, margin_m):
            return t
    return None


def illumination_files(
    root: Path, x0: float, y0: float, x1: float, y1: float
) -> tuple[str, dict[str, Path]] | None:
    """The finest illumination product that covers the box, with its three files."""
    base = root / ILLUM_DIR
    for stem in ILLUM_STEMS:
        files = {
            "sun": base / f"AVGVISIB_{stem}_201608.TIF",
            "earth": base / f"AVGVISIB_{stem}_201608_EARTH.TIF",
            "shadow": base / f"LPSR_{stem}_201608.TIF",
        }
        if not files["sun"].is_file():
            continue
        try:
            with rasterio.open(files["sun"]) as r:
                b = r.bounds
        except rasterio.RasterioIOError:
            continue
        if x0 >= b.left and x1 <= b.right and y0 >= b.bottom and y1 <= b.top:
            return stem, {k: p for k, p in files.items() if p.is_file()}
    return None
