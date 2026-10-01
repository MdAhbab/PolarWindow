"""Return (T4 B2): where the booster comes down, and whether anything comes back.

The booster's landing is read from the cited recovery zones (Launch Library
2's landing records of the flown launches) or, for a launch still to come,
from the vehicle's usual practice. Sea and wind limits for recovery are not
published by the launch providers; the team enters them. Nothing returns
from the Moon on the CLPS missions, so the capsule part says so; it carries the
capsule entry model's check against OSIRIS-REx (``make validate-capsule``).
"""

from __future__ import annotations

import asyncio
import json
import math
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.quantity import Quantity
from app.data import catalogues, copernicus_wave
from app.db.repositories.missions import MissionRecord, MissionRepository
from app.db.repositories.pm import PmRepository
from app.services import audit_service, feed_service, lifecycle
from app.services.auth_service import Claims
from app.services.mission_service import MissionNotFound

UNITS = {"wave_height_m": "m", "wind_m_s": "m/s"}
R_EARTH_KM = 6371.0
#: A GFS-Wave lattice point farther than this from the zone does not describe it.
LATTICE_WITHIN_KM = 80.0
#: A forecast step farther than this from the launch does not describe it.
STEP_WITHIN_S = 1.5 * 3600
REGION_OF_RANGE = catalogues.MODEL_REGION_OF_RANGE


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


def destination(lat_deg: float, lon_deg: float, az_deg: float, km: float) -> tuple[float, float]:
    """The point ``km`` along a great circle from ``(lat, lon)`` at azimuth ``az`` (sphere)."""
    p1, l1, th, d = (
        math.radians(lat_deg),
        math.radians(lon_deg),
        math.radians(az_deg),
        km / R_EARTH_KM,
    )
    p2 = math.asin(math.sin(p1) * math.cos(d) + math.cos(p1) * math.sin(d) * math.cos(th))
    l2 = l1 + math.atan2(
        math.sin(th) * math.sin(d) * math.cos(p1), math.cos(d) - math.sin(p1) * math.sin(p2)
    )
    return math.degrees(p2), (math.degrees(l2) + 540.0) % 360.0 - 180.0


def distance_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dl = math.radians(b[1] - a[1])
    c = math.sin(p1) * math.sin(p2) + math.cos(p1) * math.cos(p2) * math.cos(dl)
    return R_EARTH_KM * math.acos(max(-1.0, min(1.0, c)))


def sea_at(
    values: dict[str, Any], zone: tuple[float, float], t0: datetime
) -> tuple[dict[str, float], float, datetime] | None:
    """GFS-Wave at the lattice point nearest ``zone`` and the step nearest ``t0``:
    ``(fields, distance km, valid time)``, or None when neither is close enough."""
    best: tuple[float, dict[str, Any]] | None = None
    for pt in (values.get("points") or {}).values():
        d = distance_km(zone, (float(pt["grid_point"][0]), float(pt["grid_point"][1])))
        if best is None or d < best[0]:
            best = (d, pt)
    if best is None or best[0] > LATTICE_WITHIN_KM:
        return None
    steps = []
    for lead in best[1]["leads"].values():
        valid = lifecycle.parse_time(lead["valid"])
        steps.append((abs((valid - t0).total_seconds()), valid, lead["members"].get("0") or {}))
    if not steps:
        return None
    gap, valid, fields = min(steps, key=lambda x: x[0])
    if gap > STEP_WITHIN_S:
        return None
    return fields, best[0], valid


async def _next_opportunity(
    session: AsyncSession, mission_id: str
) -> tuple[dict[str, Any], datetime] | None:
    """The earliest designed launch opportunity still to come in the stored calendar,
    with the time that calendar was worked out."""
    row = (
        await session.execute(
            text(
                "SELECT result, created_at FROM assessments WHERE kind = 'launch' "
                "AND mission_id = :m ORDER BY id DESC LIMIT 1"
            ),
            {"m": mission_id},
        )
    ).first()
    if row is None:
        return None
    now = datetime.now(UTC).timestamp()
    ahead = [
        o
        for o in ((row[0] or {}).get("data") or {}).get("opportunities") or []
        if o.get("basis") == "designed" and (o.get("t0") or {}).get("value", 0) >= now
    ]
    return (min(ahead, key=lambda o: o["t0"]["value"]), row[1]) if ahead else None


