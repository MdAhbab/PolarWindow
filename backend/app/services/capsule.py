"""A capsule's fall from the entry interface to the ground, and where it lands (track H).

Wraps ``core.entry`` with the Earth's orientation from SPICE (the true pole at
the entry time, and ITRF93 to turn the landing point into latitude and
longitude), the air of the entry day (NRLMSIS 2.1 from that day's solar flux
and geomagnetic activity, the U.S. Standard Atmosphere 1976 when those are not
on disk), and the words that go with the numbers.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import numpy as np
import numpy.typing as npt

from app.core import entry, forces, spice
from app.data import msis_indices

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


STANDARD_NAME = "U.S. Standard Atmosphere 1976"
#: The empirical models the capsule can fly through: name -> pymsis ``version``.
MSIS_VERSIONS: dict[str, float] = {"NRLMSISE-00": 0, "NRLMSIS 2.1": 2.1}
#: The model the entry day's air comes from. Chosen by how near each model's density and
#: temperature came to air measured between 30 and 70 km, where a capsule loses its speed
#: (TIMED/SABER's profiles of the day and a Rayleigh lidar's nights beside it), by a rule that
#: uses no landing (``tests.golden.capsule_air``, docs/validation.md): NRLMSISE-00 is 4 to 7 %
#: too dense at 45 to 70 km in both, NRLMSIS 2.1 within 3 %. The low-orbit drag model
#: (``core.forces``) stays on NRLMSISE-00; this constant does not touch it.
DEFAULT_MODEL = "NRLMSIS 2.1"


@dataclass(frozen=True, slots=True)
class Atmosphere:
    """The air a flight goes through and what the day gave it."""

    name: str
    #: Density along a flight (``entry.Air``); None: the U.S. Standard Atmosphere 1976.
    air: entry.Air | None
    #: The 10.7 cm flux of the day before, its 81-day mean and the 3-hour ap at the time.
    f107_sfu: float | None = None
    f107_mean_sfu: float | None = None
    ap_3h: float | None = None
    #: The OMNI files the numbers were read from.
    files: tuple[str, ...] = ()
    #: Why the standard atmosphere stands in for the day's, when it does.
    fallback_reason: str | None = None


def standard(fallback_reason: str | None = None) -> Atmosphere:
    return Atmosphere(STANDARD_NAME, None, fallback_reason=fallback_reason)


def msis_column(
    when: datetime,
    lat_deg: float,
    lon_deg: float,
    h_m: FloatArray,
    f107: float,
    f107a: float,
    ap: tuple[float, ...],
    version: float = 0,
) -> tuple[FloatArray, FloatArray]:
    """(total mass density kg/m^3, temperature K) at the heights ``h_m`` (geodetic) of one
    place and time (UTC), from NRLMSISE-00 (``version`` 0) or NRLMSIS 2.x, for the given solar
    flux and geomagnetic activity (``data.msis_indices``; ap in the storm-time mode, which takes
    the 3-hour values)."""
    from pymsis import msis  # imported here: only the capsule check needs it

    out = msis.calculate(
        np.datetime64(when.astimezone(UTC).replace(tzinfo=None), "ms"),
        lon_deg,
        lat_deg,
        np.asarray(h_m, dtype=np.float64) / 1000.0,
        [f107],
        [f107a],
        [list(ap)],
        version=version,
        geomagnetic_activity=-1,
    )
    cols = np.asarray(out, dtype=np.float64).reshape(-1, 11)
    return cols[:, 0], cols[:, 10]


def msis_density(
    when: datetime,
    lat_deg: float,
    lon_deg: float,
    h_m: float,
    f107: float,
    f107a: float,
    ap: tuple[float, ...],
    version: float = 0,
) -> float:
    """``msis_column``'s density at one height, kg/m^3."""
    rho, _ = msis_column(when, lat_deg, lon_deg, np.array([h_m]), f107, f107a, ap, version)
    return float(rho[0])


def msis_air(
    t0: datetime,
    rot0: FloatArray,
    f107: float,
    f107a: float,
    ap: tuple[float, ...],
    version: float = 0,
) -> entry.Air:
    """``msis_density`` along a flight that starts at ``t0`` (UTC) with the Earth oriented by
    ``rot0`` (J2000 to ITRF93). The Earth turns at its mean rate from ``rot0``: over a
    capsule's ten minutes precession and nutation move the ground by millimetres."""

    def air(t_s: float, r: FloatArray, h: float) -> float:
        c, s = math.cos(entry.OMEGA_EARTH * t_s), math.sin(entry.OMEGA_EARTH * t_s)
        x = rot0 @ r
        lat, lon, _ = forces.geodetic(np.array([c * x[0] + s * x[1], c * x[1] - s * x[0], x[2]]))
        when = t0 + timedelta(milliseconds=int(t_s * 1000.0))
        return msis_density(when, lat, lon, h, f107, f107a, ap, version)

    return air


def day_atmosphere(et0: float, model: str = DEFAULT_MODEL) -> Atmosphere:
    """The air of the entry day: ``model`` (NRLMSIS 2.1 unless another is asked for) driven by
    that day's solar flux and geomagnetic activity from the OMNI files on disk, or the U.S.
    Standard Atmosphere 1976 (with the reason) when the files lack them."""
    when = utc(et0)
    ix = msis_indices.at(when)
    if ix is None:
        return standard(
            f"the OMNI files on disk have no solar flux or geomagnetic activity for "
            f"{when:%d %B %Y}"
        )
    rot0 = spice.rotations("J2000", "ITRF93", np.array([et0]))[0]
    air = msis_air(when, rot0, ix.f107, ix.f107a, ix.ap, MSIS_VERSIONS[model])
    return Atmosphere(model, air, ix.f107, ix.f107a, ix.ap[1], ix.files)


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
