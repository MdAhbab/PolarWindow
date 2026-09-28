"""Launch Library 2 (The Space Devs): the upcoming launch schedule at our pads.

Used for two things: other launches from the same range on a candidate day
(range conflicts), and where a booster is planned to land (landing type,
landing place, downrange distance). The anonymous allowance is 15 requests an
hour; the bucket for this provider is sized to that and kept in the
database, so a restart cannot overspend it. One request covers every pad.
"""

from __future__ import annotations

import json
from typing import Any

from app.feeds.base import Parsed, ParseError, Product, ProviderSpec, iso, utc

BASE = "https://ll.thespacedevs.com/2.3.0"
PROVIDER = ProviderSpec(name="ll2", capacity=15, per_hour=15)
LICENCE = "The Space Devs Launch Library 2 (free API; data under its terms of use)"


def _landings(rocket: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for stage in rocket.get("launcher_stage") or []:
        land = stage.get("landing")
        if not land:
            continue
        loc = land.get("landing_location") or {}
        typ = land.get("type") or {}
        out.append(
            {
                "type": typ.get("abbrev"),
                "type_name": typ.get("name"),
                "location": loc.get("name"),
                "location_abbrev": loc.get("abbrev"),
                "lat_deg": loc.get("latitude"),
                "lon_deg": loc.get("longitude"),
                "downrange_km": land.get("downrange_distance"),
            }
        )
    return out


def parse(body: bytes) -> Parsed:
    try:
        data = json.loads(body)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ParseError(f"not JSON: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("results"), list):
        raise ParseError("not a Launch Library 2 launch list")
    out = []
    for r in data["results"]:
        pad = r.get("pad") or {}
        loc = pad.get("location") or {}
        rocket = r.get("rocket") or {}
        conf = rocket.get("configuration") or {}
        if "net" not in r or "name" not in r:
            raise ParseError("launch rows need name and net")
        out.append(
            {
                "id": r.get("id"),
                "name": r["name"],
                "net": iso(utc(r["net"])),
                "net_precision": (r.get("net_precision") or {}).get("name"),
                "window_start": iso(utc(r["window_start"])) if r.get("window_start") else None,
                "window_end": iso(utc(r["window_end"])) if r.get("window_end") else None,
                "status": (r.get("status") or {}).get("abbrev"),
                "pad_id": pad.get("id"),
                "pad_name": pad.get("name"),
                "pad_lat_deg": _num(pad.get("latitude")),
                "pad_lon_deg": _num(pad.get("longitude")),
                "location_id": loc.get("id"),
                "location": loc.get("name"),
                "vehicle": conf.get("full_name") or conf.get("name"),
                "mission": (r.get("mission") or {}).get("name"),
                "landings": _landings(rocket),
                "url": r.get("url"),
            }
        )
    return Parsed(values={"count": data.get("count"), "launches": out}, issued_at=None)


def _num(v: object) -> float | None:
    try:
        return None if v is None else float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def products(location_ids: list[int]) -> list[Product]:
    ids = ",".join(str(i) for i in sorted(set(location_ids)))
    return [
        Product(
            provider="ll2",
            product="upcoming",
            url=f"{BASE}/launches/upcoming/",
            params={"limit": "40", "mode": "detailed", "location__ids": ids},
            licence=LICENCE,
            parser_version="ll2-1",
            interval_s=1800,
            staleness_s=12 * 3600,
            parse=parse,
        )
    ]
