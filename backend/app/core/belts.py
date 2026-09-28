"""Trapped radiation along a path: the AE8/AP8 belt models (plan track E).

AE8 (electrons) and AP8 (protons) are NASA's static maps of the particles
trapped in Earth's magnetic field, one for solar minimum and one for solar
maximum (Vette 1991; Sawyer and Vette 1976). They are evaluated here with
IRBEM (the library the SPENVIS and spacepy tools also build on), which works
out each point's magnetic shell (McIlwain L and B/B0, IGRF field) and reads
the maps there. The library comes compiled in spacepy's wheel; it is loaded
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
NAME = {"e": "AE8", "p": "AP8"}
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
