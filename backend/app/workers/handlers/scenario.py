"""The ``scenario`` job: a mission's steps worked out on assumed values (never saved).

The compute worker resolves each assumed field (you, published, live, default), lays
the values over an in-memory copy of the mission's record, and runs the same launch,
trip, contact and return calculations on it that a real mission gets, forwarding their
progress. Live values (Launch Library 2) are fetched here, and only here, through
``app.feeds``, rate-limited and stored as a feed snapshot like any other fetch; a failed
or empty fetch falls to the default and says so.

The scenario row carries progress and the answer; the same answer is stored as one
assessment keyed on the canonical assumptions, so a similar prompt finds it.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import re
import time
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

from app.config import get_settings
from app.core import scenario as core
from app.core.scenario import Candidate, Resolved
from app.data import catalogues
from app.db.repositories.jobs import InputRef
from app.db.repositories.missions import MissionRecord, MissionRepository
from app.db.repositories.scenarios import ScenarioRepository
from app.db.repositories.sites import SiteRecord, SiteRepository
from app.db.session import session_scope
from app.services import (
    contact_service,
    launch_service,
    lifecycle,
    mission_service,
    return_service,
    scenario_service,
    site_service,
    trip_service,
)
from app.workers.compute import HandlerResult, JobContext, handler

log = logging.getLogger("polar_window.scenario")
_pending: set[asyncio.Task[None]] = set()

#: Share of the progress bar the live-source step takes; the steps share the rest.
INPUTS_SHARE = 0.1
LL2_NAME = "Launch Library 2 (The Space Devs)"
LL2_URL = "https://ll.thespacedevs.com/"


# ---------------------------------------------------------------------------
# Live values (Launch Library 2)
# ---------------------------------------------------------------------------


def _norm(s: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def match_launch(launches: list[dict[str, Any]], m: MissionRecord) -> dict[str, Any] | None:
    """The upcoming launch that is this mission's, by its names; None when none is listed."""
    names = [_norm(x) for x in (m.name, m.vehicle_name) if x and len(_norm(x)) >= 3]
    for launch in launches:
        hay = _norm(f"{launch.get('name')} {launch.get('mission')}")
        if any(n in hay for n in names):
            return launch
    return None


def live_candidates(
    launch: dict[str, Any], fetched_at: str | None, url: str | None
) -> dict[str, Candidate]:
    """What a matched launch says, as candidates for the scenario's fields."""
    out: dict[str, Candidate] = {}
    said = f"{launch.get('name')}: net {str(launch.get('net'))[:10]}" + (
        f" ({launch['net_precision']})" if launch.get("net_precision") else ""
    )

    def cand(value: Any, note: str) -> Candidate:
        return Candidate(value, LL2_NAME, url or LL2_URL, fetched_at, note)

    vehicle = _norm(launch.get("vehicle"))
    for v in catalogues.load("vehicles").records:
        if _norm(v.name) and _norm(v.name) in vehicle:
            out["vehicle_id"] = cand(v.id, f"Listed as {launch.get('vehicle')}.")
            break
    for p in catalogues.load("launch_sites").records:
        if p.ll2_pad_id is not None and p.ll2_pad_id == launch.get("pad_id"):
            out["pad_id"] = cand(p.id, f"Listed at {launch.get('pad_name')}.")
            break
    net = str(launch.get("net") or "")[:10]
    if net:
        end = str(launch.get("window_end") or "")[:10]
        last = end if end > net else (date.fromisoformat(net) + timedelta(days=1)).isoformat()
        out["launch_from"] = cand(net, said)
        out["launch_to"] = cand(last, said)
    return out


