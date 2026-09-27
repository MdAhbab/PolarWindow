"""NOAA National Data Buoy Center real-time observations (``realtime2/{id}.txt``).

Wave height, wind and gusts at buoys near the booster landing zones and
splashdown areas. Observations, not forecasts: they show the sea state now
and check the wave forecasts later. Missing values are ``MM`` in the file and
None here, never zero.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.feeds.base import PUBLIC_DOMAIN, Parsed, ParseError, Product, ProviderSpec, in_range, iso

BASE = "https://www.ndbc.noaa.gov/data/realtime2"
PROVIDER = ProviderSpec(name="ndbc", capacity=10, per_hour=120)
LICENCE = f"NOAA National Data Buoy Center, {PUBLIC_DOMAIN}"

#: column -> (key, to SI, range in SI)
_COLS: dict[str, tuple[str, float, float, float, float]] = {
    "WDIR": ("wind_dir_deg", 1.0, 0.0, 0.0, 360.0),
    "WSPD": ("wind_m_s", 1.0, 0.0, 0.0, 80.0),
    "GST": ("gust_m_s", 1.0, 0.0, 0.0, 100.0),
    "WVHT": ("wave_height_m", 1.0, 0.0, 0.0, 30.0),
    "DPD": ("dominant_period_s", 1.0, 0.0, 0.0, 40.0),
    "APD": ("average_period_s", 1.0, 0.0, 0.0, 40.0),
    "PRES": ("pressure_pa", 100.0, 0.0, 85_000.0, 110_000.0),
    "ATMP": ("air_temp_k", 1.0, 273.15, 220.0, 330.0),
    "WTMP": ("water_temp_k", 1.0, 273.15, 265.0, 310.0),
}

HOURS = 48


def parse(body: bytes) -> Parsed:
    try:
        lines = body.decode("ascii").splitlines()
    except UnicodeDecodeError as exc:
        raise ParseError("buoy file is not plain text") from exc
    if len(lines) < 3 or not lines[0].startswith("#YY"):
        raise ParseError("not an NDBC realtime2 standard meteorological file")
    header = lines[0].lstrip("#").split()
    idx = {name: i for i, name in enumerate(header)}
    for need in ("YY", "MM", "DD", "hh", "mm"):
        if need not in idx:
            raise ParseError(f"column {need} missing")
    issues: list[str] = []
    rows: list[dict[str, Any]] = []
    newest: datetime | None = None
    for ln in lines[2:]:
        parts = ln.split()
        if len(parts) != len(header):
            continue
        t = datetime(
            int(parts[idx["YY"]]),
            int(parts[idx["MM"]]),
            int(parts[idx["DD"]]),
            int(parts[idx["hh"]]),
            int(parts[idx["mm"]]),
            tzinfo=UTC,
        )
        newest = newest or t
        if t < newest - timedelta(hours=HOURS):
            break
        row: dict[str, Any] = {"t": iso(t)}
        for col, (key, scale, offset, lo, hi) in _COLS.items():
            if col not in idx:
                continue
            raw = parts[idx[col]]
            row[key] = (
                None if raw == "MM" else in_range(key, float(raw) * scale + offset, lo, hi, issues)
            )
        rows.append(row)
    if not rows or newest is None:
        raise ParseError("no observations")

    def last_of(key: str) -> dict[str, Any] | None:
        return next(({"t": r["t"], "value": r[key]} for r in rows if r.get(key) is not None), None)

    return Parsed(
        values={
            "latest": {k[0]: last_of(k[0]) for k in _COLS.values()},
            "series": rows[:: max(1, len(rows) // 96)],
        },
        issued_at=newest,
        valid_from=newest - timedelta(hours=HOURS),
        valid_to=newest,
        issues=issues[:20],
    )


def products(buoys: list[str]) -> list[Product]:
    return [
        Product(
            provider="ndbc",
            product="obs",
            location_key=b,
            url=f"{BASE}/{b}.txt",
            licence=LICENCE,
            parser_version="ndbc-1",
            interval_s=1800,
            staleness_s=3 * 3600,
            parse=parse,
        )
        for b in buoys
    ]
