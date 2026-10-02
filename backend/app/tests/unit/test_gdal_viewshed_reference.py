"""Physical controls for the validation-only GDAL C API binding."""

import numpy as np
import pytest
import rasterio

from app.validation.validate_viewshed_gdal import GdalViewshed, write_dem


@pytest.fixture
def gdal():
    try:
        return GdalViewshed()
    except (OSError, RuntimeError) as error:
        pytest.skip(str(error))


def test_flat_ground_and_wall(gdal, tmp_path):
    heights = np.zeros((41, 41))
    src, dst = tmp_path / "flat.tif", tmp_path / "visibility.tif"
    write_dem(src, heights, 10.0, 0.0, 0.0)
    gdal.generate(src, dst, 150.0)
    with rasterio.open(dst) as ds:
        assert next(ds.sample([(100.0, 0.0)]))[0] == 255
    heights[:, 25] = 20.0  # wall 50 m east of the observer
    write_dem(src, heights, 10.0, 0.0, 0.0)
    gdal.generate(src, dst, 150.0)
    with rasterio.open(dst) as ds:
        assert next(ds.sample([(100.0, 0.0)]))[0] == 0
        assert next(ds.sample([(-100.0, 0.0)]))[0] == 255


def test_lunar_curvature_horizon(gdal, tmp_path):
    # Flat lunar ground with 2 m / 0.5 m antennas: horizon about 3,954 m.
    src, dst = tmp_path / "moon.tif", tmp_path / "visibility.tif"
    write_dem(src, np.zeros((501, 501)), 20.0, 0.0, 0.0)
    gdal.generate(src, dst, 5000.0)
    with rasterio.open(dst) as ds:
        assert next(ds.sample([(3000.0, 0.0)]))[0] == 255
        assert next(ds.sample([(4500.0, 0.0)]))[0] == 0
