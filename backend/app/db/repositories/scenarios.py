"""Scenario persistence and the activity query. Plain records in, plain records out."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, desc, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Job, Mission, Scenario


@dataclass(frozen=True, slots=True)
class ScenarioRecord:
    id: str
    mission_id: str
    key: str
    name: str
    prompt: str | None
    given: dict[str, Any]
    sections: list[str]
    preset: bool
    status: str
    progress: float
    message: str
    assumptions: list[dict[str, Any]]
    phases: list[dict[str, Any]]
    summaries: dict[str, Any]
    results: dict[str, Any] | None
    error: str | None
    job_id: int | None
    created_by: int | None
    created_by_name: str | None
    created_at: datetime
    finished_at: datetime | None


@dataclass(frozen=True, slots=True)
class ActivityRow:
    kind: str
    ref: str
    mission_id: str | None
    mission_name: str | None
    status: str
    progress: float | None
    message: str
    label: str | None
    started_at: datetime
    finished_at: datetime | None
    extra: dict[str, Any] = field(default_factory=dict)


def _rec(r: Scenario) -> ScenarioRecord:
    return ScenarioRecord(
        id=r.id,
        mission_id=r.mission_id,
        key=r.key,
        name=r.name,
        prompt=r.prompt,
        given=dict(r.given or {}),
        sections=list(r.sections or []),
        preset=bool(r.preset),
        status=r.status,
        progress=float(r.progress or 0.0),
        message=r.message or "",
        assumptions=list(r.assumptions or []),
        phases=list(r.phases or []),
        summaries=dict(r.summaries or {}),
        results=None if r.results is None else dict(r.results),
        error=r.error,
        job_id=r.job_id,
        created_by=r.created_by,
        created_by_name=r.created_by_name,
        created_at=r.created_at,
        finished_at=r.finished_at,
    )


def _now() -> datetime:
    return datetime.now(UTC)


class ScenarioRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get(self, scenario_id: str) -> ScenarioRecord | None:
        row = await self._s.get(Scenario, scenario_id)
        return None if row is None else _rec(row)

    async def by_key(self, key: str) -> ScenarioRecord | None:
        row = (
            await self._s.execute(select(Scenario).where(Scenario.key == key))
        ).scalar_one_or_none()
        return None if row is None else _rec(row)

    async def for_mission(self, mission_id: str, *, limit: int = 100) -> list[ScenarioRecord]:
        """Presets first, then newest."""
        stmt = (
            select(Scenario)
            .where(Scenario.mission_id == mission_id)
            .order_by(desc(Scenario.preset), desc(Scenario.created_at), Scenario.id)
            .limit(limit)
        )
        return [_rec(r) for r in (await self._s.execute(stmt)).scalars()]

    async def create(
        self,
        *,
        scenario_id: str,
        mission_id: str,
        key: str,
        name: str,
        prompt: str | None,
        given: dict[str, Any],
        sections: list[str],
        preset: bool,
        phases: list[dict[str, Any]],
        created_by: int | None,
        created_by_name: str | None,
    ) -> tuple[ScenarioRecord, bool]:
        """Insert, or return the row that already has this key. ``(record, created)``."""
        stmt = (
            pg_insert(Scenario)
            .values(
                id=scenario_id,
                mission_id=mission_id,
                key=key,
                name=name,
                prompt=prompt,
                given=given,
                sections=sections,
                preset=preset,
                status="queued",
                progress=0.0,
                message="Waiting for a compute worker.",
                phases=phases,
                created_by=created_by,
                created_by_name=created_by_name,
            )
            .on_conflict_do_nothing(index_elements=[Scenario.key])
            .returning(Scenario)
        )
        row = (await self._s.execute(stmt)).scalar_one_or_none()
        if row is not None:
            return _rec(row), True
        found = await self.by_key(key)
        assert found is not None
        return found, False

    async def set_job(self, scenario_id: str, job_id: int) -> None:
        await self._s.execute(
            update(Scenario).where(Scenario.id == scenario_id).values(job_id=job_id)
        )

    async def progress(
        self,
        scenario_id: str,
        *,
        status: str = "running",
        progress: float,
        message: str,
        phases: list[dict[str, Any]],
        assumptions: list[dict[str, Any]] | None = None,
    ) -> None:
        values: dict[str, Any] = {
            "status": status,
            "progress": progress,
            "message": message,
            "phases": phases,
        }
        if assumptions is not None:
            values["assumptions"] = assumptions
        await self._s.execute(update(Scenario).where(Scenario.id == scenario_id).values(**values))

    async def finish(
        self,
        scenario_id: str,
        *,
        results: dict[str, Any],
        summaries: dict[str, str],
        assumptions: list[dict[str, Any]],
        phases: list[dict[str, Any]],
        message: str,
    ) -> None:
        await self._s.execute(
            update(Scenario)
            .where(Scenario.id == scenario_id)
            .values(
                status="done",
                progress=1.0,
                message=message,
                results=results,
                summaries=summaries,
                assumptions=assumptions,
                phases=phases,
                error=None,
                finished_at=_now(),
            )
        )

    async def fail(self, scenario_id: str, error: str) -> None:
        await self._s.execute(
            update(Scenario)
            .where(Scenario.id == scenario_id, Scenario.status.in_(("queued", "running")))
            .values(
                status="failed",
                message="Could not be worked out.",
                error=error[:1000],
                finished_at=_now(),
            )
        )

    async def requeue(self, scenario_id: str) -> None:
        await self._s.execute(
            update(Scenario)
            .where(Scenario.id == scenario_id)
            .values(
                status="queued",
                progress=0.0,
                message="Waiting for a compute worker.",
                error=None,
                finished_at=None,
            )
        )

    async def delete(self, scenario_id: str) -> bool:
        res = await self._s.execute(delete(Scenario).where(Scenario.id == scenario_id))
        return bool(res.rowcount)


class ActivityRepository:
    """Jobs and scenarios in progress or just finished."""

    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def jobs(self, since: datetime, kinds: tuple[str, ...]) -> list[ActivityRow]:
        stmt = (
            select(Job, Mission.name)
            .outerjoin(Mission, Mission.id == Job.mission_id)
            .where(
                Job.kind.in_(kinds),
                or_(Job.status.in_(("queued", "running")), Job.finished_at >= since),
            )
            .order_by(Job.id)
            .limit(200)
        )
        out = []
        for j, mname in (await self._s.execute(stmt)).all():
            out.append(
                ActivityRow(
                    kind=j.kind,
                    ref=str(j.id),
                    mission_id=j.mission_id,
                    mission_name=mname,
                    status=j.status,
                    progress=j.progress,
                    message=j.message or "",
                    label=None,
                    started_at=j.created_at,
                    finished_at=j.finished_at,
                )
            )
        return out

    async def scenarios(self, since: datetime) -> list[ActivityRow]:
        stmt = (
            select(Scenario, Mission.name)
            .outerjoin(Mission, Mission.id == Scenario.mission_id)
            .where(or_(Scenario.status.in_(("queued", "running")), Scenario.finished_at >= since))
            .order_by(Scenario.created_at)
            .limit(200)
        )
        out = []
        for s, mname in (await self._s.execute(stmt)).all():
            out.append(
                ActivityRow(
                    kind="scenario",
                    ref=s.id,
                    mission_id=s.mission_id,
                    mission_name=mname,
                    status=s.status,
                    progress=s.progress,
                    message=s.message or "",
                    label=s.name,
                    started_at=s.created_at,
                    finished_at=s.finished_at,
                    extra={"sections": list(s.sections or [])},
                )
            )
        return out
