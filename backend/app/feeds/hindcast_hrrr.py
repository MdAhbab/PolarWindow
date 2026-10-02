"""HRRR's one forecast against the pads' weather stations (T4, Verification).

Run: ``make hindcast-hrrr`` (``uv run python -m app.feeds.hindcast_hrrr``).
The launch weather shows HRRR (3 km, one run) as a single "over" or "under" at the
rule's limit. Nothing said how good that call is, so this reads HRRR's archive on
AWS (``noaa-hrrr-bdp-pds``, keyless), version 4 (December 2020 on, the one the live
feed reads), for the 00 and 12 UTC runs on every ``--stride``-th day of 2021-2025
(by default every second day: 1,826 runs, about 35 minutes for a fresh cache) at the
leads the feed keeps (1, 6, 12, 18 h): the 10 m wind at the grid point nearest
each pad's weather station (Cape Canaveral Skid Strip ASOS KXMR, Vandenberg ASOS KVBG),
read as two bytes of the message (``parsers.grib_ranges``, equal to ecCodes) after the
message's index says where it starts. Each file is cached as it arrives, in a fixed
random order, and a run stopped at any time is resumed by running again.

Scored against the station's sustained wind in the report nearest the valid time (within
30 minutes): the bias and the mean absolute error, and their skill against the station's own
month-by-hour record over 2000-2019, twice: against the typical (median) wind of that month and
hour used as a forecast, and against the whole range of what has happened then (the CRPS of a
single forecast is its absolute error, so the second is the skill number the GEFS check gives,
and a harder bar for one forecast to clear); and the over/under call at the
Falcon 9 limit brought to 10 m (``app.feeds.hindcast``): how many hours above it HRRR called
and how many of its calls were right, with the Brier skill of the call where 10 or more
cases were above the limit. Every skill has a 95 % interval from resampling whole months
of cases. The 162 ft wind the rule names is HRRR's 10 m and 80 m winds on a logarithmic
profile and no public station measures it, so the 10 m wind is what is checked.
Writes ``data/hindcast/hrrr_wind_{region}.json``.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import math
import signal
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
from app.feeds import hindcast_reforecast as hr
from app.feeds import http as feed_http
from app.feeds.adapters import nomads
from app.feeds.parsers import grib_ranges as gr

BUCKET = "https://noaa-hrrr-bdp-pds.s3.amazonaws.com"
LEADS = nomads.HRRR_LEADS_H
INITS = (0, 12)
YEARS = (2021, 2025)
CLIM_YEARS = (2000, 2019)
STRIDE = 2
STATIONS = hr.STATIONS
PARALLEL = 16
AT_ONCE = 6
SYSTEM = "HRRR v4 (NOAA NCEP), 00 and 12 UTC runs, 3 km"


def cache_path() -> Path:
    return get_settings().data_dir / "hindcast" / "hrrr_wind.cache.jsonl"


def out_path(region: str) -> Path:
    return get_settings().data_dir / "hindcast" / f"hrrr_wind_{region}.json"


def file_url(day: date, hour: int, lead: int) -> str:
    return f"{BUCKET}/hrrr.{day:%Y%m%d}/conus/hrrr.t{hour:02d}z.wrfsfcf{lead:02d}.grib2"


def wind_ranges(idx: str, lead: int) -> dict[str, tuple[int, int]]:
    """Byte range of the 10 m U and V wind messages at ``lead``, from a file's index."""
    rows = [x.split(":") for x in idx.strip().splitlines()]
    out: dict[str, tuple[int, int]] = {}
    for i, r in enumerate(rows):
        if len(r) < 6 or r[3] not in ("UGRD", "VGRD") or r[4] != "10 m above ground":
            continue
        if r[5] != f"{lead} hour fcst":
            continue
        end = int(rows[i + 1][1]) - 1 if i + 1 < len(rows) else -1
        out[r[3]] = (int(r[1]), end)
    return out


def plan(stride: int, first: int, last: int, seed: int = 0) -> list[tuple[date, int]]:
    """(day, run hour) for every ``stride``-th day of the years, in a fixed random order."""
    out: list[tuple[date, int]] = []
    d = date(first, 1, 1)
    while d.year <= last:
        if d.toordinal() % stride == 0:
            out += [(d, h) for h in INITS]
        d += timedelta(days=1)
    order = np.random.default_rng(seed).permutation(len(out))
    return [out[int(i)] for i in order]


