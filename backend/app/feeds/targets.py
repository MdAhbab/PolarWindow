"""Every product the feeds worker records, built from the cited catalogues.

The pads (and their buoys and Launch Library locations) come from
``data/catalogues/launch_sites.json``, so adding a pad there is all it takes
to start recording its weather.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from app.config import get_settings
from app.data import catalogues
from app.feeds.adapters import donki, dsn_now, glm, horizons, ll2, ndbc, nomads, nws, swpc
from app.feeds.base import Product, ProviderSpec

#: Pads close enough to share one weather model point (a GEFS cell is ~50 km).
REGION_OF_RANGE = catalogues.MODEL_REGION_OF_RANGE
#: HRRR covers the contiguous United States only.
HRRR_REGIONS = frozenset({"florida", "vandenberg"})


def providers() -> dict[str, ProviderSpec]:
    return {
        p.name: p
        for p in (
            swpc.PROVIDER,
            donki.provider(),
            dsn_now.PROVIDER,
            nws.PROVIDER,
            ndbc.PROVIDER,
            ll2.PROVIDER,
            nomads.PROVIDER,
            glm.PROVIDER,
            horizons.PROVIDER,
        )
    }


def orbiters() -> list[tuple[str, int]]:
    """Real lunar orbiters whose trajectories are recorded (``validation_only`` relays)."""
    return [
        (r.id, r.naif_id)
        for r in catalogues.load("relays").records
        if r.role == "validation_only" and r.naif_id is not None
    ]


def _date(d: dict[str, str], *, end: bool) -> datetime:
    t = d["date"].replace("Z", "+00:00")
    at = datetime.fromisoformat(t if "T" in t else t + "T00:00:00+00:00").astimezone(UTC)
    return at + timedelta(days=1) if end and d["precision"] == "day" else at


def flown_surface_days() -> list[tuple[str, datetime, datetime]]:
    """Landed missions whose landing and end of mission are published to the day or better
    (the same span the Contact answer uses by default)."""
    data = json.loads(get_settings().missions_path.read_text())
    out = []
    for m in data.get("missions") or data.get("records") or []:
        land, eom = m.get("landing"), m.get("end_of_mission")
        if m.get("status") not in ("completed", "partial_success") or not land or not eom:
            continue
        if land.get("precision") in ("second", "minute", "day") and eom.get("precision") in (
            "second",
            "minute",
            "day",
        ):
            out.append((m["id"], _date(land, end=False), _date(eom, end=True)))
    return out


def products(wanted: nomads.Wanted | None = None) -> list[Product]:
    """``wanted``: launch times of upcoming opportunities per model region (B3)."""
    sites = [s for s in catalogues.load("launch_sites").records if s.status != "inactive"]
    pads = [
        (s.id, s.lat_deg, s.lon_deg)
        for s in sites
        if s.nws_forecast and s.lat_deg is not None and s.lon_deg is not None
    ]
    buoys = sorted({b for s in sites for b in s.ndbc_buoys})
    locations = sorted({s.ll2_location_id for s in sites if s.ll2_location_id is not None})
    regions: dict[str, list[tuple[str, float, float]]] = {}
    for s in sites:
        region = REGION_OF_RANGE.get(s.launch_range)
        if region and s.lat_deg is not None and s.lon_deg is not None:
            regions.setdefault(region, []).append((s.id, s.lat_deg, s.lon_deg))
    out: list[Product] = []
    out += swpc.products()
    out += donki.products()
    out += dsn_now.products()
    out += nws.products(pads)
    out += ndbc.products(buoys)
    if locations:
        out += ll2.products(locations)
    out += nomads.products(regions, hrrr_regions=set(HRRR_REGIONS), wanted=wanted)
    out += glm.products(regions, wanted=wanted)
    out += horizons.products(orbiters(), flown_surface_days())
    return out


def secrets() -> tuple[str, ...]:
    s = get_settings()
    return tuple(x for x in (s.nasa_api_key, s.earthdata_token) if x)


def region_of_pad(pad_id: str) -> str | None:
    try:
        return REGION_OF_RANGE.get(catalogues.load("launch_sites").get(pad_id).launch_range)
    except KeyError:
        return None
