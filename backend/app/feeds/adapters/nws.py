"""US National Weather Service forecasts at the launch pads (api.weather.gov).

Keyless; NWS asks for a User-Agent that identifies the application and a
contact, which the HTTP layer sends. For each pad:

* ``grid``: ``/points/{lat},{lon}`` gives the forecast office and grid cell,
  then ``/gridpoints/{office}/{x},{y}`` the raw forecast grid: hourly wind
  speed and gusts (10 m), direction, temperature, sky cover, and the chances
  of rain and thunder. Values arrive as ISO-8601 stretches ("from 12:00 for
  3 hours"); they are expanded to hourly values and converted to SI.
* ``alerts``: active watches and warnings at the pad.

NWS keeps no archive of its forecasts, which is why these are recorded: a
forecast used for a launch answer can only be checked later if it was kept.
One forecast is shown as "one forecast", never as a probability (ADR-14).
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
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
    utc,
)

BASE = "https://api.weather.gov"
PROVIDER = ProviderSpec(name="nws", capacity=30, per_hour=600)
LICENCE = f"NOAA National Weather Service, {PUBLIC_DOMAIN}"
HEADERS = {"Accept": "application/geo+json"}

#: Hours of forecast kept per snapshot.
HOURS = 7 * 24

_DUR = re.compile(r"^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?)?$")

#: grid property -> (key, converter to SI, physical range in SI)
_FIELDS: dict[str, tuple[str, str, float, float]] = {
    "windSpeed": ("wind_speed_m_s", "km_h", 0.0, 120.0),
    "windGust": ("wind_gust_m_s", "km_h", 0.0, 150.0),
    "windDirection": ("wind_dir_deg", "deg", 0.0, 360.0),
    "temperature": ("temperature_k", "degc", 180.0, 340.0),
    "dewpoint": ("dewpoint_k", "degc", 180.0, 330.0),
    "skyCover": ("sky_cover_frac", "pct", 0.0, 1.0),
    "probabilityOfPrecipitation": ("p_precip_frac", "pct", 0.0, 1.0),
    "probabilityOfThunder": ("p_thunder_frac", "pct", 0.0, 1.0),
    "quantitativePrecipitation": ("precip_mm", "mm", 0.0, 500.0),
}


def duration(text: str) -> timedelta:
    m = _DUR.match(text)
    if not m:
        raise ParseError(f"cannot read the duration {text!r}")
    d, h, mi = (int(x) if x else 0 for x in m.groups())
    return timedelta(days=d, hours=h, minutes=mi)


def _convert(kind: str, v: float) -> float:
    if kind == "km_h":
        return v / 3.6
    if kind == "degc":
        return v + 273.15
    if kind == "pct":
        return v / 100.0
    return v


def expand(values: list[dict[str, Any]], start: datetime, hours: int) -> list[float | None]:
    """Hourly values from NWS's ``{validTime: "t/PT3H", value}`` stretches."""
    out: list[float | None] = [None] * hours
    for item in values:
        vt = str(item.get("validTime", ""))
        if "/" not in vt:
            raise ParseError(f"validTime without a duration: {vt!r}")
        t0_s, dur_s = vt.split("/", 1)
        t0 = utc(t0_s)
        t1 = t0 + duration(dur_s)
        v = item.get("value")
        if v is None:
            continue
        i0 = max(0, int((t0 - start).total_seconds() // 3600))
        i1 = min(hours, int(-(-(t1 - start).total_seconds() // 3600)))
        for i in range(i0, i1):
            out[i] = float(v)
    return out


def parse_grid(body: bytes) -> Parsed:
    try:
        data = json.loads(body)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ParseError(f"not JSON: {exc}") from exc
    props = data.get("properties") if isinstance(data, dict) else None
    if not isinstance(props, dict) or "updateTime" not in props or "validTimes" not in props:
        raise ParseError("not an NWS forecast grid (no properties.updateTime/validTimes)")
    issued = utc(props["updateTime"])
    vstart = utc(str(props["validTimes"]).split("/")[0])
    start = vstart.replace(minute=0, second=0, microsecond=0)
    issues: list[str] = []
    series: dict[str, list[float | None]] = {}
    for name, (key, conv, lo, hi) in _FIELDS.items():
        block = props.get(name)
        if not isinstance(block, dict) or "values" not in block:
            issues.append(f"{name}: not in this grid")
            continue
        raw = expand(block["values"], start, HOURS)
        clean: list[float | None] = []
        for v in raw:
            clean.append(None if v is None else in_range(key, _convert(conv, v), lo, hi, issues))
        series[key] = clean
    if "wind_speed_m_s" not in series or "temperature_k" not in series:
        raise ParseError("grid has no wind speed or temperature")
    times = [iso(start + timedelta(hours=i)) for i in range(HOURS)]
    return Parsed(
        values={
            "office": props.get("gridId"),
            "grid": [props.get("gridX"), props.get("gridY")],
            "height_m": {"wind": 10.0, "temperature": 2.0},
            "times": times,
            **series,
        },
        issued_at=issued,
        valid_from=start,
        valid_to=start + timedelta(hours=HOURS),
        issues=issues[:30],
    )


def parse_alerts(body: bytes) -> Parsed:
    try:
        data = json.loads(body)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ParseError(f"not JSON: {exc}") from exc
    feats = data.get("features") if isinstance(data, dict) else None
    if not isinstance(feats, list):
        raise ParseError("not an NWS alert collection")
    out = []
    for f in feats:
        p = f.get("properties", {})
        out.append(
            {
                "event": p.get("event"),
                "headline": p.get("headline"),
                "severity": p.get("severity"),
                "onset": p.get("onset"),
                "ends": p.get("ends") or p.get("expires"),
                "sender": p.get("senderName"),
            }
        )
    updated = data.get("updated")
    return Parsed(values={"alerts": out}, issued_at=utc(updated) if updated else None)


def _grid_fetch(lat: float, lon: float) -> Any:
    async def fetch(
        client: httpx.AsyncClient, etag: str | None, last_modified: str | None
    ) -> http.Fetched:
        pts = await http.fetch(client, f"{BASE}/points/{lat:.4f},{lon:.4f}", headers=HEADERS)
        try:
            grid_url = json.loads(pts.body)["properties"]["forecastGridData"]
        except (ValueError, KeyError, TypeError) as exc:
            raise http.FeedHttpError("NWS points lookup had no forecastGridData") from exc
        return await http.fetch(
            client, grid_url, headers=HEADERS, etag=etag, last_modified=last_modified
        )

    return fetch


def products(pads: list[tuple[str, float, float]]) -> list[Product]:
    """``pads``: (id, lat, lon) of every pad inside NWS coverage (the US)."""
    out: list[Product] = []
    for pad_id, lat, lon in pads:
        out.append(
            Product(
                provider="nws",
                product="grid",
                location_key=pad_id,
                url=f"{BASE}/points/{lat:.4f},{lon:.4f}",
                licence=LICENCE,
                parser_version="nwsgrid-1",
                interval_s=3600,
                staleness_s=6 * 3600,
                parse=parse_grid,
                custom_fetch=_grid_fetch(lat, lon),
                cost=2.0,
            )
        )
        out.append(
            Product(
                provider="nws",
                product="alerts",
                location_key=pad_id,
                url=f"{BASE}/alerts/active",
                params={"point": f"{lat:.4f},{lon:.4f}"},
                headers=HEADERS,
                licence=LICENCE,
                parser_version="nwsalerts-1",
                interval_s=900,
                staleness_s=3 * 3600,
                parse=parse_alerts,
            )
        )
    return out
