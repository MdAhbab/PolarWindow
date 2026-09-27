"""Accelerations on a spacecraft between the Earth and the Moon (T2, C1). Pure.

Frame J2000 (ICRF axes), time TDB seconds past J2000 (SPICE ET), SI units.
The integration origin C is the Earth or the Moon. With ``r`` the spacecraft
relative to C and ``p_B`` each body relative to C,

    a = sum_B g_B(r - p_B) - sum_{B != C} g_B(-p_B)

where ``g_B`` is body B's gravity (point mass, plus its harmonics where they
are switched on). The second sum is the acceleration of the origin itself, so
the frame is the non-rotating one that moves with C, and a lunar orbit can be
integrated about the Moon without the Earth-centred round-off.

Bodies and fields:

* Earth: point mass plus zonal terms J2..J6 (EGM2008, tide-free; Pavlis et al.,
  *JGR* 117, B04406, 2012) in ITRF93, whose pole the EOP kernel supplies.
* Moon: point mass plus GRGM1200A (Lemoine et al., *GRL* 41, 2014) in
  MOON_PA, switched on within ``moon_sh_within_m`` of the Moon's centre.
* Sun: point mass. GMs are DE440's (``gm_de440.tpc``).
* Solar radiation pressure, cannonball: ``Cr A/m`` times the solar flux over
  c at the spacecraft's distance, times the visible fraction of the Sun's disc
  behind the Earth and the Moon (the disc-overlap of core.eclipse).
* Drag below 1,000 km: NRLMSISE-00 density (``pymsis``, version 0) for the
  F10.7 and Ap given, with the atmosphere turning with the Earth.

Body positions come from :class:`Tables`: SPICE states at fixed knots,
interpolated with cubic Hermite polynomials (error ``dt^4/384 |x''''|``,
about 4e-7 m for the Moon at 300 s knots). Rotations are interpolated
element-wise and linearly: 8e-8 rad for MOON_PA at 300 s, 6e-5 rad for
ITRF93, which only orients Earth's zonal terms and the atmosphere.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

import numpy as np
import numpy.typing as npt
from numba import njit

from app.core.gravity import Field, nonspherical, zonal_field

FloatArray = npt.NDArray[np.float64]

EARTH: Final[int] = 0
MOON: Final[int] = 1

#: Total solar irradiance at 1 au, W/m^2 (Kopp and Lean, GRL 38, L01706, 2011).
TSI_W_M2: Final[float] = 1360.8
C_M_S: Final[float] = 299_792_458.0
AU_M: Final[float] = 149_597_870_700.0  # IAU 2012 Resolution B2
#: Earth's rotation rate, rad/s (IERS Conventions 2010, table 1.1).
OMEGA_EARTH: Final[float] = 7.292115e-5
#: Drag is evaluated below this height above the WGS84 ellipsoid, metres.
DRAG_BELOW_M: Final[float] = 1_000_000.0
#: TT - UTC since 2017-01-01 (37 leap seconds + 32.184 s); TDB - TT < 2 ms.
TT_MINUS_UTC_S: Final[float] = 69.184

#: EGM2008 fully normalised zonal coefficients, GM and reference radius.
EGM2008_GM: Final[float] = 3.986004415e14
EGM2008_R_M: Final[float] = 6_378_136.3
EGM2008_CN0: Final[dict[int, float]] = {
    2: -0.484165143790815e-03,
    3: 0.957161207093473e-06,
    4: 0.539965866638991e-06,
    5: 0.686702913736681e-07,
    6: -0.149953927978527e-06,
}


def earth_zonal(degree: int = 6) -> Field:
    """Earth's zonal field J2..J``degree`` (EGM2008); below 2, a point mass."""
    if degree < 2:
        return Field(EGM2008_GM, EGM2008_R_M, np.ones((1, 1)), np.zeros((1, 1)), 0)
    return zonal_field(
        EGM2008_GM, EGM2008_R_M, {n: c for n, c in EGM2008_CN0.items() if n <= degree}
    )


@dataclass(frozen=True, slots=True)
class Tables:
    """Where the Sun and Moon are, and how the Moon and Earth are turned, over a span."""

    t0: float  # ET of the first knot
    dt: float  # knot spacing, s
    moon: FloatArray  # (n, 6) Moon relative to Earth, J2000, m and m/s
    sun: FloatArray  # (n, 6) Sun relative to Earth
    moon_pa: FloatArray  # (n, 3, 3) J2000 -> MOON_PA
    itrf: FloatArray  # (n, 3, 3) J2000 -> ITRF93
    gm_earth: float
    gm_moon: float
    gm_sun: float
    r_earth_m: float  # shadow spheres
    r_moon_m: float
    r_sun_m: float

    @property
    def span(self) -> tuple[float, float]:
        return self.t0, self.t0 + self.dt * (self.moon.shape[0] - 1)


