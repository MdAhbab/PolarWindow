"""Capsule entry to the ground: 3-DOF ballistic flight (plan track H).

A point mass with a ballistic coefficient beta = m / (C_D A), falling from the
entry interface through an atmosphere that turns with the Earth, under Earth's
gravity with J2. The air is the U.S. Standard Atmosphere 1976
(``core.atmosphere``) unless the caller gives a density (``Capsule.air``: the
capsule service gives an empirical model's for the entry day). No lift and no
parachutes: the plan asks for beta as the input, and for a blunt capsule the
parachutes change the landing point little (the OSIRIS-REx team found its
no-parachute touchdown within 100 m of the nominal one). A wind, when given, is
one horizontal vector below 30 km, where the capsule is slow enough for it to
matter. Integrated in an
inertial frame whose z axis is the Earth's true pole at the entry time, until
the height above the WGS84 ellipsoid reaches the ground's.

``footprint`` runs the same flight many times from dispersed entry states,
ballistic coefficients and air densities (a seeded Monte Carlo) and gives the
landing points.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
from scipy.integrate import solve_ivp

from app.core import atmosphere

FloatArray = npt.NDArray[np.float64]

MU_EARTH = 3.986004418e14  # m^3/s^2 (EGM96 / WGS84)
J2 = 1.08262668e-3
R_EQ = 6_378_137.0
F_WGS84 = 1.0 / 298.257223563
OMEGA_EARTH = 7.292115e-5  # rad/s
#: The height of the entry interface the plan names (400,000 ft).
EI_HEIGHT_M = 121_920.0
#: A given wind blows below this height.
WIND_TOP_M = 30_000.0
#: The integrator's tolerances. The empirical models give their density as single-precision
#: numbers (noise of 1e-7 relative in NRLMSISE-00, 2e-6 in NRLMSIS 2.1), and an eighth-order
#: integrator asked for 1e-9 spends six times the steps following that noise, for nothing:
#: at these the landing point is within 0.5 m of the landing at tolerances ten times tighter
#: and a hundred times looser (OSIRIS-REx case; NRLMSIS 2.1 moves 0.02 m and 0.04 m, NRLMSISE-00
#: 0.00 m and 0.5 m, the standard atmosphere 0.00 m and 0.04 m), and a flight in NRLMSIS 2.1
#: takes one second, not thirteen.
RTOL = 1e-8
ATOL = 1e-5

#: Air density (kg/m^3) at (seconds from the entry state, inertial position, height
#: above WGS84).
Air = Callable[[float, FloatArray, float], float]


def geodetic_height(r: FloatArray, pole: FloatArray) -> tuple[float, float]:
    """(height above WGS84, geodetic latitude in rad) of an inertial position whose
    frame has ``pole`` as the Earth's axis. Longitude is not needed for either."""
    z = float(np.dot(r, pole))
    p = float(np.linalg.norm(r - z * pole))
    e2 = F_WGS84 * (2 - F_WGS84)
    lat = math.atan2(z, p * (1 - e2))
    h = 0.0
    for _ in range(6):
        n = R_EQ / math.sqrt(1 - e2 * math.sin(lat) ** 2)
        h = p / math.cos(lat) - n if abs(lat) < 1.4 else z / math.sin(lat) - n * (1 - e2)
        lat = math.atan2(z, p * (1 - e2 * n / (n + h)))
    return h, lat


@dataclass(frozen=True, slots=True)
class Capsule:
    beta_kg_m2: float
    #: Multiplies the atmosphere's density (1 = as the atmosphere gives it).
    density_scale: float = 1.0
    #: Wind below ``WIND_TOP_M``, (east, north) m/s.
    wind_en_m_s: tuple[float, float] = (0.0, 0.0)
    #: The atmosphere; None: the U.S. Standard Atmosphere 1976.
    air: Air | None = None

    def density(self, t_s: float, r: FloatArray, h: float) -> float:
        rho = self.air(t_s, r, h) if self.air else atmosphere.density(h)
        return rho * self.density_scale


