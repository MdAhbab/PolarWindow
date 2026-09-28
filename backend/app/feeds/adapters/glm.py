"""Lightning seen from space near the pads, in the half hour before a launch (T4 B0, B1).

NOAA's Geostationary Lightning Mapper (GLM) Level 2 flash files, from the
open-data buckets on AWS (GOES-19, GOES-East since April 2025, for the
Eastern Range; GOES-18, GOES-West, for Vandenberg). Each file holds 20 seconds;
half an hour is about 90 files and 22 MB, so the product is recorded only
while a designed launch opportunity from the region's pads is less than six
hours away. It keeps, for each pad, the good-quality flashes within 20 nmi
(their distance and time) and the counts within 5, 10 and 20 nmi.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import numpy as np

from app.feeds import http
from app.feeds.adapters.nomads import Wanted
from app.feeds.base import PUBLIC_DOMAIN, Parsed, ParseError, Product, ProviderSpec, iso
from app.feeds.parsers import glm

PROVIDER = ProviderSpec(name="goes", capacity=400, per_hour=6000)
LICENCE = f"NOAA GOES-R Series GLM on the AWS open data registry, {PUBLIC_DOMAIN}"
BUCKETS = {"florida": "noaa-goes19", "vandenberg": "noaa-goes18"}
PREFIX = "GLM-L2-LCFA"
WINDOW = timedelta(minutes=30)
LOOKAHEAD = timedelta(hours=6)
RADII_NMI: tuple[float, ...] = (5.0, 10.0, 20.0)
FILE_S = 20.0
PARALLEL = 8
_START = re.compile(r"_s(\d{4})(\d{3})(\d{2})(\d{2})(\d{2})\d_")

Point = tuple[str, float, float]


def start_of(key: str) -> datetime | None:
    """The start time written in a GLM file name (``_sYYYYJJJHHMMSSt_``)."""
    m = _START.search(key)
    if m is None:
        return None
    y, doy, hh, mm, ss = (int(x) for x in m.groups())
    return datetime(y, 1, 1, hh, mm, ss, tzinfo=UTC) + timedelta(days=doy - 1)


def parse_near(points: list[Point]) -> Callable[[bytes], Parsed]:
    far_km = max(RADII_NMI) * glm.NMI_KM

    def parse(body: bytes) -> Parsed:
        files = [glm.read(b) for b in glm.unframe(body)]
        if not files:
            raise ParseError("no GLM files in the body")
        start = min(f.start for f in files)
        end = max(f.end for f in files)
        pads: dict[str, Any] = {}
        for pid, lat, lon in points:
            near: list[tuple[float, datetime]] = []
            for f in files:
                if f.lat.size == 0:
                    continue
                d = glm.distance_km(lat, lon, f.lat, f.lon)
                near += [(float(d[i]), f.t[i]) for i in np.flatnonzero(d <= far_km)]
            near.sort(key=lambda x: x[1])
            pads[pid] = {
                "counts": {
                    f"{r:g}": sum(1 for d, _ in near if d <= r * glm.NMI_KM) for r in RADII_NMI
                },
                "nearest_km": min((d for d, _ in near), default=None),
                "flashes": [{"km": round(d, 2), "t": iso(t)} for d, t in near],
            }
        expected = round((end - start).total_seconds() / FILE_S)
        issues = []
        if len(files) < expected:
            issues.append(f"{len(files)} of {expected} 20-second files present")
        return Parsed(
            values={
                "satellite": files[0].platform,
                "start": iso(start),
                "end": iso(end),
                "files": len(files),
                "radii_nmi": list(RADII_NMI),
                "pads": pads,
            },
            issued_at=end,
            valid_from=start,
            valid_to=end,
            issues=issues,
        )

    return parse


def _fetch(region: str, wanted: Wanted | None, now: Callable[[], datetime]) -> Any:
    bucket = f"https://{BUCKETS[region]}.s3.amazonaws.com"

    async def keys(client: httpx.AsyncClient, hour: datetime) -> list[str]:
        prefix = f"{PREFIX}/{hour:%Y}/{hour.timetuple().tm_yday:03d}/{hour:%H}/"
        got = await http.fetch(client, f"{bucket}/", params={"list-type": "2", "prefix": prefix})
        return re.findall(r"<Key>([^<]+)</Key>", got.body.decode("utf-8", "replace"))

    async def fetch(client: httpx.AsyncClient, _e: str | None, _lm: str | None) -> http.Fetched:
        t = now().astimezone(UTC)
        soon = [x for x in (await wanted(region) if wanted else []) if t <= x <= t + LOOKAHEAD]
        if not soon:
            # No launch opportunity within six hours: nothing is asked for.
            return http.Fetched(f"{bucket}/{PREFIX}/", 304, b"", None, None, None, True, 0)
        since = t - WINDOW
        hours = sorted(
            {
                since.replace(minute=0, second=0, microsecond=0),
                t.replace(minute=0, second=0, microsecond=0),
            }
        )
        found: list[str] = []
        for h in hours:
            found += await keys(client, h)
        wanted_keys = sorted(k for k in found if (s := start_of(k)) is not None and s >= since)
        if not wanted_keys:
            raise http.FeedHttpError(f"no GLM files after {iso(since)} in {bucket}")
        gate = asyncio.Semaphore(PARALLEL)

        async def one(key: str) -> bytes:
            async with gate:
                return (await http.fetch(client, f"{bucket}/{key}")).body

        bodies = await asyncio.gather(*(one(k) for k in wanted_keys))
        return http.Fetched(
            url=f"{bucket}/?prefix={PREFIX}&from={iso(since)}&files={len(wanted_keys)}",
            status=200,
            body=glm.frame(list(bodies)),
            etag=None,
            last_modified=None,
            content_type="application/x-netcdf",
            not_modified=False,
            attempts=1,
        )

    return fetch


def products(
    regions: dict[str, list[Point]],
    *,
    wanted: Wanted | None = None,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> list[Product]:
    return [
        Product(
            provider="goes",
            product="glm",
            location_key=region,
            url=f"https://{BUCKETS[region]}.s3.amazonaws.com/{PREFIX}/",
            licence=LICENCE,
            parser_version="glm-1",
            interval_s=600,
            staleness_s=1200,
            parse=parse_near(pts),
            custom_fetch=_fetch(region, wanted, now),
            keep_raw=False,
            cost=100,
        )
        for region, pts in regions.items()
        if region in BUCKETS
    ]
