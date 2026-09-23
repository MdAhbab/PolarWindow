"""Site-level orchestration: fetch the mask, compute the window, shape the DTO.

No FastAPI import anywhere in this module. That is what lets the agent tool
layer and the precompute worker call exactly the same code the HTTP routes do,
so a number can never differ depending on who asked for it.
"""

from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Hashable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import ENGINE_VERSION, get_settings
from app.core import metrics as core_metrics
from app.core import timeline
from app.core.horizon import downsample_mask
from app.core.intervals import Run
from app.core.timeline import BodyTrack
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


class _Memo:
    """A small, bounded, process-local memo with in-flight de-duplication.

    Why it exists: the clock screen asks for `/windows`, `/metrics` and
    `/timeline` for the same site and window at once, and each used to run the
    whole geometry pipeline -- three SPICE sweeps for one answer. The Redis
    layer cannot help with that, because the three payloads are different keys.
    Memoising the *geometry* below the payloads makes the three one.

    It also gives single-flight when Redis is down: concurrent callers for the
    same key await one computation instead of each starting their own.

    Bounded because a process that remembers every window anyone ever asked for
    is a leak. Each entry is roughly 0.3 MB (two tracks of 2,835 samples plus
    the mask), so the default of 32 caps it near 10 MB.

    Keys carry ``ENGINE_VERSION``, so a redeploy that changes the geometry can
    never be answered from here.
    """

    def __init__(self, capacity: int) -> None:
        self.capacity = capacity
        self._done: OrderedDict[Hashable, ComputedWindow] = OrderedDict()
        self._inflight: dict[Hashable, asyncio.Future[ComputedWindow]] = {}

    def clear(self) -> None:
        self._done.clear()
        self._inflight.clear()

    async def get(
        self, key: Hashable, factory: Callable[[], Awaitable[ComputedWindow]]
    ) -> ComputedWindow:
        hit = self._done.get(key)
        if hit is not None:
            self._done.move_to_end(key)
            return hit
        pending = self._inflight.get(key)
        if pending is not None and not pending.done():
            return await asyncio.shield(pending)

        fut: asyncio.Future[ComputedWindow] = asyncio.get_running_loop().create_future()
        self._inflight[key] = fut
        try:
            value = await factory()
        except asyncio.CancelledError:
            fut.cancel()
            raise
        except Exception as exc:
            fut.set_exception(exc)
            # Nobody may be waiting; retrieve it so the loop does not log it.
            fut.exception()
            raise
        else:
            fut.set_result(value)
            self._done[key] = value
            if len(self._done) > self.capacity:
                self._done.popitem(last=False)
            return value
        finally:
            self._inflight.pop(key, None)


_memo = _Memo(capacity=get_settings().geometry_memo_entries)


def clear_memo() -> None:
    """Forget every memoised window. For tests and for an in-place re-seed."""
    _memo.clear()


async def compute(
    session: AsyncSession,
    site_id: str,
    start: datetime,
    end: datetime,
    step_s: int,
) -> ComputedWindow:
    """Compute one site over one window.

    Memoised in-process on the quantised window (see ``_Memo``); the Redis
    payload cache sits above this in ``cached_payload``.
    """
    qs, qe, step_s = geometry_service.validate_window(start, end, step_s)

    async def build() -> ComputedWindow:
        site = await require_site(session, site_id)
        mask_rec = await require_mask(session, site_id)
        result = await geometry_service.compute_window_metrics(
            site_id=site.id,
            lat_deg=site.lat_deg,
            lon_deg=site.lon_deg,
            elev_m=site.elev_m,
            mask=mask_rec.mask,
            start=qs,
            end=qe,
            step_s=step_s,
        )
        return ComputedWindow(site=site, mask_record=mask_rec, result=result)

    return await _memo.get((ENGINE_VERSION, site_id, qs, qe, step_s), build)


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

    def body(track: BodyTrack) -> dict[str, Any]:
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


