"""The project manager's settings, one JSON value per key."""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AppSetting


class AppSettingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get(self, key: str) -> dict[str, Any] | None:
        row = await self._s.get(AppSetting, key)
        return dict(row.value) if row else None

    async def put(self, key: str, value: dict[str, Any], by: str | None) -> None:
        stmt = insert(AppSetting).values(key=key, value=value, updated_by=by)
        stmt = stmt.on_conflict_do_update(
            index_elements=[AppSetting.key],
            set_={"value": value, "updated_by": by, "updated_at": func.now()},
        )
        await self._s.execute(stmt)

    async def remove(self, key: str) -> None:
        await self._s.execute(delete(AppSetting).where(AppSetting.key == key))
