"""NOAA GEFS (31-run ensemble) and HRRR (3 km, one run) at the launch pads, and GFS-Wave
(one run, 0.25 degree) over the sea downrange of them.

Fetched through NOMADS' GRIB filter, which cuts each file down to the
variables and the few grid cells around the pads before sending it: about
1.5 kB per run per lead instead of tens of megabytes. NOMADS keeps about ten
days; older runs are in NOAA's open-data buckets on AWS (``noaa-gefs-pds``,
``noaa-hrrr-bdp-pds``), which the weather hindcast reads instead. Raw GRIB is
therefore not kept with the snapshot: the snapshot names the run, the files
and the variables, and the provider's archive holds the bytes.

Variables (all SI): wind at 10 m and 80 m (u, v), gusts at the surface,
temperature at 2 m, rain over the preceding 6 hours (GEFS) and total cloud
cover (GEFS), convective available potential energy (CAPE). GFS-Wave:
significant wave height (wind waves and swell together), the period of the
main waves and the wind speed at 10 m, on a one-degree lattice of its grid
points over the sea where boosters come down (B2).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from app.feeds import http
from app.feeds.base import (
    PUBLIC_DOMAIN,
    Parsed,
    ParseError,
    Product,
    ProviderSpec,
    in_range,
    iso,
)
from app.feeds.parsers import grib

BASE = "https://nomads.ncep.noaa.gov/cgi-bin"
PROVIDER = ProviderSpec(name="nomads", capacity=120, per_hour=3000)
LICENCE = f"NOAA NCEP (NOMADS), {PUBLIC_DOMAIN}"

GEFS_MEMBERS: tuple[str, ...] = ("gec00", *(f"gep{i:02d}" for i in range(1, 31)))
GEFS_LEADS_H: tuple[int, ...] = (24, 48)
#: GEFS output reaches 16 days (384 h).
GEFS_MAX_LEAD_H = 384
#: At most this many launch times are fetched from one run (each is 62 requests).
MAX_TARGETED_LEADS = 6
HRRR_LEADS_H: tuple[int, ...] = (1, 6, 12, 18)
#: Pause between NOMADS requests: its limit is about 120 a minute per address.
PAUSE_S = 0.6

Point = tuple[str, float, float]
#: ``region -> launch times wanted from it``, read when a run is fetched.
Wanted = Callable[[str], Awaitable[list[datetime]]]

_SHORT = {
    ("2t", 2): "t2m_k",
    ("10u", 10): "u10_m_s",
    ("10v", 10): "v10_m_s",
    ("u", 80): "u80_m_s",
    ("v", 80): "v80_m_s",
    ("gust", 0): "gust_m_s",
    ("tp", 0): "precip_mm",
    ("tcc", 0): "cloud_frac",
    ("cape", 0): "cape_j_kg",
    ("swh", 1): "wave_height_m",
    ("perpw", 1): "wave_period_s",
    ("ws", 1): "wind_m_s",
}
#: Physical ranges (SI) a value must fall in to be kept; outside, it is dropped and said.
RANGES: dict[str, tuple[float, float]] = {
    "t2m_k": (180.0, 340.0),
    "u10_m_s": (-100.0, 100.0),
    "v10_m_s": (-100.0, 100.0),
    "u80_m_s": (-120.0, 120.0),
    "v80_m_s": (-120.0, 120.0),
    "gust_m_s": (0.0, 120.0),
    "precip_mm": (0.0, 500.0),
    "cloud_frac": (0.0, 1.0),
    "cape_j_kg": (0.0, 10_000.0),
    "wave_height_m": (0.0, 30.0),
    "wave_period_s": (0.0, 40.0),
    "wind_m_s": (0.0, 100.0),
}
#: GFS-Wave: every hour to 120 h, then every 3 hours to 384 h.
WAVE_MAX_LEAD_H = 384
WAVE_LEADS_H: tuple[int, ...] = (24, 48)
MAX_WAVE_LEADS = 8
#: The sea downrange of each region's pads: ``(south, north, west, east)`` in degrees.
#: Eastern Range boosters land 550-700 km east of the Cape (Launch Library 2).
WAVE_BOXES: dict[str, tuple[int, int, int, int]] = {"florida": (26, 32, -80, -70)}


def _box(points: list[Point], pad_deg: float) -> dict[str, str]:
    lats = [p[1] for p in points]
    lons = [p[2] % 360.0 for p in points]
    return {
        "subregion": "",
        "toplat": f"{max(lats) + pad_deg:.2f}",
        "bottomlat": f"{min(lats) - pad_deg:.2f}",
        "leftlon": f"{min(lons) - pad_deg:.2f}",
        "rightlon": f"{max(lons) + pad_deg:.2f}",
    }


def parse_points(points: list[Point], model: str, n_members: int) -> Callable[[bytes], Parsed]:
    def parse(body: bytes) -> Parsed:
        rows = grib.point_values(body, points)
        if not rows:
            raise ParseError("no values at the pads")
        runs = {r.run for r in rows}
        if len(runs) != 1:
            raise ParseError(f"mixed model runs in one snapshot: {sorted(runs)}")
        run = runs.pop()
        out: dict[str, Any] = {}
        issues: list[str] = []
        for r in rows:
            key = _SHORT.get((r.short_name, r.level))
            if key is None:
                continue
            value = in_range(
                f"{r.point_id} {key} +{r.step_h} h",
                r.value / 100.0 if key == "cloud_frac" else r.value,
                *RANGES[key],
                issues,
            )
            if value is None:
                continue
            pad = out.setdefault(
                r.point_id,
                {
                    "grid_point": [r.grid_lat, r.grid_lon],
                    "distance_km": r.distance_km,
                    "method": r.method,
                    "leads": {},
                },
            )
            lead = pad["leads"].setdefault(
                str(r.step_h), {"valid": iso(grib.valid_time(r)), "members": {}}
            )
            mem = lead["members"].setdefault(str(r.member if r.member is not None else 0), {})
            mem[key] = value
        for pid, pad in out.items():
            for lh, lead in pad["leads"].items():
                if len(lead["members"]) != n_members:
                    issues.append(
                        f"{pid} lead {lh} h: {len(lead['members'])} of {n_members} runs present"
                    )
        return Parsed(
            values={"model": model, "run": iso(run), "members_expected": n_members, "points": out},
            issued_at=run,
            valid_from=min(grib.valid_time(r) for r in rows),
            valid_to=max(grib.valid_time(r) for r in rows),
            issues=issues,
        )

    return parse


async def _get_grib(client: httpx.AsyncClient, url: str, params: dict[str, str]) -> bytes | None:
    try:
        got = await http.fetch(client, url, params=params, retries=2)
    except http.FeedHttpError as exc:
        if exc.status in (403, 404):
            return None  # NOMADS answers 403 for a run that is not out yet
        raise
    if not got.body.startswith(b"GRIB"):
        return None
    return got.body


def gefs_lead(cycle: datetime, valid: datetime) -> int | None:
    """The GEFS output step nearest ``valid`` from a run at ``cycle``: every 3 hours to
    240 h, every 6 to 384 h; None outside that."""
    h = (valid - cycle).total_seconds() / 3600.0
    if h < 0 or h > GEFS_MAX_LEAD_H + 3:
        return None
    step = 3 if h <= 240 else 6
    return min(GEFS_MAX_LEAD_H, int(round(h / step)) * step)


LeadsFor = Callable[[datetime], Awaitable[list[int]]]


def wave_lead(cycle: datetime, valid: datetime) -> int | None:
    """The GFS-Wave output step nearest ``valid``: hourly to 120 h, 3-hourly to 384 h."""
    h = (valid - cycle).total_seconds() / 3600.0
    if h < 0 or h > WAVE_MAX_LEAD_H + 1.5:
        return None
    step = 1 if h <= 120 else 3
    return min(WAVE_MAX_LEAD_H, int(round(h / step)) * step)


def wave_points(region: str) -> list[Point]:
    """One-degree lattice over the region's sea box; ids like ``w28n077w``."""
    box = WAVE_BOXES.get(region)
    if box is None:
        return []
    s, n, w, e = box
    return [
        (f"w{lat:02d}n{-lon:03d}w", float(lat), float(lon))
        for lat in range(s, n + 1)
        for lon in range(w, e + 1)
    ]


