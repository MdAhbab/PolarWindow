"""GEFS wind shares checked against what the Cape's weather station measured (T4, Verification).

Run: ``make hindcast-weather`` (``uv run python -m app.feeds.hindcast``). About an
hour: a year of GEFS runs is read from NOAA's open-data bucket on AWS
(``noaa-gefs-pds``), 10 m wind only, byte ranges found from each file's index;
nothing but the value at the station is kept. Results are cached per run, so a
second run only fetches what is missing.

The Falcon 9 wind rule is at 162 ft (49 m), which no public station measures.
The check is made where the Cape Canaveral Skid Strip's weather station (ASOS
KXMR, from the Iowa Environmental Mesonet archive) measures, at 10 m: the
rule's limit is brought down to 10 m with a neutral logarithmic profile over
open flat ground (roughness 0.03 m, Davenport's "open" class in WMO-No. 8), so
30 mph at 49 m is 23.5 mph at 10 m. A case is one GEFS run (one a day, its hour
turning through 00, 06, 12 and 18 UTC) at 24 and at 48 hours: the share of the
31 runs whose 10 m wind (bilinear at the station) is above that, against
whether the station's sustained wind in its report nearest the hour was. The
reference is the month-by-hour frequency of the same event in the station's
own record for 2015-2024. ``core.verification`` scores it against the plan's
gate. Writes ``data/hindcast/gefs_wind_{region}.json``.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import io
import json
import math
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import numpy as np

from app.config import get_settings
from app.core import verification as vf
from app.core import weather_rules as wr
from app.data import catalogues
from app.feeds.adapters.nomads import GEFS_MEMBERS
from app.feeds.parsers import grib

BUCKET = "https://noaa-gefs-pds.s3.amazonaws.com"
IEM = "https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py"
STATIONS = {"florida": ("XMR", "KXMR", 28.4677, -80.5668)}
RULE_ID = "f9-wind-162ft"
RULE_HEIGHT_M = 162 * 0.3048
OBS_HEIGHT_M = 10.0
Z0_M = 0.03
LEADS = (24, 48)
CLIM_YEARS = (2015, 2024)
KT = 1852.0 / 3600.0
PARALLEL = 48
#: Runs fetched at once (each is 31 members).
BATCH = 8
OBS_WITHIN = timedelta(minutes=30)


def out_path(region: str) -> Path:
    return get_settings().data_dir / "hindcast" / f"gefs_wind_{region}.json"


def cache_path(region: str) -> Path:
    return get_settings().data_dir / "hindcast" / f"gefs_wind_{region}.cache.jsonl"


def threshold_m_s() -> float:
    rule = catalogues.load("weather_rules").get(RULE_ID)
    assert rule.threshold is not None and rule.unit is not None
    top = wr.to_m_s(float(rule.threshold), rule.unit)
    return top * vf.neutral_ratio(RULE_HEIGHT_M, OBS_HEIGHT_M, Z0_M)


async def observations(
    client: httpx.AsyncClient, station: str, y0: int, y1: int, keep: Path
) -> dict[datetime, float]:
    """Sustained wind (m/s) of each routine report, by report time (UTC), in one request
    (the archive answers 429 to a quick series of them); kept in ``keep``."""
    if not keep.exists():
        params = {
            "station": station,
            "data": "sknt",
            "year1": str(y0),
            "month1": "1",
            "day1": "1",
            "year2": str(y1 + 1),
            "month2": "1",
            "day2": "1",
            "tz": "Etc/UTC",
            "format": "onlycomma",
            "latlon": "no",
            "missing": "M",
            "trace": "T",
            "direct": "no",
            "report_type": "3",
        }
        for attempt in range(5):
            r = await client.get(IEM, params=params, timeout=600)
            if r.status_code != 429:
                break
            await asyncio.sleep(30.0 * (attempt + 1))
        r.raise_for_status()
        keep.write_text(r.text)
    out: dict[datetime, float] = {}
    for row in csv.DictReader(io.StringIO(keep.read_text())):
        v = row.get("sknt")
        if not v or v == "M":
            continue
        t = datetime.strptime(row["valid"], "%Y-%m-%d %H:%M").replace(tzinfo=UTC)
        out[t] = float(v) * KT
    print(f"obs {station}: {len(out)} reports", file=sys.stderr)
    return out


def nearest_obs(obs: dict[datetime, float], sorted_t: list[datetime], t: datetime) -> float | None:
    import bisect

    i = bisect.bisect_left(sorted_t, t)
    best: tuple[timedelta, datetime] | None = None
    for j in (i - 1, i):
        if 0 <= j < len(sorted_t):
            d = abs(sorted_t[j] - t)
            if d <= OBS_WITHIN and (best is None or d < best[0]):
                best = (d, sorted_t[j])
    return None if best is None else obs[best[1]]


def _range_of(idx: str) -> tuple[int, int] | None:
    """Bytes of the 10 m UGRD and VGRD messages (adjacent) from a GRIB index."""
    rows = [x.split(":") for x in idx.strip().splitlines()]
    starts = [int(r[1]) for r in rows]
    for i, r in enumerate(rows):
        nxt = rows[i + 1] if i + 1 < len(rows) else None
        if r[3:5] == ["UGRD", "10 m above ground"] and nxt and nxt[3:5] == ["VGRD", r[4]]:
            end = starts[i + 2] - 1 if i + 2 < len(rows) else -1
            return starts[i], end
    return None


async def member_speed(
    client: httpx.AsyncClient,
    gate: asyncio.Semaphore,
    cycle: datetime,
    member: str,
    lead: int,
    point: tuple[float, float],
) -> float | None:
    hh = f"{cycle.hour:02d}"
    url = (
        f"{BUCKET}/gefs.{cycle:%Y%m%d}/{hh}/atmos/pgrb2ap5/"
        f"{member}.t{hh}z.pgrb2a.0p50.f{lead:03d}"
    )
    async with gate:
        for attempt in range(4):
            try:
                ir = await client.get(url + ".idx")
                if ir.status_code == 404:
                    return None
                ir.raise_for_status()
                rng = _range_of(ir.text)
                if rng is None:
                    return None
                a, b = rng
                r = await client.get(url, headers={"Range": f"bytes={a}-{'' if b < 0 else b}"})
                r.raise_for_status()
                break
            except (httpx.HTTPError, httpx.StreamError):
                if attempt == 3:
                    raise
                await asyncio.sleep(2.0 * (attempt + 1))
    vals = grib.point_values(r.content, [("s", point[0], point[1])])
    u = next((v.value for v in vals if v.short_name == "10u"), None)
    v = next((v.value for v in vals if v.short_name == "10v"), None)
    return None if u is None or v is None else math.hypot(u, v)


async def run(region: str, start: date, end: date) -> Path:
    station, icao, lat, lon = STATIONS[region]
    cp = cache_path(region)
    cp.parent.mkdir(parents=True, exist_ok=True)
    done: dict[tuple[str, int], list[float | None]] = {}
    if cp.exists():
        for line in cp.read_text().splitlines():
            x = json.loads(line)
            done[(x["cycle"], x["lead"])] = x["speeds"]
    gate = asyncio.Semaphore(PARALLEL)
    limits = httpx.Limits(max_connections=PARALLEL + 4)
    async with httpx.AsyncClient(timeout=120, limits=limits, follow_redirects=True) as client:
        keep = cp.parent / f"asos_{station}_{CLIM_YEARS[0]}_{end.year}.csv"
        obs = await observations(client, station, CLIM_YEARS[0], end.year, keep)
        todo = []
        day = start
        while day <= end:
            cycle = datetime(day.year, day.month, day.day, 6 * (day.toordinal() % 4), tzinfo=UTC)
            todo += [(cycle, lead) for lead in LEADS if (cycle.isoformat(), lead) not in done]
            day += timedelta(days=1)

        async def case(cycle: datetime, lead: int) -> list[float | None]:
            return list(
                await asyncio.gather(
                    *(member_speed(client, gate, cycle, m, lead, (lat, lon)) for m in GEFS_MEMBERS)
                )
            )

        with cp.open("a") as cache:
            for b in range(0, len(todo), BATCH):
                part = todo[b : b + BATCH]
                got = await asyncio.gather(*(case(c, lead) for c, lead in part))
                for (cycle, lead), speeds in zip(part, got, strict=True):
                    done[(cycle.isoformat(), lead)] = speeds
                    cache.write(
                        json.dumps({"cycle": cycle.isoformat(), "lead": lead, "speeds": speeds})
                        + "\n"
                    )
                cache.flush()
                print(f"{part[-1][0]:%Y-%m-%d}: {len(done)} cases", file=sys.stderr)
    return write(region, start, end, done, obs)


def write(
    region: str,
    start: date,
    end: date,
    done: dict[tuple[str, int], list[float | None]],
    obs: dict[datetime, float],
) -> Path:
    station, icao, lat, lon = STATIONS[region]
    thr = threshold_m_s()
    ts = sorted(obs)
    # Month-by-hour frequency of the event in the station's record (the reference).
    clim_n: dict[tuple[int, int], int] = {}
    clim_k: dict[tuple[int, int], int] = {}
    for t, v in obs.items():
        if CLIM_YEARS[0] <= t.year <= CLIM_YEARS[1]:
            h = (t + timedelta(minutes=30)).replace(minute=0)
            key = (h.month, h.hour)
            clim_n[key] = clim_n.get(key, 0) + 1
            clim_k[key] = clim_k.get(key, 0) + (1 if v > thr else 0)
    rows: dict[int, list[tuple[float, float, float]]] = {lead: [] for lead in LEADS}
    for (cyc, lead), speeds in sorted(done.items()):
        cycle = datetime.fromisoformat(cyc)
        if not start <= cycle.date() <= end:
            continue
        good = [s for s in speeds if s is not None]
        if len(good) < len(GEFS_MEMBERS):
            continue  # a run with members missing is left out, and counted below
        valid = cycle + timedelta(hours=lead)
        o = nearest_obs(obs, ts, valid)
        n_ref = clim_n.get((valid.month, valid.hour), 0)
        if o is None or n_ref == 0:
            continue
        p = sum(1 for s in good if s > thr) / len(good)
        rows[lead].append(
            (p, 1.0 if o > thr else 0.0, clim_k.get((valid.month, valid.hour), 0) / n_ref)
        )
    skills: dict[int, float | None] = {}
    per_lead: dict[str, Any] = {}
    all_p: list[float] = []
    all_o: list[float] = []
    for lead, rs in rows.items():
        arr = np.array(rs, dtype=np.float64).reshape(-1, 3)
        fp, fo, ref = arr[:, 0], arr[:, 1], arr[:, 2]
        skills[lead] = vf.brier_skill(fp, fo, ref) if len(rs) else None
        per_lead[str(lead)] = {
            "cases": len(rs),
            "events": int(fo.sum()),
            "brier": vf.brier(fp, fo) if len(rs) else None,
            "brier_climatology": vf.brier(ref, fo) if len(rs) else None,
            "skill": skills[lead],
        }
        all_p += list(fp)
        all_o += list(fo)
    bins = vf.reliability(np.array(all_p), np.array(all_o))
    passed = vf.passes(skills, bins)
    runs_expected = ((end - start).days + 1) * len(LEADS)
    out = {
        "rule_id": RULE_ID,
        "region": region,
        "station": icao,
        "station_point": [lat, lon],
        "event": f"sustained wind at 10 m above {thr:.2f} m/s ({thr / 0.44704:.1f} mph)",
        "threshold_m_s": thr,
        "roughness_m": Z0_M,
        "period": f"{start.isoformat()}..{end.isoformat()}",
        "climatology_years": f"{CLIM_YEARS[0]}-{CLIM_YEARS[1]}",
        "runs_expected": runs_expected,
        "leads": per_lead,
        "reliability": [
            {
                "lo": b.lo,
                "hi": b.hi,
                "n": b.n,
                "mean_share": b.mean_p,
                "observed": b.freq,
                "counted": b.counted,
                "ok": b.ok,
            }
            for b in bins
        ],
        "passes": passed,
        "gate": f"Brier skill >= {vf.BSS_MIN} at each lead and reliability within "
        f"{vf.RELIABILITY_TOL} in bins with >= {vf.MIN_BIN_CASES} cases",
        "sources": {
            "forecasts": f"{BUCKET}/ (GEFS v12, pgrb2ap5, 10 m wind)",
            "observations": f"{IEM}?station={station}&data=sknt&report_type=3",
        },
        "built": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    dest = out_path(region)
    dest.write_text(json.dumps(out, indent=1))
    return dest


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", default="florida")
    ap.add_argument("--start", default="2025-01-01")
    ap.add_argument("--end", default="2025-12-31")
    a = ap.parse_args()
    p = asyncio.run(run(a.region, date.fromisoformat(a.start), date.fromisoformat(a.end)))
    print(p)
    print(json.dumps(json.loads(p.read_text())["leads"], indent=1))


if __name__ == "__main__":
    main()