@dataclass(frozen=True, slots=True)
class Flight:
    t_s: FloatArray  # seconds from the entry state
    r_m: FloatArray  # (n, 3) inertial position
    v_m_s: FloatArray  # (n, 3) inertial velocity
    height_m: FloatArray
    landed: bool

    @property
    def duration_s(self) -> float:
        return float(self.t_s[-1])

    def peak_deceleration_g(self, pole: FloatArray, capsule: Capsule) -> float:
        best = 0.0
        for t, r, v, h in zip(self.t_s, self.r_m, self.v_m_s, self.height_m, strict=True):
            vr = _air_relative(r, v, float(h), pole, capsule)
            rho = capsule.density(float(t), r, max(float(h), 0.0))
            best = max(best, 0.5 * rho * float(np.dot(vr, vr)) / capsule.beta_kg_m2)
        return best / 9.80665


def _air_relative(
    r: FloatArray, v: FloatArray, h: float, pole: FloatArray, capsule: Capsule
) -> FloatArray:
    """The velocity through the air: less the Earth's turn and, low down, the wind."""
    vr = v - np.cross(OMEGA_EARTH * pole, r)
    we, wn = capsule.wind_en_m_s
    if (we or wn) and h < WIND_TOP_M:
        east = np.cross(pole, r)
        east /= np.linalg.norm(east)
        north = np.cross(r / np.linalg.norm(r), east)
        vr = vr - we * east - wn * north
    return np.asarray(vr, dtype=np.float64)


def _accel(
    t: float, r: FloatArray, v: FloatArray, pole: FloatArray, capsule: Capsule
) -> FloatArray:
    rn = float(np.linalg.norm(r))
    z = float(np.dot(r, pole))
    # Point mass plus J2 about the true pole.
    k = 1.5 * J2 * MU_EARTH * R_EQ**2 / rn**5
    zr = z / rn
    a = -MU_EARTH * r / rn**3 + k * ((5 * zr**2 - 1) * r - 2 * z * pole)
    h, _ = geodetic_height(r, pole)
    rho = capsule.density(t, r, max(h, 0.0))
    if rho > 0.0:
        vr = _air_relative(r, v, h, pole, capsule)
        a = a - 0.5 * rho * float(np.linalg.norm(vr)) * vr / capsule.beta_kg_m2
    return np.asarray(a, dtype=np.float64)


def fly(
    r0_m: FloatArray,
    v0_m_s: FloatArray,
    pole: FloatArray,
    capsule: Capsule,
    ground_m: float = 0.0,
    *,
    max_s: float = 3600.0,
) -> Flight:
    """From an inertial entry state down to ``ground_m`` above the ellipsoid."""
    pole = np.asarray(pole, dtype=np.float64) / np.linalg.norm(pole)

    def rhs(t: float, y: FloatArray) -> FloatArray:
        return np.concatenate([y[3:], _accel(t, y[:3], y[3:], pole, capsule)])

    def ground(_t: float, y: FloatArray) -> float:
        return geodetic_height(y[:3], pole)[0] - ground_m

    ground.terminal = True  # type: ignore[attr-defined]
    ground.direction = -1  # type: ignore[attr-defined]
    sol = solve_ivp(
        rhs,
        (0.0, max_s),
        np.concatenate([r0_m, v0_m_s]),
        method="DOP853",
        rtol=RTOL,
        atol=ATOL,
        events=ground,
        max_step=2.0,
    )
    ys = sol.y.T
    landed = bool(sol.t_events[0].size)
    if landed:
        ys = np.vstack([ys, sol.y_events[0][0]])
        ts = np.concatenate([sol.t, sol.t_events[0][:1]])
    else:
        ts = sol.t
    hs = np.array([geodetic_height(y[:3], pole)[0] for y in ys])
    return Flight(t_s=ts, r_m=ys[:, :3], v_m_s=ys[:, 3:], height_m=hs, landed=landed)