def _edges(run: Run, t_start: float, t_end: float) -> tuple[bool, bool]:
    """Was this run cut by the window at its start, its end, or both?"""
    slack = core_metrics.EDGE_SLACK_S
    return run.start <= t_start + slack, run.end >= t_end - slack


def _arcs(track: BodyTrack, start: datetime) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    t0, t1 = float(track.t_s[0]), float(track.t_s[-1])
    for i, arc in enumerate(track.arcs):
        open_start, open_end = _edges(arc, t0, t1)
        bearing = track.blocked_by_bearing_deg[i]
        block_el = track.blocked_by_el_deg[i]
        tol_start, tol_end = track.arc_edge_tolerance_s[i]
        out.append(
            {
                "up": arc.value,
                "start": _at(start, arc.start),
                "end": _at(start, arc.end),
                "duration_s": round(arc.duration, 3),
                "tolerance_s": round(track.arc_tolerance_s[i], 3),
                "start_tolerance_s": round(tol_start, 3) if tol_start is not None else None,
                "end_tolerance_s": round(tol_end, 3) if tol_end is not None else None,
                "grazing": bool(track.arc_grazing[i]),
                "open_start": open_start,
                "open_end": open_end,
                "blocked_by_bearing_deg": round(bearing, 3) if bearing is not None else None,
                "blocked_by_el_deg": round(block_el, 4) if block_el is not None else None,
            }
        )
    return out


def _body_windows(
    track: BodyTrack, arcs_payload: list[dict[str, Any]], start: datetime
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
        "longest_down_open": bm.longest_down_open,
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
                "open_start": edges[0],
                "open_end": edges[1],
            }
            for c in r.metrics.compound
            for edges in (_edges(c, float(r.sun.t_s[0]), float(r.sun.t_s[-1])),)
        ],
        "worst_compound_s": round(r.metrics.worst_compound_s, 3),
        "meta": cw.meta(cache_state),
    }


def _tolerances(r: Any) -> dict[str, Any]:
    """Each of the four numbers' own timing uncertainty, from its own edges."""
    sun = timeline.metric_tolerance(r.sun)
    earth = timeline.metric_tolerance(r.earth)

    def rnd(v: float | None) -> float | None:
        return round(v, 1) if v is not None else None

    return {
        "sunlit_tolerance_s": rnd(sun.total_s),
        "earth_contact_tolerance_s": rnd(earth.total_s),
        "longest_dark_tolerance_s": rnd(sun.longest_down_s),
        "longest_blackout_tolerance_s": rnd(earth.longest_down_s),
        "longest_dark_grazing": sun.longest_down_grazing,
        "longest_blackout_grazing": earth.longest_down_grazing,
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
        "longest_dark_open": m.longest_dark_open,
        "longest_blackout_open": m.longest_blackout_open,
        "worst_compound_open": m.worst_compound_open,
        **_tolerances(r),
        "autonomy": {
            "worst_compound_s": round(a.worst_compound_s, 3),
            "required_autonomy_s": round(a.required_autonomy_s, 3),
            "margin_fraction": core_metrics.AUTONOMY_MARGIN,
            "survival_needed_s": round(a.survival_needed_s, 3),
            "compound_inside_dark": a.compound_inside_dark,
            "survival_open": a.survival_open,
            "worst_compound_open": a.worst_compound_open,
        },
        "meta": cw.meta(cache_state),
    }