async def fetch_live(m: MissionRecord) -> tuple[dict[str, Candidate], str]:
    """Ask Launch Library 2 about this mission now: ``(candidates, what happened)``."""
    s = get_settings()
    if s.offline:
        return {}, "Live sources are off (offline mode); defaults are used."
    from app.db.repositories.feeds import FeedRepository
    from app.feeds import http, scheduler, targets

    prods = [p for p in targets.products() if p.provider == "ll2"]
    if not prods:
        return {}, "No Launch Library 2 product is set up; defaults are used."
    p = prods[0]
    sch = scheduler.Scheduler(
        products=prods,
        providers=targets.providers(),
        raw_root=s.data_dir / "feeds" / "raw",
        secrets=targets.secrets(),
    )
    note = ""
    try:
        async with http.make_client() as client:
            res = await sch.run_product(p, client)
        if not res.ok:
            note = f" (a new request was not made: {res.message})"
    except Exception as exc:
        note = f" (the request failed: {type(exc).__name__})"
    async with session_scope() as sess:
        snap = await FeedRepository(sess).latest_ok(p.provider, p.product, p.location_key)
    if snap is None or not snap.parsed:
        return {}, f"Asked Launch Library 2: no answer is stored{note}."
    fetched = snap.fetched_at.astimezone(UTC).isoformat()
    launch = match_launch(list(snap.parsed.get("launches") or []), m)
    if launch is None:
        return {}, f"Asked Launch Library 2: nothing listed for {m.name}{note}."
    return live_candidates(launch, fetched, snap.url), (
        f"Launch Library 2 lists {launch.get('name')}, net {str(launch.get('net'))[:10]}{note}."
    )


# ---------------------------------------------------------------------------
# Progress
# ---------------------------------------------------------------------------


class Tracker:
    """Phases and the 0 to 1 progress of one scenario, written to its row as it goes."""

    def __init__(self, ctx: JobContext, scenario_id: str, sections: list[str]) -> None:
        self.ctx = ctx
        self.sid = scenario_id
        self.phases = core.phases(sections)
        self.n = max(1, len(sections))
        self.assumptions: list[dict[str, Any]] | None = None
        self.progress = 0.0

    def phase(self, pid: str) -> dict[str, Any]:
        return next(p for p in self.phases if p["id"] == pid)

    def base(self, pid: str) -> float:
        if pid == "inputs":
            return 0.0
        ids = [p["id"] for p in self.phases if p["id"] != "inputs"]
        return INPUTS_SHARE + (1 - INPUTS_SHARE) * ids.index(pid) / self.n

    async def set(
        self, pid: str, state: str, detail: str | None = None, within: float = 0.0
    ) -> None:
        ph = self.phase(pid)
        if state == "active" and ph["state"] in ("done", "skipped", "failed"):
            return  # a late progress report must not undo the end of its phase
        ph["state"], ph["detail"] = state, detail
        width = INPUTS_SHARE if pid == "inputs" else (1 - INPUTS_SHARE) / self.n
        done = 1.0 if state in ("done", "skipped", "failed") else within
        self.progress = max(self.progress, min(0.99, self.base(pid) + width * done))
        msg = detail or ph["label"]
        self.ctx.progress(self.progress, msg)
        async with session_scope() as s:
            await ScenarioRepository(s).progress(
                self.sid,
                progress=self.progress,
                message=msg,
                phases=self.phases,
                assumptions=self.assumptions,
            )


@dataclasses.dataclass
class _Sub(JobContext):
    """A section's own job context: its progress is forwarded to the scenario's phase."""

    report: Callable[[float, str | None], None] | None = None

    def progress(self, fraction: float, message: str | None = None) -> None:
        super().progress(fraction, message)
        if self.report is not None:
            self.report(fraction, message)


# ---------------------------------------------------------------------------
# The steps
# ---------------------------------------------------------------------------


def _day(iso_day: str) -> datetime:
    return datetime.fromisoformat(f"{iso_day[:10]}T00:00:00+00:00")


def _sec(
    data: dict[str, Any],
    sources: list[dict[str, Any]],
    parts: list[tuple[str, str]],
    engines: tuple[str, ...],
) -> dict[str, Any]:
    return {"data": data, "meta": lifecycle.meta(engines=engines, sources=sources, parts=parts)}


