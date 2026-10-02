"""Native terrain selection, safe coverage fallback and invalidation of cached sight."""

from pathlib import Path

import numpy as np
import pytest

from app.config import Settings
from app.core.projections import local_frame
from app.data import rover_terrain as rt
from app.data.lola import LDEM_875S_5M


def _tile(path: Path, step: float, half: float) -> None:
    frame = local_frame(120.0, -89.0)
    n = int(2 * half / step) + 1
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        path,
        heights=np.zeros((n, n), dtype=np.float32),
        origin_x_m=frame.x0_m - half,
        origin_y_m=frame.y0_m + half,
        scale_m=step,
        product="test",
        vertical_error_m=2.0,
    )


def test_native_five_metre_product_matches_its_pds_label() -> None:
    p = LDEM_875S_5M
    assert p.size_px == 30336 and p.record_bytes == 60672
    assert p.projection_offset_px == 15167.5 and p.scale_m == 5.0
    assert p.scaling_factor == 0.5 and p.vertical_error_m == 2.0


def test_finer_terrain_is_used_only_when_the_full_neighbourhood_fits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(data_dir=tmp_path)
    monkeypatch.setattr(rt, "get_settings", lambda: settings)
    five, twenty = settings.rover_dem_path("site"), settings.fine_dem_path("site")
    _tile(twenty, 20, 1000)
    assert rt.terrain_path("site", -89, 120, 500) == twenty
    _tile(five, 5, 600)
    assert rt.terrain_path("site", -89, 120, 500) == five
    assert rt.terrain_path("site", -89, 120, 700) == twenty
    assert rt.terrain_path("site", -89, 120, 1200) == settings.regional_dem_path
    assert rt.terrain_path("site", -89, -60, 500) == settings.regional_dem_path
    stereo = settings.rover_stereo_path("site")
    _tile(stereo, 3, 600)
    assert rt.terrain_path("site", -89, 120, 500) == stereo
    with np.load(stereo) as z:
        fields = dict(z)
    heights = fields["heights"]
    heights[198:203, 198:203] = np.nan  # the antenna's own ground is missing
    np.savez_compressed(stereo, **fields)
    assert rt.terrain_path("site", -89, 120, 500) == five


def test_terrain_content_changes_have_a_new_job_version(tmp_path: Path) -> None:
    path = tmp_path / "terrain.npz"
    assert rt.version(path) == "missing"
    _tile(path, 5, 600)
    before = rt.version(path)
    _tile(path, 5, 700)
    assert rt.version(path) != before and len(before) == 64


@pytest.mark.parametrize("step,error", [(3.0, 4.43), (4.0, 4.12)])
def test_stereo_crop_preserves_native_posts_pixel_centres_and_nodata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    step: float,
    error: float,
) -> None:
    import rasterio
    from affine import Affine

    from app.core.projections import MOON_SOUTH_POLAR
    from app.data.lola import DemTile

    monkeypatch.setattr(rt, "WINDOW_RADIUS_M", 12.0)
    frame = local_frame(120.0, -89.0)
    heights = np.arange(31 * 31, dtype=np.float32).reshape(31, 31)
    heights[12, 12] = -9999
    source, dest = tmp_path / "source.tif", tmp_path / "crop.npz"
    with rasterio.open(
        source,
        "w",
        driver="GTiff",
        height=31,
        width=31,
        count=1,
        dtype="float32",
        nodata=-9999,
        crs=MOON_SOUTH_POLAR,
        transform=Affine(step, 0, frame.x0_m - 15.5 * step, 0, -step, frame.y0_m + 15.5 * step),
    ) as tif:
        tif.write(heights, 1)
    assert rt.crop_stereo(source, dest, -89, 120, post_m=step, error_m=error)
    tile = DemTile.load(dest)
    assert tile.scale_m == step and tile.vertical_error_m == pytest.approx(error)
    assert np.isnan(tile.heights).sum() == 1
    z = tile.sample_grid(np.array([frame.x0_m]), np.array([frame.y0_m]))
    assert z[0] == pytest.approx(heights[15, 15])
    assert not rt.crop_stereo(source, tmp_path / "outside.npz", -89, -60, post_m=step)
    # A small DTM can serve a small radius, without extending its actual footprint.
    monkeypatch.setattr(rt, "WINDOW_RADIUS_M", 1000.0)
    clipped = tmp_path / "clipped.npz"
    assert rt.crop_stereo(source, clipped, -89, 120, post_m=step, clip_to_footprint=True)
    assert DemTile.load(clipped).heights.shape == (31, 31)
    assert rt._covers(clipped, clipped.stat().st_mtime_ns, -89, 120, 12)
    assert not rt._covers(clipped, clipped.stat().st_mtime_ns, -89, 120, 100)
