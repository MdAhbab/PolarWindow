"""Opt-in process pool for read-only SPICE calls (ADR-24).

CSPICE is not thread-safe and ``furnsh`` mutates process-global state, so
``app.core.spice`` funnels every call through one thread. Under concurrent load
ephemeris sweeps queue behind each other. A *process* has its own CSPICE, so
N worker processes give N independent, never-mutated copies of the pinned
kernel set.

Only pure-in / pure-out calls go here (strings or ET arrays in, numpy arrays
out). Anything that mutates kernel state (``load_extra``, ``unload_extra``,
``write_spk13``) stays on the single thread, and so does any call that depends
on extra kernels loaded in the parent: workers never see them, so such a call
passes ``needs_extra=True`` to ``eligible`` and is refused (falls back to the thread).

Default ``PW_SPICE_WORKERS=0``: nothing here is started and behaviour is
exactly the single-thread path. This module never imports ``spiceypy``.
"""

from __future__ import annotations

import asyncio
import logging
import multiprocessing
import threading
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

log = logging.getLogger(__name__)

#: Below this a pool cannot beat the thread (one worker is the thread plus pickling).
MIN_WORKERS = 2


class PoolUnavailableError(RuntimeError):
    """The pool is not running (or just died); the caller uses the thread instead."""


_lock = threading.Lock()
_pool: ProcessPoolExecutor | None = None
_workers = 0
_directory = ""
_served = 0


# --- worker side (runs in the child process) -------------------------------

_worker_ready = False


def _init_worker(directory: str, expected_fingerprint: str) -> None:
    """Load the pinned kernels once; refuse to serve on a fingerprint mismatch."""
    global _worker_ready
    from app.core import spice

    spice.load_existing(Path(directory))
    got = spice.fingerprint()
    if got != expected_fingerprint:
        raise RuntimeError(
            f"kernel fingerprint mismatch: worker {got} != parent {expected_fingerprint}"
        )
    _worker_ready = True


def _w_ping() -> bool:
    return _worker_ready


def _w_ephemeris(start_utc: str, end_utc: str, step_s: float) -> Any:
    from app.core import spice

    return spice.ephemeris(start_utc, end_utc, step_s)


def _w_positions(
    target: str,
    observer: str,
    frame: str,
    abcorr: Any,
    ets: npt.NDArray[np.float64],
    knot_s: float | None,
) -> npt.NDArray[np.float64]:
    from app.core import spice

    return spice.positions(target, observer, frame, abcorr, ets, knot_s=knot_s)


# --- parent side ------------------------------------------------------------


def start(workers: int, directory: Path) -> bool:
    """Start the pool against the parent's loaded kernels. Never raises.

    Returns True when a pool is running. ``workers < 2`` starts nothing.
    """
    global _pool, _workers, _directory
    from app.core import spice

    if workers < MIN_WORKERS:
        return False
    with _lock:
        if _pool is not None:
            return True
        try:
            if not spice.state().loaded:
                raise RuntimeError("parent kernels are not loaded")
            fp = spice.fingerprint()
            pool = ProcessPoolExecutor(
                max_workers=workers,
                mp_context=multiprocessing.get_context("spawn"),
                initializer=_init_worker,
                initargs=(str(directory), fp),
            )
            try:
                # Warm every worker now so a bad kernel set fails here, not on a request.
                futs = [pool.submit(_w_ping) for _ in range(workers)]
                if not all(f.result(timeout=120) for f in futs):
                    raise RuntimeError("worker did not initialise")
            except BaseException:
                pool.shutdown(wait=False, cancel_futures=True)
                raise
        except Exception as exc:
            log.warning("SPICE worker pool failed to start (%s); using the single thread", exc)
            return False
        _pool, _workers, _directory = pool, workers, str(directory)
        log.info("SPICE worker pool: %d processes", workers)
        return True


def shutdown() -> None:
    """Stop the pool. Idempotent."""
    global _pool, _workers
    with _lock:
        pool, _pool, _workers = _pool, None, 0
    if pool is not None:
        pool.shutdown(wait=True, cancel_futures=True)


def eligible(*, needs_extra: bool = False) -> bool:
    """True when this call may go to the pool.

    A call that needs extra kernels (``load_extra``) loaded in the parent must
    stay on the thread: the workers hold only the pinned set.
    """
    if _pool is None or needs_extra:
        return False
    from app.core import spice

    st = spice.state()
    return st.loaded and st.directory == _directory


async def _run(fn: Any, *args: Any) -> Any:
    global _served, _pool
    pool = _pool
    if pool is None:
        raise PoolUnavailableError("pool not running")
    loop = asyncio.get_running_loop()
    try:
        out = await loop.run_in_executor(pool, fn, *args)
    except (BrokenProcessPool, RuntimeError) as exc:
        if isinstance(exc, BrokenProcessPool) or "shutdown" in str(exc):
            log.warning("SPICE worker pool broke (%s); falling back to the single thread", exc)
            with _lock:
                if _pool is pool:
                    _pool = None
            raise PoolUnavailableError(str(exc)) from exc
        raise
    _served += 1
    return out


async def ephemeris(start_utc: str, end_utc: str, step_s: float) -> Any:
    """``spice.ephemeris`` in a worker. Raises ``PoolUnavailableError`` if not running."""
    return await _run(_w_ephemeris, start_utc, end_utc, step_s)


async def positions(
    target: str,
    observer: str,
    frame: str,
    abcorr: Any,
    ets: npt.NDArray[np.float64],
    *,
    knot_s: float | None,
) -> npt.NDArray[np.float64]:
    """``spice.positions`` in a worker (pinned kernels only; see ``eligible``)."""
    ets64 = np.asarray(ets, np.float64)
    out = await _run(_w_positions, target, observer, frame, abcorr, ets64, knot_s)
    return np.asarray(out, dtype=np.float64)


def describe() -> dict[str, Any]:
    """For ``spice.describe`` and the health endpoint."""
    return {"workers": _workers, "started": _pool is not None, "tasks_served": _served}
