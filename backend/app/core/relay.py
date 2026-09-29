"""Planned relays (T1, F3 and F4): where a relay in its planned orbit is, who can
talk to it, and what it adds to a lander's contact with Earth. Pure.

A planned relay's orbit is published as a shape (heights, inclination, perhaps
the argument of periapsis) but never with the two numbers that place it in
time: where its node will sit and where along the orbit it will be on a given
day. Those are swept on a 36 x 36 grid of node and phase, and every number
built on the relay is the spread over that grid ("X-Y h through the relay, if
it flies as planned"). An element that is not published either is an assumed
range; both of its ends are swept.

Two-body motion about the Moon. A frozen orbit keeps its shape and its
argument of periapsis by design; Earth's pull turns its node by about half a
degree a day, which the node sweep covers but a single run does not follow.

Frames: the orbit is fixed in space, its elements relative to the lunar
equator at the start of the dates (MOON_ME frozen then). The caller supplies
the rotations to MOON_ME at each instant (for the lander) and to J2000 (for
Earth and the ground stations); this module does no SPICE.

Links
-----
* lander -> relay: the relay above the lander's terrain skyline.
* relay -> Earth: Earth's centre not behind the Moon, seen from the relay.
* relay -> station: the relay above the station's published mask, and the
  straight line between them clear of the Moon (a ray-sphere test).

Routing: a message may wait at the relay (store and forward). With only the
lander, relays and Earth as nodes, and no relay-to-relay link, every route is
lander -> Earth or lander -> relay -> Earth, so the earliest arrival is the
smaller of the two, found exactly with sorted searches rather than a general
search over contacts (:func:`app.core.network.earliest_arrival` gives the same
answer, and the tests hold them to it).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

import numpy as np
import numpy.typing as npt

from app.core import intervals
from app.core.contact import Stretches, mask_elevation
from app.core.intervals import Run
from app.core.visibility import ENUBasis

FloatArray = npt.NDArray[np.float64]

#: The grid the unknown node and phase are swept on (ADR-9 range).
NODE_STEPS: Final[int] = 36
PHASE_STEPS: Final[int] = 36


@dataclass(frozen=True, slots=True)
class Orbit:
    """A Keplerian orbit's shape and orientation, less node and phase."""

    a_m: float
    e: float
    i_deg: float
    argp_deg: float

    @classmethod
    def from_heights(
        cls, peri_alt_m: float, apo_alt_m: float, i_deg: float, argp_deg: float, r_body_m: float
    ) -> Orbit:
        rp, ra = r_body_m + peri_alt_m, r_body_m + apo_alt_m
        if not 0.0 < rp <= ra:
            raise ValueError(f"periapsis {peri_alt_m} m above apoapsis {apo_alt_m} m")
        return cls(a_m=(rp + ra) / 2.0, e=(ra - rp) / (ra + rp), i_deg=i_deg, argp_deg=argp_deg)

    def period_s(self, gm: float) -> float:
        return 2.0 * math.pi * math.sqrt(self.a_m**3 / gm)


def eccentric_anomaly(m: FloatArray, e: float) -> FloatArray:
    """Kepler's equation ``M = E - e sin E`` by Newton's method, to 1e-12 rad."""
    m = np.mod(m, 2.0 * math.pi)
    big_e = m + e * np.sin(m) if e < 0.8 else np.full_like(m, math.pi)
    for _ in range(50):
        d = (big_e - e * np.sin(big_e) - m) / (1.0 - e * np.cos(big_e))
        big_e = big_e - d
        if float(np.max(np.abs(d))) < 1e-12:
            break
    return big_e


def _orientation(raan_deg: float, i_deg: float, argp_deg: float) -> FloatArray:
    """Perifocal -> reference frame: R3(-raan) R1(-i) R3(-argp)."""
    o, i, w = (math.radians(x) for x in (raan_deg, i_deg, argp_deg))
    co, so, ci, si, cw, sw = (
        math.cos(o),
        math.sin(o),
        math.cos(i),
        math.sin(i),
        math.cos(w),
        math.sin(w),
    )
    return np.array(
        [
            [co * cw - so * sw * ci, -co * sw - so * cw * ci, so * si],
            [so * cw + co * sw * ci, -so * sw + co * cw * ci, -co * si],
            [sw * si, cw * si, ci],
        ],
        dtype=np.float64,
    )


