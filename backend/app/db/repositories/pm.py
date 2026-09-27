"""The project manager's records (ADR-17). Plain records in, plain records out.

The services write the change history in the same transaction; this module
only stores the current state of each record.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    ContactBooking,
    LessonAdoption,
    Milestone,
    OfficialForecast,
    Part,
    PmParameter,
    ReadinessItem,
    ReturnLimits,
    RiskRecord,
    VehicleLimit,
)


@dataclass(frozen=True, slots=True)
class ItemRow:
    id: str
    mission_id: str
    kind: str
    name: str
    organisation: str | None
    state: str
    blocked_from: str | None
    blocked_reason: str | None
    changed_on: str | None
    changed_by: str | None
    evidence_url: str | None
    source: str
    tests: list[dict[str, Any]]
    position: int


@dataclass(frozen=True, slots=True)
class PartRow:
    id: str
    mission_id: str
    name: str
    part_number: str | None
    serial: str | None
    parent_item_id: str | None
    status: str
    location: str | None
    changed_at: datetime
    changed_by: str


@dataclass(frozen=True, slots=True)
class RiskRow:
    id: str
    mission_id: str
    title: str
    cause: str
    consequence_text: str
    scale_id: str
    ratings: list[dict[str, Any]]
    trend: str
    owner: str | None
    mitigation: str | None
    links: dict[str, Any]
    changed_at: datetime
    changed_by: str


def _item(r: ReadinessItem) -> ItemRow:
    return ItemRow(
        id=r.id,
        mission_id=r.mission_id,
        kind=r.kind,
        name=r.name,
        organisation=r.organisation,
        state=r.state,
        blocked_from=r.blocked_from,
        blocked_reason=r.blocked_reason,
        changed_on=r.changed_on,
        changed_by=r.changed_by,
        evidence_url=r.evidence_url,
        source=r.source,
        tests=list(r.tests or []),
        position=int(r.position),
    )


def _part(r: Part) -> PartRow:
    return PartRow(
        id=r.id,
        mission_id=r.mission_id,
        name=r.name,
        part_number=r.part_number,
        serial=r.serial,
        parent_item_id=r.parent_item_id,
        status=r.status,
        location=r.location,
        changed_at=r.changed_at,
        changed_by=r.changed_by,
    )


def _risk(r: RiskRecord) -> RiskRow:
    return RiskRow(
        id=r.id,
        mission_id=r.mission_id,
        title=r.title,
        cause=r.cause,
        consequence_text=r.consequence_text,
        scale_id=r.scale_id,
        ratings=list(r.ratings),
        trend=r.trend,
        owner=r.owner,
        mitigation=r.mitigation,
        links=dict(r.links),
        changed_at=r.changed_at,
        changed_by=r.changed_by,
    )


class PmRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    # --- readiness items -----------------------------------------------------

    async def items(self, mission_id: str) -> list[ItemRow]:
        rows = (
            await self._s.execute(
                select(ReadinessItem)
                .where(ReadinessItem.mission_id == mission_id)
                .order_by(ReadinessItem.position, ReadinessItem.id)
            )
        ).scalars()
        return [_item(r) for r in rows]

    async def item(self, item_id: str, *, lock: bool = False) -> ItemRow | None:
        q = select(ReadinessItem).where(ReadinessItem.id == item_id)
        if lock:
            q = q.with_for_update()
        row = (await self._s.execute(q)).scalar_one_or_none()
        return None if row is None else _item(row)

    async def put_item(self, row: ItemRow) -> None:
        values = {f: getattr(row, f) for f in ItemRow.__dataclass_fields__}
        stmt = (
            insert(ReadinessItem)
            .values(**values)
            .on_conflict_do_update(index_elements=[ReadinessItem.id], set_=values)
        )
        await self._s.execute(stmt)

    # --- milestones ----------------------------------------------------------

    async def milestones(self, mission_id: str) -> list[dict[str, Any]]:
        rows = (
            await self._s.execute(
                select(Milestone)
                .where(Milestone.mission_id == mission_id)
                .order_by(Milestone.on_date)
            )
        ).scalars()
        return [
            {
                "id": r.id,
                "name": r.name,
                "on_date": r.on_date,
                "done": r.done,
                "source_url": r.source_url,
                "entered_by": r.entered_by,
                "entered_at": r.entered_at,
            }
            for r in rows
        ]

    # --- parts ---------------------------------------------------------------

    async def parts(self, mission_id: str) -> list[PartRow]:
        rows = (
            await self._s.execute(
                select(Part).where(Part.mission_id == mission_id).order_by(Part.name, Part.id)
            )
        ).scalars()
        return [_part(r) for r in rows]

    async def part(self, part_id: str, *, lock: bool = False) -> PartRow | None:
        q = select(Part).where(Part.id == part_id)
        if lock:
            q = q.with_for_update()
        row = (await self._s.execute(q)).scalar_one_or_none()
        return None if row is None else _part(row)

    async def put_part(self, values: dict[str, Any]) -> PartRow:
        stmt = (
            insert(Part)
            .values(**values, changed_at=func.now())
            .on_conflict_do_update(
                index_elements=[Part.id], set_={**values, "changed_at": func.now()}
            )
            .returning(Part)
        )
        return _part((await self._s.execute(stmt)).scalar_one())

    # --- risks ---------------------------------------------------------------

    async def risks(self, mission_id: str) -> list[RiskRow]:
        rows = (
            await self._s.execute(
                select(RiskRecord)
                .where(RiskRecord.mission_id == mission_id)
                .order_by(RiskRecord.changed_at.desc())
            )
        ).scalars()
        return [_risk(r) for r in rows]

    async def risk(self, risk_id: str, *, lock: bool = False) -> RiskRow | None:
        q = select(RiskRecord).where(RiskRecord.id == risk_id)
        if lock:
            q = q.with_for_update()
        row = (await self._s.execute(q)).scalar_one_or_none()
        return None if row is None else _risk(row)

    async def put_risk(self, values: dict[str, Any]) -> RiskRow:
        stmt = (
            insert(RiskRecord)
            .values(**values, changed_at=func.now())
            .on_conflict_do_update(
                index_elements=[RiskRecord.id], set_={**values, "changed_at": func.now()}
            )
            .returning(RiskRecord)
        )
        return _risk((await self._s.execute(stmt)).scalar_one())

    # --- lessons -------------------------------------------------------------

    async def adoptions(self, mission_id: str) -> dict[str, str]:
        rows = (
            await self._s.execute(
                select(LessonAdoption.lesson_id, LessonAdoption.item_id).where(
                    LessonAdoption.mission_id == mission_id
                )
            )
        ).all()
        return {r.lesson_id: r.item_id for r in rows}

    async def adopt(self, mission_id: str, lesson_id: str, item_id: str, by: str) -> bool:
        stmt = (
            insert(LessonAdoption)
            .values(mission_id=mission_id, lesson_id=lesson_id, item_id=item_id, adopted_by=by)
            .on_conflict_do_nothing()
            .returning(LessonAdoption.lesson_id)
        )
        return (await self._s.execute(stmt)).scalar_one_or_none() is not None

    # --- parameters ----------------------------------------------------------

    async def parameters(self) -> dict[str, dict[str, Any]]:
        rows = (await self._s.execute(select(PmParameter))).scalars()
        return {
            r.id: {
                "value": r.value,
                "note": r.note,
                "changed_by": r.changed_by,
                "changed_at": r.changed_at,
            }
            for r in rows
        }

    async def put_parameter(self, pid: str, value: float, note: str | None, by: str) -> None:
        values = {"value": value, "note": note, "changed_by": by}
        await self._s.execute(
            insert(PmParameter)
            .values(id=pid, **values)
            .on_conflict_do_update(
                index_elements=[PmParameter.id], set_={**values, "changed_at": func.now()}
            )
        )

    # --- bookings ------------------------------------------------------------

    async def bookings(self, mission_id: str) -> list[dict[str, Any]]:
        rows = (
            await self._s.execute(
                select(ContactBooking)
                .where(ContactBooking.mission_id == mission_id)
                .order_by(ContactBooking.start)
            )
        ).scalars()
        return [
            {
                "id": int(r.id),
                "station": r.station,
                "start": r.start,
                "end": r.end,
                "note": r.note,
                "entered_by": r.entered_by,
                "entered_at": r.entered_at,
            }
            for r in rows
        ]

    async def add_booking(
        self,
        mission_id: str,
        station: str,
        start: datetime,
        end: datetime,
        note: str | None,
        by: str,
    ) -> int:
        row = (
            await self._s.execute(
                insert(ContactBooking)
                .values(
                    mission_id=mission_id,
                    station=station,
                    start=start,
                    end=end,
                    note=note,
                    entered_by=by,
                )
                .returning(ContactBooking.id)
            )
        ).scalar_one()
        return int(row)

    # --- launch weather entries ----------------------------------------------

    async def official_forecast(self, mission_id: str) -> dict[str, Any] | None:
        row = (
            await self._s.execute(
                select(OfficialForecast)
                .where(OfficialForecast.mission_id == mission_id)
                .order_by(OfficialForecast.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        return {
            "id": int(row.id),
            "probability_pct": row.probability_pct,
            "concerns": list(row.concerns),
            "pdf_url": row.pdf_url,
            "entered_by": row.entered_by,
            "entered_at": row.entered_at,
        }

    async def add_official_forecast(
        self, mission_id: str, pct: float, concerns: list[str], pdf_url: str, by: str
    ) -> int:
        row = (
            await self._s.execute(
                insert(OfficialForecast)
                .values(
                    mission_id=mission_id,
                    probability_pct=pct,
                    concerns=concerns,
                    pdf_url=pdf_url,
                    entered_by=by,
                )
                .returning(OfficialForecast.id)
            )
        ).scalar_one()
        return int(row)

    async def vehicle_limits(self, vehicle_id: str) -> list[dict[str, Any]]:
        rows = (
            await self._s.execute(
                select(VehicleLimit)
                .where(VehicleLimit.vehicle_id == vehicle_id)
                .order_by(VehicleLimit.rule_id)
            )
        ).scalars()
        return [
            {
                "rule_id": r.rule_id,
                "value": r.value,
                "unit": r.unit,
                "note": r.note,
                "entered_by": r.entered_by,
                "entered_at": r.entered_at,
            }
            for r in rows
        ]

    async def replace_vehicle_limits(
        self, vehicle_id: str, limits: list[dict[str, Any]], by: str
    ) -> None:
        await self._s.execute(delete(VehicleLimit).where(VehicleLimit.vehicle_id == vehicle_id))
        if limits:
            await self._s.execute(
                insert(VehicleLimit),
                [{**x, "vehicle_id": vehicle_id, "entered_by": by} for x in limits],
            )

    async def return_limits(self, mission_id: str) -> dict[str, Any] | None:
        row = await self._s.get(ReturnLimits, mission_id)
        if row is None:
            return None
        return {
            "booster": dict(row.booster),
            "capsule": dict(row.capsule),
            "entered_by": row.entered_by,
            "entered_at": row.entered_at,
        }

    async def put_return_limits(
        self, mission_id: str, booster: dict[str, Any], capsule: dict[str, Any], by: str
    ) -> None:
        values = {"booster": booster, "capsule": capsule, "entered_by": by}
        await self._s.execute(
            insert(ReturnLimits)
            .values(mission_id=mission_id, **values)
            .on_conflict_do_update(
                index_elements=[ReturnLimits.mission_id],
                set_={**values, "entered_at": func.now()},
            )
        )