def key(day: date, hour: int) -> str:
    return f"{day.isoformat()}T{hour:02d}"


class Reader(hr.Fetcher):
    """Byte ranges of HRRR's archive files (retries and the gate on requests are the parent's)."""

    async def message(self, url: str, rng: tuple[int, int]) -> list[float]:
        """The message's value at each station's nearest grid point."""
        a, _ = rng
        head = await self.get(url, a, a + gr.HEAD - 1)
        if head is None:
            raise gr.RangeError("message not found")
        lay = gr.layout(head)
        ks = [lay.grid.nearest(lat, lon) for _, _, lat, lon in STATIONS.values()]
        spans = [lay.span(k) for k in ks]
        chunks = await asyncio.gather(*(self.get(url, a + s0, a + s1) for s0, s1 in spans))
        if any(c is None for c in chunks):
            raise gr.RangeError("value not found")
        return [lay.value(c, k) for c, k in zip(chunks, ks, strict=True) if c is not None]

    async def one(self, day: date, hour: int, lead: int) -> dict[str, float] | None:
        """10 m wind speed at each station for one run and lead; None when the file is not there."""
        url = file_url(day, hour, lead)
        idx = await self.get(url + ".idx")
        if idx is None:
            return None
        rng = wind_ranges(idx.decode(), lead)
        if set(rng) != {"UGRD", "VGRD"}:
            return None
        u, v = await asyncio.gather(self.message(url, rng["UGRD"]), self.message(url, rng["VGRD"]))
        return {region: math.hypot(u[i], v[i]) for i, region in enumerate(STATIONS)}

    async def run(self, day: date, hour: int) -> dict[str, Any]:
        res = await asyncio.gather(*(self.one(day, hour, ld) for ld in LEADS))
        return {
            "init": key(day, hour),
            "speeds": {str(ld): r for ld, r in zip(LEADS, res, strict=True)},
        }


def read_cache() -> dict[str, dict[str, Any]]:
    return hr.read_cache(cache_path())


async def fetch(
    stride: int, first: int, last: int, hours: float, parallel: int, workers: int
) -> None:
    done = read_cache()
    todo = [(d, h) for d, h in plan(stride, first, last) if key(d, h) not in done]
    print(f"{len(done)} runs cached, {len(todo)} to fetch", file=sys.stderr)
    stop = time.monotonic() + hours * 3600.0
    cp = cache_path()
    cp.parent.mkdir(parents=True, exist_ok=True)
    timeout = httpx.Timeout(connect=20.0, read=90.0, write=30.0, pool=None)
    queue: asyncio.Queue[tuple[date, int]] = asyncio.Queue()
    for x in todo:
        queue.put_nowait(x)
    async with httpx.AsyncClient(
        timeout=timeout,
        limits=httpx.Limits(max_connections=parallel + 2),
        follow_redirects=True,
        headers={"User-Agent": feed_http.user_agent()},
    ) as client:
        f = Reader(client, parallel)
        t0 = time.monotonic()
        got = 0
        failed = 0
        with cp.open("a") as cache:

            async def worker() -> None:
                nonlocal got, failed
                while time.monotonic() < stop:
                    try:
                        d, h = queue.get_nowait()
                    except asyncio.QueueEmpty:
                        return
                    try:
                        r = await f.run(d, h)
                    except (httpx.HTTPError, httpx.StreamError) as exc:
                        failed += 1
                        print(
                            f"{key(d, h)}: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True
                        )
                        queue.put_nowait((d, h))
                        await asyncio.sleep(min(300.0, 20.0 * failed))
                        continue
                    except Exception as exc:  # a run that cannot be read: left for another
                        print(
                            f"{key(d, h)}: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True
                        )
                        continue
                    failed = 0
                    cache.write(json.dumps(r) + "\n")
                    cache.flush()
                    got += 1
                    if got % 20 == 0:
                        print(
                            f"{key(d, h)}: {got}/{len(todo)} runs, {f.bytes / 1e6:.1f} MB, "
                            f"{(time.monotonic() - t0) / got:.1f} s a run",
                            file=sys.stderr,
                            flush=True,
                        )

            tasks = [asyncio.ensure_future(worker()) for _ in range(workers)]
            loop = asyncio.get_running_loop()
            for sig in (signal.SIGINT, signal.SIGTERM):
                with contextlib.suppress(NotImplementedError):
                    loop.add_signal_handler(sig, lambda: [t.cancel() for t in tasks])
            with contextlib.suppress(asyncio.CancelledError):
                await asyncio.gather(*tasks)