def positions(
    orbit: Orbit, raan_deg: float, m0_deg: float, t_s: FloatArray, gm: float
) -> FloatArray:
    """``(n, 3)`` position from the Moon's centre, metres, in the orbit's reference frame.

    ``m0_deg`` is the mean anomaly at ``t = 0``.
    """
    n = math.sqrt(gm / orbit.a_m**3)
    big_e = eccentric_anomaly(math.radians(m0_deg) + n * np.asarray(t_s, dtype=np.float64), orbit.e)
    a, e = orbit.a_m, orbit.e
    x = a * (np.cos(big_e) - e)
    y = a * math.sqrt(1.0 - e * e) * np.sin(big_e)
    rot = _orientation(raan_deg, orbit.i_deg, orbit.argp_deg)
    return np.asarray(np.column_stack([x, y, np.zeros_like(x)]) @ rot.T, dtype=np.float64)


def segment_clearance_m(p0: FloatArray, p1: FloatArray, radius_m: float) -> FloatArray:
    """How far the segment ``p0 -> p1`` passes outside a sphere at the origin (m).

    ``> 0``: the line of sight is clear; ``<= 0``: the sphere is in the way.
    The closest point is clamped to the segment, so a sphere behind either end
    never blocks.
    """
    p0 = np.asarray(p0, dtype=np.float64).reshape(-1, 3)
    p1 = np.asarray(p1, dtype=np.float64).reshape(-1, 3)
    d = p1 - p0
    dd = np.einsum("ij,ij->i", d, d)
    s = np.clip(-np.einsum("ij,ij->i", p0, d) / np.where(dd == 0.0, 1.0, dd), 0.0, 1.0)
    closest = p0 + s[:, None] * d
    return np.asarray(np.linalg.norm(closest, axis=1) - radius_m, dtype=np.float64)


@dataclass(frozen=True, slots=True)
class StationFrame:
    """One ground station over the dates: where it is and how it looks."""

    id: str
    pos_j2k_m: FloatArray  # (n, 3) from Earth's centre, J2000
    j2k_to_topo: FloatArray  # (n, 3, 3): x north, y west, z up
    mask_az_deg: FloatArray
    mask_el_deg: FloatArray


@dataclass(frozen=True, slots=True)
class Geometry:
    """Everything about the dates a relay's links need, worked out once per answer."""

    t_s: FloatArray  # (n,) seconds from the start of the dates
    in_to_me: FloatArray  # (n, 3, 3): orbit reference frame -> MOON_ME at t
    in_to_j2k: FloatArray  # (3, 3): orbit reference frame -> J2000
    moon_from_earth_j2k_m: FloatArray  # (n, 3)
    site_me_m: FloatArray  # (3,)
    basis: ENUBasis
    skyline_az_deg: FloatArray
    skyline_el_deg: FloatArray
    stations: list[StationFrame]
    r_moon_m: float
    gm: float


@dataclass(frozen=True, slots=True)
class RelayLinks:
    """One relay's links over the dates, for one node and phase."""

    lander_relay: list[Run]
    relay_earth: list[Run]
    relay_station: list[Run]
    lander_relay_owlt_s: float
    relay_station_owlt_s: float


def _station_margin(
    geom: Geometry, st: StationFrame, r_j: FloatArray, relay_geo: FloatArray, r_dist: FloatArray
) -> tuple[FloatArray, float]:
    """One station's margin to the relay (degrees, ``> 0`` = it can hear it) and the
    farthest the relay is from that station over the dates (m).

    The smaller of two margins: the relay above the station's published mask, and
    the Moon not in the way (its clearance as an angle seen from the relay).
    """
    rel = relay_geo - st.pos_j2k_m
    w = np.einsum("nij,nj->ni", st.j2k_to_topo, rel)
    rng = np.linalg.norm(w, axis=1)
    s_el = np.degrees(np.arcsin(np.clip(w[:, 2] / rng, -1.0, 1.0)))
    s_az = np.mod(np.degrees(np.arctan2(-w[:, 1], w[:, 0])), 360.0)
    above = s_el - mask_elevation(st.mask_az_deg, st.mask_el_deg, s_az)
    clear = segment_clearance_m(r_j, st.pos_j2k_m - geom.moon_from_earth_j2k_m, geom.r_moon_m)
    return np.minimum(above, np.degrees(clear / r_dist)), float(rng.max())


