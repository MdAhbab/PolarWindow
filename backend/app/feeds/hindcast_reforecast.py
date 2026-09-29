"""GEFS wind shares over many years, from NOAA's GEFSv12 reforecast (T4, Verification).

Run: ``make hindcast-reforecast`` (``uv run python -m app.feeds.hindcast_reforecast``).
The one-year check (``app.feeds.hindcast``) could not say anything about a
limit the Cape's station reached once in 682 verified runs, so this one reads
the GEFSv12 reforecast NOAA ran with the operational model over 2000-2019
(``noaa-gefs-retrospective`` on AWS, keyless): its 00 UTC run each day, five
runs (the control and four perturbed; the operational forecast has 31), 10 m
wind at 24 and 48 hours. Each field is one global message; only its first
part, down to the pads' latitude, is fetched (``parsers.grib_prefix``), about
40 % of it. Days are taken every ``--stride`` days, the latest years first,
and the next pass fills the days between, so a stopped run still covers as
many years as it reached. Each day is cached as it arrives.

The check itself is the one ``app.feeds.hindcast`` makes, at both pads' weather
stations (Cape Canaveral Skid Strip ASOS KXMR, Vandenberg ASOS KVBG, from the
Iowa Environmental Mesonet): the Falcon 9 limit brought down to 10 m, the
share of runs above it against whether the station's report nearest the valid
time was, scored against the station's own month-by-hour frequency over the
same years. The CRPS of the runs' wind against the measured wind, against the
same station climatology, is added as a skill number that needs no event.
Writes ``data/hindcast/gefs_reforecast_wind_{region}.json``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import numpy as np

from app.config import get_settings
from app.core import verification as vf
from app.feeds import hindcast as hc
from app.feeds.parsers import grib_prefix as gp

BUCKET = "https://noaa-gefs-retrospective.s3.amazonaws.com"
MEMBERS = ("c00", "p01", "p02", "p03", "p04")
LEADS = (24, 48)
YEARS = (2000, 2019)
STATIONS = {
    "florida": ("XMR", "KXMR", 28.4677, -80.5668),
    "vandenberg": ("VBG", "KVBG", 34.7297, -120.5768),
}
#: Requests in flight at once, and days fetched together.
PARALLEL = 8
DAYS_AT_ONCE = 2
#: First guess of the share of a message needed (it is about 0.40 at the Cape).
GUESS = 0.42


def cache_path() -> Path:
    return get_settings().data_dir / "hindcast" / "gefs_reforecast_wind.cache.jsonl"


def out_path(region: str) -> Path:
    return get_settings().data_dir / "hindcast" / f"gefs_reforecast_wind_{region}.json"


def file_url(day: date, member: str, var: str) -> str:
    stamp = f"{day:%Y%m%d}00"
    return (
        f"{BUCKET}/GEFSv12/reforecast/{day.year}/{stamp}/{member}/Days:1-10/"
        f"{var}_hgt_{stamp}_{member}.grib2"
    )


def lead_ranges(idx: str, var: str) -> dict[int, tuple[int, int]]:
    """Byte range of the 10 m message at each lead, from a reforecast file's index."""
    rows = [x.split(":") for x in idx.strip().splitlines()]
    out: dict[int, tuple[int, int]] = {}
    for i, r in enumerate(rows):
        if len(r) < 6 or r[3] != var.upper() or r[4] != "10 m above ground":
            continue
        lead = r[5].split()
        if len(lead) == 3 and lead[1:] == ["hour", "fcst"] and int(lead[0]) in LEADS:
            end = int(rows[i + 1][1]) - 1 if i + 1 < len(rows) else -1
            out[int(lead[0])] = (int(r[1]), end)
    return out


def plan(stride: int, first: int, last: int) -> list[date]:
    """Every ``stride``-th day, latest year first; then the days between, pass by pass."""
    out = []
    for phase in range(stride):
        for year in range(last, first - 1, -1):
            d = date(year, 1, 1)
            while d.year == year:
                if d.toordinal() % stride == phase:
                    out.append(d)
                d += timedelta(days=1)
    return out


