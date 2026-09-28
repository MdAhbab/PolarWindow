"""DSN Now: which Deep Space Network dishes are tracking which spacecraft.

``https://eyes.nasa.gov/dsn/data/dsn.xml`` feeds NASA's DSN Now page. It is
not a documented API, so the parser is strict about the few things it relies
on (``station`` and ``dish`` elements, ``timeUTC`` in milliseconds) and
carries a version: a layout change is a rejected snapshot and a visible
error, never a silently wrong track. Used to check the predicted times a
ground station can hear a spacecraft (T1, F1) against what was tracked.
Polled no faster than once a minute.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

from app.feeds.base import PUBLIC_DOMAIN, Parsed, ParseError, Product, ProviderSpec, iso

URL = "https://eyes.nasa.gov/dsn/data/dsn.xml"
PROVIDER = ProviderSpec(name="dsn_now", capacity=5, per_hour=60)
LICENCE = f"NASA JPL DSN Now, {PUBLIC_DOMAIN}"

#: DSN Now's placeholder target for a dish doing maintenance or testing.
NOT_A_SPACECRAFT = frozenset({"DSN", "DSS", "TEST", "", "NONE"})


def _f(v: str | None) -> float | None:
    try:
        return None if v in (None, "", "-1", "none") else float(v)  # type: ignore[arg-type]
    except ValueError:
        return None


def parse(body: bytes) -> Parsed:
    try:
        root = ElementTree.fromstring(body)
    except (ElementTree.ParseError, DefusedXmlException) as exc:
        raise ParseError(f"not readable XML: {exc}") from exc
    if root.tag != "dsn":
        raise ParseError(f"root element is <{root.tag}>, expected <dsn>")
    stations: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    times: list[datetime] = []
    tracks: list[dict[str, Any]] = []
    for el in root:
        if el.tag == "station":
            ms = el.get("timeUTC")
            if ms is None:
                raise ParseError("<station> has no timeUTC")
            t = datetime.fromtimestamp(int(ms) / 1000.0, UTC)
            times.append(t)
            current = {"name": el.get("name"), "friendly": el.get("friendlyName"), "dishes": []}
            stations.append(current)
        elif el.tag == "dish":
            if current is None:
                raise ParseError("<dish> before any <station>")
            dish = el.get("name")
            targets: list[dict[str, Any]] = [
                {"name": g.get("name"), "id": g.get("id"), "rtlt_s": _f(g.get("rtlt"))}
                for g in el.findall("target")
            ]
            signals: list[dict[str, Any]] = [
                {
                    "dir": s.tag.replace("Signal", ""),
                    "active": s.get("active") == "true",
                    "band": s.get("band"),
                    "rate_bps": _f(s.get("dataRate")),
                    "spacecraft": s.get("spacecraft"),
                    "spacecraft_id": s.get("spacecraftID"),
                }
                for s in el
                if s.tag in ("upSignal", "downSignal")
            ]
            current["dishes"].append(
                {
                    "dish": dish,
                    "az_deg": _f(el.get("azimuthAngle")),
                    "el_deg": _f(el.get("elevationAngle")),
                    "activity": el.get("activity"),
                    "targets": targets,
                    "signals": signals,
                }
            )
            for tgt in targets:
                if str(tgt["name"] or "").upper() in NOT_A_SPACECRAFT:
                    continue
                active = any(
                    sig["active"]
                    and str(sig["spacecraft"] or "").upper() == str(tgt["name"] or "").upper()
                    for sig in signals
                )
                tracks.append(
                    {
                        "station": current["name"],
                        "dish": dish,
                        "spacecraft": tgt["name"],
                        "spacecraft_id": tgt["id"],
                        "signal_active": active,
                        "az_deg": _f(el.get("azimuthAngle")),
                        "el_deg": _f(el.get("elevationAngle")),
                    }
                )
    if not stations:
        raise ParseError("no <station> elements")
    at = max(times)
    return Parsed(
        values={"at": iso(at), "stations": stations, "tracks": tracks},
        issued_at=at,
        valid_from=at,
        valid_to=at,
    )


def products() -> list[Product]:
    return [
        Product(
            provider="dsn_now",
            product="dishes",
            url=URL,
            licence=LICENCE,
            parser_version="dsnnow-1",
            interval_s=300,
            staleness_s=900,
            parse=parse,
        )
    ]
