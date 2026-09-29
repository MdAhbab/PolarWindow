"""One point from a few bytes of a simple-packed HRRR message, against ecCodes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest

from app.feeds.parsers import grib
from app.feeds.parsers import grib_ranges as gr

# ecCodes, through the one module the import contract lets name it.
eccodes: Any = grib.eccodes  # type: ignore[attr-defined]

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "feeds"
# HRRR's own grid and packing cut by NOMADS to 39 x 42 cells around the Cape: gust, the
# 80 m and the 10 m winds (6 and 7 bits a value, so every place a value can start in a byte).
CUT = FIX / "hrrr_f06_subset.grb2"
# The first 512 bytes of a whole 10 m U message of the archive on AWS (noaa-hrrr-bdp-pds,
# 2025-06-01 00 UTC run, hour 6): the layout of a real file, 1799 x 1059 cells, 10 bits a value.
HEAD = FIX / "hrrr_f06_u10_head.bin"
CAPE = (28.4677, -80.5668)
VANDENBERG = (34.7297, -120.5768)


def _field(handle: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    return (
        eccodes.codes_get_values(handle),
        eccodes.codes_get_array(handle, "latitudes"),
        eccodes.codes_get_array(handle, "longitudes"),
    )


def _nearest_index(handle: int, lat: float, lon: float) -> int:
    near = eccodes.codes_grib_find_nearest(handle, lat, lon % 360.0, npoints=4)
    return int(min(near, key=lambda n: n["distance"])["index"])


def test_every_value_of_the_cut_is_read_from_its_own_bytes() -> None:
    for msg in grib.split_messages(CUT.read_bytes()):
        lay = gr.layout(msg[: gr.HEAD])
        h = eccodes.codes_new_from_message(msg)
        want = eccodes.codes_get_values(h)
        eccodes.codes_release(h)
        assert (lay.grid.nx, lay.grid.ny, lay.n) == (39, 42, 1638)
        for k in range(lay.n):
            a, b = lay.span(k)
            assert b - a < 2  # a few bytes, never the message
            assert lay.value(msg[a : b + 1], k) == pytest.approx(want[k], abs=1e-9)


def test_nearest_point_of_the_cut_is_the_one_eccodes_finds() -> None:
    msg = grib.split_messages(CUT.read_bytes())[3]  # 10 m U
    g = gr.layout(msg[: gr.HEAD]).grid
    h = eccodes.codes_new_from_message(msg)
    _, lats, lons = _field(h)
    for k in range(g.nx * g.ny):  # each grid point's own place is its own index
        assert g.nearest(float(lats[k]), float(lons[k])) == k
    rng = np.random.default_rng(3)
    for lat, lon in zip(
        rng.uniform(lats.min() + 0.05, lats.max() - 0.05, 300),
        rng.uniform(lons.min() + 0.05, lons.max() - 0.05, 300),
        strict=True,
    ):
        try:
            k = g.nearest(float(lat), float(lon))
        except gr.RangeError:
            continue  # a corner of the box the grid does not cover
        assert k == _nearest_index(h, float(lat), float(lon))
    eccodes.codes_release(h)


def test_the_layout_of_a_real_message_head() -> None:
    lay = gr.layout(HEAD.read_bytes())
    g = lay.grid
    assert (g.nx, g.ny, lay.n) == (1799, 1059, 1799 * 1059)
    assert (g.la1, g.lo1, g.lov, g.latin1, g.latin2) == (21.138123, 237.280472, 262.5, 38.5, 38.5)
    assert (g.dx, g.dy, g.radius) == (3000.0, 3000.0, 6371229.0)
    assert (lay.nbits, lay.e, lay.d, lay.data_at, lay.total) == (10, -4, 0, 184, 2381615)
    # The Cape and Vandenberg are 0.7 and 0.3 km from the cells the live product reads.
    assert lay.grid.nearest(*CAPE) == 373849
    assert lay.grid.nearest(*VANDENBERG) == 858325
    # 10 bits from bit 10 * k: value 3 starts in byte 3, the last one ends at the section's end.
    assert lay.span(3) == (184 + 3, 184 + 4)
    assert lay.span(lay.n - 1)[1] == lay.total - 4 - 1  # then the 4 bytes of "7777"


def test_the_full_size_grid_matches_eccodes() -> None:
    """A message with HRRR's whole grid, made by ecCodes, read at scattered values and cells."""
    h0 = eccodes.codes_new_from_message(grib.split_messages(CUT.read_bytes())[3])
    h = eccodes.codes_clone(h0)
    eccodes.codes_release(h0)
    for key, val in (
        ("Ni", 1799),
        ("Nj", 1059),
        ("latitudeOfFirstGridPointInDegrees", 21.138123),
        ("longitudeOfFirstGridPointInDegrees", 237.280472),
        ("bitsPerValue", 10),
    ):
        eccodes.codes_set(h, key, val)
    eccodes.codes_set_values(h, np.random.default_rng(0).normal(2.0, 4.0, 1799 * 1059))
    msg = eccodes.codes_get_message(h)
    lay = gr.layout(msg[: gr.HEAD])
    assert lay.grid == gr.layout(HEAD.read_bytes()).grid and lay.total == len(msg)
    want, lats, lons = _field(h)
    rng = np.random.default_rng(1)
    for k in [0, 1, lay.n - 1, *rng.integers(0, lay.n, 20_000).tolist()]:
        a, b = lay.span(int(k))
        assert lay.value(msg[a : b + 1], int(k)) == pytest.approx(want[k], abs=1e-9)
        assert lay.grid.nearest(float(lats[k]), float(lons[k])) == k
    for place in (CAPE, VANDENBERG):
        assert lay.grid.nearest(*place) == _nearest_index(h, *place)
    eccodes.codes_release(h)


def test_what_is_not_read_is_refused() -> None:
    head = HEAD.read_bytes()
    lay = gr.layout(head)
    with pytest.raises(gr.RangeError):
        gr.layout(b"not a message" * 40)
    with pytest.raises(gr.RangeError):
        gr.layout(head[:100])  # the head ends before section 7
    with pytest.raises(gr.RangeError):
        gr.layout((FIX / "gefs_gep01_f024_subset.grb2").read_bytes())  # a latitude-longitude grid
    with pytest.raises(gr.RangeError):
        lay.grid.nearest(50.0, -160.0)  # off the grid
    with pytest.raises(gr.RangeError):
        lay.span(lay.n)
    with pytest.raises(gr.RangeError):
        lay.value(b"\x00", 0)  # a value is read from the bytes span() names, no others
