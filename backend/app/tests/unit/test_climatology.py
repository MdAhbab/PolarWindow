"""The wind climatology's histogram and the share read from it (T4 B1)."""

from __future__ import annotations

import pytest

from app.data import climatology as c


def _clim(series: dict[str, float]) -> c.Climatology:
    return c.Climatology("x", 0.0, 0.0, "2001-2002", "https://example.test", c.histogram(series))


def test_histogram_keeps_month_and_hour_and_skips_fill() -> None:
    h = c.histogram({"2001010112": 3.1, "2002010112": 12.0, "2001010113": -999.0, "2001070112": 0})
    assert sum(h["01"]["12"]) == 2 and "13" not in h["01"] and sum(h["07"]["12"]) == 1
    assert h["01"]["12"][-1] != 0  # trailing empty bins are left out


def test_share_above_a_limit() -> None:
    speeds = [2, 4, 6, 8, 10, 12, 14, 16]
    series = {f"20{y:02d}010112": float(v) for y, v in enumerate(speeds)}
    cl = _clim(series)
    assert cl.share_above(1, 12, 9.0) == (0.5, 8)
    assert cl.share_above(1, 12, 100.0) == (0.0, 8)
    assert cl.share_above(1, 12, -1.0) == (1.0, 8)
    assert cl.share_above(2, 12, 5.0) is None  # no hours for that month
    # Inside a bin the hours are taken as spread evenly across it.
    one = _clim({"2001010100": 10.1})
    got = one.share_above(1, 0, 10.0 + c.BIN_M_S / 2)
    assert got is not None and got[1] == 1 and got[0] == pytest.approx(0.5)