def links(geom: Geometry, orbit: Orbit, raan_deg: float, m0_deg: float) -> RelayLinks:
    """The relay's three links over the dates for one point of the sweep."""
    c = 299_792_458.0
    t = geom.t_s
    r_in = positions(orbit, raan_deg, m0_deg, t, geom.gm)
    # lander -> relay: elevation above the skyline.
    r_me = np.einsum("nij,nj->ni", geom.in_to_me, r_in)
    v = r_me - geom.site_me_m[None, :]
    rng_lr = np.linalg.norm(v, axis=1)
    u = v / rng_lr[:, None]
    el = np.degrees(np.arcsin(np.clip(u @ geom.basis.up, -1.0, 1.0)))
    az = np.mod(np.degrees(np.arctan2(u @ geom.basis.east, u @ geom.basis.north)), 360.0)
    lr = intervals.runs_from_margin(
        t, el - mask_elevation(geom.skyline_az_deg, geom.skyline_el_deg, az)
    )
    # relay -> Earth's centre, Moon at the origin.
    r_j = r_in @ geom.in_to_j2k.T
    earth = -geom.moon_from_earth_j2k_m
    re = intervals.runs_from_margin(t, segment_clearance_m(r_j, earth, geom.r_moon_m))
    # relay -> each station: above its mask, and the Moon not in the way. Both
    # margins in degrees (the Moon's clearance as seen from the relay); a
    # station hears where the smaller is positive, any station where the
    # largest of those is. Edges are placed on this combined margin, within
    # one step of where each part crosses on its own.
    relay_geo = geom.moon_from_earth_j2k_m + r_j
    r_dist = np.linalg.norm(r_j, axis=1)
    best = np.full(t.shape, -180.0)
    rng_rs = 0.0
    for st in geom.stations:
        margin, rng_max = _station_margin(geom, st, r_j, relay_geo, r_dist)
        best = np.maximum(best, margin)
        rng_rs = max(rng_rs, rng_max)
    rs = intervals.runs_from_margin(t, best)
    return RelayLinks(
        lander_relay=lr,
        relay_earth=re,
        relay_station=rs,
        lander_relay_owlt_s=float(rng_lr.max()) / c,
        relay_station_owlt_s=rng_rs / c,
    )


def station_links(
    geom: Geometry, orbit: Orbit, raan_deg: float, m0_deg: float
) -> dict[str, tuple[list[Run], float]]:
    """For one placement, each station's own link to the relay: ``id -> (runs, light time)``.

    The contact plan needs a link per pair of nodes, where :func:`links` folds all
    stations into "any station hears it". The light time is the farthest the relay is
    from that station over the dates.
    """
    c = 299_792_458.0
    r_in = positions(orbit, raan_deg, m0_deg, geom.t_s, geom.gm)
    r_j = r_in @ geom.in_to_j2k.T
    relay_geo = geom.moon_from_earth_j2k_m + r_j
    r_dist = np.linalg.norm(r_j, axis=1)
    out: dict[str, tuple[list[Run], float]] = {}
    for st in geom.stations:
        margin, rng_max = _station_margin(geom, st, r_j, relay_geo, r_dist)
        out[st.id] = (intervals.runs_from_margin(geom.t_s, margin), rng_max / c)
    return out


# ---------------------------------------------------------------------------
# Routing over lander -> (relay ->) Earth
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Hop:
    """The open stretches of one link, sorted and disjoint, and its light time."""

    starts: FloatArray
    ends: FloatArray
    owlt_s: float

    @classmethod
    def of(cls, runs: list[Run], owlt_s: float) -> Hop:
        on = [r for r in runs if r.value and r.duration > intervals.EPS_S]
        return cls(
            np.array([r.start for r in on], dtype=np.float64),
            np.array([r.end for r in on], dtype=np.float64),
            owlt_s,
        )

    def send(self, t: FloatArray) -> FloatArray:
        """Earliest time at or after ``t`` the link is open; inf if it never is again.

        A stretch that ends exactly at ``t`` is closed (as in
        :func:`app.core.network.earliest_arrival`).
        """
        t = np.asarray(t, dtype=np.float64)
        if self.ends.size == 0:
            return np.full(t.shape, np.inf)
        i = np.searchsorted(self.ends, t, side="right")
        j = np.minimum(i, self.ends.size - 1)
        return np.asarray(
            np.where(i < self.ends.size, np.maximum(t, self.starts[j]), np.inf), dtype=np.float64
        )


def earliest_arrival(t: FloatArray, direct: Hop, relays: list[tuple[Hop, Hop]]) -> FloatArray:
    """Earliest time a message created at the lander at each ``t`` reaches Earth."""
    best = direct.send(t) + direct.owlt_s
    for up, down in relays:
        at_relay = up.send(t) + up.owlt_s
        best = np.minimum(best, down.send(at_relay) + down.owlt_s)
    return np.asarray(best, dtype=np.float64)


