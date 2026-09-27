"""Jobs and the answers they produce (ADR-12).

A job is leased with ``FOR UPDATE SKIP LOCKED``, so any number of compute
workers can poll one table without two of them taking the same job. A lease
has an expiry that the running worker keeps pushing forward (its heartbeat);
a worker that dies stops pushing, and the job becomes claimable again. The
partial unique index ``uq_jobs_in_flight`` makes a repeated request join the
job already queued or running for the same key instead of adding a second.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Assessment, AssessmentInput, Job

#: The channel compute workers LISTEN on; an enqueue NOTIFYs it.
JOBS_CHANNEL = "pw_jobs"


@dataclass(frozen=True, slots=True)
class JobRecord:
    id: int
    kind: str
    mission_id: str | None
    params: dict[str, Any]
    params_hash: str
    closure: str
    status: str
    priority: int
    attempts: int
    max_attempts: int
    run_after: datetime
    lease_owner: str | None
    lease_until: datetime | None
    progress: float | None
    message: str
    error: str | None
    assessment_id: int | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


@dataclass(frozen=True, slots=True)
class InputRef:
    """One thing an answer was built from (ADR-12 lineage)."""

    kind: str
    ref: str
    version: str = ""
    snapshot_id: int | None = None


@dataclass(frozen=True, slots=True)
class AssessmentRecord:
    id: int
    kind: str
    mission_id: str | None
    params: dict[str, Any]
    params_hash: str
    closure: str
    result: dict[str, Any]
    code_version: str
    compute_ms: float
    created_at: datetime
    inputs: tuple[InputRef, ...] = ()


def _job(r: Any) -> JobRecord:
    return JobRecord(
        id=int(r.id),
        kind=r.kind,
        mission_id=r.mission_id,
        params=dict(r.params),
        params_hash=r.params_hash,
        closure=r.closure,
        status=r.status,
        priority=int(r.priority),
        attempts=int(r.attempts),
        max_attempts=int(r.max_attempts),
        run_after=r.run_after,
        lease_owner=r.lease_owner,
        lease_until=r.lease_until,
        progress=r.progress,
        message=r.message,
        error=r.error,
        assessment_id=None if r.assessment_id is None else int(r.assessment_id),
        created_at=r.created_at,
        started_at=r.started_at,
        finished_at=r.finished_at,
    )


class JobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def enqueue(
        self,
        *,
        kind: str,
        params: dict[str, Any],
        params_hash: str,
        closure: str,
        mission_id: str | None,
        priority: int = 0,
        max_attempts: int = 3,
        requested_by: int | None = None,
    ) -> JobRecord:
        """Queue a job, or return the one already queued or running for this key."""
        stmt = (
            insert(Job)
            .values(
                kind=kind,
                params=params,
                params_hash=params_hash,
                closure=closure,
                mission_id=mission_id,
                priority=priority,
                max_attempts=max_attempts,
                requested_by=requested_by,
                status="queued",
                message="Waiting for a compute worker.",
            )
            .on_conflict_do_nothing(
                index_elements=[Job.kind, Job.params_hash, Job.closure],
                index_where=text("status IN ('queued', 'running')"),
            )
            .returning(Job)
        )
        row = (await self._s.execute(stmt)).scalar_one_or_none()
        if row is None:
            row = (
                await self._s.execute(
                    select(Job).where(
                        Job.kind == kind,
                        Job.params_hash == params_hash,
                        Job.closure == closure,
                        Job.status.in_(("queued", "running")),
                    )
                )
            ).scalar_one()
        else:
            await self._s.execute(text(f"NOTIFY {JOBS_CHANNEL}"))
        return _job(row)

    async def get(self, job_id: int) -> JobRecord | None:
        row = await self._s.get(Job, job_id)
        return None if row is None else _job(row)

    async def latest_for(self, kind: str, params_hash: str, closure: str) -> JobRecord | None:
        row = (
            await self._s.execute(
                select(Job)
                .where(Job.kind == kind, Job.params_hash == params_hash, Job.closure == closure)
                .order_by(Job.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        return None if row is None else _job(row)

    async def fail_exhausted(self) -> int:
        """Fail running jobs whose lease ran out on their last allowed attempt."""
        res = await self._s.execute(
            update(Job)
            .where(
                Job.status == "running",
                Job.lease_until < text("now()"),
                Job.attempts >= Job.max_attempts,
            )
            .values(
                status="failed",
                finished_at=text("now()"),
                lease_owner=None,
                lease_until=None,
                error="The compute worker stopped responding on every attempt.",
                message="Could not be worked out.",
            )
        )
        return int(getattr(res, "rowcount", 0) or 0)

    async def claim(self, owner: str, lease_s: float) -> JobRecord | None:
        """Lease the next runnable job: queued and due, or running with a dead lease."""
        sql = text(
            """
            UPDATE jobs SET
                status = 'running',
                lease_owner = :owner,
                lease_until = now() + make_interval(secs => :lease),
                heartbeat_at = now(),
                attempts = attempts + 1,
                started_at = coalesce(started_at, now()),
                message = 'Working it out.',
                progress = coalesce(progress, 0)
            WHERE id = (
                SELECT id FROM jobs
                WHERE (status = 'queued' AND run_after <= now())
                   OR (status = 'running' AND lease_until < now() AND attempts < max_attempts)
                ORDER BY priority DESC, id
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            )
            RETURNING *
            """
        )
        row = (await self._s.execute(sql, {"owner": owner, "lease": lease_s})).one_or_none()
        return None if row is None else _job(row)

    async def heartbeat(
        self,
        job_id: int,
        owner: str,
        lease_s: float,
        *,
        progress: float | None = None,
        message: str | None = None,
    ) -> bool:
        """Extend the lease. False when this worker no longer holds it."""
        values: dict[str, Any] = {
            "lease_until": func.now() + timedelta(seconds=float(lease_s)),
            "heartbeat_at": func.now(),
        }
        if progress is not None:
            values["progress"] = max(0.0, min(1.0, progress))
        if message is not None:
            values["message"] = message
        res = await self._s.execute(
            update(Job)
            .where(Job.id == job_id, Job.lease_owner == owner, Job.status == "running")
            .values(**values)
        )
        return bool(getattr(res, "rowcount", 0))

    async def finish(self, job_id: int, owner: str, assessment_id: int, message: str) -> bool:
        res = await self._s.execute(
            update(Job)
            .where(Job.id == job_id, Job.lease_owner == owner)
            .values(
                status="done",
                assessment_id=assessment_id,
                progress=1.0,
                message=message,
                error=None,
                finished_at=text("now()"),
                lease_owner=None,
                lease_until=None,
            )
        )
        return bool(getattr(res, "rowcount", 0))

    async def retry_or_fail(self, job: JobRecord, owner: str, error: str, backoff_s: float) -> str:
        """After a handler raised: queue it again with a delay, or give up."""
        if job.attempts < job.max_attempts:
            status, when = "queued", func.now() + timedelta(seconds=float(backoff_s))
            message = f"Failed on attempt {job.attempts}; trying again."
        else:
            status, when = "failed", func.now()
            message = "Could not be worked out."
        await self._s.execute(
            update(Job)
            .where(Job.id == job.id, Job.lease_owner == owner)
            .values(
                status=status,
                run_after=when,
                error=error[:4000],
                message=message,
                lease_owner=None,
                lease_until=None,
                finished_at=text("now()") if status == "failed" else None,
            )
        )
        return status


class AssessmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def save(
        self,
        *,
        kind: str,
        mission_id: str | None,
        params: dict[str, Any],
        params_hash: str,
        closure: str,
        result: dict[str, Any],
        code_version: str,
        compute_ms: float,
        inputs: list[InputRef],
        of_record: bool = False,
    ) -> int:
        row = (
            await self._s.execute(
                insert(Assessment)
                .values(
                    kind=kind,
                    mission_id=mission_id,
                    params=params,
                    params_hash=params_hash,
                    closure=closure,
                    result=result,
                    code_version=code_version,
                    compute_ms=compute_ms,
                    of_record=of_record,
                )
                .returning(Assessment.id)
            )
        ).scalar_one()
        if inputs:
            await self._s.execute(
                insert(AssessmentInput),
                [
                    {
                        "assessment_id": row,
                        "kind": i.kind,
                        "ref": i.ref[:200],
                        "version": i.version[:128],
                        "snapshot_id": i.snapshot_id,
                    }
                    for i in inputs
                ],
            )
        return int(row)

    async def latest(self, kind: str, params_hash: str, closure: str) -> AssessmentRecord | None:
        row = (
            await self._s.execute(
                select(Assessment)
                .where(
                    Assessment.kind == kind,
                    Assessment.params_hash == params_hash,
                    Assessment.closure == closure,
                )
                .order_by(Assessment.created_at.desc(), Assessment.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        return None if row is None else await self._with_inputs(row)

    async def get(self, assessment_id: int) -> AssessmentRecord | None:
        row = await self._s.get(Assessment, assessment_id)
        return None if row is None else await self._with_inputs(row)

    async def _with_inputs(self, row: Assessment) -> AssessmentRecord:
        inputs = (
            await self._s.execute(
                select(AssessmentInput)
                .where(AssessmentInput.assessment_id == row.id)
                .order_by(AssessmentInput.id)
            )
        ).scalars()
        return AssessmentRecord(
            id=int(row.id),
            kind=row.kind,
            mission_id=row.mission_id,
            params=dict(row.params),
            params_hash=row.params_hash,
            closure=row.closure,
            result=dict(row.result),
            code_version=row.code_version,
            compute_ms=float(row.compute_ms),
            created_at=row.created_at,
            inputs=tuple(
                InputRef(kind=i.kind, ref=i.ref, version=i.version, snapshot_id=i.snapshot_id)
                for i in inputs
            ),
        )
