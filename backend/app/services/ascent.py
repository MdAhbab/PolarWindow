"""What each launch vehicle's flown lunar launches say about its climb (T2, D1).

From NASA's reconstructed trajectories of the flown CLPS landers, each
launch's TLI time and point, parking orbit and ascent constant are measured
(``core.flown``). A vehicle's constant for a new launch is the mean over its
flights; checked by leaving each flight out in turn and predicting its
liftoff from the others (``hold_one_out``). Synchronous: call on the SPICE
thread (``spice.run_async``).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import numpy as np

from app.config import get_settings
from app.core import flown, launchwin, propagate, spice
from app.core.flown import FlownLaunch
from app.core.vec import unit
from app.data import catalogues, registry

#: Flown CLPS missions with a reconstructed trajectory: registry id and NAIF id.
RECONSTRUCTED: dict[str, tuple[str, int]] = {
    "peregrine-m1": ("clps:peregrine_cruise", -244),
    "im-1": ("clps:im1_cruise", -370011),
    "blue-ghost-m1": ("clps:bgm1_cruise", -2711),
    "im-2": ("clps:im2_cruise", -370021),
}


@dataclass(frozen=True, slots=True)
class Flight:
    mission_id: str
    vehicle_id: str
    pad_id: str
    t0_et: float  # published liftoff
    launch: FlownLaunch


@dataclass(frozen=True, slots=True)
class Ascent:
    """A vehicle's climb for a new launch: the mean over its flights."""

    vehicle_id: str
    c_rad: float
    r_park_m: float
    coasts_s: tuple[float, ...]
    flights: tuple[str, ...]
    #: Liftoff predicted from the other flights minus the published one, per flight (s).
    hold_one_out_s: dict[str, float]


def pad_j2000(pad_id: str) -> Any:
    """``t -> J2000 position of the pad`` (m)."""
    site = catalogues.load("launch_sites").get(pad_id)
    if site.lat_deg is None or site.lon_deg is None:
        raise ValueError(f"the coordinates of {site.name} are not published")
    itrf = launchwin.pad_itrf(site.lat_deg, site.lon_deg)

    def at(t: float) -> Any:
        return spice.rotations(spice.ITRF93, spice.J2000, np.array([t]))[0] @ itrf

    return at


def spk_path(mission_id: str) -> Any:
    ds = registry.by_id(RECONSTRUCTED[mission_id][0])
    return get_settings().data_dir / ds.dest


def coverage(mission_id: str) -> list[tuple[float, float]]:
    path = spk_path(mission_id)
    spice.load_extra([path])
    return spice.coverage(path, RECONSTRUCTED[mission_id][1])


def states_of(mission_id: str) -> Any:
    naif = str(RECONSTRUCTED[mission_id][1])

    def at(ets: Any) -> Any:
        return spice.states(naif, "EARTH", spice.J2000, "NONE", np.atleast_1d(ets))

    return at


@lru_cache(maxsize=8)
def measure(flights: tuple[tuple[str, str, str, str], ...]) -> dict[str, Flight]:
    """``flights``: ``(mission_id, vehicle_id, pad_id, published liftoff ISO)``; the ones
    whose reconstruction is on disk are measured."""
    out: dict[str, Flight] = {}
    for mid, vid, pad_id, t0_iso in flights:
        if mid not in RECONSTRUCTED or not spk_path(mid).exists():
            continue
        cov = coverage(mid)
        t0 = spice.utc_to_et(t0_iso.replace("Z", ""))
        tables = propagate.environment(t0 - 3600.0, cov[-1][1] + 4 * 86_400.0)
        f = flown.measure(tables, states_of(mid), cov, t0, pad_j2000(pad_id))
        out[mid] = Flight(mid, vid, pad_id, t0, f)
    return out


def liftoff_from(f: FlownLaunch, pad_at: Any, c_rad: float, gm_earth: float) -> float | None:
    """The liftoff that puts a climb with constant ``c`` onto this TLI (D1 from a flown TLI)."""
    n = math.sqrt(gm_earth / f.r_park_m**3)
    period = 2.0 * math.pi / n
    r_hat = unit(f.r_tli)

    def res(t: float) -> float:
        return launchwin.residual(t, pad_at, lambda _t: (r_hat, f.t_tli), c_rad, n)

    # A coast from ten minutes to one parking orbit more: one root.
    found = launchwin.roots(res, f.t_tli - 600.0 - period, f.t_tli - 600.0, step_s=120.0)
    return found[-1] if found else None


def ascent(vehicle_id: str, flights: dict[str, Flight], gm_earth: float) -> Ascent | None:
    mine = [f for f in flights.values() if f.vehicle_id == vehicle_id]
    if not mine:
        return None
    hold: dict[str, float] = {}
    if len(mine) > 1:
        for f in mine:
            others = [o.launch.c_rad for o in mine if o.mission_id != f.mission_id]
            t = liftoff_from(f.launch, pad_j2000(f.pad_id), float(np.mean(others)), gm_earth)
            if t is not None:
                hold[f.mission_id] = t - f.t0_et
    return Ascent(
        vehicle_id=vehicle_id,
        c_rad=float(np.mean([f.launch.c_rad for f in mine])),
        r_park_m=float(np.mean([f.launch.r_park_m for f in mine])),
        coasts_s=tuple(f.launch.tau_s for f in mine),
        flights=tuple(f.mission_id for f in mine),
        hold_one_out_s=hold,
    )


def gm_earth() -> float:
    return spice.gm_m3_s2("EARTH")
