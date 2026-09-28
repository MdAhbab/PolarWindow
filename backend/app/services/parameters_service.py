"""Values the project sets for itself (ADR-17), with who set them and when.

Each parameter has a definition here: its unit, its allowed range and what it
is for. Until someone enters it there is no value, only the reason; nothing
is filled in with a default that looks like a fact.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.quantity import Quantity
from app.db.repositories.pm import PmRepository
from app.services import audit_service, lifecycle
from app.services.auth_service import Claims


@dataclass(frozen=True, slots=True)
class Definition:
    id: str
    name: str
    unit: str
    lo: float
    hi: float
    why_missing: str


DEFINITIONS: tuple[Definition, ...] = (
    Definition(
        "battery_limit_h",
        "Battery limit: the longest night the lander is built to survive",
        "h",
        1.0,
        2000.0,
        "The lander's battery limit is not published; enter the one from its power budget.",
    ),
    Definition(
        "landing_sun_min_deg",
        "Lowest Sun height allowed at landing",
        "deg",
        -5.0,
        90.0,
        "No landing Sun height limit has been entered. IM-2's landing showed that a low Sun "
        "and long shadows can confuse camera navigation (see Lessons).",
    ),
    Definition(
        "landing_sun_max_deg",
        "Highest Sun height allowed at landing",
        "deg",
        -5.0,
        90.0,
        "No upper Sun height limit has been entered.",
    ),
    Definition(
        "surface_days",
        "Planned days on the surface (when the mission does not publish it)",
        "d",
        0.5,
        3650.0,
        "Enter the planned surface duration when the mission record does not give one.",
    ),
)
BY_ID = {d.id: d for d in DEFINITIONS}


class UnknownParameter(LookupError):
    pass


class BadValue(ValueError):
    pass


def _value(d: Definition, stored: dict[str, Any] | None) -> dict[str, Any]:
    if stored is None:
        return lifecycle.missing(d.unit, d.why_missing, provenance="entered")
    return lifecycle.q(
        Quantity(
            value=float(stored["value"]),
            unit=d.unit,
            provenance="entered",
            no_margin_reason="Entered by the project team as a limit, not measured.",
            source=stored["changed_by"],
        )
    )


async def list_parameters(session: AsyncSession) -> dict[str, Any]:
    stored = await PmRepository(session).parameters()
    return {
        "parameters": [
            {
                "id": d.id,
                "name": d.name,
                "value": _value(d, stored.get(d.id)),
                "note": (stored.get(d.id) or {}).get("note"),
                "changed_by": (stored.get(d.id) or {}).get("changed_by"),
                "changed_at": (stored.get(d.id) or {}).get("changed_at"),
            }
            for d in DEFINITIONS
        ]
    }


async def values(session: AsyncSession) -> dict[str, float]:
    """Entered values only, for the engines that use them."""
    return {k: float(v["value"]) for k, v in (await PmRepository(session).parameters()).items()}


async def set_parameter(
    session: AsyncSession, who: Claims, pid: str, value: float, note: str | None
) -> dict[str, Any]:
    d = BY_ID.get(pid)
    if d is None:
        raise UnknownParameter(pid)
    if not d.lo <= value <= d.hi:
        raise BadValue(f"{d.name}: {value} {d.unit} is outside {d.lo:g} to {d.hi:g} {d.unit}")
    repo = PmRepository(session)
    before = (await repo.parameters()).get(pid)
    await repo.put_parameter(pid, value, note, who.actor)
    await audit_service.record(
        session,
        who,
        action="set",
        entity="parameter",
        entity_id=pid,
        before=None if before is None else {"value": before["value"], "note": before["note"]},
        after={"value": value, "note": note},
    )
    return await list_parameters(session)
