"""The compute worker: runs lifecycle jobs (ADR-12).

``python -m app.workers.compute`` (or ``make compute``). One process, one job
at a time, one SPICE thread. Any number of these can run against the same
database: a job is leased with ``FOR UPDATE SKIP LOCKED``, and the lease is
kept alive by a heartbeat while the job runs. A worker that dies stops
beating; its job becomes claimable again once the lease runs out, up to the
job's attempt limit, after which it is failed with the reason.

Handlers are registered by kind (``@handler("contact")``) in
``app/workers/handlers/``. A handler gets a :class:`JobContext` (the job, a
progress callback, a session factory) and returns a :class:`HandlerResult`:
the answer and everything it was built from. The worker stores both as one
assessment and marks the job done, in one transaction.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import signal
import socket
import subprocess
import time
import traceback
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.db.repositories.jobs import (
    JOBS_CHANNEL,
    AssessmentRepository,
    InputRef,
    JobRecord,
    JobRepository,
)
from app.db.session import session_scope

log = logging.getLogger("polar_window.compute")


@dataclass(frozen=True, slots=True)
class HandlerResult:
    result: dict[str, Any]
    inputs: list[InputRef] = field(default_factory=list)
    message: str = "Worked out."
    of_record: bool = False


@dataclass
class JobContext:
    job: JobRecord
    _progress: float | None = None
    _message: str | None = None

    def progress(self, fraction: float, message: str | None = None) -> None:
        """Report progress; the next heartbeat writes it."""
        self._progress = max(0.0, min(1.0, fraction))
        if message is not None:
            self._message = message


Handler = Callable[[JobContext], Coroutine[Any, Any, HandlerResult]]

HANDLERS: dict[str, Handler] = {}


def handler(kind: str) -> Callable[[Handler], Handler]:
    """Register a job handler for ``kind``."""

    def register(fn: Handler) -> Handler:
        if kind in HANDLERS and HANDLERS[kind] is not fn:
            raise ValueError(f"two handlers for job kind {kind!r}")
        HANDLERS[kind] = fn
        return fn

    return register


class UnknownJobKind(LookupError):
    pass


@lru_cache(maxsize=1)
def code_version() -> str:
    """The commit this worker runs (``PW_CODE_VERSION``, else ``git``), for lineage."""
    env = os.environ.get("PW_CODE_VERSION")
    if env:
        return env[:64]
    repo = Path(__file__).resolve().parents[3]
    try:
        out = subprocess.run(  # noqa: S603 -- fixed argv, no user input
            ["git", "-C", str(repo), "rev-parse", "--short=12", "HEAD"],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        dirty = subprocess.run(  # noqa: S603
            ["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=no"],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return out.stdout.strip() + ("+dirty" if dirty.stdout.strip() else "")
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def backoff_s(attempt: int) -> float:
    """30 s, 60 s, 120 s ... capped at 15 minutes."""
    return float(min(900, 30 * 2 ** max(0, attempt - 1)))


class Worker:
    def __init__(
        self,
        *,
        owner: str | None = None,
        lease_s: float = 60.0,
        poll_s: float = 5.0,
        handlers: dict[str, Handler] | None = None,
    ) -> None:
        self.owner = owner or f"{socket.gethostname()}:{os.getpid()}"
        self.lease_s = lease_s
        self.poll_s = poll_s
        self.handlers = HANDLERS if handlers is None else handlers
        self._wake = asyncio.Event()
        self._stop = asyncio.Event()
        self._task: asyncio.Task[HandlerResult] | None = None

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._task is not None and not self._task.done():
            self._task.cancel()

    async def run_once(self) -> JobRecord | None:
        """Claim and run one job. Returns the job it ran, or None if there was none."""
        async with session_scope() as s:
            await JobRepository(s).fail_exhausted()
        async with session_scope() as s:
            job = await JobRepository(s).claim(self.owner, self.lease_s)
        if job is None:
            return None
        await self._run(job)
        return job

    async def _run(self, job: JobRecord) -> None:
        ctx = JobContext(job=job)
        fn = self.handlers.get(job.kind)
        t0 = time.perf_counter()
        task: asyncio.Task[HandlerResult] | None = None
        beat: asyncio.Task[None] | None = None
        try:
            if fn is None:
                raise UnknownJobKind(f"no handler for job kind {job.kind!r}")
            task = asyncio.create_task(fn(ctx))
            self._task = task
            beat = asyncio.create_task(self._heartbeat(ctx, task))
            result = await task
        except asyncio.CancelledError:
            if self._stop.is_set():

                async def _do_release() -> None:
                    async with session_scope() as s:
                        await JobRepository(s).release(job.id, self.owner)

                await asyncio.shield(_do_release())
                raise
            log.warning("job %s lost its lease and was cancelled", job.id)
            return
        except Exception as exc:
            detail = f"{type(exc).__name__}: {exc}"
            log.error(
                "job %s (%s) failed: %s\n%s", job.id, job.kind, detail, traceback.format_exc()
            )
            async with session_scope() as s:
                status = await JobRepository(s).retry_or_fail(
                    job, self.owner, detail, backoff_s(job.attempts)
                )
            log.info("job %s is now %s", job.id, status)
            return
        finally:
            self._task = None
            if beat is not None:
                beat.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await beat
        ms = (time.perf_counter() - t0) * 1000.0
        async with session_scope() as s:
            aid = await AssessmentRepository(s).save(
                kind=job.kind,
                mission_id=job.mission_id,
                params=job.params,
                params_hash=job.params_hash,
                closure=job.closure,
                result=result.result,
                code_version=code_version(),
                compute_ms=ms,
                inputs=result.inputs,
                of_record=result.of_record,
            )
            await JobRepository(s).finish(job.id, self.owner, aid, result.message)
        log.info("job %s (%s) done in %.0f ms -> assessment %s", job.id, job.kind, ms, aid)

    async def _heartbeat(self, ctx: JobContext, task: asyncio.Task[HandlerResult]) -> None:
        period = max(1.0, self.lease_s / 3.0)
        while not task.done():
            await asyncio.sleep(period)
            try:
                async with session_scope() as s:
                    held = await JobRepository(s).heartbeat(
                        ctx.job.id,
                        self.owner,
                        self.lease_s,
                        progress=ctx._progress,
                        message=ctx._message,
                    )
            except Exception as exc:  # a database blip must not kill the job
                log.warning("heartbeat for job %s failed: %s", ctx.job.id, exc)
                continue
            if not held:
                task.cancel()
                return

    async def _listen(self) -> None:
        """Wake on NOTIFY pw_jobs; polling covers a lost connection."""
        import asyncpg

        dsn = get_settings().database_url.replace("postgresql+asyncpg://", "postgresql://")
        while not self._stop.is_set():
            try:
                conn = await asyncpg.connect(dsn)
                await conn.add_listener(JOBS_CHANNEL, lambda *_: self._wake.set())
                try:
                    await self._stop.wait()
                finally:
                    await conn.close()
            except Exception as exc:
                log.warning(
                    "LISTEN %s failed (%s); polling every %.0f s", JOBS_CHANNEL, exc, self.poll_s
                )
                await asyncio.sleep(30)

    async def run_forever(self) -> None:
        listener = asyncio.create_task(self._listen())
        try:
            while not self._stop.is_set():
                try:
                    ran = await self.run_once()
                except Exception as exc:
                    log.error("compute loop error: %s", exc)
                    ran = None
                if ran is None:
                    self._wake.clear()
                    with contextlib.suppress(TimeoutError):
                        await asyncio.wait_for(self._wake.wait(), timeout=self.poll_s)
        finally:
            listener.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await listener


def main() -> None:
    s = get_settings()
    logging.basicConfig(level=s.log_level, format="%(levelname)s %(name)s: %(message)s")
    from app.core import spice
    from app.core.kernels import KernelError
    from app.workers import handlers  # noqa: F401 -- registers every job kind

    try:
        state = spice.load(s.kernel_dir)
        log.info("SPICE ready: %d kernels", state.count)
    except KernelError as exc:
        log.error("SPICE kernels unavailable; jobs that need them will fail with this:\n%s", exc)

    # Run as ``python -m``, this file is ``__main__``, and the handlers
    # registered themselves in the importable ``app.workers.compute`` module:
    # take the registry from there, not from this copy.
    import app.workers.compute as registry

    worker = Worker(handlers=registry.HANDLERS)

    async def run() -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, worker.stop)
            except NotImplementedError:
                # Windows event loops do not implement add_signal_handler.
                signal.signal(sig, lambda *_: loop.call_soon_threadsafe(worker.stop))
        log.info("compute worker %s: kinds %s", worker.owner, sorted(worker.handlers))
        await worker.run_forever()
        from app.db.session import dispose_engine

        await dispose_engine()

        # Python joins pool threads at exit, but a CSPICE call cannot be interrupted.
        # If the SPICE executor is still busy, exit immediately: the job is already
        # back in the queue.
        if spice.busy():
            logging.shutdown()
            os._exit(0)

    asyncio.run(run())


if __name__ == "__main__":
    main()