async def _droneship_sea(session: AsyncSession, m: MissionRecord) -> dict[str, Any] | None:
    """The sea where a droneship would wait for the next opportunity, from GFS-Wave."""
    found = await _next_opportunity(session, m.id)
    zones = [
        z.downrange_km
        for z in catalogues.load("recovery_zones").records
        if z.kind == "booster_droneship" and z.downrange_km is not None
    ]
    if found is None or not zones:
        return None
    opp, worked_out = found
    site = catalogues.load("launch_sites").get(opp["pad_id"])
    if site.lat_deg is None or site.lon_deg is None:
        return None
    az = (opp.get("azimuth_deg") or {}).get("value")
    if az is None:
        return None
    km = max(zones)
    zone = destination(site.lat_deg, site.lon_deg, float(az), km)
    t0 = datetime.fromtimestamp(float(opp["t0"]["value"]), UTC)
    when = f"{t0:%d %b %Y %H:%M} UTC"
    where = (
        f"{km:.0f} km along the launch direction ({az:.0f} degrees), where the droneships "
        "waited for the flown CLPS launches"
    )
    region = REGION_OF_RANGE.get(site.launch_range, "")
    latest = await feed_service.latest(session, "nomads", "gfswave", region)
    values = latest.values
    got = None if values is None else sea_at(values, zone, t0)
    try:
        marine = await asyncio.to_thread(copernicus_wave.wave_at, zone, t0)
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        # A damaged or incomplete local import must not remove NOAA evidence.
        marine = None
    if got is None:
        why = (
            latest.missing_reason
            if values is None
            else f"GFS-Wave does not reach the next launch opportunity ({when}) yet."
        )
        missing_sea = {
            "zone": zone,
            "note": f" Sea at {where}, for the next opportunity: {why}",
            "times": [worked_out],
            "sources": [],
        }
        return _with_marine(missing_sea, marine)
    fields, d_km, valid = got
    assert latest.snapshot is not None and values is not None
    how = (
        f"One forecast (GFS-Wave, run of {values['run'][:16].replace('T', ' ')} UTC) for "
        f"{valid:%d %b %H:%M} UTC, at its grid point {d_km:.0f} km from the zone; wind at 10 m. "
        "Whether this booster lands on a droneship is not published."
    )

    def one(key: str, unit: str) -> dict[str, Any]:
        v = fields.get(key)
        if v is None:
            return lifecycle.missing(unit, "GFS-Wave gave no value there.")
        return lifecycle.q(
            Quantity(
                value=float(v),
                unit=unit,
                provenance="published",
                no_margin_reason=how,
                source=latest.snapshot.url,  # type: ignore[union-attr]
            )
        )

    return _with_marine({
        "zone": zone,
        "wave_height_m": one("wave_height_m", "m"),
        "wind_m_s": one("wind_m_s", "m/s"),
        "note": f" Sea shown at {where}, for the next opportunity ({when}).",
        "times": [worked_out, latest.snapshot.fetched_at],
        "sources": [latest.source_ref("GFS-Wave (NOAA)")],
    }, marine)


