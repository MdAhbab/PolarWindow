"""Compare rover visibility with GDAL's public viewshed C API.

Run ``python -m app.validation.validate_viewshed_gdal``. Uses the GDAL library
already shipped with Rasterio; no osgeo Python package or executable is needed.
Both algorithms see the same local, metre-spaced lunar raster and target pixel
centres. Original native-DEM sampling is also reported to expose reprojection
effects. Neither nodata nor uncertain cells count as agreement.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.transform import from_origin
from scipy.ndimage import map_coordinates

from app.config import get_settings
from app.core import viewshed as vs
from app.core.horizon import R_MOON_M
from app.data.lola import DemTile, make_samplers
from app.data.rover_terrain import terrain_path
from app.validation.validate_viewshed import LANDER, ROVER, SITES, _run


class GdalViewshed:
    """Small validation-only binding to GDALViewshedGenerate, Edge/Normal mode."""

    def __init__(self) -> None:
        bundled = Path(rasterio.__file__).parent.parent / "rasterio.libs"
        candidates = [
            p
            for p in bundled.glob("*gdal*")
            if p.suffix in (".dll", ".so") or ".so." in p.name or p.suffix == ".dylib"
        ]
        library = str(candidates[0]) if candidates else ctypes.util.find_library("gdal")
        if not library:
            raise RuntimeError("GDAL shared library not found; reference check unavailable")
        self.lib = ctypes.CDLL(library)
        ptr, text, integer, real = (ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_double)
        self.lib.GDALAllRegister()
        self.lib.GDALOpen.argtypes = [text, integer]
        self.lib.GDALOpen.restype = ptr
        self.lib.GDALGetRasterBand.argtypes = [ptr, integer]
        self.lib.GDALGetRasterBand.restype = ptr
        self.lib.GDALClose.argtypes = [ptr]
        self.lib.GDALClose.restype = None
        signature: list[Any] = (
            [ptr, text, text, ptr] + [real] * 9 + [integer, real, ptr, ptr, integer, ptr]
        )
        self.lib.GDALViewshedGenerate.argtypes = signature
        self.lib.GDALViewshedGenerate.restype = ptr
        self.lib.GDALVersionInfo.argtypes = [text]
        self.lib.GDALVersionInfo.restype = text
        self.version = self.lib.GDALVersionInfo(b"RELEASE_NAME").decode()

    def generate(self, source: Path, destination: Path, radius: float) -> None:
        ds = self.lib.GDALOpen(str(source).encode("utf-8"), 0)
        if not ds:
            raise RuntimeError(f"GDAL could not open {source}")
        try:
            band = self.lib.GDALGetRasterBand(ds, 1)
            # GDAL's default Edge algorithm (2), normal visibility output (1).
            # No atmospheric refraction: curvature coefficient 1, lunar CRS.
            out = self.lib.GDALViewshedGenerate(
                band,
                b"GTiff",
                str(destination).encode("utf-8"),
                None,
                0.0,
                0.0,
                LANDER,
                ROVER,
                255.0,
                0.0,
                127.0,
                127.0,
                1.0,
                2,
                radius,
                None,
                None,
                1,
                None,
            )
            if not out:
                raise RuntimeError("GDALViewshedGenerate failed")
            self.lib.GDALClose(out)
        finally:
            self.lib.GDALClose(ds)


def write_dem(path: Path, heights: np.ndarray, post: float, lat: float, lon: float):
    """Centre the observer on a pixel; metres and lunar radius are explicit."""
    half = (heights.shape[0] - 1) // 2
    transform = from_origin(-(half + 0.5) * post, (half + 0.5) * post, post, post)
    crs = f"+proj=aeqd +lat_0={lat} +lon_0={lon} +R={R_MOON_M} +units=m +type=crs"
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=heights.shape[0],
        width=heights.shape[1],
        count=1,
        dtype="float64",
        crs=crs,
        transform=transform,
    ) as ds:
        ds.write(heights, 1)
    return transform


def compare_case(reference: GdalViewshed, directory: Path, site, radius: float) -> dict:
    name, sid, lat, lon = site
    source = terrain_path(sid, lat, lon, radius)
    dem = DemTile.load(source)
    original, sigma = make_samplers(lat, lon, dem, None)
    post = dem.scale_m
    half = int(np.ceil(radius / post))
    axis = np.arange(-half, half + 1) * post
    x, y = np.meshgrid(axis, axis[::-1])
    heights = original(x.ravel(), y.ravel()).reshape(x.shape)
    row = {
        "site": sid,
        "name": name,
        "radius_m": radius,
        "post_m": post,
        "source": source.relative_to(get_settings().data_dir).as_posix(),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
    }
    # GDAL does not specially handle input nodata. Never fill a hole to pass.
    missing = int((~np.isfinite(heights)).sum())
    if missing:
        return {**row, "status": "unresolved_nodata", "missing_raster_cells": missing}
    src = directory / f"{sid}-{radius:g}-dem.tif"
    dst = directory / f"{sid}-{radius:g}-gdal.tif"
    transform = write_dem(src, heights, post, lat, lon)
    reference.generate(src, dst, radius + 2 * post)

    def common_grid(xs, ys):
        col, rr = (~transform) * (xs, ys)
        return map_coordinates(
            heights, [rr - 0.5, col - 0.5], order=1, mode="constant", cval=np.nan
        )

    counts = {
        key: {"compared": 0, "agree": 0, "false_clear": 0, "false_blocked": 0, "uncertain": 0}
        for key in ("common_grid", "native_sampler")
    }
    mismatches: dict[str, list[dict]] = {key: [] for key in counts}
    eligible_targets = 0
    outside_radius = 0
    with rasterio.open(dst) as ds:
        targets = {
            ds.index(np.sin(np.radians(b)) * r, np.cos(np.radians(b)) * r)
            for b in np.arange(0, 360, 5)
            for r in radius * np.arange(1, 21) / 20
        }
        states = ds.read(1)
        for rr, col in sorted(targets):
            tx, ty = ds.xy(rr, col)
            distance = float(np.hypot(tx, ty))
            if distance > radius:
                outside_radius += 1
                continue
            if distance == 0 or states[rr, col] == 127:
                continue
            eligible_targets += 1
            bearing = np.array([np.degrees(np.arctan2(tx, ty))])
            ranges = np.array([distance])
            for key, sample in (("common_grid", common_grid), ("native_sampler", original)):
                sight = _run(sample, sigma, bearing, ranges, post).sight[0, 0]
                if sight == vs.UNCERTAIN:
                    counts[key]["uncertain"] += 1
                    continue
                engine_clear = sight == vs.CLEAR
                ref_clear = states[rr, col] == 255
                count = counts[key]
                count["compared"] += 1
                count["agree"] += int(engine_clear == ref_clear)
                count["false_clear"] += int(engine_clear and not ref_clear)
                count["false_blocked"] += int(not engine_clear and ref_clear)
                if engine_clear != ref_clear:
                    mismatches[key].append(
                        {
                            "east_m": tx,
                            "north_m": ty,
                            "distance_m": distance,
                            "engine_clear": bool(engine_clear),
                            "gdal_clear": bool(ref_clear),
                        }
                    )
    summaries = {
        key: {
            **count,
            "agreement": count["agree"] / count["compared"] if count["compared"] else None,
        }
        for key, count in counts.items()
    }
    primary = summaries["common_grid"]["agreement"]
    status = "unresolved_uncertainty" if primary is None else "pass" if primary >= 0.99 else "fail"
    return {
        **row,
        "unique_targets": len(targets),
        "eligible_targets": eligible_targets,
        "outside_radius": outside_radius,
        "status": status,
        "mismatches": mismatches,
        **summaries,
    }


def main() -> int:
    directory = get_settings().data_dir / "validation" / "viewshed-gdal"
    directory.mkdir(parents=True, exist_ok=True)
    reference = GdalViewshed()
    rows = [
        compare_case(reference, directory, site, radius)
        for site in SITES
        for radius in (500.0, 2000.0)
    ]
    report = {
        "gdal_version": reference.version,
        "mode": "Edge/Normal",
        "curvature_coefficient": 1,
        "moon_radius_m": R_MOON_M,
        "lander_antenna_m": LANDER,
        "rover_antenna_m": ROVER,
        "minimum_agreement": 0.99,
        "method": "Native DEM sampled to local lunar ENU raster at native post; matched pixel "
        "centres; common-grid primary and native-sampler diagnostic; uncertainty "
        "uses source height error; no nodata filling; deduplicated polar targets.",
        "source": "https://gdal.org/en/stable/api/gdal_alg.html#_CPPv420GDALViewshedGenerate",
        "status": "pass" if all(r["status"] == "pass" for r in rows) else "not_passed",
        "cases": rows,
    }
    path = directory / "report.json"
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"Report: {path}")
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
