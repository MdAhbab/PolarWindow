"""NASA DONKI (Space Weather Database Of Notifications, Knowledge, Information).

Coronal mass ejections, solar flares and solar energetic particle events for
the last 30 days, through api.nasa.gov. ``PW_NASA_API_KEY`` raises the
allowance from DEMO_KEY's 30 requests an hour to 1,000; the key is sent as a
query parameter and never stored with the snapshot URL.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from app.config import get_settings
from app.feeds.base import PUBLIC_DOMAIN, Parsed, ParseError, Product, ProviderSpec, iso, utc

BASE = "https://api.nasa.gov/DONKI"
LICENCE = f"NASA CCMC DONKI, {PUBLIC_DOMAIN}"
DAYS = 30


def provider() -> ProviderSpec:
    keyed = get_settings().nasa_api_key not in ("", "DEMO_KEY")
    return ProviderSpec(name="donki", capacity=10, per_hour=300 if keyed else 20)


def _events(body: bytes) -> list[dict[str, Any]]:
    try:
        data = json.loads(body) if body.strip() else []
    except (ValueError, UnicodeDecodeError) as exc:
        raise ParseError(f"not JSON: {exc}") from exc
    if not isinstance(data, list):
        raise ParseError("expected a list of events")
    return data


def _t(v: object) -> str | None:
    return iso(utc(str(v))) if v else None


def parse_cme(body: bytes) -> Parsed:
    out = []
    for e in _events(body):
        if "activityID" not in e:
            raise ParseError("CME rows need activityID")
        analyses = e.get("cmeAnalyses") or []
        best = next(
            (a for a in analyses if a.get("isMostAccurate")), analyses[0] if analyses else {}
        )
        earth = []
        for a in analyses:
            for m in a.get("enlilList") or []:
                if m.get("estimatedShockArrivalTime"):
                    earth.append(_t(m["estimatedShockArrivalTime"]))
        out.append(
            {
                "id": e["activityID"],
                "start": _t(e.get("startTime")),
                "source_location": e.get("sourceLocation"),
                "speed_m_s": float(best["speed"]) * 1000.0 if best.get("speed") else None,
                "half_angle_deg": best.get("halfAngle"),
                "type": best.get("type"),
                "earth_arrival_estimates": sorted({x for x in earth if x}),
                "link": e.get("link"),
            }
        )
    return _wrap(out, "start")


def parse_flr(body: bytes) -> Parsed:
    out = []
    for e in _events(body):
        if "flrID" not in e:
            raise ParseError("flare rows need flrID")
        out.append(
            {
                "id": e["flrID"],
                "begin": _t(e.get("beginTime")),
                "peak": _t(e.get("peakTime")),
                "end": _t(e.get("endTime")),
                "class": e.get("classType"),
                "source_location": e.get("sourceLocation"),
                "link": e.get("link"),
            }
        )
    return _wrap(out, "peak")


def parse_sep(body: bytes) -> Parsed:
    out = []
    for e in _events(body):
        if "sepID" not in e:
            raise ParseError("SEP rows need sepID")
        out.append(
            {
                "id": e["sepID"],
                "time": _t(e.get("eventTime")),
                "instruments": [i.get("displayName") for i in e.get("instruments") or []],
                "linked": [x.get("activityID") for x in e.get("linkedEvents") or []],
                "link": e.get("link"),
            }
        )
    return _wrap(out, "time")


def _wrap(events: list[dict[str, Any]], tkey: str) -> Parsed:
    events.sort(key=lambda x: str(x.get(tkey) or ""), reverse=True)
    # No issue time: the list is as new as the request for it. Its newest event's time
    # would make a quiet Sun (no CME for a day) look like stale data and hide the list.
    return Parsed(
        values={"count": len(events), "events": events[:100], "days": DAYS}, issued_at=None
    )


def products(now: datetime | None = None) -> list[Product]:
    now = now or datetime.now(UTC)
    start = (now - timedelta(days=DAYS)).date().isoformat()
    end = now.date().isoformat()
    key = get_settings().nasa_api_key or "DEMO_KEY"
    out = []
    for product, path, parse in (
        ("cme", "CME", parse_cme),
        ("flr", "FLR", parse_flr),
        ("sep", "SEP", parse_sep),
    ):
        out.append(
            Product(
                provider="donki",
                product=product,
                url=f"{BASE}/{path}",
                params={"startDate": start, "endDate": end, "api_key": key},
                secret_params=frozenset({"api_key"}),
                licence=LICENCE,
                parser_version=f"{product}-1",
                interval_s=3 * 3600,
                staleness_s=24 * 3600,
                parse=parse,
            )
        )
    return out