def flight_path_angle_deg(r: FloatArray, v: FloatArray) -> float:
    return math.degrees(math.asin(float(np.dot(r, v)) / (np.linalg.norm(r) * np.linalg.norm(v))))


def rotate_about(vec: FloatArray, axis: FloatArray, angle_rad: float) -> FloatArray:
    axis = axis / np.linalg.norm(axis)
    c, s = math.cos(angle_rad), math.sin(angle_rad)
    return np.asarray(
        vec * c + np.cross(axis, vec) * s + axis * float(np.dot(axis, vec)) * (1 - c),
        dtype=np.float64,
    )


def disperse(
    r0: FloatArray,
    v0: FloatArray,
    d_fpa_deg: float,
    d_heading_deg: float,
    d_speed_frac: float,
) -> tuple[FloatArray, FloatArray]:
    """The entry state with its flight path angle, heading and speed changed by the given
    amounts (position kept): the angles are rotations of the velocity about the local
    horizontal normal to it and about the local vertical."""
    up = r0 / np.linalg.norm(r0)
    side = np.cross(up, v0)
    side /= np.linalg.norm(side)
    v = rotate_about(v0, side, -math.radians(d_fpa_deg))
    v = rotate_about(v, up, -math.radians(d_heading_deg))
    return r0, v * (1.0 + d_speed_frac)


@dataclass(frozen=True, slots=True)
class Spread:
    """One-sigma dispersions for the footprint (all assumed unless a source is given)."""

    fpa_deg: float
    heading_deg: float
    speed_frac: float
    beta_frac: float
    density_frac: float
    #: Each horizontal component of the wind below 30 km.
    wind_m_s: float = 0.0


def footprint(
    r0: FloatArray,
    v0: FloatArray,
    pole: FloatArray,
    capsule: Capsule,
    spread: Spread,
    *,
    ground_m: float = 0.0,
    runs: int = 200,
    seed: int = 20230924,
) -> list[Flight]:
    """Seeded Monte Carlo of the landing: each run draws normal dispersions of the entry
    flight path angle, heading and speed, the ballistic coefficient, the density and the
    low wind (about the given capsule's own wind)."""
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(runs):
        dr = rng.standard_normal(7)
        r, v = disperse(
            r0,
            v0,
            dr[0] * spread.fpa_deg,
            dr[1] * spread.heading_deg,
            dr[2] * spread.speed_frac,
        )
        cap = Capsule(
            beta_kg_m2=capsule.beta_kg_m2 * (1 + dr[3] * spread.beta_frac),
            density_scale=capsule.density_scale * max(0.1, 1 + dr[4] * spread.density_frac),
            wind_en_m_s=(
                capsule.wind_en_m_s[0] + dr[5] * spread.wind_m_s,
                capsule.wind_en_m_s[1] + dr[6] * spread.wind_m_s,
            ),
            air=capsule.air,
        )
        out.append(fly(r, v, pole, cap, ground_m))
    return out


def ellipse_km(east_km: FloatArray, north_km: FloatArray, p: float = 0.99) -> dict[str, float]:
    """Centre, semi-axes and orientation (deg from north) of the ``p`` ellipse of points
    on a local plane, from their covariance (taken as normal)."""
    e = np.asarray(east_km)
    n = np.asarray(north_km)
    cov = np.cov(np.vstack([e, n]))
    vals, vecs = np.linalg.eigh(cov)
    k = math.sqrt(-2.0 * math.log(1.0 - p))  # chi-square with 2 degrees of freedom
    major = vecs[:, 1]
    return {
        "east_km": float(np.mean(e)),
        "north_km": float(np.mean(n)),
        "semi_major_km": k * math.sqrt(max(vals[1], 0.0)),
        "semi_minor_km": k * math.sqrt(max(vals[0], 0.0)),
        "azimuth_deg": math.degrees(math.atan2(major[0], major[1])) % 180.0,
    }
