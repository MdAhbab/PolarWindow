"""Reading a point from the first bytes of a complex-packed GRIB2 message, against ecCodes."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from app.feeds.parsers import grib, grib_prefix

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "feeds"
# A 40 x 30 cut (27.75-35 N, 275-284.75 E) of the GEFSv12 reforecast's 10 m u wind,
# control run, 2019-01-02 00 UTC + 24 h, packed again by ecCodes with template 5.3.
SUBSET = FIX / "gefs_reforecast_u10_cplx_subset.grb2"
CAPE = (28.4677, -80.5668)


def test_whole_field_matches_eccodes_at_grid_points() -> None:
    b = SUBSET.read_bytes()
    lay = grib_prefix.layout(b)
    assert (lay.grid.ni, lay.grid.nj, lay.order) == (40, 30, 2)
    vals = grib_prefix.decode_prefix(b, lay.n)
    for j, i in ((0, 0), (7, 13), (29, 39), (12, 31)):
        lat, lon = 35.0 - 0.25 * j, 275.0 + 0.25 * i
        pv = grib.point_values(b, [("p", lat, lon)])[0]
        assert vals[j * 40 + i] == pytest.approx(pv.value, abs=1e-6)


def test_prefix_is_enough_and_bilinear_matches_eccodes() -> None:
    b = SUBSET.read_bytes()
    lay = grib_prefix.layout(b)
    k = grib_prefix.prefix_points([CAPE], lay)
    need = grib_prefix.bytes_needed(lay, b[: lay.meta_end], k)
    assert need < lay.total
    got = grib_prefix.points(b[:need], [CAPE])[0]
    want = grib.point_values(b, [("cape", *CAPE)])[0].value
    assert got == pytest.approx(want, abs=1e-6)
    full = grib_prefix.decode_prefix(b, lay.n)
    assert np.allclose(grib_prefix.decode_prefix(b[:need], k), full[:k])


def test_a_short_prefix_or_another_layout_is_refused() -> None:
    b = SUBSET.read_bytes()
    lay = grib_prefix.layout(b)
    with pytest.raises(grib_prefix.PrefixError):
        grib_prefix.decode_prefix(b[: lay.meta_end + 10], lay.n)
    other = (FIX / "hrrr_f06_subset.grb2").read_bytes()
    with pytest.raises(grib_prefix.PrefixError):
        grib_prefix.layout(other)
