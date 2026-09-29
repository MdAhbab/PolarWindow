"""Planned relays (T1, F3 and F4): orbit, links, routing and the sweep, on analytic cases."""

from __future__ import annotations

import math
import random

import numpy as np
import pytest

from app.core import intervals, network, relay
from app.core.intervals import Run
from app.core.visibility import enu_basis
from app.data import catalogues
from app.data.catalogues import Assumption, Relay
from app.workers.handlers import relay_sweep

R = 1_737_400.0
GM = 4.9028e12


def test_kepler_solves_a_very_elliptical_orbit() -> None:
    m = np.linspace(0.0, 2.0 * math.pi, 1001)
    for e in (0.0, 0.58, 0.692, 0.95):
        big_e = relay.eccentric_anomaly(m, e)
        back = np.mod(big_e - e * np.sin(big_e), 2.0 * math.pi)
        err = np.abs(np.angle(np.exp(1j * (back - m))))
        assert float(err.max()) < 1e-11


def test_orbit_from_heights_and_its_period() -> None:
    o = relay.Orbit.from_heights(673.4e3, 7331.8e3, 50.0, 90.0, R)
    assert o.a_m == pytest.approx(5_740_000.0, abs=1.0)
    assert o.e == pytest.approx(0.58, abs=5e-4)
    assert o.period_s(GM) / 3600.0 == pytest.approx(10.84, abs=0.01)
    with pytest.raises(ValueError):
        relay.Orbit.from_heights(8000e3, 7000e3, 50.0, 90.0, R)


def test_argument_of_periapsis_90_puts_the_far_point_over_the_south_pole() -> None:
    o = relay.Orbit.from_heights(700e3, 7000e3, 90.0, 90.0, R)
    p = o.period_s(GM)
    at = relay.positions(o, 0.0, 0.0, np.array([0.0, p / 2.0, p]), GM)
    assert at[0] == pytest.approx([0.0, 0.0, R + 700e3], abs=1e-3)  # near point, north
    assert at[1] == pytest.approx([0.0, 0.0, -(R + 7000e3)], abs=1e-3)  # far point, south
    assert at[2] == pytest.approx(at[0], abs=1e-3)


def test_segment_clearance_is_the_miss_distance() -> None:
    p0 = np.array([[-10.0, 3.0, 0.0], [5.0, 0.0, 0.0], [-10.0, 0.5, 0.0]])
    p1 = np.array([[10.0, 3.0, 0.0], [10.0, 0.0, 0.0], [10.0, 0.5, 0.0]])
    got = relay.segment_clearance_m(p0, p1, 1.0)
    # Passes 3 from the centre; stays beyond x = 5 (sphere behind it); passes through.
    assert got == pytest.approx([2.0, 4.0, -0.5])


def _geometry(
    t: np.ndarray, site_lat: float, *, stations: list[relay.StationFrame]
) -> relay.Geometry:
    n = t.size
    eye = np.broadcast_to(np.eye(3), (n, 3, 3)).copy()
    return relay.Geometry(
        t_s=t,
        in_to_me=eye,  # a Moon that does not turn
        in_to_j2k=np.eye(3),
        moon_from_earth_j2k_m=np.tile([384_400e3, 0.0, 0.0], (n, 1)),
        site_me_m=np.array([0.0, 0.0, R * math.copysign(1.0, site_lat)]),
        basis=enu_basis(site_lat, 0.0),
        skyline_az_deg=np.array([0.0, 180.0]),
        skyline_el_deg=np.array([0.0, 0.0]),
        stations=stations,
        r_moon_m=R,
        gm=GM,
    )


def test_a_circular_polar_relay_is_in_view_of_the_pole_for_the_exact_share() -> None:
    """From the pole, over a flat skyline, a relay at radius r is up while it is
    below latitude -asin(R/r): (pi - 2 asin(R/r)) / 2 pi of each orbit."""
    alt = 3000e3
    o = relay.Orbit.from_heights(alt, alt, 90.0, 0.0, R)
    p = o.period_s(GM)
    t = np.linspace(0.0, 10.0 * p, 20_001)
    rl = relay.links(_geometry(t, -90.0, stations=[]), o, 0.0, 0.0)
    share = intervals.total(rl.lander_relay, True) / t[-1]
    want = (math.pi - 2.0 * math.asin(R / (R + alt))) / (2.0 * math.pi)
    assert share == pytest.approx(want, abs=1e-5)


