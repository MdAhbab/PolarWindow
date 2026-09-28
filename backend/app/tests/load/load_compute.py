"""Load test of the compute queue: every section of every mission asked for at once.

``make load-compute`` (``WORKERS=2`` by default). The make target first builds
``polar_window_load`` (the migrations and the seeded rows, like the test
database), so nothing here touches the database the running app serves. This
script then starts the API on :8011 and WORKERS compute workers against it,
asks for the trip, contact and launch sections of every mission in one burst
(plus extra contact and launch windows, so the queue holds more than the
defaults), waits for the queue to empty and reports, from the jobs table:

- the burst: how long the API took to answer each request (it only queues);
- per job: the wait in the queue (claimed - created) and the run (finished -
  claimed), by kind;
- the queue as a whole: time to empty, jobs per minute, and the workers'
  busy share (sum of runs / (workers x time to empty));
- the same burst again: every answer stored, so every request is a 200.

Writes ``data/load/compute_queue.json`` and prints a table for docs/test-plan.md.
"""

# ruff: noqa: S603 -- starts this project's own API and worker by module name.
from __future__ import annotations

import asyncio
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import get_settings

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "data" / "load" / "compute_queue.json"
PORT = int(os.environ.get("LOAD_PORT", "8011"))
API = f"http://127.0.0.1:{PORT}/api/v1"
WORKERS = int(os.environ.get("WORKERS", "2"))
DB_NAME = os.environ.get("PW_TEST_DB_NAME", "polar_window_load")
TIMEOUT_S = float(os.environ.get("LOAD_TIMEOUT_S", "2400"))
#: Extra windows per mission, so the burst is more than one job per section.
EXTRA_CONTACT = int(os.environ.get("LOAD_EXTRA_CONTACT", "6"))
EXTRA_LAUNCH = int(os.environ.get("LOAD_EXTRA_LAUNCH", "12"))


def _urls() -> tuple[str, str]:
    s = get_settings()
    dev = urlsplit(s.database_url).path.lstrip("/")
    if dev == DB_NAME:
        sys.exit("refusing: the load database is the development one")
    db = s.database_url.replace(f"/{dev}", f"/{DB_NAME}", 1)
    redis = s.redis_url.rsplit("/", 1)[0] + "/2"
    return db, redis


def _pct(xs: list[float], p: float) -> float | None:
    if not xs:
        return None
    ys = sorted(xs)
    k = (len(ys) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(ys) - 1)
    return round(ys[lo] + (ys[hi] - ys[lo]) * (k - lo), 2)


def _stats(xs: list[float]) -> dict[str, Any]:
    return {
        "n": len(xs),
        "p50": _pct(xs, 0.5),
        "p95": _pct(xs, 0.95),
        "max": round(max(xs), 2) if xs else None,
        "mean": round(statistics.fmean(xs), 2) if xs else None,
    }


async def _requests(c: httpx.AsyncClient) -> list[str]:
    """Every section of every mission, plus extra windows."""
    missions = (await c.get(f"{API}/missions", params={"limit": 200})).json()["items"]
    paths: list[str] = []
    today = datetime.now(UTC).date()
    for m in missions:
        mid = m["id"]
        paths += [f"/missions/{mid}/trip", f"/missions/{mid}/contact", f"/missions/{mid}/launch"]
        landing = (m.get("landing") or {}).get("date")
        if landing and m.get("status") != "lost_before_landing":
            d0 = date.fromisoformat(landing[:10])
            for k in range(1, EXTRA_CONTACT + 1):
                s = datetime(d0.year, d0.month, d0.day, tzinfo=UTC) + timedelta(days=k)
                e = s + timedelta(days=10)
                paths.append(
                    f"/missions/{mid}/contact?start={s:%Y-%m-%dT%H:%M:%SZ}"
                    f"&end={e:%Y-%m-%dT%H:%M:%SZ}"
                )
        if m.get("status") == "planned" and m.get("launch"):
            for k in range(1, EXTRA_LAUNCH + 1):
                f = today + timedelta(days=7 * k)
                paths.append(f"/missions/{mid}/launch?from={f}&to={f + timedelta(days=60)}")
    return paths


async def _burst(c: httpx.AsyncClient, paths: list[str]) -> list[dict[str, Any]]:
    async def one(p: str) -> dict[str, Any]:
        t = time.perf_counter()
        r = await c.get(f"{API}{p}")
        ms = (time.perf_counter() - t) * 1000
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        job = body.get("job_id") if r.status_code == 202 else None
        return {"path": p, "status": r.status_code, "ms": round(ms, 1), "job_id": job}

    return list(await asyncio.gather(*(one(p) for p in paths)))


async def _wait_empty(engine: Any, t0: float) -> list[dict[str, Any]]:
    """Poll until no job is queued or running; the queue length every 5 s."""
    trace = []
    while True:
        async with engine.connect() as cx:
            rows = (
                await cx.execute(text("SELECT status, count(*) FROM jobs GROUP BY status"))
            ).all()
        by = dict(rows)
        trace.append(
            {
                "t_s": round(time.perf_counter() - t0, 1),
                "queued": by.get("queued", 0),
                "running": by.get("running", 0),
            }
        )
        if not by.get("queued") and not by.get("running"):
            return trace
        if time.perf_counter() - t0 > TIMEOUT_S:
            raise TimeoutError(f"queue not empty after {TIMEOUT_S:.0f} s: {by}")
        await asyncio.sleep(5)