@dataclass(frozen=True, slots=True)
class Drag:
    """Drag parameters. ``cd_am`` is Cd times area over mass, m^2/kg."""

    cd_am: float
    f107: float
    f107a: float
    ap: float
    #: Override the density (et, lat_deg, lon_deg, alt_m) -> kg/m^3; tests use a constant.
    density: Callable[[float, float, float, float], float] | None = None


@dataclass(frozen=True, slots=True)
class Model:
    """Which forces act. The defaults are the plan's C1 model without SRP or drag."""

    origin: int = EARTH
    moon_field: Field | None = None  # None: the Moon is a point mass
    moon_sh_within_m: float = 17_380_000.0  # ten lunar radii
    earth_field: Field | None = None  # None: J2..J6 (EGM2008); use earth_zonal(0) to switch off
    sun: bool = True
    moon: bool = True
    cr_am: float = 0.0  # Cr times area over mass, m^2/kg; 0 switches SRP off
    drag: Drag | None = None

    def earth(self) -> Field:
        return self.earth_field if self.earth_field is not None else earth_zonal()


@njit(cache=True)  # type: ignore[misc]
def _knot(t: float, t0: float, dt: float, n: int) -> tuple[int, float]:
    u = (t - t0) / dt
    i = int(math.floor(u))
    if i < 0:
        i = 0
    if i > n - 2:
        i = n - 2
    return i, u - i


@njit(cache=True)  # type: ignore[misc]
def _hermite(tab: FloatArray, i: int, s: float, dt: float) -> FloatArray:
    """Position and velocity from a cubic Hermite between knots i and i+1."""
    s2 = s * s
    s3 = s2 * s
    h00 = 2 * s3 - 3 * s2 + 1
    h10 = s3 - 2 * s2 + s
    h01 = -2 * s3 + 3 * s2
    h11 = s3 - s2
    d00 = (6 * s2 - 6 * s) / dt
    d10 = 3 * s2 - 4 * s + 1
    d01 = (-6 * s2 + 6 * s) / dt
    d11 = 3 * s2 - 2 * s
    out = np.empty(6)
    for k in range(3):
        p0, v0 = tab[i, k], tab[i, k + 3]
        p1, v1 = tab[i + 1, k], tab[i + 1, k + 3]
        out[k] = h00 * p0 + h10 * dt * v0 + h01 * p1 + h11 * dt * v1
        out[k + 3] = d00 * p0 + d10 * v0 + d01 * p1 + d11 * v1
    return out


@njit(cache=True)  # type: ignore[misc]
def _rot(tab: FloatArray, i: int, s: float) -> FloatArray:
    return (1.0 - s) * tab[i] + s * tab[i + 1]  # type: ignore[no-any-return]


@njit(cache=True)  # type: ignore[misc]
def _field_acc(
    x: FloatArray,
    rot: FloatArray,
    c: FloatArray,
    sn: FloatArray,
    gm: float,
    radius: float,
    nmax: int,
) -> FloatArray:
    bf = rot @ x
    gx, gy, gz = nonspherical(bf[0], bf[1], bf[2], c, sn, gm, radius, nmax)
    return rot.T @ np.array([gx, gy, gz])  # type: ignore[no-any-return]


@njit(cache=True)  # type: ignore[misc]
def _point(x: FloatArray, gm: float) -> FloatArray:
    r = math.sqrt(x[0] * x[0] + x[1] * x[1] + x[2] * x[2])
    return -gm * x / (r * r * r)


@njit(cache=True)  # type: ignore[misc]
def _visible(to_sun: FloatArray, to_body: FloatArray, r_sun: float, r_body: float) -> float:
    """Fraction of the Sun's disc not covered by one body (Montenbruck and Gill 3.4.2)."""
    ds = math.sqrt(to_sun @ to_sun)
    db = math.sqrt(to_body @ to_body)
    if db <= r_body:
        return 0.0
    a = math.asin(min(1.0, r_sun / ds))
    b = math.asin(min(1.0, r_body / db))
    cr = np.cross(to_sun, to_body)
    c = math.atan2(math.sqrt(cr @ cr), to_sun @ to_body)
    if c >= a + b:
        return 1.0
    if c <= b - a:
        return 0.0
    if c <= a - b:
        return 1.0 - (b * b) / (a * a)
    x = (c * c + a * a - b * b) / (2.0 * c)
    y = math.sqrt(max(a * a - x * x, 0.0))
    area = (
        a * a * math.acos(min(1.0, max(-1.0, x / a)))
        + b * b * math.acos(min(1.0, max(-1.0, (c - x) / b)))
        - c * y
    )
    return 1.0 - area / (math.pi * a * a)


