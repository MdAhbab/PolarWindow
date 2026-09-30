"""Station visibility, the contact graph and routing (T1, F1 and F4)."""

from __future__ import annotations

import math

import numpy as np
import pytest

from app.core import contact, intervals, network
from app.core.intervals import Run


def test_mask_interpolates_and_wraps_at_north() -> None:
    az = np.arange(0.0, 360.0, 1.0)
    el = np.full(360, 6.0)
    el[359] = 10.0
    got = contact.mask_elevation(az, el, np.array([359.5, 0.0, 180.0]))
    assert got[0] == pytest.approx(8.0)
    assert got[1] == pytest.approx(6.0) and got[2] == pytest.approx(6.0)


def test_station_runs_cross_where_the_margin_crosses() -> None:
    t = np.arange(0.0, 3601.0, 600.0)
    el = np.linspace(0.0, 12.0, t.size)  # rises 12 deg in an hour
    runs = contact.station_runs(
        t, np.zeros_like(t), el, np.array([0.0, 180.0]), np.array([6.0, 6.0])
    )
    assert [r.value for r in runs] == [False, True]
    assert runs[1].start == pytest.approx(1800.0)


def test_heard_needs_earth_up_and_the_station() -> None:
    earth = [Run(True, 0, 50), Run(False, 50, 100)]
    st = {
        "a": [Run(False, 0, 20), Run(True, 20, 100)],
        "b": [Run(True, 0, 10), Run(False, 10, 100)],
    }
    h = contact.heard(earth, st)
    assert intervals.total(h["a"], True) == pytest.approx(30.0)
    union = contact.any_station(h)
    assert intervals.total(union, True) == pytest.approx(40.0)
    s = contact.Stretches(union, 0.0, 100.0)
    longest, is_open = s.longest(False)
    assert longest == pytest.approx(50.0) and is_open  # runs to the end of the dates


def test_edge_tolerance_counts_only_earth_edges() -> None:
    heard = [Run(False, 0, 20), Run(True, 20, 50), Run(False, 50, 100)]
    assert contact.edge_tolerance_s(heard, [(50.0, 30.0)]) == pytest.approx(30.0)
    assert contact.edge_tolerance_s(heard, [(70.0, 30.0)]) == 0.0


def test_earliest_arrival_waits_for_a_contact_and_can_hop() -> None:
    c = [
        network.Contact("lander", "relay", 10, 20, 0.1),
        network.Contact("relay", "earth", 30, 40, 1.3),
        network.Contact("lander", "earth", 100, 200, 1.3),
    ]
    assert network.earliest_arrival(c, "lander", "earth", 0) == pytest.approx(31.3)
    assert network.earliest_arrival(c, "lander", "earth", 25) == pytest.approx(101.3)
    assert math.isinf(network.earliest_arrival(c, "lander", "earth", 250))


def test_longest_wait_is_exact_and_says_when_it_is_cut_short() -> None:
    c = [
        network.Contact("lander", "earth", 0, 10, 1.0),
        network.Contact("lander", "earth", 50, 60, 1.0),
    ]
    wait, at, is_open = network.longest_wait(c, "lander", "earth", 0, 100)
    # A message made at 10 (just after the first contact closes) waits until 50, plus 1 s.
    assert wait == pytest.approx(41.0) and at == 10
    assert not is_open
    c2 = [network.Contact("lander", "earth", 0, 10, 1.0)]
    wait2, _, open2 = network.longest_wait(c2, "lander", "earth", 0, 100)
    assert open2 and wait2 == pytest.approx(90.0)


@pytest.mark.requires_kernels
def test_station_geometry_matches_spice_observed_from_the_station() -> None:
    import spiceypy as sp

    from app.config import get_settings
    from app.core import spice

    spice.load(get_settings().kernel_dir)
    et0 = spice.utc_to_et("2025-03-06T12:00:00")
    ets = et0 + np.arange(0.0, 86400.0, 7200.0)
    looks = spice.station_look_angles(["DSS-14", "DSS-43", "DSS-63"], np.zeros(3), ets)
    for look in looks:
        for i, et in enumerate(ets):
            p, _ = sp.spkpos("MOON", et, f"{look.station}_TOPO", "LT+S", look.station)
            el = np.degrees(np.arcsin(p[2] / np.linalg.norm(p)))
            az = np.degrees(np.arctan2(-p[1], p[0])) % 360.0
            daz = ((look.az_deg[i] - az + 180.0) % 360.0) - 180.0
            assert abs(look.el_deg[i] - el) < 0.001
            assert abs(daz) * np.cos(np.radians(el)) < 0.001