def _spawn(env: dict[str, str]) -> tuple[list[subprocess.Popen[bytes]], Path]:
    """The API on PORT and WORKERS compute workers, each worker logging to a file."""
    logs = Path(tempfile.mkdtemp(prefix="load-compute-"))
    procs = [
        subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORT)],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    ]
    for i in range(WORKERS):
        with (logs / f"worker-{i}.log").open("wb") as f:
            procs.append(
                subprocess.Popen(
                    [sys.executable, "-m", "app.workers.compute"],
                    env=env,
                    stdout=f,
                    stderr=subprocess.STDOUT,
                )
            )
    return procs, logs


async def main() -> None:
    db_url, redis_url = _urls()
    env = {
        **os.environ,
        "PW_DATABASE_URL": db_url,
        "PW_REDIS_URL": redis_url,
        "PW_RATE_LIMITS": "off",
    }
    engine = create_async_engine(db_url)
    async with engine.begin() as cx:
        await cx.execute(text("TRUNCATE jobs, assessments RESTART IDENTITY CASCADE"))
    procs, logs = _spawn(env)
    try:
        async with httpx.AsyncClient(timeout=120) as c:
            for _ in range(120):
                try:
                    await c.get(f"{API}/healthz")
                    break
                except httpx.TransportError:
                    await asyncio.sleep(1)
            # Workers are running before the burst, as they are in service:
            # wait until each has loaded SPICE and is listening for jobs.
            for _ in range(240):
                ready = [
                    b"compute worker" in (logs / f"worker-{i}.log").read_bytes()
                    for i in range(WORKERS)
                ]
                if all(ready):
                    break
                await asyncio.sleep(0.5)
            else:
                raise RuntimeError(f"compute workers did not start; logs in {logs}")
            paths = await _requests(c)
            t0 = time.perf_counter()
            first = await _burst(c, paths)
            trace = await _wait_empty(engine, t0)
            elapsed = time.perf_counter() - t0
            again = await _burst(c, paths)
        async with engine.connect() as cx:
            jobs = (
                await cx.execute(
                    text(
                        "SELECT kind, status, attempts, lease_owner, "
                        "extract(epoch FROM started_at - created_at) AS wait_s, "
                        "extract(epoch FROM finished_at - started_at) AS run_s, "
                        "extract(epoch FROM finished_at) AS fin, "
                        "extract(epoch FROM created_at) AS cre FROM jobs ORDER BY id"
                    )
                )
            ).all()
    finally:
        for p in procs:
            p.terminate()
        for p in procs:
            try:
                p.wait(timeout=20)
            except subprocess.TimeoutExpired:
                p.kill()
        await engine.dispose()

    span = float(max(j.fin for j in jobs) - min(j.cre for j in jobs)) if jobs else 0.0
    runs = [float(j.run_s) for j in jobs if j.run_s is not None]
    kinds = sorted({j.kind for j in jobs})
    by_status: dict[int, int] = {}
    for r in first:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
    result: dict[str, Any] = {
        "measured_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "workers": WORKERS,
        "cpu_count": os.cpu_count(),
        "requests": len(paths),
        "burst": {
            "status_counts": {str(k): v for k, v in sorted(by_status.items())},
            "latency_ms": _stats([r["ms"] for r in first]),
        },
        "again": {
            "status_counts": {
                str(s): sum(1 for r in again if r["status"] == s)
                for s in sorted({r["status"] for r in again})
            },
            "latency_ms": _stats([r["ms"] for r in again]),
        },
        "jobs": {
            "total": len(jobs),
            "done": sum(1 for j in jobs if j.status == "done"),
            "failed": sum(1 for j in jobs if j.status == "failed"),
            "retried": sum(1 for j in jobs if j.attempts > 1),
        },
        "queue": {
            "empty_after_s": round(elapsed, 1),
            "span_s": round(span, 1),
            "jobs_per_min": round(len(jobs) / elapsed * 60, 1) if elapsed else None,
            "busy_share": round(sum(runs) / (WORKERS * elapsed), 3) if elapsed else None,
            "wait_s": _stats([float(j.wait_s) for j in jobs if j.wait_s is not None]),
            "longest_queue": max((p["queued"] for p in trace), default=0),
        },
        "wait_by_kind_s": {
            k: _stats([float(j.wait_s) for j in jobs if j.kind == k and j.wait_s is not None])
            for k in kinds
        },
        "run_s": {
            k: _stats([float(j.run_s) for j in jobs if j.kind == k and j.run_s is not None])
            for k in kinds
        },
        "trace": trace,
        "requests_detail": first,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=1) + "\n")
    q = result["queue"]
    print(f"{len(paths)} requests, {len(jobs)} jobs, {WORKERS} workers, {os.cpu_count()} CPUs")
    print(f"burst: {result['burst']['status_counts']} latency ms {result['burst']['latency_ms']}")
    print(f"again: {result['again']['status_counts']} latency ms {result['again']['latency_ms']}")
    print(
        f"queue empty after {q['empty_after_s']} s; {q['jobs_per_min']} jobs/min; "
        f"busy {q['busy_share']}; wait s {q['wait_s']}"
    )
    for k, v in result["run_s"].items():
        print(f"{k}: run s {v}; wait s {result['wait_by_kind_s'][k]}")
    print(f"jobs: {result['jobs']}")
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    asyncio.run(main())