def _with_marine(sea: dict[str, Any], marine: dict[str, Any] | None) -> dict[str, Any]:
    """Use the imported wave subset at this place/time; retain NOAA's wind evidence."""
    if marine is None:
        return sea
    note = (
        f"Copernicus Marine wave subset for {marine['valid']:%d %b %Y %H:%M} UTC, "
        f"at a grid cell {marine['distance_km']:.1f} km from the zone. "
        "One model estimate; its forecast issuance time is not provided."
    )
    sea["wave_height_m"] = lifecycle.q(Quantity(
        value=float(marine["wave_height_m"]), unit="m", provenance="published",
        no_margin_reason=note, source=marine["source_url"],
    ))
    sea["note"] += f" Wave height from {note}"
    sea["times"].append(marine["imported_at"])
    sea["sources"].append(lifecycle.source_ref(
        "Copernicus Marine (imported wave subset)", marine["source_url"],
        fetched_at=marine["imported_at"],
    ))
    return sea


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
    m: MissionRecord,
    entered: dict[str, Any] | None,
    names: dict[str, str],
    sea: dict[str, Any] | None = None,
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
            f"The booster came back to {z.name}."
            if land
            else f"The booster landed on {z.name}, {z.downrange_km:.0f} km downrange; the "
            "droneship’s position is not published."
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
            note = f"{v.name} boosters are usually recovered this way."
    sea_missing = (
        past
        if flown
        else "No droneship zone is worked out for this mission: no launch opportunity to "
        "come is stored."
    )
    wave = None if landing == "land" else lifecycle.missing("m", sea_missing)
    wind = lifecycle.missing(
        "m/s", past if flown else "No droneship zone is worked out for this mission."
    )
    if sea is not None and not flown and landing not in ("land", "expended"):
        lat, lon = sea["zone"]
        zone = {"lat_deg": round(lat, 3), "lon_deg": round(lon, 3), "pm_km": None}
        note += sea["note"]
        why = sea["note"].split(": ", 1)[-1].strip()
        wave = sea.get("wave_height_m") or lifecycle.missing("m", why)
        wind = sea.get("wind_m_s") or lifecycle.missing("m/s", why)
    return {
        "landing": landing,
        "zone": zone,
        "note": note,
        "wave_height_m": wave,
        "wind_m_s": wind,
        "limits": _limits(entered, "booster"),
        "hazard_area_seen": None,
    }


#: The capsule entry model's check, written by ``make validate-capsule``.
CAPSULE_CHECK = "capsule/orex_check.json"


#: Said after the reason the air model was chosen, so that the reason is not read as a test
#: the model could have failed on its own: the rule was written once the landings were known
#: (12.1 km in NRLMSISE-00, 6.6 km in NRLMSIS 2.1), and NRLMSIS 2.x was fitted to SABER's
#: measurements of 2002 to 2016, so SABER's agreement on a day in 2023 is a test in time and
#: not against another instrument (``golden.capsule_air``, and Emmert et al. 2021, Table 1).
AIR_CHOICE_CAVEAT = (
    "This is not a fully separate check: the rule for choosing was written after the landing "
    "results were known, and NRLMSIS 2.x was fitted to SABER’s measurements from 2002 to 2016."
)


def _atmosphere_words(c: dict[str, Any]) -> str:
    """The air the modelled fall went through, and what it was given, in plain words."""
    a = c.get("atmosphere") or {}
    name = a.get("name") or "U.S. Standard Atmosphere 1976"
    if a.get("f107_sfu") is None:
        why = a.get("standard_atmosphere_instead")
        return (
            f"{name}, the average density of the air at each height, with no input from that "
            f"day{f'; used because {why}' if why else ''}."
        )
    why = (c.get("atmosphere_choice") or {}).get("basis")
    maker = "the U.S. Naval Research Laboratory’s " if name.startswith("NRLMSIS") else ""
    return (
        f"{name}, {maker}empirical model of the air’s density at each height and place, given "
        f"that day’s solar radio flux (10.7 cm: {a['f107_sfu']:g} solar flux units the day "
        f"before, {a['f107_mean_81_day_sfu']:g} averaged over 81 days) and geomagnetic "
        f"activity (ap {a['ap_3_hour']:g} at the time). The U.S. Standard Atmosphere 1976 "
        f"takes its place when a day has none of these."
        f"{f' {why} {AIR_CHOICE_CAVEAT}' if why else ''}"
    )