async def observations(region: str, years: tuple[int, int]) -> dict[datetime, float]:
    station = STATIONS[region][0]
    keep = cache_path().parent / f"asos_{station}_{years[0]}_{years[1]}.csv"
    async with httpx.AsyncClient(timeout=600, follow_redirects=True) as client:
        return await hc.observations(client, station, years[0], years[1], keep)


def _skill(score_: vf.FloatArray, ref: vf.FloatArray) -> float | None:
    return None if ref.size == 0 or ref.mean() <= 0 else float(1.0 - score_.mean() / ref.mean())


def _call(
    call: vf.FloatArray, seen: vf.FloatArray, rp: vf.FloatArray, month: list[int]
) -> dict[str, Any]:
    """How the over/under call did: the cases where it and the station were above the limit."""
    n = int(call.size)
    hits = int(np.sum((call == 1) & (seen == 1)))
    misses = int(np.sum((call == 0) & (seen == 1)))
    false_alarms = int(np.sum((call == 1) & (seen == 0)))
    events = hits + misses
    bs, bs_ref = (call - seen) ** 2, (rp - seen) ** 2
    skill = vf.brier_skill(call, seen, rp) if events >= vf.MIN_EVENTS else None
    return {
        "cases": n,
        "events": events,
        "called_over": hits + false_alarms,
        "hits": hits,
        "misses": misses,
        "false_alarms": false_alarms,
        "brier": float(bs.mean()) if n else None,
        "brier_climatology": float(bs_ref.mean()) if n else None,
        "skill": skill,
        "skill_95": vf.skill_interval(bs, bs_ref, blocks=month) if skill is not None else None,
        "skill_note": None
        if skill is not None
        else f"not worked out: {events} of {n} cases above the limit, "
        f"fewer than the {vf.MIN_EVENTS} it takes",
    }


def climatology(obs: dict[datetime, float]) -> dict[tuple[int, int], vf.FloatArray]:
    """The station's own record per month and hour over 2000-2019 (each report to its hour)."""
    clim: dict[tuple[int, int], list[float]] = {}
    for t, v in obs.items():
        if CLIM_YEARS[0] <= t.year <= CLIM_YEARS[1]:
            h = (t + timedelta(minutes=30)).replace(minute=0)
            clim.setdefault((h.month, h.hour), []).append(v)
    return {k: np.array(v) for k, v in clim.items()}