async def _sub_run(
    ctx: JobContext,
    run: Callable[[JobContext], Any],
    params: dict[str, Any],
    kind: str,
    tracker: Tracker,
    pid: str,
) -> HandlerResult:
    last = {"t": 0.0}
    loop = asyncio.get_running_loop()

    def start(fraction: float, message: str | None) -> None:
        task = loop.create_task(
            tracker.set(pid, "active", message or tracker.phase(pid)["detail"], within=fraction)
        )
        _pending.add(task)
        task.add_done_callback(_pending.discard)

    def report(fraction: float, message: str | None) -> None:
        # The section reports from inside its own work; the scenario's row is written at
        # most every 1.5 s, in the background, and never after the phase has ended.
        now = time.monotonic()
        if now - last["t"] < 1.5:
            return
        last["t"] = now
        # Some sections report from a worker thread (``asyncio.to_thread``), where
        # there is no running loop: hand the write to the job's own loop.
        try:
            here = asyncio.get_running_loop()
        except RuntimeError:
            here = None
        if here is loop:
            start(fraction, message)
        else:
            loop.call_soon_threadsafe(start, fraction, message)

    sub = _Sub(job=dataclasses.replace(ctx.job, kind=kind, params=params), report=report)
    res: HandlerResult = await run(sub)
    return res


async def _launch(
    ctx: JobContext, tr: Tracker, m2: MissionRecord, res: dict[str, Resolved]
) -> dict[str, Any] | None:
    from app.workers.handlers import launch as launch_h

    start = _day(str(res["launch_from"].value))
    end = min(
        _day(str(res["launch_to"].value)) + timedelta(days=1),
        start + timedelta(days=launch_service.MAX_DAYS),
    )
    async with session_scope() as s:
        section, params = await launch_service.launch_plan(s, m2, start, end)
    if section is not None:
        reason = (section["data"] or {}).get("none_reason")
        await tr.set("launch", "skipped", reason)
        return None
    assert params is not None
    if "sun_el_min_deg" in res:
        params["parameters"]["landing_sun_min_deg"] = float(res["sun_el_min_deg"].value)
    if "sun_el_max_deg" in res:
        params["parameters"]["landing_sun_max_deg"] = float(res["sun_el_max_deg"].value)
    if "surface_days" in res:
        params["surface_days"] = float(res["surface_days"].value)
    out = await _sub_run(ctx, launch_h.run, params, "launch", tr, "launch")
    data = out.result["data"]
    if data.get("none_reason") and not data.get("opportunities"):
        await tr.set("launch", "skipped", data["none_reason"])
        return None
    await tr.set(
        "launch", "done", f"{len(data.get('opportunities') or [])} launch opportunities found."
    )
    return out.result


async def _trip(ctx: JobContext, tr: Tracker, m2: MissionRecord) -> dict[str, Any] | None:
    example: MissionRecord | None = None
    async with session_scope() as s:
        code, body = await trip_service.trip_for(s, m2)
        if code == 200 and (body.get("data") or {}).get("source") == "none":
            # No trip of its own: a worked example shows a named past flight's trip.
            flown = [
                r
                for r in await scenario_service.flight_rows(s, m2.id)
                if r.mission_id in trip_service.FLOWN
            ]
            if m2.status not in ("cancelled", "reassigned") and (
                pick := core.trip_precedent(m2.provider, m2.lander, flown)
            ):
                example = await MissionRepository(s).get(pick.mission_id)
                if example is not None:
                    code, body = await trip_service.trip_for(s, example)
    if code == 202:
        await tr.set(
            "trip",
            "skipped",
            f"The trip {example.name} flew is still being worked out; run this again shortly."
            if example
            else "This trip is worked out on the Trip page; it is the mission's own.",
        )
        return None
    data = body.get("data") or {}
    if data.get("source") == "none":
        await tr.set("trip", "skipped", data.get("none_reason"))
        return None
    if example is not None:
        body = {
            **body,
            "data": {**data, "example_of": {"mission_id": example.id, "name": example.name}},
        }
        await tr.set("trip", "done", f"The trip {example.name} flew, as an example.")
        return dict(body)
    await tr.set("trip", "done", "The trip from launch to the Moon.")
    return dict(body)