def _wave_fetch(region: str, wanted: Wanted | None, now: Callable[[], datetime]) -> Any:
    """The latest GFS-Wave run at 24 and 48 h and at the steps nearest upcoming launches."""
    s_, n_, w_, e_ = WAVE_BOXES[region]
    box = {
        "subregion": "",
        "toplat": str(n_ + 1),
        "bottomlat": str(s_ - 1),
        "leftlon": str((w_ - 1) % 360),
        "rightlon": str((e_ + 1) % 360),
    }
    url = f"{BASE}/filter_gfswave.pl"

    def params(cycle: datetime, lead: int) -> dict[str, str]:
        hh = f"{cycle.hour:02d}"
        return {
            "dir": f"/gfs.{cycle:%Y%m%d}/{hh}/wave/gridded",
            "file": f"gfswave.t{hh}z.global.0p25.f{lead:03d}.grib2",
            "var_HTSGW": "on",
            "var_PERPW": "on",
            "var_WIND": "on",
            "lev_surface": "on",
            **box,
        }

    async def fetch(client: httpx.AsyncClient, _e: str | None, _lm: str | None) -> http.Fetched:
        t = now().astimezone(UTC)
        latest = t.replace(hour=t.hour - t.hour % 6, minute=0, second=0, microsecond=0)
        for back in range(0, 5):
            cycle = latest - timedelta(hours=6 * back)
            leads = set(WAVE_LEADS_H)
            if wanted is not None:
                found = [wave_lead(cycle, x) for x in await wanted(region)]
                leads |= {x for x in found if x is not None}
            order = sorted(leads)[:MAX_WAVE_LEADS]
            if await _get_grib(client, url, params(cycle, max(order))) is None:
                continue  # the run is not complete yet
            bodies = []
            for lead in order:
                await asyncio.sleep(PAUSE_S)
                body = await _get_grib(client, url, params(cycle, lead))
                if body is not None:
                    bodies.append(body)
            return http.Fetched(
                url=f"{url}?dir=/gfs.{cycle:%Y%m%d}/{cycle.hour:02d}/wave/gridded"
                f"&lead={','.join(str(x) for x in order)}",
                status=200,
                body=b"".join(bodies),
                etag=None,
                last_modified=None,
                content_type="application/x-grib2",
                not_modified=False,
                attempts=1,
            )
        raise http.FeedHttpError("no complete GFS-Wave run found in the last 30 hours")

    return fetch


