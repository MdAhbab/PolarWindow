"""Ready (T3): readiness items, milestones, parts, risks, lessons, landing history.

What is shown, and where it comes from:

* **Items prefilled from the mission record**: the lander, each payload and
  rover, the launch vehicle, the range, ground-station passes, each relay
  agreement, the operations team and the licences every US launch needs.
  For a mission that has flown, every item was ready at launch, which the
  launch record shows (``public``). For one that has not, nobody has said
  where the item stands, and the answer says exactly that
  (``state_known: false``) instead of guessing a state.
* **Changes the project manager enters**, one step at a time along each
  item's ladder (``core.readiness``), each with a date, an evidence link and
  a line in the change history.
* **Counts per state, never a percentage** (invariant 9).
"""

from __future__ import annotations

import secrets
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import readiness
from app.data import catalogues
from app.db.repositories.missions import MissionRecord, MissionRepository
from app.db.repositories.pm import ItemRow, PartRow, PmRepository, RiskRow
from app.services import audit_service, lifecycle
from app.services.auth_service import Claims
from app.services.mission_service import MissionNotFound

FLOWN = frozenset(
    {
        "completed",
        "partial_success",
        "landing_failed",
        "lost_before_landing",
        "operating",
        "in_transit",
    }
)
CANCELLED = frozenset({"cancelled", "reassigned"})

#: Licences and approvals every US commercial lunar delivery needs. Named
#: generically: who holds each one (launch provider, lander provider) varies.
LICENCES: tuple[tuple[str, str], ...] = (
    ("licence-faa", "FAA launch licence (14 CFR Part 450), held by the launch provider"),
    ("licence-spectrum", "Radio spectrum: FCC licence and ITU filing"),
    ("licence-planetary-protection", "Planetary protection category (NASA)"),
    ("licence-export", "Export control review (ITAR / EAR)"),
)

TEST_KINDS = ("vibration", "shock", "thermal_vacuum", "emi_emc", "functional")


class NotFound(LookupError):
    pass


class BadEntry(ValueError):
    pass


class IllegalMove(ValueError):
    def __init__(self, message: str, allowed: list[str]) -> None:
        super().__init__(message)
        self.allowed = allowed


def _sep(x: str) -> str:
    return x.replace("/", "--")


def item_id(mission_id: str, suffix: str) -> str:
    return f"{mission_id}--{_sep(suffix)}"


def _name(cat: str, rid: str | None) -> tuple[str | None, Any]:
    if not rid:
        return None, None
    try:
        rec = catalogues.load(cat).get(rid)
    except (KeyError, catalogues.CatalogueError):
        return None, None
    return str(rec.name), rec


def _flown_evidence(m: MissionRecord) -> tuple[str | None, str | None]:
    """(date, evidence URL) of the launch, for a mission that flew."""
    lc = m.lifecycle or {}
    t0 = lc.get("t0")
    if t0:
        return str(t0["date"])[:10], (lc.get("field_sources") or {}).get("t0")
    if m.launch:
        return str(m.launch["date"])[:10], m.sources[0]["url"] if m.sources else None
    return None, None


