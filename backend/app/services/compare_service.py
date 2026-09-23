"""Rank several sites against one shared window.

Fans out to exactly the code path ``GET /sites/{id}/metrics`` uses, so
``/compare`` and the per-site endpoint can never disagree about a number. That
is a correctness property, not an optimisation: a comparison table that
contradicts the detail page it links to destroys trust in both.

Ranking is ``core.metrics.rank_with_uncertainty``: each site's value becomes an
interval from its own edge tolerance, a window-censored longest gap becomes
``[v, inf)``, and a site is ranked above another only when the intervals do not
overlap. Where a censored value is involved the rank is a range, not a number
(docs/system-design.md 10.7).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import ENGINE_VERSION, get_settings
from app.core.metrics import METRIC_KEYS, RankInput, rank_with_uncertainty, tie_groups
from app.services import geometry_service, site_service
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
    payloads: list[dict[str, Any]] = []
    unavailable: list[dict[str, str]] = []
    for sid in dict.fromkeys(site_ids):  # dedupe, preserve order
        try:
            payloads.append(
                await site_service.cached_payload(session, "metrics", sid, qs, qe, step_s)
            )
        except (site_service.SiteNotFound, site_service.MaskNotBuilt) as exc:
            # One unsurveyed or unknown site must not blank the comparison. Only
            # these two, though: a missing ephemeris or a bug is not a property of
            # one site, and folding it into `unavailable` would hide an outage
            # behind eight polite per-site notes.
            unavailable.append({"site_id": sid, "reason": _reason(exc)})

    ranked = rank_with_uncertainty(
        [_rank_input(p, rank_by) for p in payloads],
        higher_is_better=METRIC_KEYS[rank_by],
    )
    by_id = {p["site_id"]: p for p in payloads}
    ties = tie_groups(ranked)
    best = by_id[ranked[0].id] if ranked else None

    items = [
        {
            "site_id": r.id,
            "position": i,
            "rank": r.rank,
            "rank_range": [r.rank_min, r.rank_max],
            "tied": bool(r.tied_with),
            "tied_with": list(r.tied_with),
            "incomparable_with": list(r.incomparable_with),
            "censored": r.censored,
            "grazing": _grazing(by_id[r.id], rank_by),
            "uncertainty_s": _tolerance(by_id[r.id], rank_by),
            "metrics": by_id[r.id],
            "delta_vs_best": (
                {k: round(by_id[r.id][k] - best[k], 3) for k in METRIC_KEYS} if best else {}
            ),
        }
        for i, r in enumerate(ranked, start=1)
    ]

    return {
        "window": {"start": qs, "end": qe, "step_s": step_s},
        "rank_by": rank_by,
        "items": items,
        "ties": ties,
        "unavailable": unavailable,
        "meta": _aggregate_meta(payloads, qs, step_s, unavailable),
    }


_TOLERANCE_KEY = {
    "sunlit_s": "sunlit_tolerance_s",
    "earth_contact_s": "earth_contact_tolerance_s",
    "longest_dark_s": "longest_dark_tolerance_s",
    "longest_blackout_s": "longest_blackout_tolerance_s",
}
_OPEN_KEY = {"longest_dark_s": "longest_dark_open", "longest_blackout_s": "longest_blackout_open"}
_GRAZING_KEY = {
    "longest_dark_s": "longest_dark_grazing",
    "longest_blackout_s": "longest_blackout_grazing",
}


def _tolerance(p: dict[str, Any], key: str) -> float | None:
    v = p.get(_TOLERANCE_KEY[key])
    return None if v is None else float(v)


def _grazing(p: dict[str, Any], key: str) -> bool:
    return bool(p.get(_GRAZING_KEY.get(key, ""), False))


def _rank_input(p: dict[str, Any], key: str) -> RankInput:
    """One payload as an interval: its own tolerance, and censoring if any.

    A null tolerance means an edge of the ranked quantity is a graze: the value
    stands, but where it sits against another site cannot be pinned, so the
    interval is unbounded rather than silently zero.
    """
    tol = _tolerance(p, key)
    return RankInput(
        id=p["site_id"],
        value=float(p[key]),
        uncertainty=float("inf") if tol is None else tol,
        censored=bool(p.get(_OPEN_KEY.get(key, ""), False)),
    )


def _reason(exc: Exception) -> str:
    if isinstance(exc, site_service.SiteNotFound):
        return f"'{exc.args[0]}' is not a site in this dataset."
    return str(exc)


def _aggregate_meta(
    payloads: list[dict[str, Any]],
    window_start: datetime,
    step_s: int,
    unavailable: list[dict[str, str]],
) -> dict[str, Any]:
    """One envelope that is true for *every* site in the comparison.

    It used to be the top-ranked site's own `meta`, so a comparison whose third
    site grazed, or had partial terrain, reported neither. Each field now takes
    the least favourable value across the set: the lowest coverage, the largest
    error, `grazing` if any site grazes -- and then `edge_timing_s` is null,
    because at least one edge in the table cannot be timed.
    """
    if not payloads:
        s = get_settings()
        sun_r, earth_r = geometry_service.nominal_penumbra_deg()
        return {
            "computed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "resolution": {
                "azimuth_deg": s.azimuth_step_deg,
                "azimuth_count": int(round(360 / s.azimuth_step_deg)),
                "time_step_s": step_s,
                "max_range_m": s.max_range_m,
                "dem_product": "none computed",
                "dem_resolution_m": 0.0,
                "ephemeris": "de440 + moon_pa_de440 (MOON_ME)",
                "frame": "MOON_ME",
            },
            "uncertainty": {
                "dem_vertical_error_m": 0.0,
                "dem_resolution_m": 0.0,
                "coverage": 0.0,
                "horizon_el_deg": 0.0,
                "edge_timing_s": None,
                "grazing": False,
                "penumbra_sun_deg": round(sun_r, 4),
                "penumbra_earth_deg": round(earth_r, 4),
                "notes": [
                    "None of the requested sites could be computed, so there is nothing "
                    "to describe; see `unavailable` for why."
                ],
            },
            "engine_version": ENGINE_VERSION,
            "cache": "bypass",
        }

    metas = [p["meta"] for p in payloads]
    us = [m["uncertainty"] for m in metas]
    grazing = any(u["grazing"] for u in us)
    timings = [u["edge_timing_s"] for u in us if u["edge_timing_s"] is not None]
    notes: list[str] = []
    for u in us:
        for note in u["notes"]:
            if note not in notes:
                notes.append(note)
    if unavailable:
        notes.append(
            f"{len(unavailable)} requested site(s) could not be computed and are listed "
            "under `unavailable`; this envelope describes only the ranked sites."
        )
    # A site's product can itself be "A + B"; split before de-duplicating, or
    # the joined line repeats a product name (C6).
    products = sorted(
        {part.strip() for m in metas for part in str(m["resolution"]["dem_product"]).split(" + ")}
    )
    caches = {m["cache"] for m in metas}
    return {
        "computed_at": max(
            datetime.fromisoformat(str(m["computed_at"]).replace("Z", "+00:00")) for m in metas
        )
        .isoformat()
        .replace("+00:00", "Z"),
        "resolution": {
            **metas[0]["resolution"],
            "dem_product": " + ".join(products),
            "dem_resolution_m": max(m["resolution"]["dem_resolution_m"] for m in metas),
            "time_step_s": step_s,
        },
        "uncertainty": {
            "dem_vertical_error_m": max(u["dem_vertical_error_m"] for u in us),
            "dem_resolution_m": max(u["dem_resolution_m"] for u in us),
            "coverage": min(u["coverage"] for u in us),
            "horizon_el_deg": max(u["horizon_el_deg"] for u in us),
            "edge_timing_s": None if grazing or not timings else max(timings),
            "grazing": grazing,
            "penumbra_sun_deg": max(u["penumbra_sun_deg"] for u in us),
            "penumbra_earth_deg": max(u["penumbra_earth_deg"] for u in us),
            "terrain_modelled": all(u.get("terrain_modelled", True) for u in us),
            "notes": notes,
        },
        "engine_version": ENGINE_VERSION,
        "cache": caches.pop() if len(caches) == 1 else "miss",
        "compute_ms": round(sum(m.get("compute_ms") or 0.0 for m in metas), 1),
    }