def test_the_moon_hides_the_relay_from_earth_for_the_exact_share() -> None:
    """An equatorial relay seen from far away is behind the Moon for asin(R/r)/pi
    of each orbit; the station here sits at Earth's centre looking straight up
    at the Moon, so only the Moon can hide it."""
    alt = 5000e3
    o = relay.Orbit.from_heights(alt, alt, 0.0, 0.0, R)
    p = o.period_s(GM)
    t = np.linspace(0.0, 10.0 * p, 20_001)
    n = t.size
    # TOPO: z up along +x (toward the Moon), x north along +z, y west along -y.
    to_topo = np.array([[0.0, 0.0, 1.0], [0.0, -1.0, 0.0], [1.0, 0.0, 0.0]])
    st = relay.StationFrame(
        id="s",
        pos_j2k_m=np.zeros((n, 3)),
        j2k_to_topo=np.broadcast_to(to_topo, (n, 3, 3)).copy(),
        mask_az_deg=np.array([0.0, 180.0]),
        mask_el_deg=np.array([0.0, 0.0]),
    )
    rl = relay.links(_geometry(t, -90.0, stations=[st]), o, 0.0, 0.0)
    r = R + alt
    hidden = 1.0 - intervals.total(rl.relay_station, True) / t[-1]
    # Seen from 384,400 km, not infinity: the shadow cone narrows by R r / D.
    assert hidden == pytest.approx(math.asin(R / r) / math.pi, abs=2e-3)
    hidden_earth = 1.0 - intervals.total(rl.relay_earth, True) / t[-1]
    assert hidden_earth == pytest.approx(hidden, abs=1e-4)


def _random_runs(rng: random.Random, t1: float, k: int) -> list[Run]:
    edges = sorted(rng.uniform(0.0, t1) for _ in range(2 * k))
    return [Run(True, edges[i], edges[i + 1]) for i in range(0, len(edges), 2)]


def test_chain_routing_matches_the_general_search_over_contacts() -> None:
    rng = random.Random(7)
    t1 = 100_000.0
    for _ in range(40):
        d, up, down = (_random_runs(rng, t1, rng.randint(0, 8)) for _ in range(3))
        hops = (relay.Hop.of(d, 1.3), relay.Hop.of(up, 0.05), relay.Hop.of(down, 1.3))
        contacts = (
            [network.Contact("lander", "earth", r.start, r.end, 1.3) for r in d]
            + [network.Contact("lander", "relay", r.start, r.end, 0.05) for r in up]
            + [network.Contact("relay", "earth", r.start, r.end, 1.3) for r in down]
        )
        ts = np.array([rng.uniform(0.0, t1) for _ in range(50)])
        got = relay.earliest_arrival(ts, hops[0], [(hops[1], hops[2])])
        want = [network.earliest_arrival(contacts, "lander", "earth", float(x)) for x in ts]
        assert got == pytest.approx(np.array(want))


def test_longest_wait_catches_a_message_that_reaches_the_relay_too_late() -> None:
    """Relay in view all along, its link down open 0-50 s and from 1000 s: a message
    made at 49.95 s reaches the relay as that link closes and waits until 1000 s.
    The worst case is that instant, not one where a link from the lander closes
    (the only instants the general search tries)."""
    direct = relay.Hop.of([], 1.0)
    up = relay.Hop.of([Run(True, 0.0, 2000.0)], 0.05)
    down = relay.Hop.of([Run(True, 0.0, 50.0), Run(True, 1000.0, 2000.0)], 1.0)
    wait, at, cut = relay.longest_wait(direct, [(up, down)], 0.0, 2000.0)
    assert at == pytest.approx(49.95)
    assert wait == pytest.approx(1000.0 + 1.0 - 49.95)
    assert not cut
    fine = np.linspace(0.0, 2000.0, 400_001)
    arr = relay.earliest_arrival(fine, direct, [(up, down)])
    brute = float(np.where(np.isfinite(arr), arr - fine, 2000.0 - fine).max())
    assert wait >= brute - 1e-9 and wait - brute < 0.01


def test_every_orbit_the_catalogue_gives_is_swept_end_to_end() -> None:
    cat = catalogues.load("relays")
    for rid in ("lunar-pathfinder", "altus-1"):
        sp = relay_sweep.spec(cat.get(rid), True)
        assert sp.missing is None
        assert len(sp.orbits) == 4  # both ends of inclination and argument of periapsis
        incl = sorted({o.i_deg for o in sp.orbits})
        a = cat.get(rid).assumed_fields["inclination_deg"]
        assert incl == [a.lo, a.hi]
    lp = cat.get("lunar-pathfinder")
    assert lp.provenance("periapsis_km")[0] == "published"
    assert lp.provenance("inclination_deg")[0] == "assumed"
    block = relay_sweep.orbit_block(cat.get("altus-1"))
    assert block["inclination_deg"]["provenance"] == "assumed"
    assert block["inclination_deg"]["lo"] == pytest.approx(52.51)


def test_a_relay_without_an_orbit_says_so() -> None:
    rec = (
        catalogues.load("relays")
        .get("lunar-pathfinder")
        .model_copy(update={"arg_periapsis_deg": None})
    )
    sp = relay_sweep.spec(rec, False)
    assert sp.orbits == [] and sp.missing and "arg periapsis" in sp.missing