class Fetcher:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client
        self.gate = asyncio.Semaphore(PARALLEL)
        self.bytes = 0

    async def get(self, url: str, a: int | None = None, b: int | None = None) -> bytes | None:
        headers = {} if a is None else {"Range": f"bytes={a}-{'' if b is None or b < 0 else b}"}
        async with self.gate:
            for attempt in range(6):
                try:
                    r = await self.client.get(url, headers=headers)
                    if r.status_code == 404:
                        return None
                    if r.status_code in (429, 500, 502, 503, 504):
                        raise httpx.HTTPStatusError("busy", request=r.request, response=r)
                    r.raise_for_status()
                    self.bytes += len(r.content)
                    return r.content
                except (httpx.HTTPError, httpx.StreamError):
                    if attempt == 5:
                        raise
                    await asyncio.sleep(3.0 * (attempt + 1))
        return None

    async def values(
        self, url: str, rng: tuple[int, int], where: list[tuple[float, float]]
    ) -> list[float]:
        """Bilinear values at ``where`` from the prefix of one message."""
        a, b = rng
        length = (b - a + 1) if b >= 0 else 1_000_000
        head = await self.get(url, a, a + int(length * GUESS))
        if head is None:
            raise gp.PrefixError("message not found")
        lay = gp.layout(head)
        k = gp.prefix_points(where, lay)
        if len(head) < lay.meta_end:
            more = await self.get(url, a + len(head), a + lay.meta_end - 1)
            head += more or b""
        need = gp.bytes_needed(lay, head, k)
        if len(head) < need:
            more = await self.get(url, a + len(head), a + need - 1)
            head += more or b""
        return gp.points(head, where)

    async def day(self, d: date) -> dict[str, Any]:
        where = [(lat, lon) for _, _, lat, lon in STATIONS.values()]

        async def one(member: str, var: str) -> dict[int, list[float]] | None:
            url = file_url(d, member, var)
            idx = await self.get(url + ".idx")
            if idx is None:
                return None
            rngs = lead_ranges(idx.decode(), var)
            if set(rngs) != set(LEADS):
                return None
            got = await asyncio.gather(*(self.values(url, rngs[ld], where) for ld in LEADS))
            return dict(zip(LEADS, got, strict=True))

        jobs = [(m, v) for m in MEMBERS for v in ("ugrd", "vgrd")]
        res = await asyncio.gather(*(one(m, v) for m, v in jobs))
        got = dict(zip(jobs, res, strict=True))
        speeds: dict[str, dict[str, list[float | None]]] = {}
        for ri, region in enumerate(STATIONS):
            speeds[region] = {}
            for lead in LEADS:
                row: list[float | None] = []
                for m in MEMBERS:
                    u, v = got[(m, "ugrd")], got[(m, "vgrd")]
                    row.append(
                        None if u is None or v is None else math.hypot(u[lead][ri], v[lead][ri])
                    )
                speeds[region][str(lead)] = row
        return {"init": d.isoformat(), "speeds": speeds}


def read_cache() -> dict[str, dict[str, Any]]:
    p = cache_path()
    out: dict[str, dict[str, Any]] = {}
    if p.exists():
        for line in p.read_text().splitlines():
            try:
                x = json.loads(line)
            except json.JSONDecodeError:
                continue  # a line cut short when a run was stopped
            out[x["init"]] = x
    return out


async def fetch(stride: int, first: int, last: int, hours: float) -> None:
    done = read_cache()
    todo = [d for d in plan(stride, first, last) if d.isoformat() not in done]
    print(f"{len(done)} days cached, {len(todo)} to fetch", file=sys.stderr)
    stop = time.monotonic() + hours * 3600.0
    cp = cache_path()
    cp.parent.mkdir(parents=True, exist_ok=True)
    limits = httpx.Limits(max_connections=PARALLEL + 2)
    async with httpx.AsyncClient(timeout=180, limits=limits, follow_redirects=True) as client:
        f = Fetcher(client)
        t0 = time.monotonic()
        with cp.open("a") as cache:
            for i in range(0, len(todo), DAYS_AT_ONCE):
                if time.monotonic() > stop:
                    break
                part = todo[i : i + DAYS_AT_ONCE]
                res = await asyncio.gather(*(f.day(d) for d in part), return_exceptions=True)
                for d, r in zip(part, res, strict=True):
                    if isinstance(r, BaseException):
                        print(f"{d}: {type(r).__name__}: {r}", file=sys.stderr)
                        continue
                    cache.write(json.dumps(r) + "\n")
                cache.flush()
                el = time.monotonic() - t0
                print(
                    f"{part[-1]}: {i + len(part)}/{len(todo)} days, "
                    f"{f.bytes / 1e6:.0f} MB, {f.bytes / 1e3 / max(el, 1):.0f} kB/s",
                    file=sys.stderr,
                )


async def observations(region: str) -> dict[datetime, float]:
    station = STATIONS[region][0]
    keep = cache_path().parent / f"asos_{station}_{YEARS[0]}_{YEARS[1]}.csv"
    async with httpx.AsyncClient(timeout=600, follow_redirects=True) as client:
        return await hc.observations(client, station, YEARS[0], YEARS[1], keep)


def _rel(bins: list[vf.Bin]) -> list[dict[str, Any]]:
    return [
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
    ]