def score(
    region: str,
    cache: dict[str, dict[str, Any]],
    obs: dict[datetime, float],
    record: dict[datetime, float],
) -> Path:
    """Write ``hrrr_wind_{region}.json``: ``obs`` are the reports of the years forecast,
    ``record`` the station's long record the reference is made from."""
    station, icao, lat, lon = STATIONS[region]
    thr = hc.threshold_m_s()
    ts = sorted(obs)
    clim = climatology(record)
    spread = {k: vf.spread_term(v) for k, v in clim.items()}
    typical = {k: float(np.median(v)) for k, v in clim.items()}
    per_lead: dict[str, Any] = {}
    years: set[int] = set()
    all_call: list[float] = []
    all_seen: list[float] = []
    all_rp: list[float] = []
    all_month: list[int] = []
    for lead in LEADS:
        xs: list[float] = []
        ys: list[float] = []
        rp: list[float] = []
        rc: list[float] = []
        rm: list[float] = []
        month: list[int] = []
        for init, rec in sorted(cache.items()):
            sp = (rec["speeds"].get(str(lead)) or {}).get(region)
            if sp is None:
                continue
            t0 = datetime.strptime(init, "%Y-%m-%dT%H").replace(tzinfo=UTC)
            valid = t0 + timedelta(hours=lead)
            o = hc.nearest_obs(obs, ts, valid)
            k = (valid.month, valid.hour)
            if o is None or k not in clim:
                continue
            xs.append(sp)
            ys.append(o)
            c = clim[k]
            rp.append(float(np.mean(c > thr)))
            rc.append(vf.crps_sample(c, o, spread[k]))
            rm.append(abs(typical[k] - o))
            month.append(valid.year * 12 + valid.month)
            years.add(t0.year)
        x, y = np.array(xs), np.array(ys)
        n = len(ys)
        err = x - y
        call = (x > thr).astype(np.float64)
        seen = (y > thr).astype(np.float64)
        all_call += list(call)
        all_seen += list(seen)
        all_rp += rp
        all_month += month
        ae, rcs, rms = np.abs(err), np.array(rc), np.array(rm)
        per_lead[str(lead)] = {
            "cases": n,
            "bias_m_s": float(err.mean()) if n else None,
            "rmse_m_s": float(np.sqrt(np.mean(err**2))) if n else None,
            "mae_m_s": float(ae.mean()) if n else None,
            "mae_climatology_m_s": float(rms.mean()) if n else None,
            "mae_skill": _skill(ae, rms),
            "mae_skill_95": vf.skill_interval(ae, rms, blocks=month) if n else None,
            "crps_climatology_m_s": float(rcs.mean()) if n else None,
            "crps_skill": _skill(ae, rcs),
            "crps_skill_95": vf.skill_interval(ae, rcs, blocks=month) if n else None,
            "mean_forecast_m_s": float(x.mean()) if n else None,
            "mean_observed_m_s": float(y.mean()) if n else None,
            **_call(call, seen, np.array(rp), month),
        }
    runs = sorted(cache)
    pooled = _call(np.array(all_call), np.array(all_seen), np.array(all_rp), all_month)
    out = {
        "rule_id": hc.RULE_ID,
        "region": region,
        "station": icao,
        "station_point": [lat, lon],
        "system": SYSTEM,
        "event": f"sustained wind at 10 m above {thr:.2f} m/s ({thr / 0.44704:.1f} mph)",
        "threshold_m_s": thr,
        "roughness_m": hc.Z0_M,
        "period": f"{runs[0][:10]}..{runs[-1][:10]}" if runs else None,
        "years": sorted(years),
        "runs_fetched": len(cache),
        "climatology_years": f"{CLIM_YEARS[0]}-{CLIM_YEARS[1]}",
        "intervals": "95 % from resampling whole months of cases",
        "leads": per_lead,
        "call_all_leads": pooled,
        "sources": {
            "forecasts": f"{BUCKET}/ (10 m UGRD, VGRD in the wrfsfc files)",
            "observations": f"{hc.IEM}?station={station}&data=sknt&report_type=3",
        },
        "built": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    p = out_path(region)
    p.write_text(json.dumps(out, indent=1) + "\n")
    return p


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stride", type=int, default=STRIDE, help="every this-many-th day")
    ap.add_argument("--first", type=int, default=YEARS[0])
    ap.add_argument("--last", type=int, default=YEARS[1])
    ap.add_argument("--hours", type=float, default=2.0, help="stop fetching after this long")
    ap.add_argument("--parallel", type=int, default=PARALLEL, help="requests in flight")
    ap.add_argument("--workers", type=int, default=AT_ONCE, help="runs worked on at once")
    ap.add_argument("--score-only", action="store_true")
    a = ap.parse_args()
    if not a.score_only:
        asyncio.run(fetch(a.stride, a.first, a.last, a.hours, a.parallel, a.workers))
    cache = read_cache()
    if not cache:
        raise SystemExit(
            "No raw HRRR cache found; existing validation reports kept. "
            "Run without --score-only to fetch the archive first."
        )
    for region in STATIONS:
        obs = asyncio.run(observations(region, (a.first, a.last)))
        record = asyncio.run(observations(region, CLIM_YEARS))
        p = score(region, cache, obs, record)
        d = json.loads(p.read_text())
        print(p, d["period"], d["runs_fetched"], "runs")
        print(json.dumps(d["leads"], indent=1))


if __name__ == "__main__":
    main()
