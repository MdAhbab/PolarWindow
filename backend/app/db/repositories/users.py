"""Named people (ADR-17). Returns plain records, never ORM instances."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User


@dataclass(frozen=True, slots=True)
class UserRecord:
    id: int
    name: str
    team: str | None


def name_key(name: str, team: str | None) -> str:
    """One person per name and team, whatever the spacing or case."""
    norm = " ".join(name.split()).casefold()
    t = " ".join((team or "").split()).casefold()
    return f"{norm}|{t}"


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def sign_in(self, name: str, team: str | None) -> UserRecord:
        """The user with this name and team, created on first sign-in."""
        clean = " ".join(name.split())
        clean_team = " ".join(team.split()) if team and team.strip() else None
        stmt = (
            insert(User)
            .values(name=clean, team=clean_team, name_key=name_key(clean, clean_team))
            .on_conflict_do_update(
                index_elements=[User.name_key], set_={"last_seen_at": func.now()}
            )
            .returning(User.id, User.name, User.team)
        )
        row = (await self._s.execute(stmt)).one()
        return UserRecord(id=int(row.id), name=str(row.name), team=row.team)

    async def get(self, user_id: int) -> UserRecord | None:
        row = (
            await self._s.execute(select(User.id, User.name, User.team).where(User.id == user_id))
        ).one_or_none()
        return None if row is None else UserRecord(id=int(row.id), name=row.name, team=row.team)

    async def list(self) -> list[UserRecord]:
        rows = (
            await self._s.execute(select(User.id, User.name, User.team).order_by(User.id))
        ).all()
        return [UserRecord(id=int(r.id), name=r.name, team=r.team) for r in rows]
