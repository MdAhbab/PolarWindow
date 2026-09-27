"""The append-only change history (ADR-17).

The database numbers, links and hashes each entry (see the lifecycle
foundations migration); this repository only inserts and reads. There is no
update or delete here, and the table's triggers refuse both anyway.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditEntry


@dataclass(frozen=True, slots=True)
class AuditRecord:
    seq: int
    at: datetime
    user_id: int | None
    actor: str
    action: str
    entity: str
    entity_id: str
    mission_id: str | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    note: str | None
    hash: str


@dataclass(frozen=True, slots=True)
class ChainCheck:
    checked: int
    first_bad: int | None

    @property
    def intact(self) -> bool:
        return self.first_bad is None


def _record(r: Any) -> AuditRecord:
    return AuditRecord(
        seq=int(r.seq),
        at=r.at,
        user_id=r.user_id,
        actor=r.actor,
        action=r.action,
        entity=r.entity,
        entity_id=r.entity_id,
        mission_id=r.mission_id,
        before=r.before,
        after=r.after,
        note=r.note,
        hash=r.hash,
    )


class AuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def append(
        self,
        *,
        user_id: int | None,
        actor: str,
        action: str,
        entity: str,
        entity_id: str,
        mission_id: str | None,
        before: dict[str, Any] | None,
        after: dict[str, Any] | None,
        note: str | None,
        request_id: str | None,
    ) -> AuditRecord:
        stmt = (
            insert(AuditEntry)
            .values(
                user_id=user_id,
                actor=actor,
                action=action,
                entity=entity,
                entity_id=entity_id,
                mission_id=mission_id,
                before=before,
                after=after,
                note=note,
                request_id=request_id,
                # Placeholders: the trigger sets seq, at and both hashes.
                seq=0,
                prev_hash="",
                hash="",
            )
            .returning(AuditEntry)
        )
        row = (await self._s.execute(stmt)).scalar_one()
        return _record(row)

    async def history(self, entity: str, entity_id: str) -> list[AuditRecord]:
        rows = (
            await self._s.execute(
                select(AuditEntry)
                .where(AuditEntry.entity == entity, AuditEntry.entity_id == entity_id)
                .order_by(AuditEntry.seq)
            )
        ).scalars()
        return [_record(r) for r in rows]

    async def for_mission(self, mission_id: str, limit: int = 200) -> list[AuditRecord]:
        rows = (
            await self._s.execute(
                select(AuditEntry)
                .where(AuditEntry.mission_id == mission_id)
                .order_by(AuditEntry.seq.desc())
                .limit(limit)
            )
        ).scalars()
        return [_record(r) for r in rows]

    async def verify(self) -> ChainCheck:
        row = (await self._s.execute(text("SELECT first_bad, checked FROM audit_verify()"))).one()
        return ChainCheck(
            checked=int(row.checked),
            first_bad=None if row.first_bad is None else int(row.first_bad),
        )
