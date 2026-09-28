"""A capsule's fall from the entry interface to the ground, and where it lands (track H).

Wraps ``core.entry`` with the Earth's orientation from SPICE (the true pole at
the entry time, and ITRF93 to turn the landing point into latitude and
longitude), and the words that go with the numbers.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

import numpy as np
import numpy.typing as npt

from app.core import entry, forces, spice

FloatArray = npt.NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class Landing:
    lat_deg: float
    lon_deg: float
    et: float
    duration_s: float
    peak_g: float
    landed: bool


def pole_at(et: float) -> FloatArray:
    """The Earth's true pole (ITRF93 z) in J2000 at ``et``."""
    rot = spice.rotations("ITRF93", "J2000", np.array([et]))[0]
    return np.asarray(rot @ np.array([0.0, 0.0, 1.0]), dtype=np.float64)


def to_ground(et: float, r_j2000_m: FloatArray) -> tuple[float, float, float]:
    """Geodetic latitude, longitude (deg) and height (m) of a J2000 position at ``et``."""
    rot = spice.rotations("J2000", "ITRF93", np.array([et]))[0]
    return forces.geodetic(np.asarray(rot @ r_j2000_m, dtype=np.float64))


def land(
    et0: float,
    r0_m: FloatArray,
    v0_m_s: FloatArray,
    capsule: entry.Capsule,
    ground_m: float,
) -> Landing:
    pole = pole_at(et0)
    fl = entry.fly(r0_m, v0_m_s, pole, capsule, ground_m)
    et1 = et0 + fl.duration_s
    lat, lon, _ = to_ground(et1, fl.r_m[-1])
    return Landing(lat, lon, et1, fl.duration_s, fl.peak_deceleration_g(pole, capsule), fl.landed)


def footprint(
    et0: float,
    r0_m: FloatArray,
    v0_m_s: FloatArray,
    capsule: entry.Capsule,
    spread: entry.Spread,
    ground_m: float,
    runs: int = 200,
) -> list[Landing]:
    pole = pole_at(et0)
    out = []
    for fl in entry.footprint(r0_m, v0_m_s, pole, capsule, spread, ground_m=ground_m, runs=runs):
        et1 = et0 + fl.duration_s
        lat, lon, _ = to_ground(et1, fl.r_m[-1])
        out.append(Landing(lat, lon, et1, fl.duration_s, 0.0, fl.landed))
    return out


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    c = math.sin(p1) * math.sin(p2) + math.cos(p1) * math.cos(p2) * math.cos(dl)
    return 6371.0 * math.acos(max(-1.0, min(1.0, c)))


def local_km(lat0: float, lon0: float, lat: float, lon: float) -> tuple[float, float]:
    """(east, north) km of a point from a reference, on a local plane."""
    north = math.radians(lat - lat0) * 6371.0
    east = math.radians(lon - lon0) * 6371.0 * math.cos(math.radians(lat0))
    return east, north


def entry_state(r_m: FloatArray, v_m_s: FloatArray, et: float) -> dict[str, float]:
    """The entry state in the terms mission teams publish: inertial flight path angle and
    heading, Earth-relative speed, geocentric latitude and longitude."""
    up = r_m / np.linalg.norm(r_m)
    pole = pole_at(et)
    z_j2000 = np.array([0.0, 0.0, 1.0])
    east = np.cross(z_j2000, up)
    east /= np.linalg.norm(east)
    north = np.cross(up, east)
    heading = math.degrees(math.atan2(float(np.dot(v_m_s, east)), float(np.dot(v_m_s, north))))
    rot = spice.rotations("J2000", "ITRF93", np.array([et]))[0]
    r_f = rot @ r_m
    v_rel = v_m_s - np.cross(entry.OMEGA_EARTH * pole, r_m)
    return {
        "radius_km": float(np.linalg.norm(r_m)) / 1000.0,
        "fpa_j2000_deg": entry.flight_path_angle_deg(r_m, v_m_s),
        "heading_j2000_deg": heading % 360.0,
        "speed_ecef_km_s": float(np.linalg.norm(v_rel)) / 1000.0,
        "lat_geocentric_deg": math.degrees(math.asin(float(r_f[2]) / float(np.linalg.norm(r_f)))),
        "lon_deg": math.degrees(math.atan2(float(r_f[1]), float(r_f[0]))) % 360.0,
    }


def utc(et: float) -> datetime:
    from app.services import lifecycle

    return lifecycle.parse_time(spice.et_to_utc(et))
