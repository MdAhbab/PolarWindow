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


# ---------------------------------------------------------------------------
# The map layer: tiles in the terrain tiles' scheme
# ---------------------------------------------------------------------------

from app.core.projections import local_frame  # noqa: E402

CLASSES = {
    vs.CLEAR: vs.CLEAR_RGBA,
    vs.BLOCKED: vs.BLOCKED_RGBA,
    vs.UNCERTAIN: vs.UNCERTAIN_RGBA,
}
STRIPES = {vs.BLOCKED: vs.BLOCKED_STRIPE_RGBA, vs.UNCERTAIN: vs.UNCERTAIN_STRIPE_RGBA}
SITE = (-85.0, 120.0)  # lat, lon: grid north is 120 degrees from true north here


def _pixel_at(frame, east: float, north: float, bearings, ranges, states, pixel_m: float = 1.0):
    """The tile pixel that lies on the ground point ``east``, ``north`` of the lander, and
    where in the whole map its tile starts (so the stripes' phase is known)."""
    gx, gy = frame.local_to_grid(np.array([east]), np.array([north]))
    gx, gy = float(gx[0]), float(gy[0])
    # A 256 px tile whose pixel (128, 128) is exactly that grid point, ``pixel_m`` apart.
    bounds = (gx - 128 * pixel_m, gy - 127 * pixel_m, gx + 127 * pixel_m, gy + 128 * pixel_m)
    origin = (1000, 3000)
    tile = vs.tile_rgba(bounds, frame, bearings, ranges, states, pixel_origin=origin)
    assert tile is not None
    return tuple(int(c) for c in tile[128, 128]), (origin[0] + 128, origin[1] + 128)


def test_cell_edges_are_half_way_between_samples() -> None:
    edges = vs.cell_edges(25.0 * np.arange(1, 21))
    assert edges[0] == 0.0 and edges[1] == 37.5 and edges[2] == 62.5
    assert edges[-2] == 487.5 and edges[-1] == 512.5 and edges.size == 21


def test_a_tile_draws_each_ground_point_in_its_cell_whichever_way_the_grid_turns() -> None:
    """A different state in every (bearing, range) cell, read back from the picture at points
    given as bearing and range from the lander. At 120 deg E the grid's north is 120 degrees
    from true north, so a tile that forgot the turn would put every cell in the wrong place."""
    frame = local_frame(SITE[1], SITE[0])
    assert abs(math.degrees(frame.grid_convergence_rad) - 120.0) < 0.01
    bearings = np.arange(0.0, 360.0, 5.0)
    ranges = 25.0 * np.arange(1, 21)
    rng = np.random.default_rng(7)
    states = rng.integers(0, 3, size=(72, 20)).astype(np.int8)
    for _ in range(300):
        i, k = int(rng.integers(0, 72)), int(rng.integers(0, 20))
        # Inside the cell: within 2 degrees of the bearing, a few metres off the range (a
        # metre is a pixel here, and the grid turns and stretches the point by up to a pixel).
        b = math.radians(bearings[i] + rng.uniform(-2.0, 2.0))
        r = ranges[k] + rng.uniform(-6.0, 6.0) if k else rng.uniform(5.0, 30.0)
        px, _ = _pixel_at(frame, r * math.sin(b), r * math.cos(b), bearings, ranges, states)
        want = int(states[i, k])
        assert px in (CLASSES[want], STRIPES.get(want)), (bearings[i], ranges[k], px, want)


def test_a_tile_is_empty_away_from_the_lander_and_clear_beyond_the_last_cell() -> None:
    frame = local_frame(SITE[1], SITE[0])
    bearings = np.arange(0.0, 360.0, 5.0)
    ranges = 25.0 * np.arange(1, 21)
    states = np.full((72, 20), vs.CLEAR, dtype=np.int8)
    far = (frame.x0_m + 5000.0, frame.y0_m + 5000.0)
    assert (
        vs.tile_rgba((far[0], far[1], far[0] + 500, far[1] + 500), frame, bearings, ranges, states)
        is None
    )
    here = (frame.x0_m - 700.0, frame.y0_m - 700.0, frame.x0_m + 700.0, frame.y0_m + 700.0)
    tile = vs.tile_rgba(here, frame, bearings, ranges, states)
    assert tile is not None
    drawn = tile[..., 3] > 0
    # A disc of radius 512.5 m on 1400 m: pi r^2 / side^2 of the picture, to a pixel of edge.
    assert drawn.mean() == pytest.approx(
        math.pi * 512.5**2 / 1400.0**2 * (256 / 255) ** 2, abs=0.01
    )
    assert set(map(tuple, tile[drawn][:, :].tolist())) == {vs.CLEAR_RGBA}


def test_stripes_run_on_across_tiles_and_tell_blocked_from_uncertain() -> None:
    """Both hatch states are stripes of the map, not of the tile: a pixel's stripe depends
    on where it is in the whole picture, so two neighbouring tiles join up."""
    frame = local_frame(SITE[1], SITE[0])
    bearings = np.arange(0.0, 360.0, 5.0)
    ranges = 25.0 * np.arange(1, 21)
    for state, width in (
        (vs.BLOCKED, vs.BLOCKED_STRIPE_PX),
        (vs.UNCERTAIN, vs.UNCERTAIN_STRIPE_PX),
    ):
        states = np.full((72, 20), state, dtype=np.int8)
        # The tile sits inside the disc (a 300 m square from the lander), at two places
        # in the whole map.
        b = (frame.x0_m - 150.0, frame.y0_m - 150.0, frame.x0_m + 150.0, frame.y0_m + 150.0)
        for origin in ((0, 0), (256, 512), (263, 517)):
            tile = vs.tile_rgba(b, frame, bearings, ranges, states, pixel_origin=origin)
            assert tile is not None
            u = origin[0] + np.arange(256)[None, :]
            v = origin[1] + np.arange(256)[:, None]
            phase = (
                (u + v) % vs.HATCH_PERIOD_PX
                if state == vs.BLOCKED
                else (u - v) % vs.HATCH_PERIOD_PX
            )
            striped = np.all(tile == np.array(STRIPES[state], dtype=np.uint8), axis=-1)
            assert np.array_equal(striped, phase < width)
            assert striped.mean() == pytest.approx(width / vs.HATCH_PERIOD_PX, abs=0.01)
    assert vs.BLOCKED_STRIPE_PX != vs.UNCERTAIN_STRIPE_PX  # two claims, two looks
