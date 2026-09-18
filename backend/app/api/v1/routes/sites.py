"""Site endpoints: list, detail, horizon, timeline, windows, metrics.

Routes parse, delegate and serialise. They import no SQLAlchemy and no ORM
model -- enforced by an import-linter contract, not by discipline alone.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query

from app.api.v1 import deps
from app.api.v1.schemas.sites import (
    HorizonResponse,
    MetricsResponse,
    SiteDetail,
    SiteList,
    TimelineResponse,
    WindowsResponse,
)
from app.config import ENGINE_VERSION, Settings
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
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: Any = Depends(deps.db),
    s: Settings = Depends(deps.settings),
) -> dict[str, Any]:
    try:
        sites, total, summaries = await site_service.list_with_summaries(
            session,
            q=q,
            region=region,
            lat_min=lat_min,
            lat_max=lat_max,
            limit=limit,
            offset=offset,
        )
    except Exception as exc:
        raise deps.to_http(exc) from exc

    items: list[dict[str, Any]] = []
    for site in sites:
        summary = summaries.get(site.id)
        # A site with no precompute cannot be judged against a metric filter, so
        # it is excluded rather than assumed to pass.
        if min_sun_fraction is not None and (
            summary is None or summary["sun_fraction_up"] < min_sun_fraction
        ):
            continue
        if max_longest_dark_s is not None and (
            summary is None or summary["longest_dark_s"] > max_longest_dark_s
        ):
            continue
        items.append(
            {
                "id": site.id,
                "code": site.code,
                "name": site.name,
                "region": site.region,
                "lat_deg": site.lat_deg,
                "lon_deg": site.lon_deg,
                "elev_m": site.elev_m,
                "slope_deg": site.slope_deg,
                "note": site.note,
                # null, never zeros: absence is not a measurement.
                "summary": summary,
            }
        )

    return {
        "items": items,
        "total": total if (min_sun_fraction is None and max_longest_dark_s is None) else len(items),
        "meta": _list_meta(
            s, filtered=min_sun_fraction is not None or max_longest_dark_s is not None
        ),
    }


def _list_meta(s: Settings, *, filtered: bool) -> dict[str, Any]:
    notes = [
        "Summaries are computed over the reference window at a "
        f"{s.default_step_s} s step, not over any window you have selected.",
        "A site with no summary has not been surveyed yet; it is shown without "
        "numbers rather than with zeros.",
    ]
    if filtered:
        notes.append(
            "Metric filters were applied against the reference window. A site that "
            "passes here may fail for the window you are actually planning."
        )
    return {
        "computed_at": s.reference_window_start.isoformat().replace("+00:00", "Z"),
        "resolution": {
            "azimuth_deg": s.azimuth_step_deg,
            "azimuth_count": int(round(360 / s.azimuth_step_deg)),
            "time_step_s": s.default_step_s,
            "max_range_m": s.max_range_m,
            "dem_product": "LOLA LDEM 80S",
            "dem_resolution_m": 20.0,
            "ephemeris": "de440 + moon_pa_de440 (MOON_ME)",
            "frame": "MOON_ME",
        },
        "uncertainty": {
            "dem_vertical_error_m": 2.0,
            "dem_resolution_m": 20.0,
            "coverage": 1.0,
            "horizon_el_deg": 0.0,
            "edge_timing_s": None,
            "grazing": False,
            "penumbra_sun_deg": 0.266,
            "penumbra_earth_deg": 0.95,
            "notes": notes,
        },
        "engine_version": ENGINE_VERSION,
        "cache": "miss",
    }


@router.get("/{site_id}", response_model=SiteDetail, summary="Site detail with provenance")
async def get_site(
    site_id: SiteId,
    session: Any = Depends(deps.db),
    s: Settings = Depends(deps.settings),
) -> dict[str, Any]:
    try:
        site = await site_service.require_site(session, site_id)
        mask_rec = await site_service.get_mask_record(session, site_id)
        summaries = await site_service.reference_summaries(session, [site_id])
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
        "id": site.id,
        "code": site.code,
        "name": site.name,
        "region": site.region,
        "lat_deg": site.lat_deg,
        "lon_deg": site.lon_deg,
        "elev_m": site.elev_m,
        "slope_deg": site.slope_deg,
        "note": site.note,
        "summary": summaries.get(site_id),
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
        "meta": _list_meta(s, filtered=False),
    }


@router.get(
    "/{site_id}/horizon", response_model=HorizonResponse, summary="Azimuth to skyline elevation"
)
async def get_horizon(
    site_id: SiteId,
    step_deg: float = Query(
        1.0,
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
