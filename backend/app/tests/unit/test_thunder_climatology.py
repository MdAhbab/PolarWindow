"""The thunder climatology: grid cells, OPeNDAP's CSV, the tally and the share (T4 B1)."""

from __future__ import annotations

import pytest

from app.data import thunder_climatology as t


def test_a_pad_falls_in_the_cell_whose_centre_is_nearest() -> None:
    i, j = t.cell_of(28.60822681, -80.60428186)  # LC-39A
    assert (i, j) == (1987, 1227)
    assert t.LON0 + i * t.STEP_DEG == pytest.approx(-80.625)
    assert t.LAT0 - j * t.STEP_DEG == pytest.approx(28.625)
    assert t.cell_of(95.0, 200.0) == (t.N_LON - 1, 0)


def test_csv_rows_map_to_cells_from_the_box_corner() -> None:
    row = ", ".join(["0"] * 20 + ["1", "1", "0", "-1"])
    text = f"Dataset: x.nc\n/thunder_hours[0][0], {row}\n/thunder_hours[1][2], {row}\n"
    cells = t.parse_csv(text, 1987, 1227)
    assert set(cells) == {(1987, 1227), (1988, 1229)}
    assert cells[(1988, 1229)][20:] == [1, 1, 0, -1]
    with pytest.raises(ValueError):
        t.parse_csv("/thunder_hours[0][0], 1, 0\n", 0, 0)


def test_tally_counts_hours_seen_and_hours_with_thunder() -> None:
    days = [
        {"day": "20230715", "pads": {"p": [0] * 20 + [1, 1, 0, -1]}},
        {"day": "20230716", "pads": {"p": [0] * 20 + [1, 0, 0, 0]}},
        {"day": "20230101", "pads": {"p": None}},
    ]
    c = t.tally(days, ["p"])
    assert c["p"]["07"]["20"] == [2, 2]
    assert c["p"]["07"]["21"] == [2, 1]
    assert c["p"]["07"]["23"] == [1, 0]  # outside the mappers' view is not counted
    assert c["p"]["01"]["20"] == [0, 0]
    cl = t.ThunderClimatology(region="r", years="2023-2023", source_url="u", counts=c)
    assert cl.share("p", 7, 21) == (0.5, 1, 2)
    assert cl.share("p", 1, 20) is None
    assert cl.share("other", 7, 20) is None