def _gefs_fetch(points: list[Point], leads_for: LeadsFor, now: Callable[[], datetime]) -> Any:
    """All members of the latest complete GEFS run at the leads ``leads_for(cycle)`` gives."""
    box = _box(points, 1.0)

    def files(cycle: datetime, member: str, lead_h: int) -> list[tuple[str, dict[str, str]]]:
        d, hh = cycle.strftime("%Y%m%d"), f"{cycle.hour:02d}"
        a = {
            "dir": f"/gefs.{d}/{hh}/atmos/pgrb2ap5",
            "file": f"{member}.t{hh}z.pgrb2a.0p50.f{lead_h:03d}",
            "var_UGRD": "on",
            "var_VGRD": "on",
            "var_TMP": "on",
            "var_APCP": "on",
            "var_TCDC": "on",
            "lev_10_m_above_ground": "on",
            "lev_2_m_above_ground": "on",
            "lev_surface": "on",
            "lev_entire_atmosphere": "on",
            **box,
        }
        b = {
            "dir": f"/gefs.{d}/{hh}/atmos/pgrb2bp5",
            "file": f"{member}.t{hh}z.pgrb2b.0p50.f{lead_h:03d}",
            "var_UGRD": "on",
            "var_VGRD": "on",
            "var_GUST": "on",
            "var_CAPE": "on",
            "lev_80_m_above_ground": "on",
            "lev_surface": "on",
            **box,
        }
        return [
            (f"{BASE}/filter_gefs_atmos_0p50a.pl", a),
            (f"{BASE}/filter_gefs_atmos_0p50b.pl", b),
        ]

    async def fetch(client: httpx.AsyncClient, _e: str | None, _lm: str | None) -> http.Fetched:
        t = now().astimezone(UTC)
        latest = t.replace(hour=t.hour - t.hour % 6, minute=0, second=0, microsecond=0)
        for back in range(0, 5):
            cycle = latest - timedelta(hours=6 * back)
            leads = sorted(set(await leads_for(cycle)))[:MAX_TARGETED_LEADS]
            url0 = f"{BASE}/filter_gefs_atmos_0p50a.pl?dir=/gefs.{cycle:%Y%m%d}/{cycle.hour:02d}"
            if not leads:
                # Nothing wanted from this run (no launch opportunity in reach): no request.
                return http.Fetched(url0, 304, b"", None, None, None, True, 0)
            url, params = files(cycle, GEFS_MEMBERS[-1], leads[-1])[1]
            if await _get_grib(client, url, params) is None:
                continue  # the last member's b-file is the last to appear
            bodies: list[bytes] = []
            for lead_h in leads:
                for m in GEFS_MEMBERS:
                    for url, params in files(cycle, m, lead_h):
                        await asyncio.sleep(PAUSE_S)
                        body = await _get_grib(client, url, params)
                        if body is not None:
                            bodies.append(body)
            return http.Fetched(
                url=f"{url0}&lead={','.join(str(x) for x in leads)}",
                status=200,
                body=b"".join(bodies),
                etag=None,
                last_modified=None,
                content_type="application/x-grib2",
                not_modified=False,
                attempts=1,
            )
        raise http.FeedHttpError("no complete GEFS run found in the last 30 hours")

    return fetch


