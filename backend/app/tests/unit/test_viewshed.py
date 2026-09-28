"""Rover-to-lander line of sight (T1, F5) on analytic surfaces, where the answer is exact."""

from __future__ import annotations

import math

import numpy as np
import pytest

from app.core import viewshed as vs

FLAT_WORLD = 1.0e30  # no curvature, so the analytic answers are plain geometry
B = np.arange(0.0, 360.0, 30.0)


def _ring_wall(r0: float, r1: float, h: float):
    def sample(x: np.ndarray, y: np.ndarray) -> np.ndarray:
        r = np.hypot(x, y)
        return np.where((r >= r0) & (r <= r1), h, 0.0)

    return sample


def _sigma(value: float):
    def sample(x: np.ndarray, y: np.ndarray) -> np.ndarray:
        return np.full(np.shape(x), value)

    return sample


def _run(sampler, sigma: float, ranges: np.ndarray, **kw: float) -> vs.Viewshed:
    args = {
        "lander_antenna_m": 3.0,
        "rover_antenna_m": 0.5,
        "frequency_hz": 2.4e9,
        "post_m": 5.0,
        "step_m": 1.0,
        "r_body_m": FLAT_WORLD,
    } | kw
    return vs.compute(
        sampler, _sigma(sigma), bearings_deg=B, ranges_m=ranges, site_height_m=0.0, **args
    )


def test_flat_ground_is_all_in_sight() -> None:
    v = _run(_ring_wall(0, 0, 0.0), 0.0, np.arange(25.0, 501.0, 25.0))
    assert (v.sight == vs.CLEAR).all()


def test_a_wall_shadows_exactly_the_rovers_below_its_top() -> None:
    """A 10 m ring wall from 200 to 205 m: a rover beyond it is hidden when the wall's
    top, seen from the lander's antenna, stands above the rover's antenna."""
    ranges = np.arange(215.0, 1001.0, 5.0)
    v = _run(_ring_wall(200.0, 205.0, 10.0), 0.0, ranges)
    eye, tip = 3.0, 0.5
    top = (10.0 - eye) / 200.0  # the near edge of the wall sets the steepest angle
    want = np.where((tip - eye) / ranges > top, vs.CLEAR, vs.BLOCKED)
    assert (v.sight == want[None, :]).all()
    # In front of the wall nothing is in the way.
    front = _run(_ring_wall(200.0, 205.0, 10.0), 0.0, np.array([100.0, 150.0, 185.0]))
    assert (front.sight == vs.CLEAR).all()


def test_a_wall_taller_than_the_line_to_a_tall_mast_still_lets_it_see() -> None:
    """Raise the rover's antenna: the shadow ends where the line clears the wall."""
    ranges = np.arange(215.0, 1001.0, 5.0)
    v = _run(_ring_wall(200.0, 205.0, 10.0), 0.0, ranges, rover_antenna_m=20.0)
    eye, tip = 3.0, 20.0
    want = np.where((tip - eye) / ranges > (10.0 - eye) / 200.0, vs.CLEAR, vs.BLOCKED)
    assert (v.sight == want[None, :]).all()
    assert (v.sight[:, ranges < 485.0] == vs.CLEAR).all()


def test_the_height_error_makes_a_band_and_never_flips_a_state() -> None:
    """With a 2 m error, every cell is either the exact state or uncertain, and the
    uncertain cells are the ones whose clearance is inside the error."""
    ranges = np.arange(215.0, 1501.0, 5.0)
    exact = _run(_ring_wall(200.0, 205.0, 10.0), 0.0, ranges)
    noisy = _run(_ring_wall(200.0, 205.0, 10.0), 2.0, ranges)
    known = noisy.sight != vs.UNCERTAIN
    assert (noisy.sight[known] == exact.sight[known]).all()
    eye, tip = 3.0, 0.5
    margin = np.arctan2(tip - eye, ranges) - math.atan2(10.0 - eye, 200.0)
    band = math.atan2(2.0, 200.0) + np.arctan2(2.0, ranges)
    assert (noisy.sight[:, np.abs(margin) > band + 1e-12] != vs.UNCERTAIN).all()
    assert (noisy.sight[:, np.abs(margin) < band - 1e-12] == vs.UNCERTAIN).all()


def test_the_fresnel_zone_is_separate_from_the_line() -> None:
    """Antennas 3 m up over flat ground at 30 GHz (the zone's middle radius is 1.12 m
    at 500 m): clear. A 2.5 m wall half way leaves the line clear but cuts the zone."""
    r = np.array([500.0])
    flat = _run(_ring_wall(0, 0, 0.0), 0.0, r, rover_antenna_m=3.0, frequency_hz=30e9)
    assert (flat.sight == vs.CLEAR).all() and (flat.radio == vs.CLEAR).all()
    wall = _run(_ring_wall(249.5, 250.5, 2.5), 0.0, r, rover_antenna_m=3.0, frequency_hz=30e9)
    assert (wall.sight == vs.CLEAR).all() and (wall.radio == vs.BLOCKED).all()
    f1 = math.sqrt((299_792_458.0 / 30e9) * 250.0 * 250.0 / 500.0)
    assert 3.0 - f1 > 0.0 > 3.0 - f1 - 2.5
    # At 2.4 GHz the zone (3.95 m) reaches the flat ground itself.
    low = _run(_ring_wall(0, 0, 0.0), 0.0, r, rover_antenna_m=3.0, frequency_hz=2.4e9)
    assert (low.sight == vs.CLEAR).all() and (low.radio == vs.BLOCKED).all()


def test_the_ground_at_either_end_is_never_a_blocker() -> None:
    """A 1 m bump right under the lander's feet or the rover's wheels, within two
    DEM posts, is ground the model cannot resolve at lander scale."""
    r = np.array([300.0])
    for bump in (_ring_wall(4.0, 8.0, 1.0), _ring_wall(292.0, 296.0, 1.0)):
        v = _run(bump, 0.0, r, rover_antenna_m=0.0, lander_antenna_m=0.2, post_m=5.0)
        assert (v.sight == vs.CLEAR).all()


def test_terrain_outside_the_model_is_never_called_clear() -> None:
    def holes(x: np.ndarray, y: np.ndarray) -> np.ndarray:
        return np.where(np.hypot(x, y) > 150.0, np.nan, 0.0)

    v = _run(holes, 0.0, np.array([100.0, 300.0]))
    assert (v.sight[:, 0] == vs.CLEAR).all()
    assert (v.sight[:, 1] == vs.UNCERTAIN).all() and not v.covered[:, 1].any()
    assert vs.ground_share(v, v.sight) == (0.0, 0.0)  # only covered cells count


def test_ground_share_weights_each_cell_by_its_ring() -> None:
    ranges = np.array([100.0, 300.0])
    v = vs.Viewshed(
        bearings_deg=np.array([0.0, 180.0]),
        ranges_m=ranges,
        sight=np.array([[vs.CLEAR, vs.BLOCKED], [vs.UNCERTAIN, vs.CLEAR]], dtype=np.int8),
        radio=np.zeros((2, 2), dtype=np.int8),
        covered=np.ones((2, 2), dtype=bool),
    )
    lo, hi = vs.ground_share(v, v.sight)  # type: ignore[misc]
    assert lo == pytest.approx(300.0 / 800.0) and hi == pytest.approx(400.0 / 800.0)