def model_check() -> dict[str, Any] | None:
    """The capsule entry model against OSIRIS-REx's landing, in numbers and words; None
    when the check has not been run here."""
    try:
        c = json.loads((get_settings().data_dir / CAPSULE_CHECK).read_text())
    except (OSError, ValueError):
        return None
    lo, hi = c["distance_range_km"]
    a, b = c["ellipse_99_km"]
    others = "; ".join(
        f"{x['name']}, {x['distance_km']:g} km ({x['distance_range_km'][0]:g} to "
        f"{x['distance_range_km'][1]:g})"
        for x in c.get("atmospheres", [])
        if not x.get("used")
    )
    name = (c.get("atmosphere") or {}).get("name") or "the U.S. Standard Atmosphere 1976"
    day = c.get("edl_team_day_km")
    note = (
        f"From OSIRIS-REx’s reconstructed entry state, the entry model lands its capsule "
        f"{c['distance_km']:g} km from where the recovery team found it ({lo:g} to {hi:g} km "
        f"over the published drag range; the limit is {c['limit_km']:g} km, "
        f"{'met' if c['passed'] else 'not met'}). It flies through {name} for that day."
        f"{f' With other air the distance is {others}.' if others else ''} "
        f"The mission’s own simulation from the same state was {c['edl_team_km']:g} km off "
        f"with its pre-flight atmosphere"
        f"{f' and {day:g} km with the day’s reconstructed one' if day else ''}. "
        f"Its 99 % landing area, {a:g} by {b:g} km, "
        f"{'holds' if c['measured_inside_ellipse'] else 'misses'} the real landing point."
    )
    return {
        "case": c["case"],
        "distance_km": c["distance_km"],
        "distance_range_km": [lo, hi],
        "limit_km": c["limit_km"],
        "passed": c["passed"],
        "atmosphere": _atmosphere_words(c),
        "mission_team_km": c["edl_team_km"],
        "ellipse_99_km": [a, b],
        "measured_inside_ellipse": c["measured_inside_ellipse"],
        "checked_at": c["checked_at"],
        "sources": c["sources"],
        "note": note,
    }


def _capsule(m: MissionRecord, entered: dict[str, Any] | None) -> dict[str, Any]:
    returns = (m.lifecycle or {}).get("returns")
    part = {
        "applicable": returns not in (None, "none"),
        "reason": "Nothing comes back to Earth on this mission.",
        "zone": None,
        "wave_height_m": None,
        "wind_m_s": None,
        "daylight": None,
        "limits": _limits(entered, "capsule"),
        "model_check": model_check(),
    }
    if part["applicable"]:
        part["reason"] = (
            "No entry state is published for this mission’s return, so where the capsule "
            "comes down is not worked out."
        )
    return part


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
    sea = None if cancelled else await _droneship_sea(session, m)
    data = {
        "booster": None if cancelled else _booster(m, entered, names, sea),
        "capsule": None if cancelled else _capsule(m, entered),
    }
    sources, times = _sources_and_times(m, cancelled, entered, sea)
    return {
        "data": data,
        "meta": lifecycle.meta(
            engines=("wx",),
            sources=sources,
            parts=[
                (
                    "Recovery limits",
                    "Launch providers do not publish their sea and wind limits for booster "
                    "recovery; only limits the team enters are shown.",
                )
            ],
            computed_at=max(times),
        ),
    }


def _day(d: Any) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=UTC)


def _sources_and_times(
    m: MissionRecord,
    cancelled: bool,
    entered: dict[str, Any] | None,
    sea: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], list[datetime]]:
    """Where the answer's facts come from, and when each last changed: the answer is as
    old as its newest input (a catalogue's compile date, the stored launch calendar, the
    sea forecast, the team's entry), not the time of the request."""
    zones = catalogues.load("recovery_zones")
    sources: list[dict[str, Any]] = []
    times = [_day(zones.compiled)]
    vid = (m.lifecycle or {}).get("vehicle_id")
    if not cancelled and vid:
        z = _zone_of(m)
        if z is not None:
            sources.append(
                lifecycle.source_ref(
                    "Launch Library 2 landing records",
                    z.sources[0].url,
                    fetched_at=_day(z.sources[0].accessed),
                )
            )
        else:
            vehicles = catalogues.load("vehicles")
            times.append(_day(vehicles.compiled))
            try:
                v = vehicles.get(vid)
            except KeyError:
                v = None
            if v is not None:
                src = v.sources[0]
                url = v.field_sources.get("booster_recovery") or src.url
                sources.append(lifecycle.source_ref(src.title, url, fetched_at=_day(src.accessed)))
    if sea is not None:
        times.extend(t for t in sea.get("times", []) if t is not None)
        sources.extend(x for x in sea.get("sources", []) if x is not None)
    if entered is not None and entered.get("entered_at") is not None:
        times.append(entered["entered_at"])
    return sources, times


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