async def _surface(tr: Tracker, m2: MissionRecord, site: SiteRecord) -> dict[str, Any] | None:
    w = mission_service.surface_window(m2)
    if w.start is None or w.end is None:
        await tr.set("landing", "skipped", w.note)
        return None
    async with session_scope() as s:
        p = await site_service.cached_payload(
            s, "metrics", site.id, w.start, w.end, get_settings().default_step_s
        )
    keys = (
        "sunlit_s",
        "earth_contact_s",
        "longest_dark_s",
        "longest_blackout_s",
        "sun_fraction_up",
        "earth_fraction_up",
        "longest_dark_open",
        "longest_blackout_open",
    )
    data = {
        "site_id": site.id,
        "site_name": site.name,
        "window_start": lifecycle.iso(w.start),
        "window_end": lifecycle.iso(w.end),
        **{k: p[k] for k in keys},
        "terrain_modelled": bool(site.terrain_modelled),
    }
    await tr.set("landing", "done", w.note)
    return _sec(
        data,
        [],
        [("Surface", f"{w.note} The dates are assumed in this scenario.")],
        ("vis", "hz"),
    )


async def _contact(
    ctx: JobContext, tr: Tracker, m2: MissionRecord, res: dict[str, Resolved]
) -> dict[str, Any] | None:
    from app.workers.handlers import contact as contact_h

    async with session_scope() as s:
        try:
            params = await contact_service.contact_params(
                s, m2, None, None, list((res["relays"].value if "relays" in res else None) or [])
            )
        except (contact_service.NoContact, contact_service.BadRequest) as exc:
            await tr.set("contact", "skipped", str(exc))
            return None
    # Relays of the mission's own are already in the overlay; none are "added" here.
    params["extra_relays"] = []
    params["site_id"] = m2.site_id
    out = await _sub_run(ctx, contact_h.run, params, "contact", tr, "contact")
    data = out.result.setdefault("data", {})
    data.setdefault("start", params["start"])
    data.setdefault("end", params["end"])
    await tr.set(
        "contact", "done", f"Contact worked out for {params['start'][:10]} to {params['end'][:10]}."
    )
    return dict(out.result)


async def _return(tr: Tracker, m2: MissionRecord) -> dict[str, Any] | None:
    async with session_scope() as s:
        body = await return_service.recovery_for(s, m2)
    if not (body.get("data") or {}).get("booster"):
        await tr.set("return", "skipped", "No booster recovery is worked out for this vehicle.")
        return None
    await tr.set("return", "done", "Where the booster comes down.")
    return dict(body)


def summarise(
    results: dict[str, Any], res: dict[str, Resolved], nm: dict[str, dict[str, str]]
) -> dict[str, str]:
    """One plain sentence per step that was worked out. Counts and names only: no verdicts."""
    out: dict[str, str] = {}
    if "launch" in results:
        d = results["launch"]["data"]
        pad = core.display("pad_id", res["pad_id"].value, nm) if "pad_id" in res else "the pad"
        out["launch"] = (
            f"{len(d.get('opportunities') or [])} launch opportunities from {pad} between "
            f"{str(d.get('start'))[:10]} and {str(d.get('end'))[:10]}."
        )
    if "trip" in results:
        ex = (results["trip"].get("data") or {}).get("example_of")
        out["trip"] = (
            f"The trip {ex['name']} flew, shown as an example of this mission's trip."
            if ex
            else "The trip from launch to the Moon, as for a real mission."
        )
    if "landing" in results:
        d = results["landing"]["data"]
        out["landing"] = (
            f"At {d['site_name']} the Sun is above the skyline {d['sun_fraction_up'] * 100:.0f}% "
            f"of the time and Earth is in view {d['earth_fraction_up'] * 100:.0f}% of the time, "
            f"{d['window_start'][:10]} to {d['window_end'][:10]}."
        )
    if "contact" in results:
        d = results["contact"]["data"]
        out["contact"] = (
            f"Contact worked out for {str(d['start'])[:10]} to {str(d['end'])[:10]} "
            "at the assumed landing spot."
        )
    if "return" in results:
        veh = (
            core.display("vehicle_id", res["vehicle_id"].value, nm)
            if "vehicle_id" in res
            else "the"
        )
        out["return"] = f"Where the {veh} booster comes down; nothing returns from the Moon."
    return out