def score(region: str, cache: dict[str, dict[str, Any]], obs: dict[datetime, float]) -> Path:
    station, icao, lat, lon = STATIONS[region]
    thr = hc.threshold_m_s()
    ts = sorted(obs)
    # The station's own record over the same years, per month and hour: how often the
    # limit was passed (the Brier reference) and every measured speed (the CRPS reference).
    clim: dict[tuple[int, int], list[float]] = {}
    for t, v in obs.items():
        if YEARS[0] <= t.year <= YEARS[1]:
            h = (t + timedelta(minutes=30)).replace(minute=0)
            clim.setdefault((h.month, h.hour), []).append(v)
    clim_arr = {k: np.array(v) for k, v in clim.items()}
    spread = {k: vf.spread_term(v) for k, v in clim_arr.items()}
    per_lead: dict[str, Any] = {}
    skills: dict[int, float | None] = {}
    all_p: list[float] = []
    all_o: list[float] = []
    years: set[int] = set()
    inits = 0
    for lead in LEADS:
        xs: list[list[float]] = []
        ys: list[float] = []
        refp: list[float] = []
        refc: list[float] = []
        for init, rec in sorted(cache.items()):
            row = rec["speeds"][region][str(lead)]
            if any(s is None for s in row):
                continue
            t0 = datetime.fromisoformat(init).replace(tzinfo=UTC)
            valid = t0 + timedelta(hours=lead)
            o = hc.nearest_obs(obs, ts, valid)
            key = (valid.month, valid.hour)
            if o is None or key not in clim_arr:
                continue
            xs.append([float(s) for s in row])
            ys.append(o)
            c = clim_arr[key]
            refp.append(float(np.mean(c > thr)))
            refc.append(vf.crps_sample(c, o, spread[key]))
            years.add(t0.year)
        inits = max(inits, len(ys))
        x = np.array(xs, dtype=np.float64).reshape(-1, len(MEMBERS))
        y = np.array(ys, dtype=np.float64)
        p = np.mean(x > thr, axis=1) if len(ys) else np.zeros(0)
        o_ev = (y > thr).astype(np.float64)
        rp = np.array(refp)
        rc = np.array(refc)
        n = len(ys)
        skills[lead] = vf.brier_skill(p, o_ev, rp) if n else None
        bs = (p - o_ev) ** 2
        bs_ref = (rp - o_ev) ** 2
        crps = vf.crps_ensemble(x, y) if n else np.zeros(0)
        crps_fair = vf.crps_ensemble(x, y, fair=True) if n else np.zeros(0)

        def sk(a: vf.FloatArray, b: vf.FloatArray) -> float | None:
            return (
                None if not len(a) or float(np.mean(b)) == 0.0 else float(1 - a.mean() / b.mean())
            )

        per_lead[str(lead)] = {
            "cases": n,
            "events": int(o_ev.sum()),
            "brier": float(bs.mean()) if n else None,
            "brier_climatology": float(bs_ref.mean()) if n else None,
            "skill": skills[lead],
            "skill_95": vf.skill_interval(bs, bs_ref) if n else None,
            "crps_m_s": float(crps.mean()) if n else None,
            "crps_fair_m_s": float(crps_fair.mean()) if n else None,
            "crps_climatology_m_s": float(rc.mean()) if n else None,
            "crps_skill": sk(crps, rc),
            "crps_skill_95": vf.skill_interval(crps, rc) if n else None,
            "crps_skill_fair": sk(crps_fair, rc),
            "mean_forecast_m_s": float(x.mean()) if n else None,
            "mean_observed_m_s": float(y.mean()) if n else None,
        }
        all_p += list(p)
        all_o += list(o_ev)
    bins = vf.reliability(np.array(all_p), np.array(all_o))
    cases = sorted(cache)
    out = {
        "rule_id": hc.RULE_ID,
        "region": region,
        "station": icao,
        "station_point": [lat, lon],
        "system": "GEFSv12 reforecast (NOAA PSL/EMC), 00 UTC runs, control and 4 perturbed "
        "runs, 0.25 degree",
        "runs": len(MEMBERS),
        "event": f"sustained wind at 10 m above {thr:.2f} m/s ({thr / 0.44704:.1f} mph)",
        "threshold_m_s": thr,
        "roughness_m": hc.Z0_M,
        "period": f"{cases[0]}..{cases[-1]}" if cases else None,
        "years": sorted(years),
        "days_fetched": len(cache),
        "climatology_years": f"{YEARS[0]}-{YEARS[1]}",
        "leads": per_lead,
        "reliability": _rel(bins),
        "passes": vf.passes(skills, bins),
        "gate": f"Brier skill >= {vf.BSS_MIN} at each lead and reliability within "
        f"{vf.RELIABILITY_TOL} in bins with >= {vf.MIN_BIN_CASES} cases",
        "sources": {
            "forecasts": f"{BUCKET}/GEFSv12/reforecast/ (10 m UGRD, VGRD)",
            "observations": f"{hc.IEM}?station={station}&data=sknt&report_type=3",
        },
        "built": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    dest = out_path(region)
    dest.write_text(json.dumps(out, indent=1))
    return dest


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stride", type=int, default=3)
    ap.add_argument("--first", type=int, default=YEARS[0])
    ap.add_argument("--last", type=int, default=YEARS[1])
    ap.add_argument("--hours", type=float, default=24.0, help="stop fetching after this long")
    ap.add_argument("--score-only", action="store_true")
    a = ap.parse_args()
    if not a.score_only:
        asyncio.run(fetch(a.stride, a.first, a.last, a.hours))
    cache = read_cache()
    for region in STATIONS:
        obs = asyncio.run(observations(region))
        p = score(region, cache, obs)
        d = json.loads(p.read_text())
        print(p, d["period"], "passes" if d["passes"] else "does not pass")
        print(json.dumps(d["leads"], indent=1))


if __name__ == "__main__":
    main()
