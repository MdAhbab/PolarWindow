"""JPL Horizons: the trajectories of real lunar orbiters (T1, F2).

LRO, Danuri, Chandrayaan-2 and CAPSTONE fly over the landing sites. Their
passes are shown as "could see the lander" geometry, never as a relay
service: none of them has an agreement to relay for a CLPS lander.

One product per orbiter, refreshed weekly: Moon-centred states in ICRF
(SPICE's J2000) every 5 minutes from a week ago to 30 days ahead. The
compute worker turns a snapshot into an SPK type 13 (Hermite) kernel. One
more product per orbiter and flown mission covers that mission's surface
days once (the past does not change).

Horizons refuses the whole request when the dates run past the end of its
data ("No ephemeris for target ... after A.D. ..."); the fetch then asks
again for the part it has.
"""

from __future__ import annotations

import itertools
import re
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import httpx

from app.feeds import http
from app.feeds.base import Parsed, ParseError, Product, ProviderSpec

URL = "https://ssd.jpl.nasa.gov/api/horizons.api"
#: Horizons asks for reasonable use and publishes no number; four weekly
#: requests (and a handful of one-off ones) stay far below any.
PROVIDER = ProviderSpec(name="horizons", capacity=20, per_hour=20)
LICENCE = "NASA/JPL Horizons (US government work, public domain)"
STEP_MIN = 5
PARSER_VERSION = "vectors-1"
_J2000_JD = 2451545.0
_J2000_UTC = datetime(2000, 1, 1, 12, tzinfo=UTC)