def _fixed(lead_h: int) -> LeadsFor:
    async def leads(_cycle: datetime) -> list[int]:
        return [lead_h]

    return leads


def _targeted(region: str, wanted: Wanted) -> LeadsFor:
    async def leads(cycle: datetime) -> list[int]:
        out = [gefs_lead(cycle, t) for t in await wanted(region)]
        return [x for x in out if x is not None]

    return leads


def _hrrr_fetch(points: list[Point], now: Callable[[], datetime]) -> Any:
    box = _box(points, 0.3)

    def params(cycle: datetime, lead: int) -> dict[str, str]:
        return {
            "dir": f"/hrrr.{cycle:%Y%m%d}/conus",
            "file": f"hrrr.t{cycle.hour:02d}z.wrfsfcf{lead:02d}.grib2",
            "var_UGRD": "on",
            "var_VGRD": "on",
            "var_GUST": "on",
            "var_TMP": "on",
            "var_CAPE": "on",
            "lev_10_m_above_ground": "on",
            "lev_80_m_above_ground": "on",
            "lev_2_m_above_ground": "on",
            "lev_surface": "on",
            **box,
        }

    async def fetch(client: httpx.AsyncClient, _e: str | None, _lm: str | None) -> http.Fetched:
        url = f"{BASE}/filter_hrrr_2d.pl"
        t = now().astimezone(UTC).replace(minute=0, second=0, microsecond=0)
        for back in range(1, 5):
            cycle = t - timedelta(hours=back)
            if await _get_grib(client, url, params(cycle, HRRR_LEADS_H[-1])) is None:
                continue
            bodies = []
            for lead in HRRR_LEADS_H:
                await asyncio.sleep(PAUSE_S)
                body = await _get_grib(client, url, params(cycle, lead))
                if body is not None:
                    bodies.append(body)
            return http.Fetched(
                url=f"{url}?dir=/hrrr.{cycle:%Y%m%d}/conus&cycle={cycle.hour:02d}",
                status=200,
                body=b"".join(bodies),
                etag=None,
                last_modified=None,
                content_type="application/x-grib2",
                not_modified=False,
                attempts=1,
            )
        raise http.FeedHttpError("no HRRR run found in the last four hours")

    return fetch