def horizon_payload(
    site: SiteRecord, rec: MaskRecord, step_deg: float, cache_state: str = "miss"
) -> dict[str, Any]:
    """Downsample by MAXIMUM, never by mean, centred on each output bearing.

    A skyline is an upper envelope. Averaging it invents sky where a ridge is,
    and at these sites a single ridge is the whole answer -- so a mean-based
    downsample would quietly add hours of fictional sunlight. Range and
    tolerance come from the bin that set each elevation, so the three arrays
    describe the same blocker.
    """
    mask = rec.mask
    if not (0.0 < step_deg <= 360.0):
        raise ValueError(f"step_deg must be in (0, 360]; got {step_deg}")
    target = int(round(360.0 / step_deg))
    el, rng, tol = downsample_mask(mask, target)
    sun_r, earth_r = geometry_service.nominal_penumbra_deg()

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
                "penumbra_sun_deg": round(sun_r, 4),
                "penumbra_earth_deg": round(earth_r, 4),
                "notes": [
                    f"Terrain modelled to {mask.max_range_m / 1000:.0f} km around the site.",
                    f"Downsampled from {mask.azimuth_count} bins by taking the maximum "
                    "around each bearing, never the mean: a skyline is an upper envelope "
                    "and averaging it would invent sky where a ridge is.",
                    "No window is involved, so no crossing is timed here; edge_timing_s "
                    "is null because it does not apply, not because a crossing grazes.",
                ],
            },
            "engine_version": rec.engine_version,
            "cache": cache_state,
            "compute_ms": round(mask.compute_ms, 1),
        },
    }


def set_meta(
    masks: dict[str, MaskRecord],
    summaries: dict[str, dict[str, Any]],
    *,
    filtered: bool,
) -> dict[str, Any]:
    """The `meta` envelope for a response describing several sites.

    Every figure is derived from the stored masks and reference rows it
    describes, and each takes the *least* favourable value across the set --
    the smallest coverage, the largest vertical error -- because one envelope
    has to be true for every site under it. An earlier version hardcoded the
    whole block (coverage 1.0, a computed_at in 2027), which is precisely the
    kind of number this API promises never to return.
    """
    s = get_settings()
    sun_r, earth_r = geometry_service.nominal_penumbra_deg()
    recs = list(masks.values())
    stamps = [r.computed_at for r in recs] + [
        datetime.fromisoformat(str(v["computed_at"]).replace("Z", "+00:00"))
        for v in summaries.values()
        if v.get("computed_at")
    ]
    grazing = any(v.get("grazing") for v in summaries.values())
    open_cut = any(
        v.get("longest_dark_open") or v.get("longest_blackout_open") for v in summaries.values()
    )
    products = sorted({r.dem_product for r in recs})
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
    if open_cut:
        notes.append(
            "Where a summary marks its longest night or blackout as open, the reference "
            "window ended that stretch, not the geometry: the figure is a lower bound."
        )
    if grazing:
        notes.append(
            "At least one site has a crossing too shallow to time; its totals stand but "
            "its edges do not."
        )
    notes.append(
        "Edge timing is not summarised across sites; it is reported per window by "
        "/timeline, /windows and /metrics."
    )
    return {
        "computed_at": _iso(max(stamps)) if stamps else _iso(datetime.now(UTC)),
        "resolution": {
            "azimuth_deg": s.azimuth_step_deg,
            "azimuth_count": int(round(360 / s.azimuth_step_deg)),
            "time_step_s": s.default_step_s,
            "max_range_m": max((r.mask.max_range_m for r in recs), default=s.max_range_m),
            "dem_product": " + ".join(products) if products else "none surveyed",
            "dem_resolution_m": max((r.dem_resolution_m for r in recs), default=0.0),
            "ephemeris": "de440 + moon_pa_de440 (MOON_ME)",
            "frame": "MOON_ME",
        },
        "uncertainty": {
            "dem_vertical_error_m": max((r.dem_vertical_error_m for r in recs), default=0.0),
            "dem_resolution_m": max((r.dem_resolution_m for r in recs), default=0.0),
            "coverage": round(min((r.mask.coverage for r in recs), default=0.0), 4),
            "horizon_el_deg": round(
                max((float(np.mean(r.mask.tol_deg)) for r in recs), default=0.0), 4
            ),
            "edge_timing_s": None,
            "grazing": grazing,
            "penumbra_sun_deg": round(sun_r, 4),
            "penumbra_earth_deg": round(earth_r, 4),
            "notes": notes,
        },
        "engine_version": ENGINE_VERSION,
        "cache": "bypass",
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
    # The same quantisation the worker stored the rows with, or every lookup
    # misses and every summary comes back null.
    qs, qe, _ = geometry_service.validate_window(start, end, s.default_step_s)
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
            "longest_dark_open": r.longest_dark_open,
            "longest_blackout_open": r.longest_blackout_open,
            "reference_window_start": _iso(qs),
            "reference_window_end": _iso(qe),
            "reference_step_s": s.default_step_s,
            "computed_at": _iso(r.computed_at),
        }
        for sid, r in rows.items()
    }


