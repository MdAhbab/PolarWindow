"""Site endpoints: list, detail, horizon, timeline, windows, metrics.

Routes parse, delegate and serialise. They import no SQLAlchemy and no ORM
model -- enforced by an import-linter contract, not by discipline alone.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Path, Query

from app.api.v1 import deps
from app.api.v1.schemas.sites import (
    CalendarResponse,
    HorizonResponse,
    MetricsResponse,
    SiteDetail,
    SiteList,
    TimelineResponse,
    WindowsResponse,
)
from app.services import site_service

router = APIRouter(prefix="/sites", tags=["sites"])

SiteId = Annotated[str, Path(description="Site slug, e.g. `connecting-ridge`.")]
Window = Annotated[tuple[datetime, datetime, int], Depends(deps.window_params)]


@router.get("", response_model=SiteList, summary="List candidate sites")
async def list_sites(
    q: str | None = Query(None, description="Substring of the name or region."),
    region: str | None = Query(None),
    lat_min: float | None = Query(None, ge=-90, le=0),
    lat_max: float | None = Query(None, ge=-90, le=0),
    min_sun_fraction: float | None = Query(
        None,
        ge=0,
        le=1,
        description="Coarse filter against the reference window, not the window on "
        "screen. Sites without a precompute are excluded when this is set, because "
        "they cannot be judged against it.",
    ),
    max_longest_dark_s: float | None = Query(None, ge=0),
    kind: Literal["candidate", "mission_target", "all"] = Query(
        "candidate",
        description="Derived candidates (the default, so the v1 list is unchanged), CLPS "
        "mission targets, or both.",
    ),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: Any = Depends(deps.db),
) -> dict[str, Any]:
    try:
        listing = await site_service.list_with_summaries(
            session,
            q=q,
            region=region,
            lat_min=lat_min,
            lat_max=lat_max,
            min_sun_fraction=min_sun_fraction,
            max_longest_dark_s=max_longest_dark_s,
            limit=limit,
            offset=offset,
            kind=None if kind == "all" else kind,
        )
    except Exception as exc:
        raise deps.to_http(exc) from exc

    return {
        # null, never zeros: absence is not a measurement.
        "items": [_brief(site, listing.summaries.get(site.id)) for site in listing.sites],
        "total": listing.total,
        "meta": listing.meta,
    }


def _brief(site: Any, summary: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "id": site.id,
        "code": site.code,
        "name": site.name,
        "region": site.region,
        "lat_deg": site.lat_deg,
        "lon_deg": site.lon_deg,
        "elev_m": site.elev_m,
        "slope_deg": site.slope_deg,
        "note": site.note,
        "search_kind": site.search_kind,
        "kind": site.kind,
        "coordinate_rule": site.coordinate_rule,
        "terrain_modelled": site.terrain_modelled,
        "summary": summary,
    }


@router.get("/{site_id}", response_model=SiteDetail, summary="Site detail with provenance")
async def get_site(
    site_id: SiteId,
    session: Any = Depends(deps.db),
) -> dict[str, Any]:
    try:
        site, mask_rec, summary, meta = await site_service.site_detail(session, site_id)
    except Exception as exc:
        raise deps.to_http(exc) from exc

    horizon = None
    if mask_rec is not None:
        horizon = {
            "max_el_deg": round(mask_rec.mask.max_el_deg, 4),
            "max_el_bearing_deg": round(mask_rec.mask.max_el_bearing_deg, 3),
            "mean_el_deg": round(mask_rec.mean_el_deg, 4),
            "coverage": round(mask_rec.mask.coverage, 4),
            "dem_product": mask_rec.dem_product,
            "computed_at": mask_rec.computed_at,
        }

    return {
        **_brief(site, summary),
        "provenance": {
            "anchor_lat_deg": site.anchor_lat_deg,
            "anchor_lon_deg": site.anchor_lon_deg,
            "search_kind": site.search_kind,
            "search_inner_km": site.search_inner_km,
            "search_outer_km": site.search_outer_km,
            "offset_from_anchor_km": site.offset_from_anchor_km,
            "source": site.source,
            "source_url": site.source_url,
            "source_note": site.source_note,
        },
        "horizon": horizon,
        "meta": meta,
    }


@router.get(
    "/{site_id}/horizon", response_model=HorizonResponse, summary="Azimuth to skyline elevation"
)
async def get_horizon(
    site_id: SiteId,
    step_deg: float = Query(
        1.0,
        gt=0,
        le=360,
        description="Output angular step. Must divide 360 and be a multiple of "
        "the stored 0.25 deg resolution.",
    ),
    session: Any = Depends(deps.db),
) -> dict[str, Any]:
    try:
        site = await site_service.require_site(session, site_id)
        rec = await site_service.require_mask(session, site_id)
        return site_service.horizon_payload(site, rec, step_deg)
    except ValueError as exc:
        raise deps.problem(
            422,
            "bad-resolution",
            "That horizon resolution is not available",
            str(exc),
            "The stored resolution and any divisor of it are available.",
        ) from exc
    except Exception as exc:
        raise deps.to_http(exc) from exc


@router.get("/{site_id}/timeline", response_model=TimelineResponse, summary="Sun and Earth track")
async def get_timeline(
    site_id: SiteId,
    window: Window,
    session: Any = Depends(deps.db),
) -> dict[str, Any]:
    start, end, step_s = window
    try:
        return await site_service.cached_payload(session, "timeline", site_id, start, end, step_s)
    except Exception as exc:
        raise deps.to_http(exc) from exc


@router.get(
    "/{site_id}/windows",
    response_model=WindowsResponse,
    summary="Lit/dark and link/blackout intervals",
)
async def get_windows(
    site_id: SiteId,
    window: Window,
    session: Any = Depends(deps.db),
) -> dict[str, Any]:
    start, end, step_s = window
    try:
        return await site_service.cached_payload(session, "windows", site_id, start, end, step_s)
    except Exception as exc:
        raise deps.to_http(exc) from exc


@router.get("/{site_id}/metrics", response_model=MetricsResponse, summary="The four key numbers")
async def get_metrics(
    site_id: SiteId,
    window: Window,
    session: Any = Depends(deps.db),
) -> dict[str, Any]:
    start, end, step_s = window
    try:
        return await site_service.cached_payload(session, "metrics", site_id, start, end, step_s)
    except Exception as exc:
        raise deps.to_http(exc) from exc


@router.get(
    "/{site_id}/calendar",
    response_model=CalendarResponse,
    summary="Sun and Earth by day or month, for choosing dates",
)
async def calendar(
    site_id: SiteId,
    start: datetime | None = Query(
        None, description="ISO 8601 UTC. Defaults to the reference start."
    ),
    end: datetime | None = Query(None, description="ISO 8601 UTC; at most 730 days after start."),
    bucket: Literal["day", "month"] = Query("month"),
    session: Any = Depends(deps.db),
) -> dict[str, Any]:
    s = deps.settings()
    begin = start or s.reference_window_start
    finish = end or begin + timedelta(days=365)
    try:
        return await site_service.calendar_payload(session, site_id, begin, finish, bucket)
    except Exception as exc:
        raise deps.to_http(exc) from exc
