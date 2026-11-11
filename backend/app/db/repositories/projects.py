"""Projects the team enters (``missions.origin = 'project'``) and the files read for them.

A project is a mission row, so reading one goes through ``MissionRepository``
like any other mission; this repository holds the writes, which only ever
touch rows whose origin is ``project``. Returns plain records, never ORM
instances.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Mission, MissionPayload, ProjectIntake, Site, SiteWindowMetrics
from app.db.repositories.missions import PROJECT


@dataclass(frozen=True, slots=True)
class IntakeRecord:
    id: int
    filename: str
    media_type: str
    size_bytes: int
    sha256: str
    method: str
    model: str | None
    extracted: dict[str, Any]
    warnings: list[str]
    created_by: int | None
    created_at: datetime


class ProjectRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def ids_starting(self, prefix: str) -> set[str]:
        """Every mission id that starts with ``prefix`` (to find a free one)."""
        like = prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        rows = await self._s.execute(select(Mission.id).where(Mission.id.like(like, escape="\\")))
        return {str(r) for r in rows.scalars().all()}

    async def insert(
        self, row: dict[str, Any], payloads: list[dict[str, Any]], owner_id: int | None
    ) -> None:
        await self._s.execute(
            pg_insert(Mission).values({**row, "origin": PROJECT, "owner_id": owner_id})
        )
        if payloads:
            await self._s.execute(pg_insert(MissionPayload).values(payloads))

    async def replace(
        self, mission_id: str, row: dict[str, Any], payloads: list[dict[str, Any]]
    ) -> bool:
        """Overwrite a project's facts and payloads. False when it is not a project."""
        values = {k: v for k, v in row.items() if k not in ("id", "origin", "owner_id")}
        res = await self._s.execute(
            update(Mission)
            .where(Mission.id == mission_id, Mission.origin == PROJECT)
            .values(**values)
        )
        if not getattr(res, "rowcount", 0):
            return False
        await self._s.execute(delete(MissionPayload).where(MissionPayload.mission_id == mission_id))
        if payloads:
            await self._s.execute(pg_insert(MissionPayload).values(payloads))
        return True

    async def delete(self, mission_id: str) -> bool:
        """Remove a project and its payloads. False when it is not a project."""
        found = (
            await self._s.execute(
                select(Mission.id).where(Mission.id == mission_id, Mission.origin == PROJECT)
            )
        ).scalar_one_or_none()
        if found is None:
            return False
        await self._s.execute(delete(MissionPayload).where(MissionPayload.mission_id == mission_id))
        await self._s.execute(
            delete(Mission).where(Mission.id == mission_id, Mission.origin == PROJECT)
        )
        return True

    async def site_in_use(self, site_id: str, other_than: str) -> bool:
        """Whether a mission other than ``other_than`` targets this site."""
        row = (
            await self._s.execute(
                select(Mission.id)
                .where(Mission.site_id == site_id, Mission.id != other_than)
                .limit(1)
            )
        ).scalar_one_or_none()
        return row is not None

    async def delete_site(self, site_id: str) -> None:
        """Remove a site (its skyline and cached numbers go with it, by cascade)."""
        await self._s.execute(delete(Site).where(Site.id == site_id))

    async def forget_site_numbers(self, site_id: str) -> None:
        """Drop a site's cached four numbers: its coordinate changed."""
        await self._s.execute(delete(SiteWindowMetrics).where(SiteWindowMetrics.site_id == site_id))

    async def save_intake(
        self,
        *,
        filename: str,
        media_type: str,
        size_bytes: int,
        sha256: str,
        method: str,
        model: str | None,
        extracted: dict[str, Any],
        warnings: list[str],
        text_excerpt: str,
        created_by: int | None,
    ) -> int:
        row = (
            await self._s.execute(
                pg_insert(ProjectIntake)
                .values(
                    filename=filename,
                    media_type=media_type,
                    size_bytes=size_bytes,
                    sha256=sha256,
                    method=method,
                    model=model,
                    extracted=extracted,
                    warnings=warnings,
                    text_excerpt=text_excerpt,
                    created_by=created_by,
                )
                .returning(ProjectIntake.id)
            )
        ).scalar_one()
        return int(row)

    async def get_intake(self, intake_id: int) -> IntakeRecord | None:
        r = await self._s.get(ProjectIntake, intake_id)
        if r is None:
            return None
        return IntakeRecord(
            id=int(r.id),
            filename=r.filename,
            media_type=r.media_type,
            size_bytes=int(r.size_bytes),
            sha256=r.sha256,
            method=r.method,
            model=r.model,
            extracted=dict(r.extracted or {}),
            warnings=[str(w) for w in r.warnings or []],
            created_by=r.created_by,
            created_at=r.created_at,
        )