@njit(cache=True)  # type: ignore[misc]
def _derivs(
    t: float,
    y: FloatArray,
    t0: float,
    dt: float,
    moon_tab: FloatArray,
    sun_tab: FloatArray,
    pa_tab: FloatArray,
    itrf_tab: FloatArray,
    gm_e: float,
    gm_m: float,
    gm_s: float,
    origin: int,
    use_moon: bool,
    use_sun: bool,
    ec: FloatArray,
    es: FloatArray,
    e_gm: float,
    e_r: float,
    e_n: int,
    mc: FloatArray,
    ms: FloatArray,
    m_gm: float,
    m_r: float,
    m_n: int,
    m_within: float,
    srp_k: float,
    r_e: float,
    r_m: float,
    r_s: float,
) -> FloatArray:
    i, s = _knot(t, t0, dt, moon_tab.shape[0])
    rm = _hermite(moon_tab, i, s, dt)[:3]
    rs = _hermite(sun_tab, i, s, dt)[:3]
    pa = _rot(pa_tab, i, s)
    itrf = _rot(itrf_tab, i, s)
    if origin == EARTH:
        pe = np.zeros(3)
        pm = rm
        ps = rs
    else:
        pe = -rm
        pm = np.zeros(3)
        ps = rs - rm
    r = y[:3]
    de = r - pe
    dm = r - pm
    dsun = r - ps

    # Earth on the spacecraft (and, about the Moon, on the origin).
    a = _point(de, gm_e) + _field_acc(de, itrf, ec, es, e_gm, e_r, e_n)
    if origin == MOON:
        a -= _point(-pe, gm_e) + _field_acc(-pe, itrf, ec, es, e_gm, e_r, e_n)
    # Moon.
    if use_moon or origin == MOON:
        a += _point(dm, gm_m)
        if m_n >= 2 and math.sqrt(dm @ dm) < m_within:
            a += _field_acc(dm, pa, mc, ms, m_gm, m_r, m_n)
        if origin == EARTH:
            a -= _point(-pm, gm_m)
    # Sun.
    if use_sun:
        a += _point(dsun, gm_s) - _point(-ps, gm_s)
    # Solar radiation pressure with conical shadows.
    if srp_k > 0.0:
        d = math.sqrt(dsun @ dsun)
        frac = _visible(-dsun, -de, r_s, r_e)
        if frac > 0.0:
            frac *= _visible(-dsun, -dm, r_s, r_m)
        a += srp_k * (AU_M / d) ** 2 * frac * dsun / d
    out = np.empty(6)
    out[:3] = y[3:]
    out[3:] = a
    return out


@njit(cache=True)  # type: ignore[misc]
def _margins(
    t: float,
    y: FloatArray,
    t0: float,
    dt: float,
    moon_tab: FloatArray,
    sun_tab: FloatArray,
    origin: int,
    r_e: float,
    r_m: float,
    r_s: float,
) -> FloatArray:
    """Where the Sun's visible fraction has a kink: first contact, annular and full cover,
    for the Earth then the Moon (radians; a sign change is a crossing)."""
    i, s = _knot(t, t0, dt, moon_tab.shape[0])
    rm = _hermite(moon_tab, i, s, dt)[:3]
    rs = _hermite(sun_tab, i, s, dt)[:3]
    if origin == EARTH:
        pe = np.zeros(3)
        pm = rm
        ps = rs
    else:
        pe = -rm
        pm = np.zeros(3)
        ps = rs - rm
    to_sun = ps - y[:3]
    out = np.empty(6)
    ds = math.sqrt(to_sun @ to_sun)
    a = math.asin(min(1.0, r_s / ds))
    for k in range(2):
        to_b = (pe if k == 0 else pm) - y[:3]
        rb = r_e if k == 0 else r_m
        db = math.sqrt(to_b @ to_b)
        b = math.asin(min(1.0, rb / db))
        cr = np.cross(to_sun, to_b)
        c = math.atan2(math.sqrt(cr @ cr), to_sun @ to_b)
        out[3 * k] = c - (a + b)
        out[3 * k + 1] = c - abs(a - b)
        out[3 * k + 2] = c - (b - a)
    return out


def shadow_events(tables: Tables, model: Model) -> list[Callable[[float, FloatArray], float]]:
    """Event functions at the shadow kinks, so an integrator can stop on each one."""
    args = (
        tables.t0,
        tables.dt,
        tables.moon,
        tables.sun,
        model.origin,
        tables.r_earth_m,
        tables.r_moon_m,
        tables.r_sun_m,
    )

    def make(k: int) -> Callable[[float, FloatArray], float]:
        def g(t: float, y: FloatArray) -> float:
            return float(_margins(t, y, *args)[k])

        return g

    return [make(k) for k in range(6)]


