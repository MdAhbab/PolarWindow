"""Trapped radiation along a path: the AE8/AP8 belt models (plan track E).

AE8 (electrons) and AP8 (protons) are NASA's static maps of the particles
trapped in Earth's magnetic field, one for solar minimum and one for solar
maximum (Vette 1991; Sawyer and Vette 1976). They are evaluated here with
IRBEM (the library the SPENVIS and spacepy tools also build on), which works
out each point's magnetic shell (McIlwain L and B/B0) with the field each map
was built with (Jensen and Cain 1960; GSFC 12/66 updated to 1970 for AP8 MAX)
and reads the maps there. Before evaluation the point is rotated eastward by
0.3 degrees/year since the map epoch to compensate the South Atlantic Anomaly's
westward drift (Heynderickx 1994; ESA UNILIB convention). This does not replace
the map field with today's IGRF. The library comes compiled in spacepy's wheel; it is loaded
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
import os
import sys
import sysconfig
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
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
#: Heynderickx (1994): compensate SAA westward drift with an eastward GEO rotation.
#: https://space-env.esa.int/Manuals/UNILIB/v3.02/reference/um510.html
#: https://orfeo.belnet.be/bitstream/handle/internal/6828/A_385.pdf
SAA_DRIFT_DEG_YR = 0.3
MAP_EPOCH = {("e", "min"): 1960, ("e", "max"): 1960, ("p", "min"): 1960, ("p", "max"): 1970}
#: IRBEM keeps state in Fortran common blocks: one call at a time.
_LOCK = threading.Lock()


class BeltsUnavailable(RuntimeError):
    pass


def _ptr(arr: npt.NDArray[np.generic]) -> ctypes.c_void_p:
    """The address of an array's data, for IRBEM's Fortran interface."""
    return arr.ctypes.data_as(ctypes.c_void_p)


@lru_cache(maxsize=1)
def _lib() -> ctypes.CDLL:
    spec = importlib.util.find_spec("spacepy")
    if spec is None or spec.origin is None:
        raise BeltsUnavailable("spacepy is not installed, so IRBEM (AE8/AP8) is not available")
    package = Path(spec.origin).parent
    names = {
        "win32": ["libirbem.dll.a", "irbem.dll"],
        "darwin": ["libirbem.dylib", "libirbem.so", "irbem.dylib", "irbem.so"],
    }.get(sys.platform, ["libirbem.so"])
    suffix = sysconfig.get_config_var("EXT_SUFFIX")
    if suffix:
        names.extend([f"libirbem{suffix}", f"irbem{suffix}"])
    failures = []
    for name in names:
        path = package / "irbempy" / name
        if not path.is_file():
            continue
        try:
            # SpacePy's Windows wheel bundles the Fortran runtime here. Load it
            # without importing SpacePy, which creates user state and fetches data.
            runtime = package / "libs"
            if sys.platform == "win32" and runtime.is_dir():
                with os.add_dll_directory(str(runtime)):
                    return ctypes.CDLL(str(path))
            return ctypes.CDLL(str(path))
        except OSError as exc:
            failures.append(f"{path.name}: {exc}")
    reason = "; ".join(failures) or f"no shared library in {package / 'irbempy'}"
    raise BeltsUnavailable(f"IRBEM could not be loaded: {reason}")


def available() -> bool:
    try:
        _lib()
    except BeltsUnavailable:
        return False
    return True


def saa_corrected_geo(
    particle: Particle, solar: Solar, times: list[datetime], xyz_geo_km: FloatArray
) -> FloatArray:
    """Rotate the evaluation point eastward into the static map's epoch.

    This compensates only longitudinal SAA drift, not the full secular field
    change. Physical trajectory coordinates remain unchanged. Use the same
    correction for flux and its diagnostic shells; never apply it to uploads.
    """
    xyz = np.asarray(xyz_geo_km, dtype=np.float64)
    if xyz.shape != (len(times), 3) or not np.isfinite(xyz).all():
        raise ValueError("finite GEO XYZ samples must match the times")
    years = []
    for t in times:
        if t.tzinfo is None or t.utcoffset() is None:
            raise ValueError("SAA correction requires timezone-aware times")
        utc = t.astimezone(UTC)
        start = datetime(utc.year, 1, 1, tzinfo=UTC)
        end = datetime(utc.year + 1, 1, 1, tzinfo=UTC)
        years.append(utc.year + (utc - start).total_seconds() / (end - start).total_seconds())
    angle = np.deg2rad(SAA_DRIFT_DEG_YR * (np.asarray(years) - MAP_EPOCH[particle, solar]))
    result = xyz.copy()
    result[:, 0] = np.cos(angle) * xyz[:, 0] - np.sin(angle) * xyz[:, 1]
    result[:, 1] = np.sin(angle) * xyz[:, 0] + np.cos(angle) * xyz[:, 1]
    return result


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
    xyz = saa_corrected_geo(particle, solar, times, xyz_geo_km) / RE_KM
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

        with _LOCK:
            lib.fly_in_nasa_aeap1_(
                ctypes.byref(i4(m)),
                ctypes.byref(i4(1)),  # GEO Cartesian, Earth radii
                ctypes.byref(i4(MODEL[(particle, solar)])),
                ctypes.byref(i4(3)),  # integral flux
                ctypes.byref(i4(len(energies_mev))),
                _ptr(energy),
                _ptr(year),
                _ptr(doy),
                _ptr(ut),
                _ptr(x1),
                _ptr(x2),
                _ptr(x3),
                _ptr(flux),
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

        with _LOCK:
            lib.make_lstar1_(
                ctypes.byref(i4(m)),
                ctypes.byref(i4(0)),  # no external field
                _ptr(opts),
                ctypes.byref(i4(1)),  # GEO Cartesian, Earth radii
                _ptr(yr),
                _ptr(doy),
                _ptr(ut),
                *(_ptr(c) for c in x),
                _ptr(maginput),
                *(_ptr(o) for o in out),
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
    geo = saa_corrected_geo(particle, solar, times, xyz_geo_km)
    lm, blocal, _ = field_lines(times, geo, BUILT_WITH[(particle, solar)])
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