def prefill(m: MissionRecord) -> list[ItemRow]:
    """The items every delivery has, from the mission record and the catalogues."""
    lc = m.lifecycle or {}
    flown = m.status in FLOWN
    on, ev = _flown_evidence(m) if flown else (None, None)
    rows: list[ItemRow] = []

    def add(suffix: str, kind: str, name: str, org: str | None) -> None:
        rows.append(
            ItemRow(
                id=item_id(m.id, suffix),
                mission_id=m.id,
                kind=kind,
                name=name,
                organisation=org,
                state="ready" if flown else "not_started",
                blocked_from=None,
                blocked_reason=None,
                changed_on=on if flown else None,
                changed_by=None,
                evidence_url=ev if flown else None,
                source="public",
                tests=[],
                position=len(rows),
            )
        )

    add("lander", "lander", m.lander or m.vehicle_name or "Lander (name not published)", m.provider)
    rover_ids = set()
    for p in m.payloads:
        kind = "rover" if "rover_mobility" in p.instrument_types else "payload"
        label = f"{p.name} ({p.acronym})" if p.acronym and p.acronym not in p.name else p.name
        add(p.id, kind, label, p.organisation)
    for r in lc.get("rovers") or []:
        if r["id"] not in rover_ids:
            rover_ids.add(r["id"])
            add(r["id"], "rover", r["name"], r.get("organisation"))
    vname, vrec = _name("vehicles", lc.get("vehicle_id"))
    add(
        "launch-vehicle",
        "launch_vehicle",
        vname or "Launch vehicle (not published)",
        getattr(vrec, "provider", None),
    )
    pname, prec = _name("launch_sites", lc.get("pad_id"))
    add(
        "range",
        "range",
        f"Launch range and pad: {pname}" if pname else "Launch range and pad (not published)",
        getattr(prec, "operator", None),
    )
    add("ground-stations", "ground_booking", "Ground station passes booked", None)
    for rid in (lc.get("comms") or {}).get("relays") or []:
        rname, rrec = _name("relays", rid)
        add(
            f"relay-{rid}",
            "relay_agreement",
            f"Relay service: {rname or rid}",
            getattr(rrec, "operator", None),
        )
    add("ops-team", "ops_team", "Mission operations team trained and staffed", m.provider)
    for suffix, name in LICENCES:
        add(suffix, "licence", name, None)
    return rows


def _item_out(r: ItemRow, known: bool) -> dict[str, Any]:
    allowed = readiness.allowed_moves(r.kind, r.state, r.blocked_from)  # type: ignore[arg-type]
    return {
        "id": r.id,
        "kind": r.kind,
        "name": r.name,
        "organisation": r.organisation,
        "state": r.state,
        "state_known": known,
        "allowed_next": allowed,
        "blocked_reason": r.blocked_reason,
        "changed_at": r.changed_on,
        "changed_by": r.changed_by,
        "evidence_url": r.evidence_url,
        "source": r.source,
        "tests": r.tests,
    }


async def _mission(session: AsyncSession, mission_id: str) -> MissionRecord:
    m = await MissionRepository(session).get(mission_id)
    if m is None:
        raise MissionNotFound(mission_id)
    return m


async def items(session: AsyncSession, m: MissionRecord) -> list[tuple[ItemRow, bool]]:
    """Every item: stored rows override their prefilled twin; entered items follow."""
    stored = {r.id: r for r in await PmRepository(session).items(m.id)}
    flown = m.status in FLOWN
    out: list[tuple[ItemRow, bool]] = []
    for r in prefill(m):
        s = stored.pop(r.id, None)
        out.append((s, True) if s is not None else (r, flown))
    out += [(r, True) for r in sorted(stored.values(), key=lambda x: (x.position, x.id))]
    return out


