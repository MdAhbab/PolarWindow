"""CLPS missions, and what Sun and Earth do at each one's target (contract v2).

Mission facts come from the database, loaded from the cited file (ADR-5). The
numbers come from the same geometry path every site uses: a mission's target
is a site (ADR-6), and its four numbers are that site's metrics over the
mission's surface window. This module decides what that window is, and says
plainly when there is none.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import ENGINE_VERSION, get_settings
from app.core.horizon import is_terrain_modelled
from app.core.projections import ellipse_ring
from app.db.repositories.missions import MissionRecord, MissionRepository
from app.db.repositories.sites import MaskRepository, SiteRecord, SiteRepository
from app.services import site_service

#: Half a synodic month: one lunar daylight period at a non-polar site. Used,
#: and named as an assumption, when a landing date is known but the planned
#: surface duration is not.
LUNAR_DAYLIGHT_S = 29.530589 * 86400.0 / 2.0

#: Missions with no time on the surface to describe.
NO_SURFACE = frozenset({"lost_before_landing", "landing_failed", "cancelled", "reassigned"})


class MissionNotFound(LookupError):
    pass


def _parse(text: str) -> datetime:
    t = text.replace("Z", "+00:00")
    dt = datetime.fromisoformat(t) if "T" in t else datetime.fromisoformat(t + "T00:00:00+00:00")
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _end_of(d: dict[str, Any]) -> datetime:
    """The last instant a date covers: a day-precision date covers the whole day."""
    at = _parse(d["date"])
    return at + timedelta(days=1) if d["precision"] == "day" else at


@dataclass(frozen=True, slots=True)
class SurfaceWindow:
    start: datetime | None
    end: datetime | None
    basis: str
    note: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "start": self.start,
            "end": self.end,
            "basis": self.basis,
            "note": self.note,
        }


def surface_window(m: MissionRecord) -> SurfaceWindow:
    """The span a mission's four numbers describe, and what it rests on.

    * ``published``: landing and end of mission both sourced to the day or better.
    * ``planned``: landing sourced to the day, planned surface duration sourced.
    * ``assumed``: landing sourced to the day, duration not; one lunar daylight
      period is used and named.
    * ``none``: no single window can be stated, and the UI shows the calendar.
    """
    if m.status in NO_SURFACE:
        return SurfaceWindow(None, None, "none", "This mission has no time on the surface.")
    landing = m.landing
    if landing is None:
        return SurfaceWindow(None, None, "none", "The landing date is not published.")
    if landing["precision"] not in ("minute", "day"):
        return SurfaceWindow(
            None,
            None,
            "none",
            f"The landing date is known only as '{landing['as_published']}', so there is no "
            "single window: compare months on the calendar instead.",
        )
    start = _parse(landing["date"])
    eom = m.end_of_mission
    if eom is not None and eom["precision"] in ("minute", "day"):
        return SurfaceWindow(
            start,
            _end_of(eom),
            "published",
            f"From landing ({landing['as_published']}) to end of mission "
            f"({eom['as_published']}), as published.",
        )
    if m.planned_surface_days:
        return SurfaceWindow(
            start,
            start + timedelta(days=m.planned_surface_days),
            "planned",
            f"From landing, for the planned {m.planned_surface_days:g} days.",
        )
    return SurfaceWindow(
        start,
        start + timedelta(seconds=LUNAR_DAYLIGHT_S),
        "assumed",
        "From landing, for one lunar daylight period (14.8 days): the surface duration "
        "is not published, so this span is an assumption, not a plan.",
    )


def _date(d: dict[str, Any] | None) -> dict[str, Any] | None:
    return None if d is None else {k: d[k] for k in ("date", "precision", "as_published")}


async def _summary(
    session: AsyncSession, m: MissionRecord, window: SurfaceWindow, site: SiteRecord | None
) -> dict[str, Any] | None:
    """The four numbers over the surface window, or None when there is none."""
    if site is None or window.start is None or window.end is None:
        return None
    try:
        p = await site_service.cached_payload(
            session, "metrics", site.id, window.start, window.end, get_settings().default_step_s
        )
    except (site_service.MaskNotBuilt, site_service.SiteNotFound):
        return None
    u = p["meta"]["uncertainty"]
    return {
        "window_start": p["start"],
        "window_end": p["end"],
        "sunlit_s": p["sunlit_s"],
        "earth_contact_s": p["earth_contact_s"],
        "longest_dark_s": p["longest_dark_s"],
        "longest_blackout_s": p["longest_blackout_s"],
        "sun_fraction_up": p["sun_fraction_up"],
        "earth_fraction_up": p["earth_fraction_up"],
        "longest_dark_open": p["longest_dark_open"],
        "longest_blackout_open": p["longest_blackout_open"],
        "grazing": u["grazing"],
        "terrain_modelled": u.get("terrain_modelled", True),
    }


def _brief(
    m: MissionRecord, site: SiteRecord | None, window: SurfaceWindow, summary: dict[str, Any] | None
) -> dict[str, Any]:
    return {
        "id": m.id,
        "name": m.name,
        "vehicle_name": m.vehicle_name,
        "task_order": m.task_order,
        "provider": m.provider,
        "lander": m.lander,
        "status": m.status,
        "region": m.region,
        "target_name": m.target_name,
        "target": m.target,
        "launch": _date(m.launch),
        "landing": _date(m.landing),
        "payload_types": m.payload_types,
        "payload_count": len(m.payloads),
        "site_id": m.site_id,
        "terrain_modelled": None if site is None else site.terrain_modelled,
        "surface_window": window.as_dict(),
        "summary": summary,
        "unconfirmed_fields": m.unconfirmed_fields,
        "data_version": m.data_version,
    }


async def _sites(session: AsyncSession, ids: list[str]) -> dict[str, SiteRecord]:
    if not ids:
        return {}
    sites, _ = await SiteRepository(session).list_sites(kind=None, ids=ids, limit=500)
    return {s.id: s for s in sites}


async def _meta(session: AsyncSession, missions: list[MissionRecord]) -> dict[str, Any]:
    ids = sorted({m.site_id for m in missions if m.site_id})
    masks = await MaskRepository(session).get_many(ids, ENGINE_VERSION)
    meta = site_service.set_meta(masks, {}, filtered=False)
    accessed = sorted({s.get("accessed", "") for m in missions for s in m.sources} - {""})
    unconfirmed = sum(1 for m in missions if m.unconfirmed_fields)
    notes = [
        "Mission facts are compiled by hand from NASA pages, LROC images and the IAU "
        "Gazetteer; every record carries its sources"
        + (f", last read {accessed[-1]}." if accessed else "."),
        f"{unconfirmed} of {len(missions)} missions have fields no source confirms; they "
        "are listed as unconfirmed, never filled in.",
        "Numbers are Sun and Earth geometry at the target over the mission's surface window, "
        "not what any lander measured.",
    ]
    smooth = [
        m
        for m in missions
        if m.site_id in masks and not is_terrain_modelled(masks[m.site_id].dem_product)
    ]
    if smooth:
        notes.append(
            f"{len(smooth)} target(s) lie outside the 80-90 deg S elevation model; there Sun and "
            "Earth are computed against a smooth sphere, so terrain could block more."
        )
    if any(m.target and m.target.get("coordinate_kind") == "feature_centre" for m in missions):
        notes.append(
            "Where no landing point is published, the target is the IAU centre of the named "
            "feature, which is not a landing point."
        )
    # The site-list notes set_meta writes describe the reference window, which
    # these numbers are not computed over; they are replaced, not appended to.
    meta["uncertainty"]["notes"] = notes
    return meta


async def list_missions(
    session: AsyncSession,
    *,
    statuses: list[str] | None = None,
    provider: str | None = None,
    payload_types: list[str] | None = None,
    region: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    q: str | None = None,
) -> dict[str, Any]:
    missions = await MissionRepository(session).find(
        statuses=statuses,
        provider=provider,
        payload_types=payload_types,
        region=region,
        date_from=date_from,
        date_to=date_to,
        q=q,
    )
    sites = await _sites(session, [m.site_id for m in missions if m.site_id])
    items = []
    for m in missions:
        site = sites.get(m.site_id) if m.site_id else None
        window = surface_window(m)
        items.append(_brief(m, site, window, await _summary(session, m, window, site)))
    return {"items": items, "total": len(items), "meta": await _meta(session, missions)}


async def get_mission(session: AsyncSession, mission_id: str) -> dict[str, Any]:
    m = await MissionRepository(session).get(mission_id)
    if m is None:
        raise MissionNotFound(mission_id)
    sites = await _sites(session, [m.site_id] if m.site_id else [])
    site = sites.get(m.site_id) if m.site_id else None
    window = surface_window(m)
    ring = None
    if m.ellipse and m.target:
        ring = [
            [lat, lon]
            for lat, lon in ellipse_ring(
                m.target["lat_deg"],
                m.target["lon_deg"],
                m.ellipse["semi_major_km"],
                m.ellipse["semi_minor_km"],
                m.ellipse["azimuth_deg"],
            )
        ]
    return {
        **_brief(m, site, window, await _summary(session, m, window, site)),
        "outcome_note": m.outcome_note,
        "end_of_mission": _date(m.end_of_mission),
        "planned_surface_days": m.planned_surface_days,
        "payloads": [
            {
                "id": p.id,
                "name": p.name,
                "acronym": p.acronym,
                "organisation": p.organisation,
                "instrument_types": p.instrument_types,
                "purpose": p.purpose,
                "source_url": p.source_url,
                "unconfirmed": p.unconfirmed,
            }
            for p in m.payloads
        ],
        "sources": m.sources,
        "notes": m.notes,
        "ellipse_ring": ring,
        "site": None if site is None else site_brief(site),
        "lifecycle": lifecycle_brief(m),
        "meta": await _meta(session, [m]),
    }


def lifecycle_brief(m: MissionRecord) -> dict[str, Any] | None:
    """The v2 facts with the catalogue names of the vehicle and pad."""
    lc = m.lifecycle
    if not lc:
        return None
    from app.data import catalogues

    def name_of(cat: str, rid: str | None) -> str | None:
        if not rid:
            return None
        try:
            return str(catalogues.load(cat).get(rid).name)
        except (KeyError, catalogues.CatalogueError):
            return None

    t0 = lc.get("t0")
    return {
        **{
            k: lc.get(k)
            for k in (
                "vehicle_id",
                "pad_id",
                "transfer",
                "descent",
                "comms",
                "spacecraft",
                "returns",
            )
        },
        "vehicle_name": name_of("vehicles", lc.get("vehicle_id")),
        "pad_name": name_of("launch_sites", lc.get("pad_id")),
        "t0": None if t0 is None else {k: t0[k] for k in ("date", "precision", "as_published")},
        "rovers": list(lc.get("rovers") or []),
        "field_sources": dict(lc.get("field_sources") or {}),
    }


def site_brief(site: SiteRecord) -> dict[str, Any]:
    return {
        "id": site.id,
        "code": site.code,
        "name": site.name,
        "lat_deg": site.lat_deg,
        "lon_deg": site.lon_deg,
        "elev_m": site.elev_m,
        "kind": site.kind,
        "coordinate_rule": site.coordinate_rule,
        "terrain_modelled": site.terrain_modelled,
        "source_note": site.source_note,
    }


async def site_ids_with_missions(
    session: AsyncSession,
    *,
    statuses: list[str] | None = None,
    provider: str | None = None,
    payload_types: list[str] | None = None,
) -> list[str]:
    """Sites that stand for a mission matching the filters (for agent search)."""
    missions = await MissionRepository(session).find(
        statuses=statuses, provider=provider, payload_types=payload_types
    )
    return sorted({m.site_id for m in missions if m.site_id})


async def missions_for_sites(
    session: AsyncSession, site_ids: list[str]
) -> dict[str, list[dict[str, Any]]]:
    """Each site's missions, trimmed to what an agent may repeat (no numbers but dates)."""
    grouped = await MissionRepository(session).by_site(site_ids)
    return {
        sid: [
            {
                "id": m.id,
                "name": m.name,
                "provider": m.provider,
                "status": m.status,
                "landing": _date(m.landing),
                "payload_types": m.payload_types,
            }
            for m in ms
        ]
        for sid, ms in grouped.items()
    }
