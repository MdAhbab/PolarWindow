"""Tests for disc-fraction bounds and weighted body timeline tracks."""


def test_disc_bounds_bracket_and_sum_to_the_window() -> None:
    """Full disc <= any limb, and both are weighted to the window's length."""
    import numpy as np

    from app.core import timeline

    t = np.arange(0, 11, dtype=np.float64) * 900.0
    state = np.array([0, 1, 2, 2, 2, 1, 0, 0, 1, 2, 2], dtype=np.int8)
    track = timeline.BodyTrack(
        body="sun",
        t_s=t,
        az_deg=t,
        el_deg=t,
        mask_el_deg=t,
        margin_deg=t,
        state=state,
        angular_radius_deg=t,
        arcs=[],
        arc_tolerance_s=[],
        arc_edge_tolerance_s=[],
        arc_grazing=[],
        blocked_by_bearing_deg=[],
        blocked_by_el_deg=[],
        grazing=False,
    )
    b = timeline.disc_bounds(track)
    assert 0 <= b.full_disc_s <= b.any_limb_s <= t[-1]
    assert b.full_disc_s == 900.0 * 3 + 900.0 * 1.5  # three interior 2s, one 2 + one end 2
