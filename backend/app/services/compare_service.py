"""Rank several sites against one shared window.

Fans out to exactly the code path ``GET /sites/{id}/metrics`` uses, so
``/compare`` and the per-site endpoint can never disagree about a number. That
is a correctness property, not an optimisation: a comparison table that
contradicts the detail page it links to destroys trust in both.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.metrics import METRIC_KEYS, TIE_TOLERANCE_S
from app.services import site_service
from app.services.geometry_service import validate_window

MAX_SITES = 8


class TooManySites(ValueError):
    pass


class UnknownMetric(ValueError):
    pass


async def compare(
    session: AsyncSession,
    site_ids: list[str],
    start: datetime,
    end: datetime,
    step_s: int,
    rank_by: str,
) -> dict[str, Any]:
    if len(site_ids) > MAX_SITES:
        raise TooManySites(
            f"compare accepts at most {MAX_SITES} sites; got {len(site_ids)}. "
            f"Comparing more than that on one screen stops being a comparison."
        )
    if rank_by not in METRIC_KEYS:
        raise UnknownMetric(f"unknown rank_by {rank_by!r}; known: {sorted(METRIC_KEYS)}")

    qs, qe, step_s = validate_window(start, end, step_s)

    # Sequential, not gathered. Every one of these ends up on the single SPICE
    # thread anyway (see docs/system-design.md 4.2), so gathering would only
    # queue them behind each other while multiplying peak memory by eight.
    # Single-flight means a concurrent second caller still waits rather than
    # duplicating the work.
    payloads: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for sid in dict.fromkeys(site_ids):  # dedupe, preserve order
        try:
            payloads.append(
                await site_service.cached_payload(session, "metrics", sid, qs, qe, step_s)
            )
        except Exception as exc:
            # One unsurveyed site must not blank the whole comparison.
            errors.append({"site_id": sid, "reason": str(exc)})

    higher_is_better = METRIC_KEYS[rank_by]
    ordered = sorted(payloads, key=lambda p: p[rank_by], reverse=higher_is_better)

    best = ordered[0] if ordered else None
    items: list[dict[str, Any]] = []
    for i, p in enumerate(ordered):
        items.append(
            {
                "site_id": p["site_id"],
                "rank": i + 1,
                "metrics": p,
                "delta_vs_best": (
                    {k: round(p[k] - best[k], 3) for k in METRIC_KEYS} if best else {}
                ),
            }
        )

    # Ties are reported, not broken. With a 20 m elevation model and a lunar
    # ephemeris, ordering two sites that differ by twenty minutes over a month
    # asserts a distinction the data does not support.
    ties: list[list[str]] = []
    group: list[dict[str, Any]] = []
    for p in ordered:
        if group and abs(p[rank_by] - group[-1][rank_by]) <= TIE_TOLERANCE_S:
            group.append(p)
        else:
            if len(group) > 1:
                ties.append([x["site_id"] for x in group])
            group = [p]
    if len(group) > 1:
        ties.append([x["site_id"] for x in group])

    s = get_settings()
    return {
        "window": {"start": qs, "end": qe, "step_s": step_s},
        "rank_by": rank_by,
        "items": items,
        "ties": ties,
        "unavailable": errors,
        "meta": (
            ordered[0]["meta"]
            if ordered
            else {
                "computed_at": qs.isoformat().replace("+00:00", "Z"),
                "resolution": {
                    "azimuth_deg": s.azimuth_step_deg,
                    "azimuth_count": int(round(360 / s.azimuth_step_deg)),
                    "time_step_s": step_s,
                    "max_range_m": s.max_range_m,
                    "dem_product": "LOLA LDEM 80S",
                    "dem_resolution_m": 20.0,
                    "ephemeris": "de440 + moon_pa_de440 (MOON_ME)",
                    "frame": "MOON_ME",
                },
                "uncertainty": {
                    "dem_vertical_error_m": 2.0,
                    "dem_resolution_m": 20.0,
                    "coverage": 0.0,
                    "horizon_el_deg": 0.0,
                    "edge_timing_s": None,
                    "grazing": False,
                    "penumbra_sun_deg": 0.266,
                    "penumbra_earth_deg": 0.95,
                    "notes": ["None of the requested sites could be computed."],
                },
                "engine_version": __import__(
                    "app.config", fromlist=["ENGINE_VERSION"]
                ).ENGINE_VERSION,
                "cache": "miss",
            }
        ),
    }