@handler("scenario")
async def run(ctx: JobContext) -> HandlerResult:
    p = ctx.job.params
    t_wall = time.perf_counter()
    sid: str = p["scenario_id"]
    given: dict[str, Any] = dict(p.get("given") or {})
    sections: list[str] = list(p.get("sections") or core.SECTIONS)
    tr = Tracker(ctx, sid, sections)

    async with session_scope() as s:
        m = await MissionRepository(s).get(p["mission_id"])
        if m is None:
            raise ValueError("the mission is gone")
        nm = await scenario_service.names(s)
        await ScenarioRepository(s).progress(
            sid, progress=0.0, message="Checking live sources.", phases=tr.phases
        )

    await tr.set("inputs", "active", "Asking Launch Library 2 about this mission.")
    live, said = await fetch_live(m)
    async with session_scope() as s:
        res_list = await scenario_service.resolve_all(s, m, given, live)
        res = {r.field: r for r in res_list}
        site = await SiteRepository(s).get(str(res["site_id"].value)) if "site_id" in res else None
    assumptions = [scenario_service.assumption_dict(r, nm) for r in res_list]
    tr.assumptions = assumptions
    await tr.set("inputs", "done", said)

    m2 = scenario_service.overlay(m, res_list, site)
    results: dict[str, Any] = {}
    failures: list[str] = []
    steps: dict[str, Callable[[], Any]] = {
        "launch": lambda: _launch(ctx, tr, m2, res)
        if "launch_from" in res and "launch_to" in res
        else _skip(tr, "launch", "Launch dates could not be settled."),
        "trip": lambda: _trip(ctx, tr, m2),
        "landing": lambda: _surface(tr, m2, site)
        if site is not None
        else _skip(tr, "landing", "No landing spot has a value."),
        "contact": lambda: _contact(ctx, tr, m2, res),
        "return": lambda: _return(tr, m2),
    }
    for sec in core.SECTIONS:
        if sec not in sections:
            continue
        if not scenario_service.can_run(sec, res_list) and sec != "trip":
            missing = core.missing_for(sec, list(res))
            await tr.set(
                sec,
                "skipped",
                "Needs "
                + ", ".join(core.SPEC_BY_ID[f].label.lower() for f in missing)
                + ", which nothing supplies.",
            )
            continue
        await tr.set(sec, "active", f"Working out {core.SECTION_LABELS[sec].lower()}.")
        try:
            got = await steps[sec]()
        except Exception as exc:  # one step failing must not cost the others
            log.warning("scenario %s: %s failed: %s", sid, sec, exc)
            why = plain_reason(exc)
            await tr.set(sec, "failed", why)
            failures.append(f"{sec}: {why}")
            continue
        if got is not None:
            results[sec] = got

    summaries = summarise(results, res, nm)
    message = "Worked out." if results else "Nothing could be worked out from these assumptions."
    status, message = core.outcome(tr.phases, message)
    error = "; ".join(failures)[:900] if status == "failed" else None
    out = {
        "status": status,
        "results": lifecycle.jsonable(results),
        "summaries": summaries,
        "assumptions": assumptions,
        "phases": tr.phases,
        "message": message,
    }
    async with session_scope() as s:
        await ScenarioRepository(s).finish(
            sid,
            results=out["results"],
            summaries=summaries,
            assumptions=assumptions,
            phases=tr.phases,
            message=message,
            status=status,
            error=error,
        )
    log.info("scenario %s done in %.1f s", sid, time.perf_counter() - t_wall)
    return HandlerResult(
        result=out,
        inputs=[
            InputRef("mission", m.id, m.data_version),
            InputRef("catalogue", "vehicles", catalogues.load("vehicles").version),
            InputRef("catalogue", "launch_sites", catalogues.load("launch_sites").version),
        ],
        message=message,
    )


def plain_reason(exc: Exception) -> str:
    """Why a step failed, in words a reader can use (no exception class names)."""
    if isinstance(exc, site_service.MaskNotBuilt):
        return (
            "The skyline at the landing spot is not built yet, so this step could not be "
            "worked out. Ask again once it is."
        )
    text = str(exc).strip()
    return text[:200] if text else "It could not be worked out."


async def _skip(tr: Tracker, pid: str, why: str) -> None:
    await tr.set(pid, "skipped", why)
