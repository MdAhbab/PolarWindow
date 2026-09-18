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

from app.core.kernels import METAKERNEL_NAME, KernelError, ensure, write_metakernel

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
            mk = directory / METAKERNEL_NAME
            if not mk.exists():
                write_metakernel(directory)
            spice.kclear()
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
            )
            log.info("SPICE: furnsh'd %d kernels in %.0f ms", count, _state.furnsh_ms)
        except KernelError as exc:
            from app.core.kernels import missing as _missing

            _state = KernelState(
                loaded=False, directory=str(directory), missing=_missing(directory), error=str(exc)
            )
            raise
        return _state


def unload() -> None:
    """Clear kernel state. Used between tests."""
    global _state
    with _lock:
        spice.kclear()
        _state = KernelState()


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


def body_vectors(body: Body, ets: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    """Position of ``body`` relative to the Moon's centre, in MOON_ME.

    Returns an ``(n, 3)`` array in **metres**.

    Aberration correction is ``LT+S`` (light time plus stellar aberration),
    which gives the *apparent* direction -- where the body appears to be from
    the Moon. For an illumination and line-of-sight product that is the correct
    choice: what matters is where the Sun appears in the sky, not where it
    geometrically is 1.3 seconds ago.

    One call handles the whole array. spiceypy loops inside CSPICE, so this is
    a single boundary crossing rather than n of them -- the difference between
    ~15 ms and ~200 ms for a 2,835-sample window.
    """
    _require_loaded()
    target = _NAIF_TARGET[body]
    with _lock:
        pos, _lt = spice.spkpos(target, ets, MOON_ME, "LT+S", "MOON")
    arr = np.asarray(pos, dtype=np.float64).reshape(-1, 3)
    # SPICE works in km; the rest of this codebase in metres.
    return np.asarray(arr * 1000.0, dtype=np.float64)


async def body_vectors_async(body: Body, ets: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    """``body_vectors`` on the dedicated SPICE thread.

    Every async caller goes through here. One hop per request, not per sample.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_get_executor(), body_vectors, body, ets)


async def utc_to_et_async(utc: str) -> float:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_get_executor(), utc_to_et, utc)


def angular_radius_deg(body: Body, vectors: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    """Apparent angular *radius* of a body, degrees, per sample.

    This is what turns the visibility boolean into the three-state lit /
    penumbral / dark result. The Sun subtends about 0.26 deg from the Moon; Earth
    subtends about 0.9 deg, which against a +-6.7 deg libration swing is a real
    fraction of the contact-window edge rather than a rounding detail.
    """
    r = R_SUN_M if body == "sun" else R_EARTH_M
    dist = np.linalg.norm(vectors, axis=1)
    return np.asarray(np.degrees(np.arcsin(np.clip(r / dist, -1.0, 1.0))), dtype=np.float64)


def describe() -> dict[str, Any]:
    """Provenance block for ``meta``."""
    return {
        "frame": MOON_ME,
        "aberration": "LT+S",
        "ephemeris": "de440 + moon_pa_de440 (MOON_ME)",
        "kernels_loaded": _state.count,
        "r_moon_m": R_MOON_M,
    }
