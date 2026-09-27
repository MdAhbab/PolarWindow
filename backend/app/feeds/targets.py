"""Every product the feeds worker records, built from the cited catalogues.

The pads (and their buoys and Launch Library locations) come from
``data/catalogues/launch_sites.json``, so adding a pad there is all it takes
to start recording its weather.
"""

from __future__ import annotations

from app.config import get_settings
from app.data import catalogues
from app.feeds.adapters import donki, dsn_now, ll2, ndbc, nomads, nws, swpc
from app.feeds.base import Product, ProviderSpec

#: Pads close enough to share one weather model point (a GEFS cell is ~50 km).
REGION_OF_RANGE = {"eastern": "florida", "western": "vandenberg"}
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
        )
    }


def products() -> list[Product]:
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
    out += nomads.products(regions, hrrr_regions=set(HRRR_REGIONS))
    return out


def secrets() -> tuple[str, ...]:
    s = get_settings()
    return tuple(x for x in (s.nasa_api_key, s.earthdata_token) if x)