_NO_AFTER = re.compile(r"No ephemeris for target .* after A\.D\. (\d{4}-[A-Z]{3}-\d{2} [\d:.]+)")
_NO_BEFORE = re.compile(
    r"No ephemeris for target .* prior to A\.D\. (\d{4}-[A-Z]{3}-\d{2} [\d:.]+)"
)
_MONTHS = {m: i for i, m in enumerate("JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split(), 1)}


def params(naif_id: int, start: datetime, stop: datetime) -> dict[str, str]:
    return {
        "format": "text",
        "COMMAND": f"'{naif_id}'",
        "OBJ_DATA": "'NO'",
        "MAKE_EPHEM": "'YES'",
        "EPHEM_TYPE": "'VECTORS'",
        "CENTER": "'500@301'",
        "START_TIME": f"'{start:%Y-%m-%d %H:%M}'",
        "STOP_TIME": f"'{stop:%Y-%m-%d %H:%M}'",
        "STEP_SIZE": f"'{STEP_MIN}m'",
        "VEC_TABLE": "'2'",
        "REF_PLANE": "'FRAME'",
        "REF_SYSTEM": "'ICRF'",
        "OUT_UNITS": "'KM-S'",
        "CSV_FORMAT": "'YES'",
        "VEC_LABELS": "'NO'",
    }


def _tdb(text: str) -> datetime:
    """``2026-AUG-14 11:58:59.9999`` (TDB, read as a calendar date to the minute)."""
    d, t = text.split()
    y, mon, day = d.split("-")
    hh, mm = t.split(":")[:2]
    return datetime(int(y), _MONTHS[mon.upper()], int(day), int(hh), int(mm), tzinfo=UTC)


def parse(body: bytes) -> Parsed:
    """States from a Horizons VECTORS table: ``[et_s, x, y, z, vx, vy, vz]`` in m and m/s.

    ``et_s`` is TDB seconds past J2000 (SPICE's ephemeris time), from the
    table's own Julian date, so no time-scale conversion is involved.
    """
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ParseError(f"not text: {exc}") from exc
    m = _NO_AFTER.search(text) or _NO_BEFORE.search(text)
    if m:
        # Horizons has no trajectory for any of the dates asked (an orbiter whose
        # data ends before them): a true answer, recorded as such, not a failure.
        tgt = re.search(r'No ephemeris for target "(.+?)"', text)
        at = _tdb(m.group(1))
        return Parsed(
            values={
                "naif_id": None,
                "target": tgt.group(1) if tgt else None,
                "source": None,
                "center": 301,
                "frame": "J2000",
                "step_s": None,
                "rows": [],
                "no_data": m.group(0),
            },
            issued_at=None,
            valid_from=at if m.re is _NO_AFTER else None,
            valid_to=at if m.re is _NO_AFTER else None,
        )
    if "$$SOE" not in text or "$$EOE" not in text:
        raise ParseError("not a Horizons VECTORS table (no $$SOE/$$EOE)")
    head, rest = text.split("$$SOE", 1)
    table = rest.split("$$EOE", 1)[0]
    tgt = re.search(r"Target body name: (.+?) \((-?\d+)\)", head)
    if not tgt:
        raise ParseError("no target body line")
    if "Center body name: Moon (301)" not in head:
        raise ParseError("vectors are not centred on the Moon")
    if "Reference frame : ICRF" not in head:
        raise ParseError("vectors are not in ICRF")
    if "GEOMETRIC cartesian states" not in head:
        raise ParseError("vectors are not geometric states")
    rows: list[list[float]] = []
    issues: list[str] = []
    for line in table.strip().splitlines():
        f = [x.strip() for x in line.split(",")]
        if len(f) < 8:
            raise ParseError(f"short row: {line[:80]!r}")
        jd = float(f[0])
        x, y, z, vx, vy, vz = (float(v) for v in f[2:8])
        r = (x * x + y * y + z * z) ** 0.5
        v = (vx * vx + vy * vy + vz * vz) ** 0.5
        if not 1737.0 < r < 1.0e6 or not v < 10.0:
            issues.append(
                f"row at JD {jd}: {r:.0f} km, {v:.2f} km/s outside a lunar orbit; dropped"
            )
            continue
        rows.append(
            [
                round((jd - _J2000_JD) * 86400.0, 3),
                x * 1e3,
                y * 1e3,
                z * 1e3,
                vx * 1e3,
                vy * 1e3,
                vz * 1e3,
            ]
        )
    if len(rows) < 8:
        raise ParseError(f"only {len(rows)} usable rows")
    steps = {round(b[0] - a[0], 3) for a, b in itertools.pairwise(rows)}
    src = re.search(r"\{source: ([^}]+)\}", head)
    return Parsed(
        values={
            "naif_id": int(tgt.group(2)),
            "target": tgt.group(1).strip(),
            "source": src.group(1).strip() if src else None,
            "center": 301,
            "frame": "J2000",
            "step_s": min(steps),
            "rows": rows,
        },
        issued_at=None,
        # TDB - UTC = 69.184 s since 2017 (to a millisecond: only the span is kept here).
        valid_from=_J2000_UTC + timedelta(seconds=rows[0][0] - 69.184),
        valid_to=_J2000_UTC + timedelta(seconds=rows[-1][0] - 69.184),
        issues=issues,
    )


Window = Callable[[], tuple[datetime, datetime]]


def rolling(now: Callable[[], datetime] = lambda: datetime.now(UTC)) -> Window:
    """A week ago to 30 days ahead of the day the fetch runs (the worker runs for weeks)."""

    def w() -> tuple[datetime, datetime]:
        d = now().replace(hour=0, minute=0, second=0, microsecond=0)
        return d - timedelta(days=7), d + timedelta(days=30)

    return w


def _fixed(start: datetime, stop: datetime) -> Window:
    return lambda: (start, stop)


def _fetch(
    naif_id: int, window: Window
) -> Callable[[httpx.AsyncClient, str | None, str | None], Awaitable[http.Fetched]]:
    async def run(client: httpx.AsyncClient, etag: str | None, lm: str | None) -> http.Fetched:
        s, e = window()
        for _ in range(3):
            got = await http.fetch(client, URL, params=params(naif_id, s, e))
            text = got.body.decode("utf-8", errors="replace")
            after = _NO_AFTER.search(text)
            before = _NO_BEFORE.search(text)
            if after:
                e = _tdb(after.group(1)) - timedelta(minutes=1)
            elif before:
                s = _tdb(before.group(1)) + timedelta(minutes=1)
            else:
                return got
            if e - s < timedelta(hours=6):
                return got  # nothing usable left: the parser says why
        return got

    return run


def product(
    naif_id: int,
    window: Window,
    *,
    location_key: str,
    interval_s: int,
    staleness_s: int,
) -> Product:
    start, stop = window()
    return Product(
        provider="horizons",
        product="vectors",
        url=URL,
        params=params(naif_id, start, stop),
        licence=LICENCE,
        parser_version=PARSER_VERSION,
        interval_s=interval_s,
        staleness_s=staleness_s,
        parse=parse,
        location_key=location_key,
        custom_fetch=_fetch(naif_id, window),
        keep_raw=False,
    )


def products(
    orbiters: list[tuple[str, int]],
    flown: list[tuple[str, datetime, datetime]],
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> list[Product]:
    """Weekly: a week ago to 30 days ahead. Once: each flown mission's surface days."""
    out = [
        product(
            naif,
            rolling(now),
            location_key=oid,
            interval_s=7 * 86400,
            staleness_s=8 * 86400,
        )
        for oid, naif in orbiters
    ]
    for mission, start, end in flown:
        s = start.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
        e = end.replace(minute=0, second=0, microsecond=0) + timedelta(hours=2)
        out += [
            product(
                naif,
                _fixed(s, e),
                location_key=f"{oid}@{mission}",
                interval_s=365 * 86400,
                # The past does not change: never stale once recorded.
                staleness_s=10 * 365 * 86400,
            )
            for oid, naif in orbiters
        ]
    return out
