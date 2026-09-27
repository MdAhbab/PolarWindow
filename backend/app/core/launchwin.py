"""Daily launch instants (T2, D1). Pure.

A launch vehicle climbs in the inertial plane that contains the pad at
liftoff, coasts in a circular parking orbit and fires for the Moon (trans-lunar
injection, TLI) at a point fixed by the transfer. With ``p`` the pad's
direction at liftoff ``T0`` and ``r`` the TLI point's, the plane is the one
through both, and the stage must cover the angle ``u(p -> r)`` along it in
the time ``t_TLI - T0``:

    u(p -> r) - n (t_TLI - T0) = c

``n`` is the parking orbit's mean motion and ``c`` the angle an ascent falls
behind a circular orbit that started at the pad: one number per vehicle,
measured from its flown lunar launches (Falcon 9 from LC-39A: -18.2, -17.5
and -17.1 degrees for IM-1, IM-2 and Blue Ghost 1). Solved for ``T0`` this
is well conditioned: a degree of error in ``c`` moves ``T0`` by about 15 s.

The plan's first formulation, the instant the pad crosses the plane of the
flown trajectory, is ill conditioned for these launches: all three flew
nearly due east (plane inclined within 0.2 degrees of the pad's latitude for
IM-1 and IM-2), the pad sat 0.05 to 0.6 degrees off that plane at liftoff
(the ascent or TLI steered), and a few hundredths of a degree there move the
crossing by ten minutes. docs/validation.md records both.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

import numpy as np
import numpy.typing as npt
from scipy.optimize import brentq

from app.core.vec import east_north, rotate, unit

FloatArray = npt.NDArray[np.float64]

OMEGA_EARTH: Final[float] = 7.292115e-5
WGS84_A: Final[float] = 6_378_137.0
WGS84_F: Final[float] = 1.0 / 298.257223563
TWO_PI: Final[float] = 2.0 * math.pi


def pad_itrf(lat_deg: float, lon_deg: float, height_m: float = 0.0) -> FloatArray:
    """ITRF93 position of a pad from WGS84 geodetic coordinates, metres."""
    e2 = WGS84_F * (2.0 - WGS84_F)
    la, lo = math.radians(lat_deg), math.radians(lon_deg)
    n = WGS84_A / math.sqrt(1.0 - e2 * math.sin(la) ** 2)
    return np.array(
        [
            (n + height_m) * math.cos(la) * math.cos(lo),
            (n + height_m) * math.cos(la) * math.sin(lo),
            (n * (1.0 - e2) + height_m) * math.sin(la),
        ]
    )


def plane_normal(p_hat: FloatArray, r_hat: FloatArray) -> FloatArray:
    """Normal of the eastward-moving plane through the pad and the TLI point."""
    h = unit(np.cross(p_hat, r_hat))
    return h if h[2] >= 0.0 else -h


def angle_along(p_hat: FloatArray, r_hat: FloatArray, h_hat: FloatArray) -> float:
    """Angle from ``p`` to ``r`` measured forward along the orbit with normal ``h``, [0, 2pi)."""
    ang = math.atan2(float(np.dot(np.cross(p_hat, r_hat), h_hat)), float(np.dot(p_hat, r_hat)))
    return ang % TWO_PI


def wrap(x: float) -> float:
    """To (-pi, pi]."""
    return (x + math.pi) % TWO_PI - math.pi


@dataclass(frozen=True, slots=True)
class Ascent:
    """A vehicle's climb and parking coast, measured from its flown lunar launches."""

    c_rad: float  # ascent angle constant, see the module docstring
    tau_s: float  # liftoff to TLI
    r_park_m: float  # parking orbit radius

    def n(self, gm_earth: float) -> float:
        return math.sqrt(gm_earth / self.r_park_m**3)


def residual(
    t0: float,
    pad_at: Callable[[float], FloatArray],
    tli_at: Callable[[float], tuple[FloatArray, float]],
    c_rad: float,
    n: float,
) -> float:
    """``u(p -> r) - n (t_TLI - T0) - c``, wrapped; zero at a launch instant."""
    p = unit(pad_at(t0))
    r_hat, t_tli = tli_at(t0)
    h = plane_normal(p, r_hat)
    return wrap(angle_along(p, r_hat, h) - n * (t_tli - t0) - c_rad)


def roots(
    f: Callable[[float], float], t_lo: float, t_hi: float, step_s: float = 300.0
) -> list[float]:
    """Sign changes of a wrapped residual in ``[t_lo, t_hi]`` that are crossings, not wraps."""
    ts = np.arange(t_lo, t_hi + step_s, step_s)
    vals = [f(float(t)) for t in ts]
    out: list[float] = []
    for i in range(len(ts) - 1):
        a, b = vals[i], vals[i + 1]
        if a == 0.0:
            out.append(float(ts[i]))
        elif a * b < 0.0 and abs(a - b) < math.pi:
            out.append(float(brentq(f, float(ts[i]), float(ts[i + 1]), xtol=1e-3)))
    return out


def azimuth_deg(
    p_itrf_hat: FloatArray, h_itrf: FloatArray, v_park: float, r_pad_m: float
) -> tuple[float, float]:
    """Inertial and Earth-relative launch azimuth (deg from north), in the Earth-fixed frame."""
    up = unit(p_itrf_hat)
    east, north = east_north(up)
    d = unit(np.cross(h_itrf, up))  # direction of motion at the pad
    az_i = math.degrees(math.atan2(float(d @ east), float(d @ north))) % 360.0
    v_rel = v_park * d - OMEGA_EARTH * np.cross([0.0, 0.0, 1.0], up * r_pad_m)
    az_r = math.degrees(math.atan2(float(v_rel @ east), float(v_rel @ north))) % 360.0
    return az_i, az_r


def due_east_gap(p_hat: FloatArray, target_hat: FloatArray) -> float:
    """``target . north`` at the pad: zero when a due-east climb's plane holds ``target``."""
    return float(target_hat @ east_north(p_hat)[1])


def climb_plane(p_hat: FloatArray, azimuth_deg: float) -> FloatArray:
    """Normal of the plane a vehicle climbs in from ``p`` at an inertial azimuth."""
    east, north = east_north(p_hat)
    a = math.radians(azimuth_deg)
    return unit(np.cross(p_hat, math.cos(a) * north + math.sin(a) * east))


__all__ = [
    "Ascent",
    "angle_along",
    "azimuth_deg",
    "climb_plane",
    "due_east_gap",
    "pad_itrf",
    "plane_normal",
    "residual",
    "roots",
    "rotate",
    "unit",
    "wrap",
]
