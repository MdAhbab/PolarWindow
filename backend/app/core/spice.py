"""The only module in this codebase that imports ``spiceypy``.

Everything else takes and returns numpy arrays. That boundary exists for three
reasons, all of them load-bearing:

1. **CSPICE is not thread-safe**, and ``furnsh`` mutates process-global state.
   Confining it here lets us serialise every entry into the library through one
   lock and one dedicated thread, explicitly, instead of hoping no two requests
   overlap.
2. **It keeps ``core/`` testable.** ``visibility.py`` takes body vectors as an
   ``(n, 3)`` array; it does not care whether they came from de440 or from a
   fixture, so the geometry can be tested without 130 MB of kernels.
3. **It makes the ephemeris swappable.** The frontend's mean-element model and
   this one differ only behind this interface, which is what allows the
   cross-implementation check in the test plan.

Frames
------
Positions are returned in **MOON_ME** (mean Earth / polar axis), which is the
frame lunar cartographic coordinates -- including every site latitude and
longitude in this product -- are defined in. MOON_PA is the dynamically correct
principal-axis frame and differs from ME by roughly an arcminute; using PA where
ME is meant is a real and silent error, so the frame is never defaulted and the
distinction is asserted in the tests.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Literal

import numpy as np
import numpy.typing as npt
import spiceypy as spice
from scipy.interpolate import CubicSpline

from app.core.kernels import (
    LIFECYCLE_KERNELS,
    METAKERNEL_NAME,
    KernelError,
    ensure,
    loadable,
    missing,
    write_metakernel,
)

log = logging.getLogger(__name__)

Body = Literal["sun", "earth"]

#: Volumetric mean radius of the Moon, metres. Matches the frontend's R_MOON so
#: the two implementations' curvature drops agree exactly.
R_MOON_M: Final[float] = 1_737_400.0

#: Photospheric radius of the Sun, metres. Used for the penumbra band.
R_SUN_M: Final[float] = 6.957e8

#: Volumetric mean radius of Earth, metres.
R_EARTH_M: Final[float] = 6_371_000.0

_NAIF_TARGET: Final[dict[str, str]] = {"sun": "SUN", "earth": "EARTH"}

#: The frame every position is expressed in. Not a parameter, by design.
MOON_ME: Final[str] = "MOON_ME"

#: Spacing of the grid CSPICE is actually evaluated on; positions between knots
#: come from a cubic spline through them.
#:
#: Why at all: ``spkpos`` with light-time and aberration costs ~4 us per epoch,
#: and a 708 h window at 900 s is 5,670 epochs -- 24 ms of the 27 ms a cold
#: timeline took, with everything else (mask lookup, bisection, the four
#: numbers) sharing the remaining 3 ms.
#:
#: Why this spacing: in MOON_ME the Sun turns about 0.5 deg/h and Earth
#: librates a few degrees over weeks, so both vectors are extremely smooth.
#: Measured against a direct evaluation over a full lunar day, hourly knots
#: reproduce the vectors to a relative error of 6e-11 (Sun) and 1e-11 (Earth)
#: -- about 1e-8 deg of direction, six orders of magnitude inside the 0.01 deg
#: az/el tolerance of the golden fixtures. ``test_spice.py`` pins that bound.
EPHEMERIS_KNOT_S: Final[float] = 3600.0

# ---------------------------------------------------------------------------
# Process-global kernel state
# ---------------------------------------------------------------------------

# One lock guards every entry into CSPICE. One thread actually makes the calls,
# so that async handlers never block the event loop on a library that cannot be
# entered concurrently anyway. See docs/system-design.md section 4.2.
_lock = threading.RLock()
_executor: ThreadPoolExecutor | None = None


@dataclass
class KernelState:
    """What is loaded, for ``/healthz`` and for provenance stamping."""

    loaded: bool = False
    count: int = 0
    furnsh_ms: float = 0.0
    directory: str = ""
    missing: list[str] = field(default_factory=list)
    error: str | None = None
    #: Lifecycle kernels (GM, Earth orientation, stations) not on disk. The
    #: surface engine works without them; the trip and station sections do not.
    lifecycle_missing: list[str] = field(default_factory=list)


_state = KernelState()


def state() -> KernelState:
    """Current kernel state. Safe to call before ``load``."""
    return _state


def _get_executor() -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        # max_workers=1 is the point, not a limitation: it makes the
        # serialisation of CSPICE access explicit rather than emergent.
        _executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="spice")
    return _executor


def load(directory: Path, *, allow_download: bool = False) -> KernelState:
    """Furnsh the kernel set. Idempotent; safe to call twice.

    Raises
    ------
    KernelError
        With a message naming the missing file and the command that fixes it.
        The caller is expected to surface this, not swallow it: a process that
        starts without an ephemeris should say so in ``/healthz`` rather than
        return plausible-looking zeros.
    """
    global _state
    import time

    with _lock:
        if _state.loaded and _state.directory == str(directory):
            return _state
        t0 = time.perf_counter()
        try:
            ensure(directory, allow_download=allow_download)
            # Regenerated on every load: a lifecycle kernel fetched since the
            # last start must be picked up, and one deleted must not be named.
            write_metakernel(directory, loadable(directory))
            mk = directory / METAKERNEL_NAME
            spice.kclear()
            _extra.clear()
            spice.furnsh(str(mk))
            count = int(spice.ktotal("ALL"))
            if count == 0:
                raise KernelError(
                    f"furnsh({mk}) loaded zero kernels. The metakernel is "
                    f"present but empty or malformed -- delete it and re-run "
                    f"`make kernels`."
                )
            _state = KernelState(
                loaded=True,
                count=count,
                furnsh_ms=(time.perf_counter() - t0) * 1000.0,
                directory=str(directory),
                missing=[],
                lifecycle_missing=missing(directory, LIFECYCLE_KERNELS),
            )
            log.info("SPICE: furnsh'd %d kernels in %.0f ms", count, _state.furnsh_ms)
        except KernelError as exc:
            _state = KernelState(
                loaded=False, directory=str(directory), missing=missing(directory), error=str(exc)
            )
            raise
        return _state


def _require_loaded() -> None:
    if not _state.loaded:
        raise KernelError(
            "SPICE kernels are not loaded, so no Sun or Earth position can be "
            "computed. Horizon masks and terrain are unaffected.\n"
            f"  missing : {', '.join(_state.missing) or 'unknown'}\n"
            "  fix     : make kernels && restart the api"
        )


# ---------------------------------------------------------------------------
# Time
# ---------------------------------------------------------------------------


def utc_to_et(utc: str) -> float:
    """Convert an ISO-8601 UTC string to ephemeris time (TDB seconds past J2000)."""
    _require_loaded()
    with _lock:
        return float(spice.str2et(utc))


def et_range(start_et: float, end_et: float, step_s: float) -> npt.NDArray[np.float64]:
    """Inclusive ET grid.

    ``np.arange`` on floats drops or duplicates the endpoint depending on
    rounding, and a timeline that is one sample short at one step and one long
    at another produces off-by-one arc totals. ``linspace`` on an integer count
    is exact.
    """
    if step_s <= 0:
        raise ValueError("step_s must be positive")
    n = int(round((end_et - start_et) / step_s))
    if n < 1:
        raise ValueError(f"window too short for step {step_s}s")
    return np.linspace(start_et, end_et, n + 1, dtype=np.float64)


# ---------------------------------------------------------------------------
# Positions
# ---------------------------------------------------------------------------


def _spkpos_m(target: str, ets: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    """One vectorised ``spkpos``, in metres. Caller holds nothing; this locks."""
    with _lock:
        pos, _lt = spice.spkpos(target, ets, MOON_ME, "LT+S", "MOON")
    # SPICE works in km; the rest of this codebase in metres.
    return np.asarray(np.asarray(pos, dtype=np.float64).reshape(-1, 3) * 1000.0, dtype=np.float64)


def body_vectors(
    body: Body,
    ets: npt.NDArray[np.float64],
    *,
    knot_s: float | None = EPHEMERIS_KNOT_S,
) -> npt.NDArray[np.float64]:
    """Position of ``body`` relative to the Moon's centre, in MOON_ME.

    Returns an ``(n, 3)`` array in **metres**.

    Aberration correction is ``LT+S`` (light time plus stellar aberration),
    which gives the *apparent* direction -- where the body appears to be from
    the Moon. For an illumination and line-of-sight product that is the correct
    choice: what matters is where the Sun appears in the sky, not where it
    geometrically is 1.3 seconds ago.

    When the requested grid is finer than ``knot_s``, CSPICE is evaluated on a
    knot grid that brackets the request by one knot at each end and the
    positions are interpolated with a cubic spline (see ``EPHEMERIS_KNOT_S``
    for the measured error). ``knot_s=None`` forces direct evaluation at every
    epoch, which is what the accuracy test compares against.
    """
    _require_loaded()
    target = _NAIF_TARGET[body]
    ets = np.asarray(ets, dtype=np.float64)
    if knot_s is None or ets.size < 4:
        return _spkpos_m(target, ets)
    span = float(ets[-1] - ets[0])
    step = span / (ets.size - 1)
    if step >= knot_s or span < 4.0 * knot_s:
        return _spkpos_m(target, ets)
    n = int(np.ceil(span / knot_s))
    knots = ets[0] - knot_s + knot_s * np.arange(n + 3, dtype=np.float64)
    spline = CubicSpline(knots, _spkpos_m(target, knots), axis=0)
    return np.asarray(spline(ets), dtype=np.float64)


@dataclass(frozen=True, slots=True)
class Ephemeris:
    """Everything one window needs from SPICE, fetched in a single hop."""

    ets: npt.NDArray[np.float64]
    sun: npt.NDArray[np.float64]
    earth: npt.NDArray[np.float64]


def ephemeris(start_utc: str, end_utc: str, step_s: float) -> Ephemeris:
    """Time grid plus both bodies' positions for one window."""
    start_et = utc_to_et(start_utc)
    end_et = utc_to_et(end_utc)
    ets = et_range(start_et, end_et, step_s)
    return Ephemeris(ets=ets, sun=body_vectors("sun", ets), earth=body_vectors("earth", ets))