def _milestones(m: MissionRecord, entered: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    now = datetime.now(UTC)
    lc = m.lifecycle or {}
    src = m.sources[0]["url"] if m.sources else None
    for key, name in (("launch", "Launch"), ("landing", "Landing")):
        d = lc.get("t0") if key == "launch" and lc.get("t0") else getattr(m, key)
        if d is None:
            continue
        url = (lc.get("field_sources") or {}).get("t0") if d is lc.get("t0") else src
        out.append(
            {
                "id": item_id(m.id, f"milestone-{key}"),
                "name": name,
                "date": lifecycle.published_date(d, url or "mission record"),
                "done": lifecycle.parse_time(d["date"]) < now and m.status in FLOWN,
                "source": url,
            }
        )
    for e in entered:
        out.append(
            {
                "id": e["id"],
                "name": e["name"],
                "date": lifecycle.entered_date(e["on_date"], e["entered_by"]),
                "done": e["done"],
                "source": e["source_url"],
            }
        )
    return out


def _risk_out(r: RiskRow) -> dict[str, Any]:
    return {
        "id": r.id,
        "title": r.title,
        "cause": r.cause,
        "consequence_text": r.consequence_text,
        "scale_id": r.scale_id,
        "ratings": r.ratings,
        "trend": r.trend,
        "owner": r.owner,
        "mitigation": r.mitigation,
        "links": r.links,
        "changed_at": r.changed_at,
        "changed_by": r.changed_by,
    }


def _part_out(p: PartRow) -> dict[str, Any]:
    return {
        "id": p.id,
        "name": p.name,
        "part_number": p.part_number,
        "serial": p.serial,
        "parent_item_id": p.parent_item_id,
        "status": p.status,
        "location": p.location,
        "changed_at": p.changed_at,
        "changed_by": p.changed_by,
    }


def _parts_summary(parts: list[PartRow]) -> dict[str, int]:
    return {
        "total": len(parts),
        "spares": sum(p.status == "spare" for p in parts),
        "lost": sum(p.status == "lost" for p in parts),
        "damaged": sum(p.status == "damaged" for p in parts),
        "failed": sum(p.status == "failed" for p in parts),
    }


def _meta(m: MissionRecord, any_entered: bool) -> dict[str, Any]:
    sources = [
        lifecycle.source_ref("CLPS mission record (data/missions.json)", s["url"])
        for s in m.sources[:3]
    ]
    if any_entered:
        sources.append(lifecycle.source_ref("Entered by the project team"))
    return lifecycle.meta(
        engines=("ready",),
        sources=sources,
        parts=[
            (
                "States not entered",
                "An item nobody has entered a state for shows "
                "'not entered yet'; it is not counted as not started.",
            ),
            (
                "Entered by people",
                "States, parts and risks are what the team entered, with "
                "their names and evidence links; they are not checked against the hardware.",
            ),
        ],
    )


async def ready(session: AsyncSession, mission_id: str) -> dict[str, Any]:
    m = await _mission(session, mission_id)
    repo = PmRepository(session)
    rows = await items(session, m)
    known_states = [r.state for r, known in rows if known]
    parts = await repo.parts(m.id)
    adopted = await repo.adoptions(m.id)
    try:
        lessons_available = len(catalogues.load("lessons").records)
    except catalogues.CatalogueError:
        lessons_available = 0
    entered = any(r.source == "entered" or r.changed_by for r, _ in rows) or bool(parts)
    return {
        "data": {
            "counts": readiness.counts(known_states),
            "not_entered": sum(1 for _, known in rows if not known),
            "items": [_item_out(r, known) for r, known in rows],
            "milestones": _milestones(m, await repo.milestones(m.id)),
            "risks": [_risk_out(r) for r in await repo.risks(m.id)],
            "parts": _parts_summary(parts),
            "lessons_available": lessons_available,
            "lessons_adopted": len(adopted),
        },
        "meta": _meta(m, entered),
    }


# ---------------------------------------------------------------------------
# Writes. Each one records its change in the history, in the same transaction.
# ---------------------------------------------------------------------------


def _state_dict(r: ItemRow) -> dict[str, Any]:
    return {
        "state": r.state,
        "blocked_reason": r.blocked_reason,
        "changed_on": r.changed_on,
        "evidence_url": r.evidence_url,
    }


async def _find_item(session: AsyncSession, iid: str) -> tuple[MissionRecord, ItemRow]:
    mission_id = iid.split("--", 1)[0]
    m = await MissionRepository(session).get(mission_id)
    stored = await PmRepository(session).item(iid, lock=True)
    if stored is not None:
        return (m or await _mission(session, stored.mission_id)), stored
    if m is None:
        raise NotFound(iid)
    for r in prefill(m):
        if r.id == iid:
            return m, r
    raise NotFound(iid)


async def move_item(
    session: AsyncSession,
    who: Claims,
    iid: str,
    *,
    state: str,
    date: str | None,
    evidence_url: str | None,
    note: str | None,
    blocked_reason: str | None,
) -> dict[str, Any]:
    m, row = await _find_item(session, iid)
    if state not in readiness.STATES:
        raise BadEntry(f"'{state}' is not a readiness state")
    mv = readiness.Move(
        to=state,  # type: ignore[arg-type]
        date=date,
        evidence_url=evidence_url,
        note=note,
        blocked_reason=blocked_reason,
    )
    try:
        blocked_from = readiness.check(row.kind, row.state, row.blocked_from, mv)  # type: ignore[arg-type]
    except readiness.IllegalMove as exc:
        raise IllegalMove(str(exc), list(exc.allowed)) from exc
    except ValueError as exc:
        raise BadEntry(str(exc)) from exc
    new = replace(
        row,
        state=state,
        blocked_from=blocked_from,
        blocked_reason=blocked_reason if state == "blocked" else None,
        changed_on=date,
        changed_by=who.actor,
        evidence_url=evidence_url,
    )
    await PmRepository(session).put_item(new)
    await audit_service.record(
        session,
        who,
        action="move",
        entity="ready_item",
        entity_id=iid,
        mission_id=m.id,
        before=_state_dict(row),
        after=_state_dict(new),
        note=note,
    )
    return _item_out(new, True)


async def add_item(
    session: AsyncSession,
    who: Claims,
    mission_id: str,
    *,
    kind: str,
    name: str,
    organisation: str | None,
) -> dict[str, Any]:
    m = await _mission(session, mission_id)
    if kind not in readiness.LADDERS:
        raise BadEntry(f"'{kind}' is not an item kind")
    if not name.strip():
        raise BadEntry("an item needs a name")
    row = ItemRow(
        id=item_id(m.id, f"entered-{secrets.token_hex(4)}"),
        mission_id=m.id,
        kind=kind,
        name=name.strip()[:200],
        organisation=(organisation or "").strip()[:200] or None,
        state="not_started",
        blocked_from=None,
        blocked_reason=None,
        changed_on=datetime.now(UTC).date().isoformat(),
        changed_by=who.actor,
        evidence_url=None,
        source="entered",
        tests=[],
        position=5000,
    )
    await PmRepository(session).put_item(row)
    await audit_service.record(
        session,
        who,
        action="create",
        entity="ready_item",
        entity_id=row.id,
        mission_id=m.id,
        before=None,
        after={"kind": kind, "name": row.name, "organisation": row.organisation},
    )
    return _item_out(row, True)


async def record_test(
    session: AsyncSession,
    who: Claims,
    iid: str,
    *,
    kind: str,
    result: str,
    report_url: str | None,
    date: str | None,
) -> dict[str, Any]:
    m, row = await _find_item(session, iid)
    if kind not in TEST_KINDS:
        raise BadEntry(f"'{kind}' is not a test kind; one of {', '.join(TEST_KINDS)}")
    if result not in ("passed", "failed", "not_done"):
        raise BadEntry("result is passed, failed or not_done")
    if result != "not_done" and not (report_url and date):
        raise BadEntry("a test result needs its date and a link to its report")
    tests = [t for t in row.tests if t.get("kind") != kind]
    tests.append({"kind": kind, "result": result, "report_url": report_url, "date": date})
    tests.sort(key=lambda t: TEST_KINDS.index(t["kind"]))
    before = {"tests": row.tests}
    new = replace(row, tests=tests)
    await PmRepository(session).put_item(new)
    await audit_service.record(
        session,
        who,
        action="test",
        entity="ready_item",
        entity_id=iid,
        mission_id=m.id,
        before=before,
        after={"tests": tests},
    )
    return _item_out(new, True)


async def history(session: AsyncSession, entity: str, eid: str) -> dict[str, Any]:
    if entity not in audit_service.ENTITIES:
        raise BadEntry(f"no history kept for '{entity}'")
    return {"entries": await audit_service.history(session, entity, eid)}


# --- parts ---------------------------------------------------------------------

PART_STATUSES = ("installed", "spare", "in_test", "damaged", "failed", "lost")


async def parts(session: AsyncSession, mission_id: str) -> dict[str, Any]:
    m = await _mission(session, mission_id)
    return {"parts": [_part_out(p) for p in await PmRepository(session).parts(m.id)]}


async def save_part(
    session: AsyncSession,
    who: Claims,
    mission_id: str | None,
    part_id: str | None,
    fields: dict[str, Any],
) -> dict[str, Any]:
    repo = PmRepository(session)
    before = None
    if part_id is not None:
        old = await repo.part(part_id, lock=True)
        if old is None:
            raise NotFound(part_id)
        before = _part_out(old)
        mission_id = old.mission_id
        merged = {
            k: before[k]
            for k in ("name", "part_number", "serial", "parent_item_id", "status", "location")
        }
        merged.update({k: v for k, v in fields.items() if k in merged})
    else:
        assert mission_id is not None
        await _mission(session, mission_id)
        merged = fields
        part_id = f"part-{secrets.token_hex(5)}"
    if merged.get("status") not in PART_STATUSES:
        raise BadEntry(f"status is one of {', '.join(PART_STATUSES)}")
    if not str(merged.get("name") or "").strip():
        raise BadEntry("a part needs a name")
    row = await repo.put_part(
        {
            "id": part_id,
            "mission_id": mission_id,
            "name": str(merged["name"]).strip()[:200],
            "part_number": merged.get("part_number"),
            "serial": merged.get("serial"),
            "parent_item_id": merged.get("parent_item_id"),
            "status": merged["status"],
            "location": merged.get("location"),
            "changed_by": who.actor,
        }
    )
    out = _part_out(row)
    await audit_service.record(
        session,
        who,
        action="update" if before else "create",
        entity="part",
        entity_id=part_id,
        mission_id=mission_id,
        before=before and _strip_time(before),
        after=_strip_time(out),
    )
    return out


def _strip_time(d: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in d.items() if k not in ("changed_at",)}


async def part_impact(session: AsyncSession, part_id: str) -> dict[str, Any]:
    """What stops working if this part is lost: its item, and all a lander carries."""
    p = await PmRepository(session).part(part_id)
    if p is None:
        raise NotFound(part_id)
    if p.status == "spare":
        return {"stops_working": [], "note": "A spare: losing it leaves one spare fewer."}
    m = await _mission(session, p.mission_id)
    rows = [r for r, _ in await items(session, m)]
    parent = next((r for r in rows if r.id == p.parent_item_id), None)
    if parent is None:
        return {
            "stops_working": [],
            "note": "This part is not linked to a readiness item, so its effect is unknown.",
        }
    hit = [parent]
    if parent.kind == "lander":
        hit += [r for r in rows if r.kind in ("payload", "rover") and r.id != parent.id]
    return {
        "stops_working": [{"id": r.id, "name": r.name, "kind": r.kind} for r in hit],
        "note": "Everything the lander carries depends on it."
        if parent.kind == "lander"
        else "The item this part belongs to.",
    }


# --- risks -------------------------------------------------------------------------


def risk_scales() -> dict[str, Any]:
    return catalogues.risk_scales()


async def risks(session: AsyncSession, mission_id: str) -> dict[str, Any]:
    m = await _mission(session, mission_id)
    return {"risks": [_risk_out(r) for r in await PmRepository(session).risks(m.id)]}


def _check_risk(fields: dict[str, Any]) -> None:
    scales = {s["id"]: s for s in catalogues.risk_scales()["scales"]}
    scale = scales.get(fields.get("scale_id", ""))
    if scale is None:
        raise BadEntry(f"unknown risk scale; one of {', '.join(scales)}")
    lmax = max(x["level"] for x in scale["likelihood"])
    cats = {c["category"]: max(x["level"] for x in c["levels"]) for c in scale["consequence"]}
    ratings = fields.get("ratings") or []
    if not ratings:
        raise BadEntry("a risk needs at least one likelihood and consequence rating")
    seen = set()
    for r in ratings:
        c = r.get("category")
        if c not in cats:
            raise BadEntry(f"'{c}' is not a consequence category of this scale")
        if c in seen:
            raise BadEntry(f"two ratings for '{c}'")
        seen.add(c)
        if (
            not 1 <= int(r.get("likelihood", 0)) <= lmax
            or not 1 <= int(r.get("consequence", 0)) <= cats[c]
        ):
            raise BadEntry(f"ratings for '{c}' are outside the scale's levels")
    if fields.get("trend") not in ("rising", "steady", "falling"):
        raise BadEntry("trend is rising, steady or falling")
    for k in ("title", "cause", "consequence_text"):
        if not str(fields.get(k) or "").strip():
            raise BadEntry(f"a risk needs its {k.replace('_', ' ')}")


async def save_risk(
    session: AsyncSession,
    who: Claims,
    mission_id: str | None,
    risk_id: str | None,
    fields: dict[str, Any],
) -> dict[str, Any]:
    repo = PmRepository(session)
    before = None
    keys = (
        "title",
        "cause",
        "consequence_text",
        "scale_id",
        "ratings",
        "trend",
        "owner",
        "mitigation",
        "links",
    )
    if risk_id is not None:
        old = await repo.risk(risk_id, lock=True)
        if old is None:
            raise NotFound(risk_id)
        before = {k: getattr(old, k) for k in keys}
        mission_id = old.mission_id
        merged = {**before, **{k: v for k, v in fields.items() if k in keys}}
    else:
        assert mission_id is not None
        await _mission(session, mission_id)
        merged = {k: fields.get(k) for k in keys}
        risk_id = f"risk-{secrets.token_hex(5)}"
    merged["links"] = merged.get("links") or {"readiness_items": [], "parts": [], "lessons": []}
    _check_risk(merged)
    row = await repo.put_risk(
        {"id": risk_id, "mission_id": mission_id, **merged, "changed_by": who.actor}
    )
    await audit_service.record(
        session,
        who,
        action="update" if before else "create",
        entity="risk",
        entity_id=risk_id,
        mission_id=mission_id,
        before=before,
        after={k: getattr(row, k) for k in keys},
    )
    return _risk_out(row)


# --- lessons and landing history ---------------------------------------------------------


async def lessons(session: AsyncSession, mission_id: str | None) -> dict[str, Any]:
    adopted: dict[str, str] = {}
    if mission_id:
        await _mission(session, mission_id)
        adopted = await PmRepository(session).adoptions(mission_id)
    out = []
    for r in catalogues.load("lessons").records:
        out.append(
            {
                "id": r.id,
                "text": r.text,
                "from_mission": r.from_mission,
                "year": r.year,
                "source_url": r.sources[0].url,
                "checklist_item": r.checklist_item,
                "adopted": r.id in adopted,
            }
        )
    return {"lessons": out}


async def adopt_lesson(
    session: AsyncSession, who: Claims, mission_id: str, lesson_id: str
) -> dict[str, Any]:
    m = await _mission(session, mission_id)
    try:
        lesson = catalogues.load("lessons").get(lesson_id)
    except KeyError as exc:
        raise NotFound(lesson_id) from exc
    repo = PmRepository(session)
    existing = await repo.adoptions(m.id)
    if lesson_id in existing:
        return {"adopted": True, "item_id": existing[lesson_id]}
    kind = lesson.applies_to[0] if lesson.applies_to else "lander"
    row = ItemRow(
        id=item_id(m.id, f"lesson-{lesson_id}"),
        mission_id=m.id,
        kind=kind,
        name=lesson.checklist_item,
        organisation=None,
        state="not_started",
        blocked_from=None,
        blocked_reason=None,
        changed_on=datetime.now(UTC).date().isoformat(),
        changed_by=who.actor,
        evidence_url=None,
        source="entered",
        tests=[],
        position=4000,
    )
    await repo.put_item(row)
    await repo.adopt(m.id, lesson_id, row.id, who.actor)
    await audit_service.record(
        session,
        who,
        action="adopt",
        entity="lesson",
        entity_id=f"{m.id}:{lesson_id}",
        mission_id=m.id,
        before=None,
        after={"lesson": lesson_id, "item_id": row.id},
    )
    return {"adopted": True, "item_id": row.id}


def landing_history() -> dict[str, Any]:
    cat = catalogues.load("landing_attempts")
    attempts = sorted(cat.records, key=lambda r: r.date)
    return {
        "attempts": [
            {
                "mission": r.mission,
                "agency": r.agency,
                "date": r.date.isoformat(),
                "outcome": r.outcome,
                "cause": r.cause,
                "source_url": r.sources[0].url,
                "cause_url": r.field_sources.get("cause"),
                "clps": r.clps,
                "mission_id": r.mission_id,
            }
            for r in attempts
        ],
        "counts": {
            "attempts": len(attempts),
            "landed_working": sum(r.outcome == "landed_working" for r in attempts),
            "landed_tipped_or_partial": sum(
                r.outcome == "landed_tipped_or_partial" for r in attempts
            ),
            "failed": sum(r.outcome == "failed" for r in attempts),
        },
        "since": attempts[0].date.isoformat() if attempts else None,
        "note": "Counts of what happened, from the images NASA's Lunar Reconnaissance Orbiter "
        "took of each site. They are not a chance of success for any mission.",
    }