def longest_wait(
    direct: Hop, relays: list[tuple[Hop, Hop]], t0: float, t1: float
) -> tuple[float, float, bool]:
    """``(wait_s, created_at, open)``: the longest a message created in ``[t0, t1]`` waits.

    The wait ``A(t) - t`` falls or stays level between the instants the
    earliest arrival jumps: when a link from the lander closes, or when a
    message would reach a relay just after its link down closes. Only those
    instants (and ``t0``) are tried, so the answer is exact. ``open``: a
    message created then is not delivered inside the dates (a lower bound).
    """
    cand = [np.array([t0]), direct.ends]
    for up, down in relays:
        cand += [up.ends, down.ends - up.owlt_s]
    ts = np.unique(np.concatenate(cand))
    ts = ts[(ts >= t0) & (ts <= t1)]
    arr = earliest_arrival(ts, direct, relays)
    cut = ~np.isfinite(arr)
    wait = np.where(cut, t1 - ts, arr - ts)
    k = int(np.argmax(wait))
    return float(wait[k]), float(ts[k]), bool(cut[k]) and float(wait[k]) > 0.0


# ---------------------------------------------------------------------------
# The numbers, per point of the sweep
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CellNumbers:
    """Contact numbers for one node and phase of every relay (seconds)."""

    via_s: list[float]  # per relay: lander -> relay -> Earth at the same time
    via_any_s: float  # through any relay
    adds_s: list[float]  # per relay: time it adds to direct contact
    either_s: float
    unheard_s: float
    unheard_open: bool
    wait_s: float
    wait_open: bool
    wait_at_s: float


def cell_numbers(
    t1: float,
    earth_up: list[Run],
    heard_any: list[Run],
    direct_owlt_s: float,
    relay_links: list[RelayLinks],
) -> CellNumbers:
    """The Contact numbers with relays in the graph, for one point of the sweep.

    ``earth_up`` is Earth above the skyline (direct contact, as ``direct_h``);
    ``heard_any`` is a station hearing the lander directly. Through a relay:
    ``via`` is the relay in view of the lander and of Earth at once (as
    ``direct_h``, geometry only); "heard" through it is the relay in view of
    the lander and heard by a station at once, and a message may also wait
    at the relay for a station.
    """
    direct_s = intervals.total(earth_up, True)
    vias = [intervals.both(rl.lander_relay, rl.relay_earth) for rl in relay_links]
    via_s = [intervals.total(v, True) for v in vias]
    adds_s = [intervals.total(intervals.union(earth_up, v), True) - direct_s for v in vias]
    either = intervals.any_of([earth_up, *vias])
    bent = [intervals.both(rl.lander_relay, rl.relay_station) for rl in relay_links]
    heard = intervals.any_of([heard_any, *bent])
    unheard_s, unheard_open = Stretches(heard, 0.0, t1).longest(False)
    wait_s, wait_at, wait_open = longest_wait(
        Hop.of(heard_any, direct_owlt_s),
        [
            (
                Hop.of(rl.lander_relay, rl.lander_relay_owlt_s),
                Hop.of(rl.relay_station, rl.relay_station_owlt_s),
            )
            for rl in relay_links
        ],
        0.0,
        t1,
    )
    return CellNumbers(
        via_s=via_s,
        via_any_s=intervals.total(intervals.any_of(vias), True),
        adds_s=[max(0.0, a) for a in adds_s],
        either_s=intervals.total(either, True),
        unheard_s=unheard_s,
        unheard_open=unheard_open,
        wait_s=wait_s,
        wait_open=wait_open,
        wait_at_s=wait_at,
    )


def grid(n_node: int = NODE_STEPS, n_phase: int = PHASE_STEPS) -> list[tuple[float, float]]:
    """The node and phase pairs swept, in degrees: ``n_node x n_phase`` evenly spaced."""
    return [
        (360.0 * i / n_node, 360.0 * j / n_phase) for i in range(n_node) for j in range(n_phase)
    ]


@dataclass(frozen=True, slots=True)
class Spread:
    """A number over the sweep: the middle value and both ends."""

    median: float
    lo: float
    hi: float
    open: bool  # some point of the sweep was cut short by the dates

    @classmethod
    def of(cls, values: list[float], opens: list[bool] | None = None) -> Spread:
        a = np.asarray(values, dtype=np.float64)
        return cls(float(np.median(a)), float(a.min()), float(a.max()), bool(opens and any(opens)))
