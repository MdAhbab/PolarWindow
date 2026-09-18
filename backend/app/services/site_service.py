"""Site-level orchestration: fetch the mask, compute the window, shape the DTO.

No FastAPI import anywhere in this module. That is what lets the agent tool
layer and the precompute worker call exactly the same code the HTTP routes do,
so a number can never differ depending on who asked for it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import ENGINE_VERSION, get_settings
from app.core import metrics as core_metrics
from app.db.repositories.metrics import WindowMetricsRepository
from app.db.repositories.sites import MaskRecord, MaskRepository, SiteRecord, SiteRepository
from app.services import cache, geometry_service

log = logging.getLogger(__name__)


class SiteNotFound(LookupError):
    pass


class MaskNotBuilt(RuntimeError):
    """The site exists but its horizon has not been precomputed.

    A distinct failure from "site not found", and deliberately not silently
    degraded into a flat horizon: a flat horizon presented as terrain is worse
    than an error, because it produces confident, wrong sunlight numbers.
    """

    def __init__(self, site_id: str) -> None:
        # Written for a reader, not for a log. The engine version matters when
        # something is wrong, so it is kept -- but after the sentence that
        # explains what happened, not in place of one.
        super().__init__(
            f"The skyline at this site has not been mapped yet, so its sunlight "
            f"and Earth-contact hours cannot be worked out. Surveying a site takes "
            f"a couple of minutes and only has to happen once. "
            f"(site: {site_id}, engine: {ENGINE_VERSION})"
        )
        self.site_id = site_id


@dataclass(frozen=True, slots=True)
class ComputedWindow:
    """A geometry result plus the provenance needed to describe it."""

    site: SiteRecord
    mask_record: MaskRecord
    result: geometry_service.GeometryResult

    def meta(self, cache_state: str = "miss") -> dict[str, Any]:
        return geometry_service.meta(
            self.result,
            self.mask_record.mask,
            dem_product=self.mask_record.dem_product,
            dem_resolution_m=self.mask_record.dem_resolution_m,
            dem_vertical_error_m=self.mask_record.dem_vertical_error_m,
            coverage=self.mask_record.mask.coverage,
            cache=cache_state,
        )


async def require_site(session: AsyncSession, site_id: str) -> SiteRecord:
    site = await SiteRepository(session).get(site_id)
    if site is None:
        raise SiteNotFound(site_id)
    return site


async def require_mask(session: AsyncSession, site_id: str) -> MaskRecord:
    rec = await MaskRepository(session).get(site_id, ENGINE_VERSION)
    if rec is None:
        raise MaskNotBuilt(site_id)
    return rec


async def compute(
    session: AsyncSession,
    site_id: str,
    start: datetime,
    end: datetime,
    step_s: int,
) -> ComputedWindow:
    """Compute one site over one window. Uncached; callers add caching."""
    site = await require_site(session, site_id)
    mask_rec = await require_mask(session, site_id)
    result = await geometry_service.compute_window_metrics(
        site_id=site.id,
        lat_deg=site.lat_deg,
        lon_deg=site.lon_deg,
        elev_m=site.elev_m,
        mask=mask_rec.mask,
        start=start,
        end=end,
        step_s=step_s,
    )
    return ComputedWindow(site=site, mask_record=mask_rec, result=result)


# ---------------------------------------------------------------------------
# DTO shaping
# ---------------------------------------------------------------------------


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def _at(start: datetime, offset_s: float) -> str:
    return _iso(start + timedelta(seconds=float(offset_s)))


def timeline_payload(cw: ComputedWindow, cache_state: str = "miss") -> dict[str, Any]:
    """Parallel arrays, not an array of objects.

    2,835 samples x 2 bodies x 5 fields is ~1.1 MB as objects and ~230 KB as
    arrays before compression, and the frontend indexes by sample anyway.
    """
    r = cw.result

    def body(track: Any) -> dict[str, Any]:
        return {
            "az_deg": np.round(track.az_deg, 4).tolist(),
            "el_deg": np.round(track.el_deg, 4).tolist(),
            "mask_el_deg": np.round(track.mask_el_deg, 4).tolist(),
            "margin_deg": np.round(track.margin_deg, 4).tolist(),
            "state": track.state.astype(int).tolist(),
        }

    return {
        "site_id": r.site_id,
        "start": _iso(r.start),
        "end": _iso(r.end),
        "step_s": r.step_s,
        "t_s": r.sun.t_s.astype(int).tolist(),
        "sun": body(r.sun),
        "earth": body(r.earth),
        "meta": cw.meta(cache_state),
    }


def _arcs(track: Any, start: datetime) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i, arc in enumerate(track.arcs):
        out.append(
            {
                "up": arc.value,
                "start": _at(start, arc.start),
                "end": _at(start, arc.end),
                "duration_s": round(arc.duration, 3),
                "tolerance_s": round(track.arc_tolerance_s[i], 3),
                "grazing": bool(track.arc_grazing[i]),
                "blocked_by_bearing_deg": (
                    round(track.blocked_by_bearing_deg[i], 3)
                    if track.blocked_by_bearing_deg[i] is not None
                    else None
                ),
                "blocked_by_el_deg": (
                    round(track.blocked_by_el_deg[i], 4)
                    if track.blocked_by_el_deg[i] is not None
                    else None
                ),
            }
        )
    return out


def _body_windows(
    track: Any, arcs_payload: list[dict[str, Any]], start: datetime
) -> dict[str, Any]:
    bm = core_metrics.body_metrics(track.body, track.arcs, grazing=track.grazing)
    longest = max((a for a in track.arcs if not a.value), key=lambda a: a.duration, default=None)
    longest_tol = 0.0
    if longest is not None:
        longest_tol = track.arc_tolerance_s[track.arcs.index(longest)]
    return {
        "body": track.body,
        "arcs": arcs_payload,
        "up_s": round(bm.up_s, 3),
        "down_s": round(bm.down_s, 3),
        "fraction_up": round(bm.fraction_up, 6),
        "longest_down_s": round(bm.longest_down_s, 3),
        "longest_down_tolerance_s": round(longest_tol, 3),
        "longest_down_start": _at(start, longest.start) if longest else None,
        "longest_down_end": _at(start, longest.end) if longest else None,
        "grazing": track.grazing,
    }


def windows_payload(cw: ComputedWindow, cache_state: str = "miss") -> dict[str, Any]:
    r = cw.result
    return {
        "site_id": r.site_id,
        "start": _iso(r.start),
        "end": _iso(r.end),
        "sun": _body_windows(r.sun, _arcs(r.sun, r.start), r.start),
        "earth": _body_windows(r.earth, _arcs(r.earth, r.start), r.start),
        "compound": [
            {
                "start": _at(r.start, c.start),
                "end": _at(r.start, c.end),
                "duration_s": round(c.duration, 3),
            }
            for c in r.metrics.compound
        ],
        "worst_compound_s": round(r.metrics.worst_compound_s, 3),
        "meta": cw.meta(cache_state),
    }


def metrics_payload(cw: ComputedWindow, cache_state: str = "miss") -> dict[str, Any]:
    r = cw.result
    m = r.metrics
    a = r.autonomy
    return {
        "site_id": r.site_id,
        "start": _iso(r.start),
        "end": _iso(r.end),
        "sunlit_s": round(m.sunlit_s, 3),
        "earth_contact_s": round(m.earth_contact_s, 3),
        "longest_dark_s": round(m.longest_dark_s, 3),
        "longest_blackout_s": round(m.longest_blackout_s, 3),
        "sun_fraction_up": round(m.sun.fraction_up, 6),
        "earth_fraction_up": round(m.earth.fraction_up, 6),
        "worst_compound_s": round(m.worst_compound_s, 3),
        "autonomy": {
            "worst_compound_s": round(a.worst_compound_s, 3),
            "required_autonomy_s": round(a.required_autonomy_s, 3),
            "survival_needed_s": round(a.survival_needed_s, 3),
            "compound_inside_dark": a.compound_inside_dark,
        },
        "meta": cw.meta(cache_state),
    }


def horizon_payload(
    site: SiteRecord, rec: MaskRecord, step_deg: float, cache_state: str = "miss"
) -> dict[str, Any]:
    """Downsample by MAXIMUM, never by mean.

    A skyline is an upper envelope. Averaging it invents sky where a ridge is,
    and at these sites a single ridge is the whole answer -- so a mean-based
    downsample would quietly add hours of fictional sunlight.
    """
    from app.core.horizon import downsample

    mask = rec.mask
    target = int(round(360.0 / step_deg))
    el = downsample(mask.el_deg, target) if target != mask.azimuth_count else mask.el_deg
    factor = mask.azimuth_count // target
    rng = mask.range_m.reshape(target, factor).min(axis=1) if factor > 1 else mask.range_m
    tol = mask.tol_deg.reshape(target, factor).max(axis=1) if factor > 1 else mask.tol_deg

    return {
        "site_id": site.id,
        "azimuth_step_deg": 360.0 / target,
        "azimuth_count": target,
        "el_deg": np.round(el.astype(float), 4).tolist(),
        "range_m": np.round(rng.astype(float), 1).tolist(),
        "tol_deg": np.round(tol.astype(float), 4).tolist(),
        "max_el_deg": round(mask.max_el_deg, 4),
        "max_el_bearing_deg": round(mask.max_el_bearing_deg, 3),
        "meta": {
            "computed_at": _iso(rec.computed_at),
            "resolution": {
                "azimuth_deg": 360.0 / target,
                "azimuth_count": target,
                "time_step_s": 0,
                "max_range_m": mask.max_range_m,
                "dem_product": rec.dem_product,
                "dem_resolution_m": rec.dem_resolution_m,
                "ephemeris": "not used for a horizon mask",
                "frame": "site-local ENU",
            },
            "uncertainty": {
                "dem_vertical_error_m": rec.dem_vertical_error_m,
                "dem_resolution_m": rec.dem_resolution_m,
                "coverage": round(mask.coverage, 4),
                "horizon_el_deg": round(float(np.mean(mask.tol_deg)), 4),
                "edge_timing_s": None,
                "grazing": False,
                "penumbra_sun_deg": 0.0,
                "penumbra_earth_deg": 0.0,
                "notes": [
                    f"Terrain modelled to {mask.max_range_m / 1000:.0f} km around the site.",
                    f"Downsampled from {mask.azimuth_count} bins by taking the maximum of "
                    f"each group, never the mean: a skyline is an upper envelope and "
                    f"averaging it would invent sky where a ridge is.",
                ],
            },
            "engine_version": rec.engine_version,
            "cache": cache_state,
            "compute_ms": round(mask.compute_ms, 1),
        },
    }


# ---------------------------------------------------------------------------
# Cached entry points
# ---------------------------------------------------------------------------


async def cached_payload(
    session: AsyncSession,
    kind: str,
    site_id: str,
    start: datetime,
    end: datetime,
    step_s: int,
) -> dict[str, Any]:
    """Compute or fetch one of the three window payloads, with single-flight."""
    s = get_settings()
    qs, qe, step_s = geometry_service.validate_window(start, end, step_s)
    key = cache.make_key(kind, site=site_id, start=_iso(qs), end=_iso(qe), step=step_s)
    ttl = {
        "timeline": s.cache_ttl_timeline_s,
        "windows": s.cache_ttl_windows_s,
        "metrics": s.cache_ttl_metrics_s,
    }[kind]
    builder = {
        "timeline": timeline_payload,
        "windows": windows_payload,
        "metrics": metrics_payload,
    }[kind]

    async def compute_it() -> dict[str, Any]:
        cw = await compute(session, site_id, qs, qe, step_s)
        return builder(cw)

    payload, state = await cache.single_flight(key, compute_it, ttl)
    # The cached body carries whatever cache state it had when stored; correct
    # it so `meta.cache` describes *this* request rather than the one that
    # populated the entry.
    if isinstance(payload.get("meta"), dict):
        payload["meta"]["cache"] = state
    return payload


async def reference_summaries(
    session: AsyncSession, site_ids: list[str]
) -> dict[str, dict[str, Any]]:
    """Coarse summaries for the site list, from the precomputed table.

    Sites without a precompute are simply absent from the result, which the
    route turns into ``summary: null``. Never zeros: a zero is a measurement.
    """
    s = get_settings()
    start = s.reference_window_start
    end = start + timedelta(days=s.reference_window_days)
    qs = geometry_service.quantise(start, s.default_step_s)
    qe = geometry_service.quantise(end, s.default_step_s)
    rows = await WindowMetricsRepository(session).get_many(
        site_ids, ENGINE_VERSION, qs, qe, s.default_step_s
    )
    return {
        sid: {
            "sunlit_s": r.sunlit_s,
            "earth_contact_s": r.earth_contact_s,
            "longest_dark_s": r.longest_dark_s,
            "longest_blackout_s": r.longest_blackout_s,
            "sun_fraction_up": r.sun_fraction_up,
            "earth_fraction_up": r.earth_fraction_up,
            "worst_compound_s": r.worst_compound_s,
            "grazing": r.grazing,
            "reference_window_start": _iso(qs),
            "reference_window_end": _iso(qe),
            "reference_step_s": s.default_step_s,
        }
        for sid, r in rows.items()
    }


# ---------------------------------------------------------------------------
# Entry points that used to live in the route layer
# ---------------------------------------------------------------------------


async def list_with_summaries(
    session: AsyncSession,
    *,
    q: str | None = None,
    region: str | None = None,
    lat_min: float | None = None,
    lat_max: float | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[SiteRecord], int, dict[str, dict[str, Any]]]:
    """Sites plus their reference summaries.

    Lives here rather than in the route so that routes never touch a repository
    -- the layering rule in docs/system-design.md section 2, which import-linter
    enforces rather than trusting to review.
    """
    sites, total = await SiteRepository(session).list_sites(
        q=q, region=region, lat_min=lat_min, lat_max=lat_max, limit=limit, offset=offset
    )
    summaries = await reference_summaries(session, [x.id for x in sites])
    return sites, total, summaries


async def get_mask_record(session: AsyncSession, site_id: str) -> MaskRecord | None:
    """The stored mask, or None when the site has not been surveyed."""
    return await MaskRepository(session).get(site_id, ENGINE_VERSION)


async def database_is_reachable(session: AsyncSession) -> bool:
    """Liveness probe for /healthz, so the route need not import sqlalchemy."""
    from sqlalchemy import text

    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        return False
    return True