def products(
    regions: dict[str, list[Point]],
    *,
    hrrr_regions: set[str] | None = None,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    wanted: Wanted | None = None,
) -> list[Product]:
    """One GEFS product per region and lead; HRRR for regions inside its grid (CONUS).

    With ``wanted`` (the launch times of upcoming opportunities from a region's pads),
    also ``gefs_launch``: every member at the GEFS steps nearest those times (B0, B3).
    """
    out: list[Product] = []
    for region, pts in regions.items():
        if wanted is not None:
            out.append(
                Product(
                    provider="nomads",
                    product="gefs_launch",
                    location_key=region,
                    url=f"{BASE}/filter_gefs_atmos_0p50a.pl",
                    licence=LICENCE,
                    parser_version="gefs-1",
                    interval_s=6 * 3600,
                    staleness_s=18 * 3600,
                    parse=parse_points(pts, "GEFS", len(GEFS_MEMBERS)),
                    custom_fetch=_gefs_fetch(pts, _targeted(region, wanted), now),
                    keep_raw=False,
                    cost=MAX_TARGETED_LEADS * 2 * len(GEFS_MEMBERS) + 1,
                )
            )
        for lead in GEFS_LEADS_H:
            out.append(
                Product(
                    provider="nomads",
                    product=f"gefs_f{lead:03d}",
                    location_key=region,
                    url=f"{BASE}/filter_gefs_atmos_0p50a.pl",
                    licence=LICENCE,
                    parser_version="gefs-1",
                    interval_s=6 * 3600,
                    staleness_s=18 * 3600,
                    parse=parse_points(pts, "GEFS", len(GEFS_MEMBERS)),
                    custom_fetch=_gefs_fetch(pts, _fixed(lead), now),
                    keep_raw=False,
                    cost=2 * len(GEFS_MEMBERS) + 1,
                )
            )
        if region in WAVE_BOXES:
            out.append(
                Product(
                    provider="nomads",
                    product="gfswave",
                    location_key=region,
                    url=f"{BASE}/filter_gfswave.pl",
                    licence=LICENCE,
                    parser_version="gfswave-1",
                    interval_s=6 * 3600,
                    staleness_s=18 * 3600,
                    parse=parse_points(wave_points(region), "GFS-Wave", 1),
                    custom_fetch=_wave_fetch(region, wanted, now),
                    keep_raw=False,
                    cost=MAX_WAVE_LEADS + 1,
                )
            )
        if hrrr_regions is None or region in hrrr_regions:
            out.append(
                Product(
                    provider="nomads",
                    product="hrrr",
                    location_key=region,
                    url=f"{BASE}/filter_hrrr_2d.pl",
                    licence=LICENCE,
                    parser_version="hrrr-1",
                    interval_s=3 * 3600,
                    staleness_s=6 * 3600,
                    parse=parse_points(pts, "HRRR", 1),
                    custom_fetch=_hrrr_fetch(pts, now),
                    keep_raw=False,
                    cost=len(HRRR_LEADS_H) + 1,
                )
            )
    return out


FetchFn = Callable[[httpx.AsyncClient, str | None, str | None], Awaitable[http.Fetched]]
