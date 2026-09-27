"""GRIB2 point extraction through ecCodes. The only module that imports eccodes.

Takes the bytes of one or more GRIB2 messages (a NOMADS subset, or byte
ranges of an AWS open-data file) and returns the value of every message at
each requested point:

* on a regular latitude-longitude grid (GEFS, GFS) by bilinear interpolation
  between the four surrounding grid points, which is exact for a field that
  is linear across one cell;
* on any other grid (HRRR's Lambert conformal, 3 km) at the nearest grid
  point, with the distance to it recorded.

Nothing here knows what a launch rule is; it returns numbers with their
grid, level, run, lead and ensemble member.
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import eccodes

from app.feeds.base import ParseError


@dataclass(frozen=True, slots=True)
class PointValue:
    short_name: str
    level_type: str
    level: int
    run: datetime
    step_h: int
    member: int | None
    point_id: str
    value: float
    grid_lat: float
    grid_lon: float
    distance_km: float
    units: str
    method: str


def split_messages(data: bytes) -> list[bytes]:
    """Cut a byte string into GRIB messages using each message's own length."""
    out = []
    i = 0
    while True:
        j = data.find(b"GRIB", i)
        if j < 0:
            break
        if len(data) < j + 16:
            raise ParseError("truncated GRIB message header")
        edition = data[j + 7]
        if edition == 2:
            (length,) = struct.unpack(">Q", data[j + 8 : j + 16])
        elif edition == 1:
            length = int.from_bytes(data[j + 4 : j + 7], "big")
        else:
            raise ParseError(f"unknown GRIB edition {edition}")
        msg = data[j : j + length]
        if len(msg) != length or not msg.endswith(b"7777"):
            raise ParseError("truncated GRIB message")
        out.append(msg)
        i = j + length
    return out


def _get(h: Any, key: str) -> Any:
    try:
        return eccodes.codes_get(h, key)
    except eccodes.KeyValueNotFoundError:
        return None


def _bilinear(near: list[dict[str, float]], lat: float, lon: float) -> float:
    lats = sorted({round(n["lat"], 6) for n in near})
    lons = sorted({round(n["lon"], 6) for n in near})
    if len(lats) != 2 or len(lons) != 2:
        # Exactly on a grid line or point: the nearest value is exact there.
        return float(min(near, key=lambda n: n["distance"])["value"])
    val = {(round(n["lat"], 6), round(n["lon"], 6)): n["value"] for n in near}
    lon_q = lon % 360.0
    x0, x1 = lons
    y0, y1 = lats
    tx = (lon_q - x0) / (x1 - x0) if x1 != x0 else 0.0
    ty = (lat - y0) / (y1 - y0) if y1 != y0 else 0.0
    v00, v10 = val[(y0, x0)], val[(y0, x1)]
    v01, v11 = val[(y1, x0)], val[(y1, x1)]
    return float(
        v00 * (1 - tx) * (1 - ty) + v10 * tx * (1 - ty) + v01 * (1 - tx) * ty + v11 * tx * ty
    )


def point_values(data: bytes, points: list[tuple[str, float, float]]) -> list[PointValue]:
    """Every message's value at every point. Raises ParseError on unreadable data."""
    msgs = split_messages(data)
    if not msgs:
        raise ParseError("no GRIB messages in the body")
    out: list[PointValue] = []
    for m in msgs:
        try:
            h = eccodes.codes_new_from_message(m)
        except eccodes.CodesInternalError as exc:
            raise ParseError(f"ecCodes could not read a message: {exc}") from exc
        try:
            date, time = int(_get(h, "dataDate")), int(_get(h, "dataTime"))
            run = datetime(
                date // 10000, date // 100 % 100, date % 100, time // 100, time % 100, tzinfo=UTC
            )
            step_range = str(_get(h, "stepRange"))
            step_h = int(step_range.split("-")[-1])
            member = _get(h, "perturbationNumber")
            grid = str(_get(h, "gridType"))
            missing = _get(h, "missingValue")
            for pid, lat, lon in points:
                near = eccodes.codes_grib_find_nearest(h, lat, lon % 360.0, npoints=4)
                values = [n for n in near if missing is None or n["value"] != missing]
                if not values:
                    continue
                if grid == "regular_ll" and len(values) == 4:
                    v, method = _bilinear(list(values), lat, lon), "bilinear"
                    nn = min(values, key=lambda n: n["distance"])
                else:
                    nn = min(values, key=lambda n: n["distance"])
                    v, method = float(nn["value"]), "nearest"
                if not math.isfinite(v):
                    continue
                out.append(
                    PointValue(
                        short_name=str(_get(h, "shortName")),
                        level_type=str(_get(h, "typeOfLevel")),
                        level=int(_get(h, "level") or 0),
                        run=run,
                        step_h=step_h,
                        member=None if member is None else int(member),
                        point_id=pid,
                        value=v,
                        grid_lat=float(nn["lat"]),
                        grid_lon=float(nn["lon"]),
                        distance_km=float(nn["distance"]),
                        units=str(_get(h, "units")),
                        method=method,
                    )
                )
        finally:
            eccodes.codes_release(h)
    return out


def valid_time(pv: PointValue) -> datetime:
    return pv.run + timedelta(hours=pv.step_h)
