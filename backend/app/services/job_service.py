"""Heavy answers as jobs (ADR-12): look up, enqueue, report progress.

The API never computes a trip, a contact plan or a launch calendar on a
request. A section endpoint asks this module for the answer to a key; the
key hashes the job kind, its parameters and every version the answer depends
on (engine closure, mission record, catalogues, kernels). A stored answer for
that key is returned as is; otherwise a job is queued (or the one already
queued for that key is joined) and the caller gets a job reference to poll.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import orjson
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.jobs import (
    AssessmentRecord,
    AssessmentRepository,
    JobRecord,
    JobRepository,
)

#: How long a client should wait before polling again, by state.
POLL_AFTER_S = {"queued": 3.0, "running": 2.0, "done": 0.0, "failed": 0.0}

#: A queued job older than this with no worker picking it up is reported as
#: such, rather than as quietly "queued" forever.
STUCK_AFTER_S = 120.0

#: Cheapest kind first. Measured by ``make load-compute`` (58 jobs, 2 workers):
#: a contact plan runs in ~0.1 s, a launch calendar ~10 s, a trip ~50 s. In
#: arrival order a contact plan waited behind every trip asked before it
#: (median wait 95 s for a 0.1 s answer); cheapest first, it does not.
PRIORITY = {"contact": 2, "launch": 1, "trip": 0}


#: Set by a read-only caller (an agent's tool): a missing answer is not queued.
_READ_ONLY: ContextVar[bool] = ContextVar("jobs_read_only", default=False)


class NotWorkedOut(LookupError):
    """A read-only caller asked for an answer that is not stored; nothing was queued."""


@contextmanager
def read_only() -> Iterator[None]:
    """Within this block ``answer_or_enqueue`` returns stored answers only."""
    token = _READ_ONLY.set(True)
    try:
        yield
    finally:
        _READ_ONLY.reset(token)


class JobNotFound(LookupError):
    pass


def params_hash(kind: str, closure: str, params: dict[str, Any]) -> str:
    """Stable SHA-256 over the kind, the engine closure and sorted parameters."""
    blob = orjson.dumps(
        {"kind": kind, "closure": closure, "params": params}, option=orjson.OPT_SORT_KEYS
    )
    return hashlib.sha256(blob).hexdigest()


@dataclass(frozen=True, slots=True)
class Answer:
    """Either a stored answer or a job to poll; exactly one is set."""

    assessment: AssessmentRecord | None
    job: dict[str, Any] | None


def job_ref(
    job: JobRecord, now: datetime | None = None, ahead: int | None = None
) -> dict[str, Any]:
    """The contract's ``JobRef`` (+ ``assessment_id`` once done). ``ahead``: queued jobs a
    worker takes first, said in the message so a wait has a reason."""
    now = now or datetime.now(UTC)
    message = job.message
    if job.status == "queued" and ahead:
        message = (
            f"Waiting for a compute worker; {ahead} "
            f"{'answer is' if ahead == 1 else 'answers are'} being worked out first."
        )
    elif job.status == "queued" and (now - job.created_at).total_seconds() > STUCK_AFTER_S:
        # Only with nothing ahead of it: under a long queue a job waits past
        # this while both workers are busy, and "not running" would be false.
        message = (
            "Still waiting for a compute worker. If this does not change, the compute "
            "worker is not running (make compute)."
        )
    if job.status == "failed" and job.error:
        message = f"Could not be worked out: {job.error.splitlines()[0][:300]}"
    return {
        "job_id": job.id,
        "status": job.status,
        "progress": job.progress,
        "message": message,
        "poll_after_s": POLL_AFTER_S.get(job.status, 3.0),
        "assessment_id": job.assessment_id,
    }


async def _ahead(session: AsyncSession, job: JobRecord) -> int | None:
    if job.status != "queued":
        return None
    from sqlalchemy import text

    n = (
        await session.execute(
            text(
                "SELECT count(*) FROM jobs WHERE status IN ('queued', 'running') AND id <> :id "
                "AND (status = 'running' OR priority > :p OR (priority = :p AND id < :id))"
            ),
            {"id": job.id, "p": job.priority},
        )
    ).scalar_one()
    return int(n)


async def answer_or_enqueue(
    session: AsyncSession,
    *,
    kind: str,
    closure: str,
    params: dict[str, Any],
    mission_id: str | None,
    requested_by: int | None = None,
    priority: int | None = None,
) -> Answer:
    """The stored answer for this key, or a job that will produce it."""
    key = params_hash(kind, closure, params)
    found = await AssessmentRepository(session).latest(kind, key, closure)
    if found is not None:
        return Answer(assessment=found, job=None)
    repo = JobRepository(session)
    last = await repo.latest_for(kind, key, closure)
    if last is not None and last.status == "failed":
        # A failed job is reported, not silently retried on every page load:
        # the failure message is the answer until the inputs change.
        return Answer(assessment=None, job=job_ref(last))
    if _READ_ONLY.get():
        if last is not None and last.status in ("queued", "running"):
            raise NotWorkedOut("It is being worked out now; ask again in a few minutes.")
        raise NotWorkedOut(
            "It has not been worked out yet; opening this section of the mission starts it."
        )
    job = await repo.enqueue(
        kind=kind,
        params=params,
        params_hash=key,
        closure=closure,
        mission_id=mission_id,
        requested_by=requested_by,
        priority=PRIORITY.get(kind, 0) if priority is None else priority,
    )
    return Answer(assessment=None, job=job_ref(job, ahead=await _ahead(session, job)))


async def get_job(session: AsyncSession, job_id: int) -> dict[str, Any]:
    job = await JobRepository(session).get(job_id)
    if job is None:
        raise JobNotFound(job_id)
    return job_ref(job, ahead=await _ahead(session, job))


async def retry(session: AsyncSession, job_id: int, requested_by: int | None) -> dict[str, Any]:
    """Queue a failed job's key again (the person asked; inputs may have been fixed)."""
    repo = JobRepository(session)
    job = await repo.get(job_id)
    if job is None:
        raise JobNotFound(job_id)
    if job.status != "failed":
        return job_ref(job)
    again = await repo.enqueue(
        kind=job.kind,
        params=job.params,
        params_hash=job.params_hash,
        closure=job.closure,
        mission_id=job.mission_id,
        requested_by=requested_by,
    )
    return job_ref(again)