async def ephemeris_async(start_utc: str, end_utc: str, step_s: float) -> Ephemeris:
    """``ephemeris`` on the dedicated SPICE thread: one hop per window, not four."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_get_executor(), ephemeris, start_utc, end_utc, step_s)


# ---------------------------------------------------------------------------
# General positions, rotations and constants (lifecycle engines)
# ---------------------------------------------------------------------------
#
# The Sun/Earth helpers above fix the frame (MOON_ME), the observer (MOON) and
# the aberration correction (LT+S) because the surface engine only ever asks one
# question. The trip, launch and station engines ask many: a relay seen from a
# site wants geometric positions in MOON_ME; a spacecraft propagated under
# gravity wants J2000 states with no correction at all; a launch pad wants
# ITRF93. Getting any of these wrong is silent, so none of them is defaulted --
# every caller names its frame, its observer and its correction (ADR-11).

Aberration = Literal["NONE", "LT", "LT+S", "CN", "CN+S", "XLT", "XLT+S", "XCN", "XCN+S"]

#: Frames the lifecycle engines use, named once so a typo is a NameError.
J2000: Final[str] = "J2000"
MOON_PA: Final[str] = "MOON_PA"
ITRF93: Final[str] = "ITRF93"


def _require_lifecycle(names: tuple[str, ...]) -> None:
    _require_loaded()
    gone = [n for n in names if n in _state.lifecycle_missing]
    if gone:
        raise KernelError(
            "This answer needs kernels that are not on disk: "
            + ", ".join(gone)
            + ". The surface numbers are unaffected.\n  fix: make kernels"
        )


def _spkezr_m(
    target: str, ets: npt.NDArray[np.float64], frame: str, abcorr: Aberration, observer: str
) -> npt.NDArray[np.float64]:
    with _lock:
        st, _lt = spice.spkezr(target, ets, frame, abcorr, observer)
    return np.asarray(np.asarray(st, dtype=np.float64).reshape(-1, 6) * 1000.0, dtype=np.float64)


def _spkpos_general_m(
    target: str, ets: npt.NDArray[np.float64], frame: str, abcorr: Aberration, observer: str
) -> npt.NDArray[np.float64]:
    with _lock:
        pos, _lt = spice.spkpos(target, ets, frame, abcorr, observer)
    return np.asarray(np.asarray(pos, dtype=np.float64).reshape(-1, 3) * 1000.0, dtype=np.float64)


def positions(
    target: str,
    observer: str,
    frame: str,
    abcorr: Aberration,
    ets: npt.NDArray[np.float64],
    *,
    knot_s: float | None,
) -> npt.NDArray[np.float64]:
    """``(n, 3)`` position of ``target`` relative to ``observer`` in ``frame``, metres.

    ``knot_s`` is required, not defaulted: hourly knots are exact to 1e-8 deg
    for the Sun and Earth but catastrophically wrong for a spacecraft in a
    two-hour lunar orbit. Pass ``None`` for anything that orbits quickly.
    """
    _require_loaded()
    ets = np.asarray(ets, dtype=np.float64)
    if knot_s is None or ets.size < 4:
        return _spkpos_general_m(target, ets, frame, abcorr, observer)
    span = float(ets[-1] - ets[0])
    step = span / (ets.size - 1)
    if step >= knot_s or span < 4.0 * knot_s:
        return _spkpos_general_m(target, ets, frame, abcorr, observer)
    n = int(np.ceil(span / knot_s))
    knots = ets[0] - knot_s + knot_s * np.arange(n + 3, dtype=np.float64)
    spline = CubicSpline(knots, _spkpos_general_m(target, knots, frame, abcorr, observer), axis=0)
    return np.asarray(spline(ets), dtype=np.float64)


def states(
    target: str,
    observer: str,
    frame: str,
    abcorr: Aberration,
    ets: npt.NDArray[np.float64],
) -> npt.NDArray[np.float64]:
    """``(n, 6)`` state (m, m/s) of ``target`` relative to ``observer``. Always direct."""
    _require_loaded()
    return _spkezr_m(target, np.asarray(ets, dtype=np.float64), frame, abcorr, observer)


def rotations(
    from_frame: str, to_frame: str, ets: npt.NDArray[np.float64]
) -> npt.NDArray[np.float64]:
    """``(n, 3, 3)`` rotation matrices taking vectors in ``from_frame`` to ``to_frame``."""
    _require_loaded()
    ets = np.asarray(ets, dtype=np.float64)
    out = np.empty((ets.size, 3, 3), dtype=np.float64)
    with _lock:
        for i, et in enumerate(ets):
            out[i] = spice.pxform(from_frame, to_frame, float(et))
    return out


def gm_m3_s2(body: str) -> float:
    """Gravitational parameter from ``gm_de440.tpc``, m^3/s^2."""
    _require_lifecycle(("gm_de440.tpc",))
    with _lock:
        _dim, values = spice.bodvrd(body, "GM", 1)
    return float(np.asarray(values, dtype=np.float64).ravel()[0]) * 1e9


def radii_m(body: str) -> npt.NDArray[np.float64]:
    """Triaxial radii from the PCK, metres."""
    _require_loaded()
    with _lock:
        _dim, r = spice.bodvrd(body, "RADII", 3)
    return np.asarray(r, dtype=np.float64).ravel() * 1000.0


def et_to_utc(et: float, *, precision: int = 3) -> str:
    """ISO-8601 UTC ("2026-09-26T12:00:00.000Z") for an ephemeris time."""
    _require_loaded()
    with _lock:
        return str(spice.et2utc(float(et), "ISOC", precision)) + "Z"


#: Kernels the ground-station geometry needs (ADR-18).
STATION_KERNELS: Final[tuple[str, ...]] = (
    "earth_1962_260806_2126_combined.bpc",
    "earthstns_itrf93_260814.bsp",
    "earth_topo_260814.tf",
)


@dataclass(frozen=True, slots=True)
class StationLook:
    """Where a point on the Moon appears from one ground station, per epoch."""

    station: str
    az_deg: npt.NDArray[np.float64]
    el_deg: npt.NDArray[np.float64]
    range_m: npt.NDArray[np.float64]


def station_look_angles(
    stations: list[str], site_me_m: npt.NDArray[np.float64], ets: npt.NDArray[np.float64]
) -> list[StationLook]:
    """Azimuth, elevation and range of a lunar surface point from each DSN station.

    The Moon's apparent position (``LT+S``) is taken from Earth's centre and
    the site vector is rotated from MOON_ME at each epoch; see
    :func:`station_look_to` for the station part.
    """
    _require_lifecycle(STATION_KERNELS)
    ets = np.asarray(ets, dtype=np.float64)
    site = np.asarray(site_me_m, dtype=np.float64).reshape(3)
    r_me2j = rotations("MOON_ME", "J2000", ets)
    moon = positions("MOON", "EARTH", "J2000", "LT+S", ets, knot_s=None)
    return station_look_to(stations, moon + np.einsum("nij,j->ni", r_me2j, site), ets)


def station_look_to(
    stations: list[str], target_geo_j2k_m: npt.NDArray[np.float64], ets: npt.NDArray[np.float64]
) -> list[StationLook]:
    """Azimuth, elevation and range from each DSN station of a target given geocentrically.

    ``target_geo_j2k_m`` is the target's position from Earth's centre in J2000
    (metres), one row per epoch. The station frames are NAIF's
    ``{station}_TOPO`` (x north, y west, z up, from ``earth_topo_*.tf``); Earth
    orientation is ITRF93 from the dated combined kernel. Observing from
    Earth's centre and subtracting the station's offset differs from
    observing at the station by milliseconds of light time: far below a DSN
    mask's 0.1 degree. Per epoch only the ITRF93-to-J2000 rotation is asked
    of CSPICE; the stations are fixed in ITRF93.
    """
    target = np.asarray(target_geo_j2k_m, dtype=np.float64).reshape(-1, 3)
    out = []
    for st, (pos, rot) in zip(stations, station_frames(stations, ets), strict=True):
        v = np.einsum("nij,nj->ni", rot, target - pos) / 1000.0
        rng = np.linalg.norm(v, axis=1)
        el = np.degrees(np.arcsin(np.clip(v[:, 2] / rng, -1.0, 1.0)))
        az = np.mod(np.degrees(np.arctan2(-v[:, 1], v[:, 0])), 360.0)
        out.append(StationLook(station=st, az_deg=az, el_deg=el, range_m=rng * 1000.0))
    return out


def station_frames(
    stations: list[str], ets: npt.NDArray[np.float64]
) -> list[tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]]:
    """Per station: ``(n, 3)`` position from Earth's centre in J2000 (metres) and
    ``(n, 3, 3)`` rotations J2000 -> ``{station}_TOPO`` (x north, y west, z up).

    Worked out once per answer so a relay sweep can ask where a station looks
    thousands of times without calling CSPICE again.
    """
    _require_lifecycle(STATION_KERNELS)
    ets = np.asarray(ets, dtype=np.float64)
    r_i2j = rotations("ITRF93", "J2000", ets)
    out = []
    with _lock:
        fixed = []
        for st in stations:
            p, _ = spice.spkpos(st, float(ets[0]), "ITRF93", "NONE", "EARTH")
            topo = np.asarray(spice.pxform("ITRF93", f"{st}_TOPO", float(ets[0])))
            fixed.append((np.asarray(p, dtype=np.float64) * 1000.0, topo))
    for p_itrf, topo in fixed:
        pos = np.einsum("nij,j->ni", r_i2j, p_itrf)
        # J2000 -> ITRF93 is the transpose of r_i2j; then ITRF93 -> TOPO.
        rot = np.einsum("ij,nkj->nik", topo, r_i2j)
        out.append((np.asarray(pos, dtype=np.float64), np.asarray(rot, dtype=np.float64)))
    return out


_extra: set[str] = set()


def load_extra(paths: list[Path]) -> None:
    """Furnsh extra kernels (a flown mission's trajectory) once each; idempotent."""
    _require_loaded()
    with _lock:
        for p in paths:
            key = str(Path(p).resolve())
            if key in _extra:
                continue
            if not Path(p).exists():
                raise KernelError(f"kernel not on disk: {p} (polar-data sync)")
            spice.furnsh(key)
            _extra.add(key)


def write_spk13(
    path: Path,
    naif_id: int,
    ets: npt.NDArray[np.float64],
    states_m: npt.NDArray[np.float64],
    *,
    center: int = 301,
    frame: str = J2000,
    degree: int = 7,
    segment: str = "orbiter",
) -> None:
    """Write states (m, m/s) as one SPK type 13 segment (Hermite, unequal steps).

    Used for a real orbiter's trajectory from JPL Horizons (T1, F2): the file
    is rewritten whole, then loaded with :func:`load_extra` like any other
    kernel, so every aberration correction CSPICE offers applies to it.
    """
    ets = np.ascontiguousarray(ets, dtype=np.float64)
    st = np.ascontiguousarray(np.asarray(states_m, dtype=np.float64).reshape(-1, 6) / 1000.0)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp.bsp")
    with _lock:
        if tmp.exists():
            tmp.unlink()
        h = spice.spkopn(str(tmp), "polar-window orbiter", 0)
        try:
            spice.spkw13(
                h,
                naif_id,
                center,
                frame,
                float(ets[0]),
                float(ets[-1]),
                segment[:40],
                degree,
                int(ets.size),
                st,
                ets,
            )
        except Exception:
            spice.dafcls(h)  # no segment written: SPKCLS would refuse the file
            tmp.unlink(missing_ok=True)
            raise
        spice.spkcls(h)
    tmp.replace(path)


def site_look(
    target: str,
    site_me_m: npt.NDArray[np.float64],
    ets: npt.NDArray[np.float64],
    abcorr: Aberration = "LT+S",
) -> npt.NDArray[np.float64]:
    """``(n, 3)`` where ``target`` appears from a point fixed on the Moon, in MOON_ME, metres.

    CSPICE's constant-position observer (``spkcpo``): the light time is from
    the site itself, and stellar aberration is the site's own motion, as a
    JPL Horizons observer table on the Moon gives them.
    """
    _require_loaded()
    obs = np.asarray(site_me_m, dtype=np.float64).reshape(3) / 1000.0
    out = np.empty((np.asarray(ets).size, 3), dtype=np.float64)
    with _lock:
        for i, et in enumerate(np.asarray(ets, dtype=np.float64)):
            state, _lt = spice.spkcpo(
                target, float(et), MOON_ME, "OBSERVER", abcorr, obs, "MOON", MOON_ME
            )
            out[i] = np.asarray(state[:3], dtype=np.float64) * 1000.0
    return out


def unload_extra(paths: list[Path]) -> None:
    """Unload kernels loaded with :func:`load_extra` (validation swaps trajectories)."""
    with _lock:
        for p in paths:
            key = str(Path(p).resolve())
            if key in _extra:
                spice.unload(key)
                _extra.discard(key)


def coverage(spk: Path, naif_id: int) -> list[tuple[float, float]]:
    """The time intervals (ET) an SPK file covers for one body."""
    with _lock:
        cov = spice.spkcov(str(spk), naif_id)
        return [tuple(map(float, spice.wnfetd(cov, i))) for i in range(spice.wncard(cov))]  # type: ignore[misc]


async def run_async(fn: Any, /, *args: Any, **kwargs: Any) -> Any:
    """Run any function of this module on the one SPICE thread."""
    import functools

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_get_executor(), functools.partial(fn, *args, **kwargs))


def describe() -> dict[str, Any]:
    """Provenance block for ``meta``."""
    return {
        "frame": MOON_ME,
        "aberration": "LT+S",
        "ephemeris": "de440 + moon_pa_de440 (MOON_ME)",
        "kernels_loaded": _state.count,
        "r_moon_m": R_MOON_M,
    }


def busy() -> bool:
    """True when the SPICE thread is currently executing a call or has one queued."""
    if _executor is None:
        return False
    if not _executor._work_queue.empty():
        return True
    if _executor._threads:
        idle = getattr(_executor, "_idle_semaphore", None)
        if idle is not None and idle._value == 0:
            return True
    return False
