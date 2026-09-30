"""Trapped radiation along a path: the AE8/AP8 belt models (plan track E).

AE8 (electrons) and AP8 (protons) are NASA's static maps of the particles
trapped in Earth's magnetic field, one for solar minimum and one for solar
maximum (Vette 1991; Sawyer and Vette 1976). They are evaluated here with
IRBEM (the library the SPENVIS and spacepy tools also build on), which works
out each point's magnetic shell (McIlwain L and B/B0) with the field each map
was built with (Jensen and Cain 1960; GSFC 12/66 updated to 1970 for AP8 MAX)
and reads the maps there. The library comes compiled in spacepy's wheel; it is loaded
directly so that importing spacepy (which reaches for the network and a data
directory) is not needed.

The maps are averages over years: an estimate from them is good to about a
factor of two (the usual reading), so every number here carries ×/÷2.

Positions are Earth-fixed (ITRF93) Cartesian, in Earth radii of 6371.2 km,
the unit IRBEM's GEO system takes.
"""

from __future__ import annotations

import ctypes
import importlib.util
import threading
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Literal

import numpy as np
import numpy.typing as npt

FloatArray = npt.NDArray[np.float64]
Particle = Literal["e", "p"]
Solar = Literal["min", "max"]

#: IRBEM's Earth radius for its GEO Cartesian system.
RE_KM = 6371.2
#: Array sizes IRBEM's Fortran interface is compiled for.
NTIME_MAX = 100_000
NENE_MAX = 25
#: IRBEM's value for "outside the model".
BAD = -1.0e31
#: The factor AE8/AP8 are usually read with (the maps are long-term averages).
FACTOR = 2.0
MODEL = {("e", "min"): 1, ("e", "max"): 2, ("p", "min"): 3, ("p", "max"): 4}
#: IRBEM keeps state in Fortran common blocks: one call at a time.
_LOCK = threading.Lock()


class BeltsUnavailable(RuntimeError):
    pass


@lru_cache(maxsize=1)
def _lib() -> ctypes.CDLL:
    spec = importlib.util.find_spec("spacepy")
    if spec is None or spec.origin is None:
        raise BeltsUnavailable("spacepy is not installed, so IRBEM (AE8/AP8) is not available")
    path = Path(spec.origin).parent / "irbempy" / "libirbem.so"
    if not path.exists():
        raise BeltsUnavailable(f"IRBEM library not found at {path}")
    return ctypes.CDLL(str(path))


def available() -> bool:
    try:
        _lib()
    except BeltsUnavailable:
        return False
    return True


def integral_flux(
    particle: Particle,
    solar: Solar,
    energies_mev: list[float],
    times: list[datetime],
    xyz_geo_km: FloatArray,
) -> FloatArray:
    """``(len(energies), n)`` omnidirectional flux above each energy, per cm² per s.

    Points outside the model (beyond its shells, or below its floor) are 0.
    """
    xyz = np.asarray(xyz_geo_km, dtype=np.float64) / RE_KM
    n = xyz.shape[0]
    if len(energies_mev) > NENE_MAX:
        raise ValueError(f"at most {NENE_MAX} energies")
    out = np.zeros((len(energies_mev), n))
    lib = _lib()
    i4 = ctypes.c_int
    for a in range(0, n, NTIME_MAX):
        b = min(n, a + NTIME_MAX)
        m = b - a
        energy = np.zeros((NENE_MAX, 2))  # Fortran energy(2, 25), column-major
        energy[: len(energies_mev), 0] = energies_mev
        year = np.zeros(NTIME_MAX, np.int32)
        doy = np.zeros(NTIME_MAX, np.int32)
        ut = np.zeros(NTIME_MAX)
        x1 = np.zeros(NTIME_MAX)
        x2 = np.zeros(NTIME_MAX)
        x3 = np.zeros(NTIME_MAX)
        for k, t in enumerate(times[a:b]):
            tt = t.timetuple()
            year[k] = tt.tm_year
            doy[k] = tt.tm_yday
            ut[k] = t.hour * 3600 + t.minute * 60 + t.second + t.microsecond * 1e-6
        x1[:m], x2[:m], x3[:m] = xyz[a:b].T
        flux = np.zeros((NENE_MAX, NTIME_MAX))  # Fortran flux(ntime_max, 25)

        def ptr(arr: npt.NDArray[np.generic]) -> ctypes.c_void_p:
            return arr.ctypes.data_as(ctypes.c_void_p)

        with _LOCK:
            lib.fly_in_nasa_aeap1_(
                ctypes.byref(i4(m)),
                ctypes.byref(i4(1)),  # GEO Cartesian, Earth radii
                ctypes.byref(i4(MODEL[(particle, solar)])),
                ctypes.byref(i4(3)),  # integral flux
                ctypes.byref(i4(len(energies_mev))),
                ptr(energy),
                ptr(year),
                ptr(doy),
                ptr(ut),
                ptr(x1),
                ptr(x2),
                ptr(x3),
                ptr(flux),
            )
        got = flux[: len(energies_mev), :m]
        out[:, a:b] = np.where((got <= BAD * 0.1) | ~np.isfinite(got), 0.0, got)
    return out


