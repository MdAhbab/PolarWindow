"""The Diviner lookup, on a tiny synthetic table (the real one is 605 MB)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.data import diviner

HEADER = ",".join(
    [f"tri{i}_{a}" for i in (1, 2, 3) for a in "xyz"]
    + ["tri_clon", "tri_clat", "tri_calt", "temp_avg", "temp_max", "ice_depth"]
)


def row(lon: float, lat: float, avg: float, tmax: float, ice: float) -> str:
    return ",".join(["0"] * 9 + [str(lon), str(lat), "0.5", str(avg), str(tmax), str(ice)])


@pytest.fixture
def index(tmp_path: Path) -> Path:
    table = tmp_path / "t.tab"
    table.write_text(
        "\n".join(
            [
                HEADER,
                row(0.0, -89.0, 50.0, 100.0, -999.0),
                row(0.0, -89.001, 60.0, 130.0, 0.5),
                row(0.0, -89.002, 70.0, 160.0, 0.7),
                row(90.0, -80.0, 200.0, 300.0, -999.0),
            ]
        )
        + "\n"
    )
    out = tmp_path / "index.npz"
    diviner.build(index_path=out, table_path=table)
    return out


def test_median_and_spread_of_triangles_in_the_radius(index: Path) -> None:
    g = diviner.at(-89.001, 0.0, 500.0, index_path=index)
    assert g is not None
    assert g.n_triangles == 3
    assert (g.temp_avg_k.lo, g.temp_avg_k.median, g.temp_avg_k.hi) == (50.0, 60.0, 70.0)
    assert (g.temp_max_k.lo, g.temp_max_k.hi) == (100.0, 160.0)
    assert g.ice_depth_m == pytest.approx(0.6)


def test_a_small_radius_picks_one_triangle(index: Path) -> None:
    g = diviner.at(-80.0, 90.0, 100.0, index_path=index)
    assert g is not None
    assert g.n_triangles == 1
    assert g.temp_avg_k.lo == g.temp_avg_k.hi == 200.0
    assert g.ice_depth_m is None


def test_outside_coverage_is_none(index: Path) -> None:
    assert diviner.at(-85.0, 180.0, 1000.0, index_path=index) is None


def test_missing_index_says_so(tmp_path: Path) -> None:
    with pytest.raises(diviner.DivinerMissing):
        diviner.at(-89.0, 0.0, 100.0, index_path=tmp_path / "none.npz")
