"""The dispersion service on synthetic terrain: a 10 degree ramp under a landing ellipse."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from app.api.v1.schemas.dispersion import DispersionResponse
from app.core.projections import local_frame
from app.services import dispersion_service as ds
from app.tests.unit.test_pgda import write

LAT, LON = -89.5, 40.0
ELLIPSE = {"semi_major_m": 300.0, "semi_minor_m": 100.0, "azimuth_deg": 30.0}
LANDER = {"footprint_diameter_m": 4.6, "cg_height_m": 1.5, "slope_limit_deg": 8.0}
T10 = math.tan(math.radians(10.0))


def ramp(n: int, spacing: float) -> np.ndarray:
    x = np.arange(n) * spacing
    xx, yy = np.meshgrid(x, x)
    a = math.radians(70.0)
    return (T10 * (xx * math.cos(a) + yy * math.sin(a))).astype(np.float32)


def centre() -> tuple[float, float]:
    f = local_frame(LON, LAT)
    return f.x0_m, f.y0_m


def build_pgda(root: Path) -> None:
    cx, cy = centre()
    n = 400  # 2 km at 5 m
    for k, arr in (
        ("surf", ramp(n, 5.0)),
        ("slp", np.full((n, n), 10.0, dtype=np.float32)),
        ("toterr", np.full((n, n), 0.3, dtype=np.float32)),
    ):
        p = root / "external" / "pgda_lola_5m" / "Site99" / f"Site99_final_adj_5mpp_{k}.tif"
        write(p, arr, cx - 1000.0, cy + 1000.0, 5.0, nodata=float("nan"))


def build_illumination(root: Path) -> None:
    cx, cy = centre()
    n = 100  # 6 km at 60 m
    d = root / "external" / "pgda_illumination"
    sun = np.full((n, n), 12500, dtype=np.int16)
    earth = np.full((n, n), 20000, dtype=np.int16)
    shadow = np.full((n, n), 20000, dtype=np.int16)
    left, top = cx - 3000.0, cy + 3000.0
    write(d / "AVGVISIB_85S_060M_201608.TIF", sun, left, top, 60.0, nodata=-32768, scale=4e-5)
    write(
        d / "AVGVISIB_85S_060M_201608_EARTH.TIF", earth, left, top, 60.0, nodata=-32768, scale=4e-5
    )
    write(
        d / "LPSR_85S_060M_201608.TIF",
        shadow,
        left,
        top,
        60.0,
        nodata=-32768,
        scale=2.5e-5,
        offset=0.5,
    )


def build_app_dem(path: Path, half_m: float = 3000.0) -> Path:
    cx, cy = centre()
    n = int(2 * half_m / 20.0) + 1
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(
        path,
        heights=ramp(n, 20.0),
        origin_x_m=np.array(cx - half_m),
        origin_y_m=np.array(cy + half_m),
        scale_m=np.array(20.0),
        product=np.array("TEST_20M"),
        vertical_error_m=np.array(2.0),
    )
    return path


def go(tmp: Path, **kw: Any) -> dict[str, Any]:
    return ds.run(
        "x",
        LAT,
        LON,
        ELLIPSE,
        kw.pop("lander", LANDER),
        500,
        data_dir=tmp,
        app_dems=kw.pop("app_dems", [tmp / "dem" / "fine" / "x.npz"]),
    )


def walk(o: Any) -> Any:
    if isinstance(o, dict):
        for k, v in o.items():
            yield k
            yield from walk(v)
    elif isinstance(o, list):
        for v in o:
            yield from walk(v)


def test_pgda_5m_ramp(tmp_path: Path) -> None:
    build_pgda(tmp_path)
    build_illumination(tmp_path)
    r = go(tmp_path)
    s = r["slope_source"]
    assert s["pgda_5m"] and not s["fell_back"] and s["tile"] == "Site99"
    assert s["spacing_m"] == 5.0 and s["baseline_m"] == 15.0 and r["slope"]["baseline_m"] == 15.0
    for k in ("p10", "p50", "p90"):
        assert r["slope"][k]["value"] == pytest.approx(10.0, abs=0.05)
        assert r["slope"][k]["pm"] > 0
    assert s["cross_check"]["p50_deg"] == pytest.approx(10.0)
    assert r["tip_over"]["angle"]["value"] == pytest.approx(56.8887, abs=1e-3)
    above = r["shares"]["above_slope_limit"]["share"]  # 10 deg slope, 8 deg limit
    assert above["k"] == above["n"] == 500
    tip = r["shares"]["above_tip_over"]["share"]
    assert tip["k"] == 0 and tip["lo"] == 0.0 and tip["hi"] < 0.01


def test_share_interval_contains_the_share(tmp_path: Path) -> None:
    build_pgda(tmp_path)
    for limit in (5.0, 9.99, 10.5, 30.0):
        r = go(tmp_path, lander={**LANDER, "slope_limit_deg": limit})
        sh = r["shares"]["above_slope_limit"]["share"]
        assert sh["lo"] <= sh["k"] / sh["n"] <= sh["hi"]


def test_illumination_is_labelled_as_the_long_term_average(tmp_path: Path) -> None:
    build_pgda(tmp_path)
    build_illumination(tmp_path)
    il = go(tmp_path)["illumination"]
    assert il["available"] and "not hours in the chosen dates" in il["basis"]
    assert "2009" in il["epoch"] and il["source"]["url"].startswith("https://pgda.gsfc.nasa.gov")
    assert il["sun"]["p50"]["value"] == pytest.approx(0.5, abs=1e-6)
    assert il["earth"]["p50"]["value"] == pytest.approx(0.8, abs=1e-6)
    assert il["sun"]["p50"]["provenance"] == "published"
    ps = il["permanent_shadow"]["share"]
    assert ps["k"] == ps["n"]


def test_outside_every_pgda_tile_falls_back_and_says_so(tmp_path: Path) -> None:
    dem = build_app_dem(tmp_path / "dem" / "fine" / "x.npz")
    r = go(tmp_path, app_dems=[dem])
    s = r["slope_source"]
    assert s["fell_back"] and not s["pgda_5m"] and s["fallback_reason"]
    assert s["spacing_m"] == 20.0 and s["baseline_m"] == 60.0
    assert s["vertical_error_m"] == 2.0
    assert r["slope"]["p50"]["value"] == pytest.approx(10.0, abs=0.05)
    assert r["illumination"]["available"] is False


def test_a_tile_that_does_not_cover_the_whole_ellipse_is_not_used(tmp_path: Path) -> None:
    build_pgda(tmp_path)
    r = ds.run(
        "x",
        LAT,
        LON,
        {**ELLIPSE, "semi_major_m": 1500.0},
        LANDER,
        200,
        data_dir=tmp_path,
        app_dems=[build_app_dem(tmp_path / "dem" / "fine" / "x.npz")],
    )
    assert r["slope_source"]["fell_back"]


def test_no_terrain_at_all_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(ds.NoTerrain):
        go(tmp_path)


def test_heatmap_is_bounded_and_the_response_validates(tmp_path: Path) -> None:
    build_pgda(tmp_path)
    r = go(tmp_path)
    h = r["heatmap"]
    assert h["nx"] <= 64 and h["ny"] <= 64
    assert len(h["slope_deg"]) == h["ny"] and len(h["slope_deg"][0]) == h["nx"]
    assert len(h["points"]["east_m"]) == 500 and len(h["outline"]["east_m"]) > 8
    assert r["not_modelled"] and r["sources"]
    DispersionResponse.model_validate(r)


def test_no_composite_names_in_the_response(tmp_path: Path) -> None:
    build_pgda(tmp_path)
    build_illumination(tmp_path)
    r = go(tmp_path)
    banned = ("score", "index", "verdict", "rating", "go_no_go", "suitability")
    bad = [k for k in walk(r) if isinstance(k, str) and any(b in k.lower() for b in banned)]
    assert bad == []