def geodetic(x: FloatArray) -> tuple[float, float, float]:
    """WGS84 geodetic latitude, longitude (deg) and height (m) of an ITRF93 position."""
    a, f = 6_378_137.0, 1.0 / 298.257223563
    e2 = f * (2 - f)
    p = math.hypot(x[0], x[1])
    lon = math.atan2(x[1], x[0])
    lat = math.atan2(x[2], p * (1 - e2))
    h = 0.0
    for _ in range(5):
        n = a / math.sqrt(1 - e2 * math.sin(lat) ** 2)
        h = p * math.cos(lat) + (x[2] + e2 * n * math.sin(lat)) * math.sin(lat) - n
        lat = math.atan2(x[2] + e2 * n * math.sin(lat), p)
    return math.degrees(lat), math.degrees(lon), h


def msis_density(et: float, lat_deg: float, lon_deg: float, alt_m: float, drag: Drag) -> float:
    """NRLMSISE-00 total mass density, kg/m^3, for the given solar and geomagnetic indices."""
    from pymsis import msis  # imported here: only low Earth orbit needs it

    j2000_utc = np.datetime64("2000-01-01T12:00:00", "ms")
    when = j2000_utc + np.timedelta64(int(round((et - TT_MINUS_UTC_S) * 1000.0)), "ms")
    out = msis.calculate(
        when,
        lon_deg,
        lat_deg,
        alt_m / 1000.0,
        [drag.f107],
        [drag.f107a],
        [[drag.ap] * 7],
        version=0,
    )
    return float(np.asarray(out).reshape(-1, 11)[0, 0])


def drag_acceleration(
    et: float, r_earth: FloatArray, v_earth: FloatArray, itrf: FloatArray, drag: Drag
) -> FloatArray:
    """Drag (m/s^2) from the spacecraft's Earth-relative J2000 position and velocity."""
    lat, lon, h = geodetic(itrf @ r_earth)
    if h >= DRAG_BELOW_M:
        return np.zeros(3)
    rho = (drag.density or (lambda e, la, lo, al: msis_density(e, la, lo, al, drag)))(
        et, lat, lon, h
    )
    omega = OMEGA_EARTH * itrf[2]
    v_rel = v_earth - np.cross(omega, r_earth)
    return np.asarray(-0.5 * drag.cd_am * rho * np.linalg.norm(v_rel) * v_rel, dtype=np.float64)


def derivatives(tables: Tables, model: Model) -> Callable[[float, FloatArray], FloatArray]:
    """The right-hand side ``f(t, y)`` for an integrator, ``y`` = (r, v) about the origin."""
    ef = model.earth()
    mf = model.moon_field
    mc = mf.c if mf is not None else np.zeros((1, 1))
    ms = mf.s if mf is not None else np.zeros((1, 1))
    m_gm = mf.gm if mf is not None else 0.0
    m_r = mf.radius_m if mf is not None else 1.0
    m_n = mf.degree if mf is not None else 0
    srp_k = TSI_W_M2 / C_M_S * model.cr_am
    if model.drag is not None and model.origin != EARTH:
        raise ValueError("drag needs the Earth as the integration origin")
    args = (
        tables.t0,
        tables.dt,
        tables.moon,
        tables.sun,
        tables.moon_pa,
        tables.itrf,
        tables.gm_earth,
        tables.gm_moon,
        tables.gm_sun,
        model.origin,
        model.moon,
        model.sun,
        ef.c,
        ef.s,
        ef.gm,
        ef.radius_m,
        ef.degree,
        mc,
        ms,
        m_gm,
        m_r,
        m_n,
        model.moon_sh_within_m,
        srp_k,
        tables.r_earth_m,
        tables.r_moon_m,
        tables.r_sun_m,
    )
    lo, hi = tables.span
    drag = model.drag

    def f(t: float, y: FloatArray) -> FloatArray:
        if not lo <= t <= hi:
            raise ValueError(f"t={t:.1f} is outside the body tables {lo:.1f}..{hi:.1f}")
        out: FloatArray = _derivs(t, y, *args)
        if drag is not None and float(np.dot(y[:3], y[:3])) < (6_378_137.0 + DRAG_BELOW_M) ** 2:
            i, s = _knot(t, tables.t0, tables.dt, tables.moon.shape[0])
            itrf = _rot(tables.itrf, i, s)
            out[3:] += drag_acceleration(t, y[:3], y[3:], itrf, drag)
        return out

    return f


def body_state(tables: Tables, body: int, ets: FloatArray) -> FloatArray:
    """(n, 6) state of the Moon (``MOON``) relative to the Earth from the tables."""
    if body != MOON:
        raise ValueError("only the Moon's state relative to the Earth is tabulated")
    out = np.empty((len(ets), 6))
    for k, t in enumerate(np.asarray(ets, dtype=np.float64)):
        i, s = _knot(float(t), tables.t0, tables.dt, tables.moon.shape[0])
        out[k] = _hermite(tables.moon, i, s, tables.dt)
    return out