#: The internal field each map was built with, as IRBEM numbers it (options(5)): Jensen
#: and Cain 1960 for AE8 MIN, AE8 MAX and AP8 MIN, GSFC 12/66 updated to 1970 for AP8 MAX.
BUILT_WITH = {("e", "min"): 2, ("e", "max"): 2, ("p", "min"): 2, ("p", "max"): 3}
#: McIlwain's dipole moment (nT RE^3) that IRBEM divides by L^3 to get B0 for the maps.
MCILWAIN_M_NT = 31165.3


def field_lines(
    times: list[datetime], xyz_geo_km: FloatArray, field: int, year: int | None = None
) -> tuple[FloatArray, FloatArray, FloatArray]:
    """McIlwain L, the local field and the field line's minimum (nT) at each point, from
    IRBEM's internal ``field`` (0 IGRF, 2 Jensen and Cain 1960, 3 GSFC 12/66), taken at
    each time's date or, with ``year``, on 1 January of that year. NaN where the field
    line is not closed or the point is outside the field model."""
    xyz = np.asarray(xyz_geo_km, dtype=np.float64) / RE_KM
    n = xyz.shape[0]
    res = np.full((3, n), np.nan)
    lib = _lib()
    i4 = ctypes.c_int
    opts = np.array([0, 0, 0, 0, field], dtype=np.int32)
    for a in range(0, n, NTIME_MAX):
        b = min(n, a + NTIME_MAX)
        m = b - a
        yr = np.zeros(NTIME_MAX, np.int32)
        doy = np.zeros(NTIME_MAX, np.int32)
        ut = np.zeros(NTIME_MAX)
        for k, t in enumerate(times[a:b]):
            tt = t.timetuple()
            yr[k], doy[k] = (year, 1) if year is not None else (tt.tm_year, tt.tm_yday)
            ut[k] = t.hour * 3600 + t.minute * 60 + t.second + t.microsecond * 1e-6
        x = [np.zeros(NTIME_MAX) for _ in range(3)]
        for c in range(3):
            x[c][:m] = xyz[a:b, c]
        maginput = np.zeros((NTIME_MAX, 25))  # Fortran maginput(25, ntime_max)
        out = [np.zeros(NTIME_MAX) for _ in range(6)]  # Lm, L*, Blocal, Bmin, XJ, MLT

        def ptr(arr: npt.NDArray[np.generic]) -> ctypes.c_void_p:
            return arr.ctypes.data_as(ctypes.c_void_p)

        with _LOCK:
            lib.make_lstar1_(
                ctypes.byref(i4(m)),
                ctypes.byref(i4(0)),  # no external field
                ptr(opts),
                ctypes.byref(i4(1)),  # GEO Cartesian, Earth radii
                ptr(yr),
                ptr(doy),
                ptr(ut),
                *(ptr(c) for c in x),
                ptr(maginput),
                *(ptr(o) for o in out),
            )
        lv, bl, bm = np.abs(out[0][:m]), out[2][:m], out[3][:m]
        ok = (lv > 0) & (lv < 1e30) & (bl > 0) & (bl < 1e30) & (bm > 0) & (bm < 1e30)
        for i, v in enumerate((lv, bl, bm)):
            res[i, a:b] = np.where(ok, v, np.nan)
    return res[0], res[1], res[2]


def shells(
    particle: Particle, solar: Solar, times: list[datetime], xyz_geo_km: FloatArray
) -> tuple[FloatArray, FloatArray]:
    """McIlwain L and B/B0 at each point, as :func:`integral_flux` reads the maps there:
    the field the map was built with (:data:`BUILT_WITH`), B0 from McIlwain's moment."""
    lm, blocal, _ = field_lines(times, xyz_geo_km, BUILT_WITH[(particle, solar)])
    return lm, blocal / (MCILWAIN_M_NT / lm**3)


def fluence(t_s: FloatArray, flux: FloatArray) -> float:
    """Time integral (trapezoid) of a flux along the path: particles per cm²."""
    t = np.asarray(t_s, dtype=np.float64)
    f = np.asarray(flux, dtype=np.float64)
    if t.size < 2:
        return 0.0
    return float(np.sum(0.5 * (f[1:] + f[:-1]) * np.diff(t)))


def time_inside(t_s: FloatArray, inside: npt.NDArray[np.bool_]) -> float:
    """Seconds with ``inside`` true, each step counted by its midpoint."""
    t = np.asarray(t_s, dtype=np.float64)
    if t.size < 2:
        return 0.0
    mid = inside[1:] & inside[:-1]
    half = inside[1:] ^ inside[:-1]
    dt = np.diff(t)
    return float(np.sum(dt[mid]) + 0.5 * np.sum(dt[half]))


@dataclass(frozen=True, slots=True)
class Passes:
    """The stretches of a path inside the belts, as (start, end) seconds."""

    stretches: list[tuple[float, float]]

    @property
    def count(self) -> int:
        return len(self.stretches)


def passes(t_s: FloatArray, inside: npt.NDArray[np.bool_]) -> Passes:
    t = np.asarray(t_s, dtype=np.float64)
    out: list[tuple[float, float]] = []
    start: float | None = None
    for k in range(t.size):
        if inside[k] and start is None:
            start = float(t[k])
        if not inside[k] and start is not None:
            out.append((start, float(t[k - 1])))
            start = None
    if start is not None:
        out.append((start, float(t[-1])))
    return Passes(out)
