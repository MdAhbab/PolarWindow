"""Launch weather for one launch opportunity (T4, B1 and B3), and its entries.

Each of the vehicle's rules is shown word for word with its limit and what
can be said about it at the launch time:

* a model rule (a wind limit at a height): the share of each ensemble's runs
  that break it, ``k`` of ``N`` with an exact 95 % interval, never pooled
  across systems, and one deterministic forecast (HRRR) over or under;
* a proxy rule (cloud thickness, cumulus tops): what the recorded model
  fields can show, which today is nothing, said so;
* an observation rule (lightning, anvils, field mills): only an observation
  at the time decides it; the lightning rules add the National Weather
  Service's chance of thunder in that hour.

Read from what the feeds worker recorded (ADR-8); nothing here fetches.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import weather_rules as wr
from app.core.quantity import Quantity, share
from app.data import catalogues, climatology, verification
from app.db.repositories.missions import MissionRecord, MissionRepository
from app.db.repositories.pm import PmRepository
from app.services import audit_service, feed_service, lifecycle
from app.services.auth_service import Claims
from app.services.mission_service import MissionNotFound

#: An ensemble step this close to the launch time stands for it.
ENSEMBLE_TOLERANCE_S = 3 * 3600.0
HRRR_TOLERANCE_S = 3600.0
FORECAST_REACH_H = 16 * 24.0
SYSTEMS = ("GEFS", "ECMWF-ENS", "AIFS-ENS")
NOT_RECORDED = {
    "ECMWF-ENS": "ECMWF's ensemble is not recorded yet.",
    "AIFS-ENS": "ECMWF's AI ensemble (AIFS) is not recorded yet.",
}
OBSERVED_DETAIL = {
    "lightning_distance": "Lightning seen from space (GOES lightning mapper) is recorded only "
    "in the six hours before a launch opportunity; the range watches it at the time.",
    "thunderstorm_distance": "Thunderstorms are watched by the range at the time.",
    "electric_field": "The range's field mill readings are not public.",
}
OPP_ID = re.compile(r"^(?P<pad>[a-z0-9.-]+)-(?P<ts>\d{8}T\d{4})$")


class BadRequest(ValueError):
    pass


def _q(value: float | None, unit: str, **kw: Any) -> dict[str, Any]:
    return lifecycle.q(Quantity(value=value, unit=unit, **kw))


async def _stored_opportunity(
    session: AsyncSession, mission_id: str, opp_id: str
) -> dict[str, Any] | None:
    row = (
        await session.execute(
            text(
                "SELECT result FROM assessments WHERE kind = 'launch' AND mission_id = :m "
                "ORDER BY id DESC LIMIT 5"
            ),
            {"m": mission_id},
        )
    ).scalars()
    for result in row:
        for o in (result.get("data") or {}).get("opportunities") or []:
            if o.get("id") == opp_id:
                return dict(o)
    return None


async def _resolve(
    session: AsyncSession,
    m: MissionRecord,
    opportunity: str | None,
    t0: datetime | None,
    pad: str | None,
) -> tuple[datetime, str]:
    lc = m.lifecycle or {}
    if opportunity:
        stored = await _stored_opportunity(session, m.id, opportunity)
        if stored is not None and stored["t0"]["value"] is not None:
            return datetime.fromtimestamp(float(stored["t0"]["value"]), UTC), stored["pad_id"]
        if opportunity.endswith("-flown") and lc.get("t0"):
            return lifecycle.parse_time(lc["t0"]["date"]), opportunity[: -len("-flown")]
        mt = OPP_ID.match(opportunity)
        if mt is None:
            raise BadRequest(f"'{opportunity}' is not a launch opportunity of this mission")
        return datetime.strptime(mt["ts"], "%Y%m%dT%H%M").replace(tzinfo=UTC), mt["pad"]
    if t0 is None or pad is None:
        raise BadRequest("give an opportunity, or a launch time (t0) and a pad")
    return t0, pad


def units_for(rule: Any) -> list[str]:
    """Units a limit for ``rule`` can be entered in, the published one first; [] = any."""
    if rule.variable == "wind_speed":
        first = [rule.unit] if rule.unit in wr.SPEED_UNITS else []
        return first + sorted(u for u in wr.SPEED_UNITS if u not in first)
    return [rule.unit] if rule.unit else []


def _limit(rule: Any, entered: dict[str, Any] | None) -> dict[str, Any]:
    if entered is not None:
        return _q(
            float(entered["value"]),
            str(entered["unit"]),
            provenance="entered",
            no_margin_reason="A limit the team entered.",
            source=str(entered["entered_by"]),
        )
    if rule.threshold is not None and rule.unit is not None:
        return _q(
            float(rule.threshold),
            str(rule.unit),
            provenance="published",
            no_margin_reason="The limit as published.",
            source=rule.sources[0].url,
        )
    units = units_for(rule)
    return lifecycle.missing(
        units[0] if units else "",
        "The limit is not published; the team can enter the one it is given."
        + ("" if units else " No unit is published for it, so any unit is taken."),
        provenance="entered",
    )


def _gefs_row(
    snaps: list[feed_service.Latest],
    pad: str,
    t0: datetime,
    rule: Any,
    limit: dict[str, Any],
    checked: bool = False,
) -> dict[str, Any]:
    lead_h = (t0 - datetime.now(UTC)).total_seconds() / 3600.0

    def missing(why: str) -> dict[str, Any]:
        return {"system": "GEFS", "share": None, "missing_reason": why}

    if lead_h < 0:
        return missing("This launch is in the past; the forecasts made before it were not kept.")
    if lead_h > FORECAST_REACH_H:
        return missing(
            "Beyond the 16 days the ensemble forecasts reach; history by month and hour is "
            "not built yet."
        )
    if rule.variable != "wind_speed" or rule.height_m is None:
        return missing(
            "The recorded model fields (winds at 10 and 80 m, gusts, cloud cover, CAPE) do "
            "not describe this rule."
        )
    if limit["value"] is None:
        return missing("The limit is not known, so the runs that break it cannot be counted.")
    reasons = [s.missing_reason for s in snaps if s.missing_reason]
    for s in snaps:
        vals = s.values
        if vals is None:
            continue
        leads = ((vals.get("points") or {}).get(pad) or {}).get("leads") or {}
        hit = wr.nearest_lead(leads, t0, ENSEMBLE_TOLERANCE_S)
        if hit is None:
            continue
        members = leads[hit[0]]["members"]
        lim = wr.to_m_s(float(limit["value"]), str(limit["unit"]))
        k, n = wr.count_breaking(members, float(rule.height_m), lim, rule.comparison or "gt")
        if n == 0:
            continue
        return {
            "system": "GEFS",
            "share": lifecycle.share(share(k, n, checked=checked)),
            "missing_reason": None,
        }
    return missing(
        reasons[0]
        if reasons and all(s.values is None for s in snaps)
        else "No GEFS step within 3 hours of this launch has been recorded yet; the feeds "
        "worker fetches the steps nearest each upcoming opportunity."
    )


def _hrrr(
    snap: feed_service.Latest, pad: str, t0: datetime, rule: Any, limit: dict[str, Any]
) -> list[dict[str, Any]]:
    vals = snap.values
    if vals is None or rule.variable != "wind_speed" or rule.height_m is None:
        return []
    if limit["value"] is None:
        return []
    leads = ((vals.get("points") or {}).get(pad) or {}).get("leads") or {}
    hit = wr.nearest_lead(leads, t0, HRRR_TOLERANCE_S)
    if hit is None:
        return []
    member = next(iter(leads[hit[0]]["members"].values()))
    sp = wr.speed_at(member, float(rule.height_m))
    if sp is None:
        return []
    unit = str(limit["unit"])
    value = wr.from_m_s(sp, unit)
    return [
        {
            "system": "HRRR",
            "value": _q(
                value,
                unit,
                provenance="computed",
                no_margin_reason="One forecast, at the rule's height from the model's 10 m and "
                "80 m winds.",
                source=snap.snapshot.url if snap.snapshot else None,
            ),
            "over": wr.breaks(value, float(limit["value"]), rule.comparison or "gt"),
        }
    ]


def _thunder(nws: feed_service.Latest, t0: datetime) -> str | None:
    vals = nws.values
    if vals is None:
        return None
    times = [lifecycle.parse_time(t) for t in vals.get("times") or []]
    p = vals.get("p_thunder_frac") or []
    for t, v in zip(times, p, strict=False):
        if t <= t0 < t + timedelta(hours=1) and v is not None:
            return (
                f"The National Weather Service gives a {100 * float(v):.0f}% chance of thunder "
                "at the pad in that hour."
            )
    return None


MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


def _climatology(
    rule: Any, limit: dict[str, Any], region: str, when: datetime
) -> dict[str, Any] | None:
    """How often the wind at 50 m has been above the limit in this month and UTC hour."""
    if rule.variable != "wind_speed" or limit.get("value") is None:
        return None
    unit = str(limit.get("unit"))
    if unit not in wr.SPEED_UNITS:
        return None
    cl = climatology.load(region)
    if cl is None:
        return None
    got = cl.share_above(when.month, when.hour, wr.to_m_s(float(limit["value"]), unit))
    if got is None:
        return None
    share, n = got
    return {
        "share": share,
        "years": cl.years,
        "source": f"NASA POWER hourly wind at 50 m from the MERRA-2 reanalysis (the rule's 162 "
        f"ft is 49 m), the {n} hours of {MONTHS[when.month - 1]} at {when.hour:02d} UTC in "
        f"those years; a reanalysis cell's hourly mean is smoother than the pad's tower.",
    }


#: GLM's latest half hour describes a launch at most this far ahead: it is "now".
GLM_REACH = timedelta(hours=6)


def _glm(
    glm: feed_service.Latest, pad_id: str, when: datetime, limit: dict[str, Any]
) -> dict[str, Any] | None:
    """Flashes within the rule's distance of the pad in GLM's latest half hour, or None."""
    v = glm.values
    now = datetime.now(UTC)
    if v is None or not (now - timedelta(hours=1) <= when <= now + GLM_REACH):
        return None
    pad = (v.get("pads") or {}).get(pad_id)
    if pad is None:
        return None
    radius_nmi = 10.0
    if limit.get("value") is not None and limit.get("unit") == "nmi":
        radius_nmi = float(limit["value"])
    n = sum(1 for f in pad["flashes"] if f["km"] <= radius_nmi * 1.852)
    end = lifecycle.parse_time(v["end"])
    start = lifecycle.parse_time(v["start"])
    sat = {"G19": "GOES-19", "G18": "GOES-18"}.get(v.get("satellite", ""), v.get("satellite"))
    span = f"the {round((end - start).total_seconds() / 60)} min to {end:%H:%M} UTC"
    if n == 0:
        return {
            "state": "clear",
            "detail": f"No flashes within {radius_nmi:g} nmi of the pad in {span} ({sat} "
            "lightning mapper). This is now, not at the launch time.",
        }
    last = max(
        lifecycle.parse_time(f["t"]) for f in pad["flashes"] if f["km"] <= radius_nmi * 1.852
    )
    return {
        "state": "seen",
        "detail": f"{n} flash{'es' if n > 1 else ''} within {radius_nmi:g} nmi of the pad in "
        f"{span}, the last at {last:%H:%M} UTC ({sat} lightning mapper). This is now, not at "
        "the launch time.",
    }


def _space_weather(
    kp: feed_service.Latest,
    protons: feed_service.Latest,
    xrays: feed_service.Latest,
    alerts: feed_service.Latest,
) -> dict[str, Any]:
    def pub(latest: feed_service.Latest, value: float | None, unit: str) -> dict[str, Any]:
        if value is None or latest.snapshot is None:
            return lifecycle.missing(
                unit, latest.missing_reason or "Not recorded yet.", provenance="published"
            )
        return _q(
            value,
            unit,
            provenance="published",
            no_margin_reason="As NOAA's Space Weather Prediction Center reports it.",
            source=latest.snapshot.url,
        )

    kv = (kp.values or {}).get("latest") or {}
    pv = ((protons.values or {}).get("latest") or {}).get(">=10 MeV") or {}
    xv = (xrays.values or {}).get("latest") or {}
    now = datetime.now(UTC)
    recent = [
        a.get("headline") or ""
        for a in (alerts.values or {}).get("alerts") or []
        if a.get("issued") and now - lifecycle.parse_time(a["issued"]) < timedelta(hours=24)
    ]
    return {
        "kp": pub(kp, kv.get("kp"), "Kp"),
        "proton_10mev_pfu": pub(protons, pv.get("pfu"), "pfu"),
        "xray_class": xv.get("class"),
        "alerts": [h for h in recent if h],
    }


def _conflicts(ll2: feed_service.Latest, pad_id: str, t0: datetime) -> tuple[list[Any], str]:
    sites = catalogues.load("launch_sites")
    rng = sites.get(pad_id).launch_range
    locations = {s.ll2_location_id for s in sites.records if s.launch_range == rng}
    if ll2.values is None:
        why = (
            "Launch Library 2 has not been recorded yet."
            if ll2.snapshot is None or not ll2.missing_reason
            else ll2.missing_reason
        )
        return [], "Other launches from this range are not known: " + why
    out = []
    for launch in ll2.values.get("launches") or []:
        if launch.get("location_id") not in locations or not launch.get("net"):
            continue
        net = lifecycle.parse_time(launch["net"])
        if abs((net - t0).total_seconds()) <= 24 * 3600:
            out.append(
                {
                    "name": launch["name"],
                    "t0": lifecycle.iso(net),
                    "pad": launch.get("pad_name") or "",
                }
            )
    return out, "Launches from the same range within a day of this one, from Launch Library 2."


async def launch_weather(
    session: AsyncSession,
    mission_id: str,
    opportunity: str | None = None,
    t0: datetime | None = None,
    pad: str | None = None,
) -> dict[str, Any]:
    m = await MissionRepository(session).get(mission_id)
    if m is None:
        raise MissionNotFound(mission_id)
    when, pad_id = await _resolve(session, m, opportunity, t0, pad)
    try:
        site = catalogues.load("launch_sites").get(pad_id)
    except KeyError as exc:
        raise BadRequest(f"unknown pad '{pad_id}'") from exc
    vehicle_id = (m.lifecycle or {}).get("vehicle_id")
    now = datetime.now(UTC)
    region = catalogues.MODEL_REGION_OF_RANGE.get(site.launch_range, "")
    pm = PmRepository(session)
    entered = {x["rule_id"]: x for x in await pm.vehicle_limits(vehicle_id)} if vehicle_id else {}
    rules = [
        r
        for r in catalogues.load("weather_rules").records
        if (vehicle_id in r.applies_to) or (r.id in entered)
    ]
    gefs = [
        await feed_service.latest(session, "nomads", p, region)
        for p in ("gefs_launch", "gefs_f024", "gefs_f048")
    ]
    hrrr = await feed_service.latest(session, "nomads", "hrrr", region)
    nws = await feed_service.latest(session, "nws", "grid", pad_id)
    glm = await feed_service.latest(session, "goes", "glm", region)
    rows = []
    for r in rules:
        limit = _limit(r, entered.get(r.id))
        per_system: list[dict[str, Any]] = []
        one: list[dict[str, Any]] = []
        observed = None
        if r.rule_class in ("model", "proxy"):
            per_system.append(
                _gefs_row(gefs, pad_id, when, r, limit, verification.checked(region, r.id))
            )
            per_system += [
                {"system": s, "share": None, "missing_reason": NOT_RECORDED[s]} for s in SYSTEMS[1:]
            ]
            one = _hrrr(hrrr, pad_id, when, r, limit)
        else:
            detail = OBSERVED_DETAIL.get(
                r.variable or "", "Decided by the range's weather officers at the time."
            )
            if r.variable in ("lightning_distance", "thunderstorm_distance"):
                extra = _thunder(nws, when)
                detail = f"{detail} {extra}" if extra else detail
            observed = {"state": "no_data", "detail": detail}
            if r.variable == "lightning_distance":
                seen = _glm(glm, pad_id, when, limit)
                if seen is not None:
                    extra = _thunder(nws, when)
                    seen["detail"] += f" {extra}" if extra else ""
                    observed = seen
        rows.append(
            {
                "id": r.id,
                "text": r.text,
                "source_url": r.sources[0].url,
                "class": r.rule_class,
                "limit": limit,
                "units": units_for(r),
                "limit_note": (entered.get(r.id) or {}).get("note"),
                "per_system": per_system,
                "one_forecast": one,
                "disagreement": False,
                "observed": observed,
                "climatology": _climatology(r, limit, region, when),
            }
        )
    off = await pm.official_forecast(m.id)
    conflicts, range_note = _conflicts(
        await feed_service.latest(session, "ll2", "upcoming"), pad_id, when
    )
    sw = _space_weather(
        await feed_service.latest(session, "swpc", "kp"),
        await feed_service.latest(session, "swpc", "goes_protons"),
        await feed_service.latest(session, "swpc", "goes_xrays"),
        await feed_service.latest(session, "swpc", "alerts"),
    )
    used = [s for s in [*gefs, hrrr, nws, glm] if s.snapshot is not None]
    names = {
        "nomads": "NOAA NCEP model output (NOMADS)",
        "nws": "National Weather Service",
        "goes": "NOAA GOES lightning mapper (AWS open data)",
    }
    sources: list[dict[str, Any]] = []
    for snap in used:
        ref = snap.source_ref(names.get(snap.snapshot.provider, snap.snapshot.provider))  # type: ignore[union-attr]
        if ref is not None:
            sources.append(ref)
    cl = climatology.load(region)
    if cl is not None and any(row["climatology"] for row in rows):
        sources.append(
            lifecycle.source_ref(
                f"NASA POWER hourly wind at 50 m (MERRA-2), {cl.years}", cl.source_url
            )
        )
    sources.append(
        lifecycle.source_ref(
            "Falcon 9 launch weather criteria (NASA Facts FS-2020-05-568-KSC)",
            catalogues.load("weather_rules").records[0].sources[0].url,
        )
    )
    no_rules = not rules
    data = {
        "t0": lifecycle.iso(when),
        "lead_time_h": (when - now).total_seconds() / 3600.0,
        "pad_id": pad_id,
        "vehicle_id": vehicle_id,
        "note": (
            "No weather rules are published for this vehicle; the team can enter its limits."
            if no_rules
            else "Each rule as published, with what the recorded forecasts say at the launch "
            "time. Shares count one forecast system's runs; they are never combined. "
            + (
                "The wind rule's GEFS shares have been checked against observations."
                if any(verification.checked(region, r.id) for r in rules)
                else "None has passed a check against observations yet."
            )
        ),
        "rules": rows,
        "official": None
        if off is None
        else {
            "probability_pct": off["probability_pct"],
            "concerns": off["concerns"],
            "pdf_url": off["pdf_url"],
            "entered_by": off["entered_by"],
            "entered_at": off["entered_at"],
        },
        "space_weather_now": sw,
        "range_conflicts": conflicts,
        "range_note": range_note,
    }
    meta = lifecycle.meta(
        engines=("wx",),
        sources=sources,
        parts=[
            (
                "Ensemble shares",
                "k of N runs break the rule at the forecast step nearest the launch (within "
                "3 hours); the ± is the exact 95 % interval for that many runs.",
            ),
            (
                "Height",
                "Winds at the rule's height are interpolated from the model's 10 m and 80 m "
                "winds on a logarithmic profile.",
            ),
            (
                "Checked against observations",
                " ".join(
                    x for x in (verification.summary(region, r.id) for r in rules) if x is not None
                )
                or "No rule has been checked against observations (hindcast) yet, so each "
                "share says so.",
            ),
        ],
        stale=any(s.stale and s.snapshot is not None for s in used),
        computed_at=now,
    )
    return {"data": data, "meta": meta}


# ---------------------------------------------------------------------------
# Entries: the range's forecast, and limits the vehicle maker does not publish
# ---------------------------------------------------------------------------


async def set_official_forecast(
    session: AsyncSession,
    who: Claims,
    mission_id: str,
    probability_pct: float,
    concerns: list[str],
    pdf_url: str,
) -> dict[str, Any]:
    m = await MissionRepository(session).get(mission_id)
    if m is None:
        raise MissionNotFound(mission_id)
    pm = PmRepository(session)
    before = await pm.official_forecast(m.id)
    fid = await pm.add_official_forecast(m.id, probability_pct, concerns, pdf_url, who.actor)
    after = {"probability_pct": probability_pct, "concerns": concerns, "pdf_url": pdf_url}
    await audit_service.record(
        session,
        who,
        action="set",
        entity="forecast",
        entity_id=m.id,
        mission_id=m.id,
        before=None
        if before is None
        else {k: before[k] for k in ("probability_pct", "concerns", "pdf_url")},
        after=after,
    )
    return {**after, "id": fid, "entered_by": who.actor, "entered_at": datetime.now(UTC)}


class NothingToRemove(LookupError):
    pass


async def remove_official_forecast(
    session: AsyncSession, who: Claims, mission_id: str
) -> dict[str, Any]:
    """Take back the forecast shown (the latest entered); the one entered before it, if
    any, is shown again. Recorded in the history like any entry."""
    m = await MissionRepository(session).get(mission_id)
    if m is None:
        raise MissionNotFound(mission_id)
    pm = PmRepository(session)
    shown = await pm.official_forecast(m.id)
    if shown is None:
        raise NothingToRemove(f"No official forecast is entered for {m.name}.")
    await pm.remove_official_forecast(shown["id"])
    now_shown = await pm.official_forecast(m.id)
    keys = ("probability_pct", "concerns", "pdf_url")
    await audit_service.record(
        session,
        who,
        action="delete",
        entity="forecast",
        entity_id=m.id,
        mission_id=m.id,
        before={k: shown[k] for k in keys},
        after=None if now_shown is None else {k: now_shown[k] for k in keys},
    )
    return {"removed_id": shown["id"], "official": now_shown}


async def vehicle_limits(session: AsyncSession, vehicle_id: str) -> dict[str, Any]:
    try:
        catalogues.load("vehicles").get(vehicle_id)
    except KeyError as exc:
        raise MissionNotFound(vehicle_id) from exc
    return {
        "vehicle_id": vehicle_id,
        "limits": await PmRepository(session).vehicle_limits(vehicle_id),
    }


async def set_vehicle_limits(
    session: AsyncSession, who: Claims, vehicle_id: str, limits: list[dict[str, Any]]
) -> dict[str, Any]:
    try:
        catalogues.load("vehicles").get(vehicle_id)
    except KeyError as exc:
        raise MissionNotFound(vehicle_id) from exc
    rules = catalogues.load("weather_rules")
    clean = []
    for x in limits:
        try:
            rule = rules.get(x["rule_id"])
        except KeyError as exc:
            raise BadRequest(f"no weather rule '{x['rule_id']}'") from exc
        unit = str(x["unit"])
        speed_rule = rule.variable == "wind_speed"
        if speed_rule and unit not in wr.SPEED_UNITS:
            raise BadRequest(f"'{rule.name}' is a wind limit; give it in {sorted(wr.SPEED_UNITS)}")
        if not speed_rule and rule.unit is not None and unit != rule.unit:
            raise BadRequest(f"'{rule.name}' is given in {rule.unit}")
        clean.append(
            {"rule_id": rule.id, "value": float(x["value"]), "unit": unit, "note": x.get("note")}
        )
    pm = PmRepository(session)
    before = await pm.vehicle_limits(vehicle_id)
    await pm.replace_vehicle_limits(vehicle_id, clean, who.actor)
    await audit_service.record(
        session,
        who,
        action="set",
        entity="limits",
        entity_id=vehicle_id,
        mission_id=None,
        before={
            "limits": [{k: b[k] for k in ("rule_id", "value", "unit", "note")} for b in before]
        },
        after={"limits": clean},
    )
    return {"vehicle_id": vehicle_id, "limits": await pm.vehicle_limits(vehicle_id)}
