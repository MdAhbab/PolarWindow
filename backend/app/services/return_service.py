"""Return (T4 B2): where the booster comes down, and whether anything comes back.

The booster's landing is read from the cited recovery zones (Launch Library
2's landing records of the flown launches) or, for a launch still to come,
from the vehicle's usual practice. Sea and wind limits for recovery are not
published by the launch providers; the team enters them. Nothing returns
from the Moon on the CLPS missions, so the capsule part says so.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.quantity import Quantity
from app.data import catalogues
from app.db.repositories.missions import MissionRecord, MissionRepository
from app.db.repositories.pm import PmRepository
from app.services import audit_service, lifecycle
from app.services.auth_service import Claims
from app.services.mission_service import MissionNotFound

UNITS = {"wave_height_m": "m", "wind_m_s": "m/s"}


class BadRequest(ValueError):
    pass


def _limits(entered: dict[str, Any] | None, part: str) -> dict[str, Any]:
    stored = (entered or {}).get(part) or {}
    out = {}
    for k, unit in UNITS.items():
        v = stored.get(k)
        if v is None:
            out[k] = lifecycle.missing(
                unit,
                "Not published by the launch provider; the team can enter the limit it is "
                "given.",
                provenance="entered",
            )
        else:
            out[k] = lifecycle.q(
                Quantity(
                    value=float(v),
                    unit=unit,
                    provenance="entered",
                    no_margin_reason="A limit the team entered.",
                    source=str((entered or {}).get("entered_by")),
                )
            )
    return out


def _zone_of(m: MissionRecord) -> Any | None:
    for z in catalogues.load("recovery_zones").records:
        if m.id in z.used_by:
            return z
    return None


def _flown_summary(names: dict[str, str]) -> str:
    zones = catalogues.load("recovery_zones").records
    parts = []
    for z in zones:
        for mid in z.used_by:
            where = (
                z.name
                if z.kind == "booster_land"
                else f"a droneship {z.downrange_km:.0f} km downrange"
            )
            parts.append(f"{names.get(mid, mid)} on {where}")
    return "; ".join(parts)


def _booster(
    m: MissionRecord, entered: dict[str, Any] | None, names: dict[str, str]
) -> dict[str, Any] | None:
    lc = m.lifecycle or {}
    vid = lc.get("vehicle_id")
    if not vid:
        return None
    flown = bool(lc.get("t0"))
    z = _zone_of(m)
    past = "This launch is in the past; the sea and wind then were not recorded."
    if z is not None:
        land = z.kind == "booster_land"
        zone = (
            {"lat_deg": z.lat_deg, "lon_deg": z.lon_deg, "pm_km": None}
            if z.lat_deg is not None and z.lon_deg is not None
            else None
        )
        note = (
            f"The booster came back to {z.name} (Launch Library 2)."
            if land
            else f"The booster landed on {z.name}, {z.downrange_km:.0f} km downrange (Launch "
            "Library 2); the droneship's position is not published."
        )
        landing = "land" if land else "droneship"
    else:
        v = catalogues.load("vehicles").get(vid)
        how = v.booster_recovery
        landing = {"droneship": "droneship", "land": "land", "expended": "expended"}.get(
            how or "", "unknown"
        )
        zone = None
        if how == "droneship_or_land":
            note = (
                f"{v.name} boosters land on a droneship or back at the Cape, decided for each "
                f"launch and not yet published for this one. On the flown CLPS launches: "
                f"{_flown_summary(names)}."
            )
        elif how is None:
            note = f"How the {v.name} booster is recovered is not published."
        else:
            note = f"{v.name} boosters are usually recovered this way (Launch Library 2)."
    sea_missing = (
        past
        if flown
        else "Wave forecasts (GFS-Wave) are not recorded yet, and no buoy is recorded near "
        "the landing zone."
    )
    return {
        "landing": landing,
        "zone": zone,
        "note": note,
        "wave_height_m": None
        if landing == "land"
        else lifecycle.missing("m", sea_missing, provenance="published"),
        "wind_m_s": lifecycle.missing(
            "m/s",
            past if flown else "Wind forecasts at the landing zone are not worked out yet.",
            provenance="published",
        ),
        "limits": _limits(entered, "booster"),
        "hazard_area_seen": None,
    }


def _capsule(m: MissionRecord, entered: dict[str, Any] | None) -> dict[str, Any]:
    returns = (m.lifecycle or {}).get("returns")
    if returns in (None, "none"):
        return {
            "applicable": False,
            "reason": "Nothing comes back to Earth on this mission.",
            "zone": None,
            "wave_height_m": None,
            "wind_m_s": None,
            "daylight": None,
            "limits": _limits(entered, "capsule"),
        }
    return {
        "applicable": True,
        "reason": "The capsule's return to Earth is not worked out yet.",
        "zone": None,
        "wave_height_m": None,
        "wind_m_s": None,
        "daylight": None,
        "limits": _limits(entered, "capsule"),
    }


async def recovery(session: AsyncSession, mission_id: str) -> dict[str, Any]:
    m = await MissionRepository(session).get(mission_id)
    if m is None:
        raise MissionNotFound(mission_id)
    entered = await PmRepository(session).return_limits(m.id)
    repo = MissionRepository(session)
    names = {}
    for z in catalogues.load("recovery_zones").records:
        for mid in z.used_by:
            r = await repo.get(mid)
            names[mid] = r.name if r else mid
    cancelled = m.status in ("cancelled", "reassigned")
    data = {
        "booster": None if cancelled else _booster(m, entered, names),
        "capsule": None if cancelled else _capsule(m, entered),
    }
    return {
        "data": data,
        "meta": lifecycle.meta(
            engines=("wx",),
            sources=[
                lifecycle.source_ref("Launch Library 2 landing records", z.sources[0].url)
                for z in catalogues.load("recovery_zones").records
                if m.id in z.used_by
            ],
            parts=[
                (
                    "Recovery limits",
                    "Launch providers do not publish their sea and wind limits for booster "
                    "recovery; only limits the team enters are shown.",
                )
            ],
            computed_at=datetime.now(UTC),
        ),
    }


async def set_limits(
    session: AsyncSession,
    who: Claims,
    mission_id: str,
    booster: dict[str, float | None],
    capsule: dict[str, float | None],
) -> dict[str, Any]:
    m = await MissionRepository(session).get(mission_id)
    if m is None:
        raise MissionNotFound(mission_id)
    for part in (booster, capsule):
        for k, v in part.items():
            if k not in UNITS:
                raise BadRequest(f"unknown limit '{k}'; known: {sorted(UNITS)}")
            if v is not None and v <= 0:
                raise BadRequest(f"{k} must be above zero")
    pm = PmRepository(session)
    before = await pm.return_limits(m.id)
    await pm.put_return_limits(m.id, booster, capsule, who.actor)
    await audit_service.record(
        session,
        who,
        action="set",
        entity="limits",
        entity_id=f"return:{m.id}",
        mission_id=m.id,
        before=None
        if before is None
        else {"booster": before["booster"], "capsule": before["capsule"]},
        after={"booster": booster, "capsule": capsule},
    )
    return await recovery(session, m.id)