def test_an_assumed_value_must_sit_inside_its_range() -> None:
    with pytest.raises(ValueError):
        Assumption(reason="a reason long enough", lo=2.0, hi=1.0)
    rec = catalogues.load("relays").get("altus-1").model_dump()
    rec["inclination_deg"] = 70.0
    with pytest.raises(ValueError, match="outside its assumed range"):
        Relay.model_validate(rec)


def test_spread_is_middle_and_ends() -> None:
    s = relay.Spread.of([3.0, 1.0, 2.0], [False, True, False])
    assert (s.median, s.lo, s.hi, s.open) == (2.0, 1.0, 3.0, True)
    assert len(relay.grid()) == relay.NODE_STEPS * relay.PHASE_STEPS


def _stations_at_the_moons_side(n: int) -> list[relay.StationFrame]:
    """Two stations at Earth's centre looking straight at the Moon, so the Moon is all that can
    hide a relay from the one with no mask; the other's mask keeps only a relay within half a
    degree of the Moon's centre."""
    to_topo = np.array([[0.0, 0.0, 1.0], [0.0, -1.0, 0.0], [1.0, 0.0, 0.0]])
    return [
        relay.StationFrame(
            id=sid,
            pos_j2k_m=np.zeros((n, 3)),
            j2k_to_topo=np.broadcast_to(to_topo, (n, 3, 3)).copy(),
            mask_az_deg=np.array([0.0, 180.0]),
            mask_el_deg=np.array([mask, mask]),
        )
        for sid, mask in (("low-mask", 0.0), ("high-mask", 89.5))
    ]


def test_each_station_on_its_own_makes_up_the_combined_link() -> None:
    alt = 5000e3
    o = relay.Orbit.from_heights(alt, alt, 30.0, 0.0, R)
    t = np.linspace(0.0, 4.0 * o.period_s(GM), 4001)
    geom = _geometry(t, -90.0, stations=_stations_at_the_moons_side(t.size))
    each = relay.station_links(geom, o, 40.0, 100.0)
    assert set(each) == {"low-mask", "high-mask"}
    combined = relay.links(geom, o, 40.0, 100.0)
    # With the low mask a station hears wherever the Moon is not in the way, and the high
    # mask hears less; the combined link is the low one.
    low, high = (intervals.total(each[k][0], True) for k in ("low-mask", "high-mask"))
    assert low == pytest.approx(intervals.total(combined.relay_station, True), rel=1e-9)
    assert 0.0 < high < low
    # The light time is the farthest the relay is from that station (from Earth's centre here).
    far = (384_400e3 + R + alt) / 299_792_458.0
    assert each["low-mask"][1] <= far + 1e-6 and each["low-mask"][1] > 1.0


def test_the_placement_listed_is_the_one_nearest_the_middle_and_is_reproducible() -> None:
    # The middle of [10, 20, 30, 50, 90] is 30, and the point with 30 in it is the third.
    assert relay_sweep.nearest_the_middle([10.0, 50.0, 30.0, 20.0, 90.0], 5) == (2, 30.0)
    # A tie goes to the earlier point of the sweep, so the choice is the same every time:
    # the middle of [1, 3, 2, 2] is 2 and it first appears at point 2.
    assert relay_sweep.nearest_the_middle([1.0, 3.0, 2.0, 2.0], 4) == (2, 2.0)
    # Point k of a sweep put this relay at placement k modulo its own count.
    assert relay_sweep.nearest_the_middle([5.0, 1.0, 2.0, 9.0, 2.0], 3) == (2, 2.0)
    assert relay_sweep.nearest_the_middle([5.0, 9.0, 1.0, 2.0, 3.0], 3) == (1, 3.0)


def test_a_sweep_names_the_placement_nearest_the_middle_of_each_relay() -> None:
    rec = catalogues.load("relays").get("lunar-pathfinder")
    sp = relay_sweep.spec(rec, True)
    o = sp.orbits[0]
    # A short run over a moon that does not turn; no stations, Earth always above the skyline.
    t = np.linspace(0.0, 2.0 * o.period_s(GM), 241)
    geom = _geometry(t, -90.0, stations=[])
    t1 = float(t[-1])
    res = relay_sweep.sweep(
        geom,
        [relay_sweep.Spec(rec, True, [o], None)],
        t1,
        [Run(True, 0.0, t1)],
        [],
        1.3,
    )
    ((j, via_s),) = res.nearest
    assert 0 <= j < relay.NODE_STEPS * relay.PHASE_STEPS
    assert res.via[0].lo <= via_s <= res.via[0].hi
    # The listed placement really gives that time through the relay, and it is as near
    # the sweep's middle as any placement on the grid.
    orbit, raan, m0 = relay_sweep.placement(relay_sweep.Spec(rec, True, [o], None), j)
    rl = relay.links(geom, orbit, raan, m0)
    again = intervals.total(intervals.both(rl.lander_relay, rl.relay_earth), True)
    assert again == pytest.approx(via_s)
