"""PGDA rasters read at points; tiny GeoTIFFs written to a tmp dir, never the real files."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from app.core.projections import MOON_SOUTH_POLAR
from app.data import pgda


def write(
    path: Path,
    arr: np.ndarray,
    left: float,
    top: float,
    res: float,
    *,
    nodata: float | None = None,
    scale: float = 1.0,
    offset: float = 0.0,
    crs: str = MOON_SOUTH_POLAR,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=arr.shape[0],
        width=arr.shape[1],
        count=1,
        dtype=arr.dtype,
        crs=crs,
        transform=from_origin(left, top, res, res),
        nodata=nodata,
    ) as d:
        d.write(arr, 1)
        d.scales = (scale,)
        d.offsets = (offset,)


def lola(root: Path, name: str, left: float, top: float, n: int = 100) -> None:
    a = np.full((n, n), 1.0, dtype=np.float32)
    for k in ("surf", "slp", "toterr"):
        p = root / "pgda_lola_5m" / name / f"{name}_final_adj_5mpp_{k}.tif"
        write(p, a, left, top, 5.0, nodata=float("nan"))


def test_bilinear_and_nearest_on_pixel_centres(tmp_path: Path) -> None:
    # Cell (r, c) holds 10*r + c; its centre is half a cell in from the corner.
    a = (np.arange(10)[:, None] * 10 + np.arange(10)[None, :]).astype(np.float32)
    p = tmp_path / "e.tif"
    write(p, a, 1000.0, 2000.0, 5.0, nodata=float("nan"))
    x = np.array([1002.5, 1005.0, 1002.5])
    y = np.array([1997.5, 1997.5, 1995.0])
    v, res, wkt = pgda.sample_points(p, x, y, "bilinear")
    assert res == 5.0 and wkt
    assert v[0] == pytest.approx(0.0)
    assert v[1] == pytest.approx(0.5)
    assert v[2] == pytest.approx(5.0)
    nx = np.array([1002.0, 1007.0, 5000.0])
    ny = np.array([1998.0, 1998.0, 1998.0])
    n, _, _ = pgda.sample_points(p, nx, ny, "nearest")
    assert n[0] == 0.0 and n[1] == 1.0 and np.isnan(n[2])


def test_scale_offset_and_nodata_come_from_the_file(tmp_path: Path) -> None:
    a = np.full((10, 10), 25000, dtype=np.int16)
    a[0, 0] = -32768
    p = tmp_path / "s.tif"
    write(p, a, 0.0, 600.0, 60.0, nodata=-32768, scale=4e-5)
    v, _, _ = pgda.sample_points(p, np.array([270.0, 30.0]), np.array([330.0, 570.0]), "nearest")
    assert v[0] == pytest.approx(1.0) and np.isnan(v[1])
    b = np.full((10, 10), 20000, dtype=np.int16)
    q = tmp_path / "l.tif"
    write(q, b, 0.0, 600.0, 60.0, nodata=-32768, scale=2.5e-5, offset=0.5)
    got = pgda.sample_points(q, np.array([270.0]), np.array([330.0]), "nearest")[0][0]
    assert got == pytest.approx(1.0)


def test_which_site_covers_a_point(tmp_path: Path) -> None:
    lola(tmp_path, "Site01", -1000.0, 0.0)  # x -1000..-500, y -500..0
    lola(tmp_path, "Site02", 5000.0, 5000.0)
    (tmp_path / "pgda_lola_5m" / "Site23").mkdir()  # still downloading: no files
    assert [t.name for t in pgda.lola_tiles(tmp_path)] == ["Site01", "Site02"]
    t = pgda.covering_tile(tmp_path, -900.0, -400.0, -600.0, -100.0)
    assert t is not None and t.name == "Site01" and t.res_m == 5.0
    assert pgda.crs_matches_app(t.crs_wkt)
    assert pgda.covering_tile(tmp_path, 0.0, 0.0, 100.0, 100.0) is None
    assert pgda.covering_tile(tmp_path, -900.0, -400.0, -520.0, -100.0, margin_m=30.0) is None


def test_a_different_projection_is_not_taken_for_the_apps(tmp_path: Path) -> None:
    other = "+proj=stere +lat_0=-90 +lon_0=0 +lat_ts=-87.5 +R=1737400 +units=m +no_defs +type=crs"
    p = tmp_path / "o.tif"
    write(p, np.zeros((4, 4), dtype=np.float32), 0, 100, 5.0, crs=other)
    with rasterio.open(p) as r:
        assert not pgda.crs_matches_app(r.crs.to_wkt())


def test_illumination_product_is_the_finest_that_covers(tmp_path: Path) -> None:
    d = tmp_path / "pgda_illumination"
    a = np.zeros((20, 20), dtype=np.int16)
    for stem, half in (("85S_060M", 600.0), ("75S_120M", 5000.0)):
        for name in (f"AVGVISIB_{stem}_201608.TIF", f"AVGVISIB_{stem}_201608_EARTH.TIF"):
            write(d / name, a, -half, half, 2 * half / 20, nodata=-32768, scale=4e-5)
    got = pgda.illumination_files(tmp_path, -300.0, -300.0, 300.0, 300.0)
    assert got is not None and got[0] == "85S_060M" and set(got[1]) == {"sun", "earth"}
    got = pgda.illumination_files(tmp_path, -3000.0, -3000.0, 3000.0, 3000.0)
    assert got is not None and got[0] == "75S_120M"
    assert pgda.illumination_files(tmp_path, -9000.0, 0.0, 9000.0, 10.0) is None