# ---------------------------------------------------------------------------
# Entry points that used to live in the route layer
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SiteListing:
    """One page of sites, their summaries, and the envelope describing them."""

    sites: list[SiteRecord]
    total: int
    summaries: dict[str, dict[str, Any]]
    meta: dict[str, Any]


async def list_with_summaries(
    session: AsyncSession,
    *,
    q: str | None = None,
    region: str | None = None,
    lat_min: float | None = None,
    lat_max: float | None = None,
    min_sun_fraction: float | None = None,
    max_longest_dark_s: float | None = None,
    limit: int = 100,
    offset: int = 0,
) -> SiteListing:
    """Sites plus their reference summaries, filtered *then* paginated.

    The metric filters used to run in the route, after the database had
    already applied ``limit``/``offset`` -- so a filtered page could come back
    short while matching sites sat on the next page, and ``total`` counted only
    the survivors of one page. Filtering needs the summaries, and the summaries
    live beside the sites, so the whole selection happens here and pagination
    is the last step. The site table is small by design (fewer than 500 rows),
    which is what makes the in-memory filter the simple and correct choice.

    A site with no precompute cannot be judged against a metric filter, so it
    is excluded rather than assumed to pass.
    """
    metric_filtered = min_sun_fraction is not None or max_longest_dark_s is not None
    repo = SiteRepository(session)
    if not metric_filtered:
        sites, total = await repo.list_sites(
            q=q, region=region, lat_min=lat_min, lat_max=lat_max, limit=limit, offset=offset
        )
        summaries = await reference_summaries(session, [x.id for x in sites])
    else:
        candidates, _ = await repo.list_sites(
            q=q, region=region, lat_min=lat_min, lat_max=lat_max, limit=10_000, offset=0
        )
        all_summaries = await reference_summaries(session, [x.id for x in candidates])
        matching = [
            site
            for site in candidates
            if _passes(all_summaries.get(site.id), min_sun_fraction, max_longest_dark_s)
        ]
        total = len(matching)
        sites = matching[offset : offset + limit]
        summaries = {x.id: all_summaries[x.id] for x in sites if x.id in all_summaries}

    masks = await MaskRepository(session).get_many([x.id for x in sites], ENGINE_VERSION)
    return SiteListing(
        sites=sites,
        total=total,
        summaries=summaries,
        meta=set_meta(masks, summaries, filtered=metric_filtered),
    )


def _passes(
    summary: dict[str, Any] | None,
    min_sun_fraction: float | None,
    max_longest_dark_s: float | None,
) -> bool:
    if summary is None:
        return min_sun_fraction is None and max_longest_dark_s is None
    if min_sun_fraction is not None and summary["sun_fraction_up"] < min_sun_fraction:
        return False
    return not (max_longest_dark_s is not None and summary["longest_dark_s"] > max_longest_dark_s)


async def site_detail(
    session: AsyncSession, site_id: str
) -> tuple[SiteRecord, MaskRecord | None, dict[str, Any] | None, dict[str, Any]]:
    """One site, its stored mask (if surveyed), its summary and its envelope."""
    site = await require_site(session, site_id)
    mask_rec = await get_mask_record(session, site_id)
    summaries = await reference_summaries(session, [site_id])
    meta = set_meta({site_id: mask_rec} if mask_rec is not None else {}, summaries, filtered=False)
    return site, mask_rec, summaries.get(site_id), meta


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
