"""CF decoding and strict place/time/missing-data limits on imported waves."""
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import numpy as np
import pytest

from app.data import copernicus_wave as cw
from app.feeds.parsers.copernicus import import_subset

netcdf = pytest.importorskip("netCDF4", reason="optional marine extra not installed")


def make_subset(path, units="m"):
    with netcdf.Dataset(path, "w") as ds:
        for name, size in [("time", 2), ("latitude", 2), ("longitude", 2)]:
            ds.createDimension(name, size)
            var = ds.createVariable(name, "f8", (name,))
            if name == "time":
                var.units = "hours since 2026-10-01 00:00:00"
                var[:] = [0, 3]
            elif name == "latitude":
                var.units = "degrees_north"
                var[:] = [28, 28.083333]
            else:
                var.units = "degrees_east"
                var[:] = [280, 280.083333]
        wave = ds.createVariable("VHM0", "i2", ("time", "latitude", "longitude"),
                                 fill_value=-32767)
        wave.units = units
        wave.scale_factor = .01
        wave[:] = np.ma.array([[[1.25, 2.], [2.5, 3.]], [[1.5, 2.], [2.5, 3.]]],
                             mask=[[[False, True], [False, False]],
                                   [[False, True], [False, False]]])


def test_decode_packed_metres_preserves_mask_and_normalizes_coordinates(tmp_path, monkeypatch):
    path = tmp_path / "waves.nc"
    make_subset(path)
    data = import_subset(path)
    assert data["VHM0"][0][0] == [1.25, None]
    assert data["times"][1] == "2026-10-01T03:00:00+00:00"
    data["imported_at"] = datetime.now(UTC).isoformat()
    directory = tmp_path / "copernicus"
    directory.mkdir()
    (directory / "waves.json").write_text(json.dumps(data))
    monkeypatch.setattr(cw, "get_settings", lambda: SimpleNamespace(data_dir=tmp_path))
    when = datetime(2026, 10, 1, tzinfo=UTC)
    got = cw.wave_at((28, -80), when)
    assert got is not None and got["wave_height_m"] == 1.25
    assert cw.wave_at((28, -79.916667), when) is None  # land/missing cell, never zero
    assert cw.wave_at((27.99, -80), when) is None  # no clamping outside coverage
    assert cw.wave_at((28, -80), when + timedelta(hours=6)) is None
    data["imported_at"] = (datetime.now(UTC) - timedelta(days=2)).isoformat()
    (directory / "waves.json").write_text(json.dumps(data))
    assert cw.wave_at((28, -80), when) is None  # old import does not become a fresh forecast


def test_wrong_units_are_rejected(tmp_path):
    path = tmp_path / "waves.nc"
    make_subset(path, "feet")
    with pytest.raises(ValueError, match="metres"):
        import_subset(path)


def test_wrong_product_and_wind_wave_component_are_rejected(tmp_path):
    path = tmp_path / "waves.nc"
    make_subset(path)
    with netcdf.Dataset(path, "a") as ds:
        ds.setncattr("subset:productId", "ANOTHER_PRODUCT")
    with pytest.raises(ValueError, match="Global Ocean Waves"):
        import_subset(path)
    with netcdf.Dataset(path, "a") as ds:
        ds.delncattr("subset:productId")
        ds.renameVariable("VHM0", "VHM0_WW")
    with pytest.raises(ValueError, match="missing VHM0"):
        import_subset(path)
