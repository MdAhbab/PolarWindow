"""CLPS mission persistence (ADR-5).

Returns plain records, never ORM instances, like every repository here. The
mission table is small (tens of rows) and replaced whole on each seed, so a
load is one transaction that deletes and re-inserts: a partially updated
mission list is worse than a stale one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Mission, MissionPayload


@dataclass(frozen=True, slots=True)
class PayloadRecord:
    id: str
    name: str
    acronym: str | None
    organisation: str | None
    instrument_types: list[str]
    purpose: str
    source_url: str
    unconfirmed: bool


@dataclass(frozen=True, slots=True)
class MissionRecord:
    id: str
    name: str
    vehicle_name: str | None
    task_order: str | None
    provider: str | None
    lander: str | None
    status: str
    outcome_note: str
    region: str | None
    target_name: str | None
    target: dict[str, Any] | None
    ellipse: dict[str, Any] | None
    launch: dict[str, Any] | None
    landing: dict[str, Any] | None
    end_of_mission: dict[str, Any] | None
    planned_surface_days: float | None
    sort_at: datetime | None
    site_id: str | None
    sources: list[dict[str, Any]]
    unconfirmed_fields: list[str]
    notes: list[str]
    data_version: str
    payloads: list[PayloadRecord] = field(default_factory=list)
    #: Schema v2 facts (ADR-10); empty for a v1 row.
    lifecycle: dict[str, Any] = field(default_factory=dict)

    @property
    def payload_types(self) -> list[str]:
        seen: dict[str, None] = {}
        for p in self.payloads:
            for t in p.instrument_types:
                seen.setdefault(t, None)
        return list(seen)


def _record(row: Mission) -> MissionRecord:
    return MissionRecord(
        id=row.id,
        name=row.name,
        vehicle_name=row.vehicle_name,
        task_order=row.task_order,
        provider=row.provider,
        lander=row.lander,
        status=row.status,
        outcome_note=row.outcome_note,
        region=row.region,
        target_name=row.target_name,
        target=row.target,
        ellipse=row.ellipse,
        launch=row.launch,
        landing=row.landing,
        end_of_mission=row.end_of_mission,
        planned_surface_days=row.planned_surface_days,
        sort_at=row.sort_at,
        site_id=row.site_id,
        sources=list(row.sources or []),
        unconfirmed_fields=list(row.unconfirmed_fields or []),
        notes=list(row.notes or []),
        data_version=row.data_version,
        lifecycle=dict(row.lifecycle or {}),
        payloads=[
            PayloadRecord(
                id=p.id,
                name=p.name,
                acronym=p.acronym,
                organisation=p.organisation,
                instrument_types=list(p.instrument_types),
                purpose=p.purpose,
                source_url=p.source_url,
                unconfirmed=p.unconfirmed,
            )
            for p in row.payloads
        ],
    )


class MissionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def replace_all(
        self, missions: list[dict[str, Any]], payloads: list[dict[str, Any]]
    ) -> None:
        """Make the tables exactly the given rows, in the caller's transaction."""
        await self._s.execute(delete(MissionPayload))
        await self._s.execute(delete(Mission))
        if missions:
            await self._s.execute(pg_insert(Mission).values(missions))
        if payloads:
            await self._s.execute(pg_insert(MissionPayload).values(payloads))

    async def find(
        self,
        *,
        statuses: list[str] | None = None,
        provider: str | None = None,
        payload_types: list[str] | None = None,
        region: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        q: str | None = None,
        site_ids: list[str] | None = None,
    ) -> list[MissionRecord]:
        stmt = select(Mission).options(selectinload(Mission.payloads))
        if statuses:
            stmt = stmt.where(Mission.status.in_(statuses))
        if provider:
            stmt = stmt.where(Mission.provider == provider)
        if region:
            stmt = stmt.where(Mission.region == region)
        if date_from is not None:
            stmt = stmt.where(Mission.sort_at >= date_from)
        if date_to is not None:
            stmt = stmt.where(Mission.sort_at <= date_to)
        if site_ids is not None:
            stmt = stmt.where(Mission.site_id.in_(site_ids))
        if payload_types:
            # Any-of: a mission qualifies when one of its payloads carries one of
            # the requested types. `&&` is array overlap, served by the GIN index.
            carrying = select(MissionPayload.mission_id).where(
                MissionPayload.instrument_types.overlap(payload_types)
            )
            stmt = stmt.where(Mission.id.in_(carrying))
        if q:
            like = f"%{q.lower()}%"
            stmt = stmt.where(
                Mission.name.ilike(like)
                | Mission.provider.ilike(like)
                | Mission.target_name.ilike(like)
                | Mission.task_order.ilike(like)
                | Mission.vehicle_name.ilike(like)
            )
        # Undated missions last; then by date; then by name, so the order is stable.
        stmt = stmt.order_by(Mission.sort_at.is_(None), Mission.sort_at, Mission.name)
        rows = (await self._s.execute(stmt)).scalars().all()
        return [_record(r) for r in rows]

    async def count(self) -> int:
        return int((await self._s.execute(select(func.count()).select_from(Mission))).scalar_one())

    async def get(self, mission_id: str) -> MissionRecord | None:
        stmt = (
            select(Mission).options(selectinload(Mission.payloads)).where(Mission.id == mission_id)
        )
        row = (await self._s.execute(stmt)).scalars().first()
        return None if row is None else _record(row)

    async def by_site(self, site_ids: list[str]) -> dict[str, list[MissionRecord]]:
        """Missions grouped by the site that stands for their target."""
        if not site_ids:
            return {}
        out: dict[str, list[MissionRecord]] = {}
        for m in await self.find(site_ids=site_ids):
            if m.site_id is not None:
                out.setdefault(m.site_id, []).append(m)
        return out
