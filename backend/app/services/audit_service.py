"""The change history (ADR-17): who changed what, when, from what, to what.

Every entered record (readiness items, parts, risks, booked passes, official
forecasts, team limits, parameters) writes one entry here in the same
transaction as the change itself, so a change without its history, or a
history entry without its change, cannot be committed.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.audit import AuditRecord, AuditRepository, ChainCheck
from app.services.auth_service import Claims

#: The entities the history covers, as the contract names them.
ENTITIES = frozenset(
    {
        "ready_item",
        "part",
        "risk",
        "booking",
        "forecast",
        "limits",
        "parameter",
        "lesson",
        "milestone",
        "feed",
        "job",
    }
)


class NotNamed(PermissionError):
    """A change was attempted from a session with no name."""


async def record(
    session: AsyncSession,
    who: Claims,
    *,
    action: str,
    entity: str,
    entity_id: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    note: str | None = None,
    mission_id: str | None = None,
    request_id: str | None = None,
) -> AuditRecord:
    if entity not in ENTITIES:
        raise ValueError(f"unknown entity {entity!r}")
    if not who.named:
        raise NotNamed("Changes are recorded against a name; this session has none.")
    return await AuditRepository(session).append(
        user_id=who.user_id,
        actor=who.actor,
        action=action,
        entity=entity,
        entity_id=entity_id,
        mission_id=mission_id,
        before=before,
        after=after,
        note=note,
        request_id=request_id,
    )


def entry_out(e: AuditRecord) -> dict[str, Any]:
    """The contract's history entry: ``{at, by, before, after, note}`` (+ action)."""
    return {
        "at": e.at,
        "by": e.actor,
        "action": e.action,
        "before": e.before,
        "after": e.after,
        "note": e.note,
    }


async def history(session: AsyncSession, entity: str, entity_id: str) -> list[dict[str, Any]]:
    return [entry_out(e) for e in await AuditRepository(session).history(entity, entity_id)]


async def verify(session: AsyncSession) -> ChainCheck:
    return await AuditRepository(session).verify()
