"""M9: every mission's six sections as served, and the warm latency of each section.

Run with the API on :8000 and a compute worker running:
  cd backend && uv run python ../docs/report/scripts/sections.py [--timing]
Writes out/sections/<mission>__<section>.json (the full answers), out/sections.json (status,
compute_ms, engines per answer) and, with --timing, out/section_latency.csv.
"""
from __future__ import annotations

import csv
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
(OUT / "sections").mkdir(parents=True, exist_ok=True)
API = "http://localhost:8000/api/v1"
SECTIONS = ["sections", "ready", "launch", "launch/weather", "trip", "contact", "return"]
TIMED = ["im-1", "im-2", "blue-ghost-m1", "griffin-1"]


def p95(xs: list[float]) -> float:
    s = sorted(xs)
    return s[max(0, -(-95 * len(s) // 100) - 1)]


def path(mid: str, sec: str) -> str:
    """The weather needs an opportunity: the first in the mission's stored launch answer."""
    if sec != "launch/weather":
        return f"{API}/missions/{mid}/{sec}"
    f = OUT / "sections" / f"{mid}__launch.json"
    opps = (json.loads(f.read_text()).get("data") or {}).get("opportunities") if f.exists() else None
    return f"{API}/missions/{mid}/{sec}" + (f"?opportunity={opps[0]['id']}" if opps else "")


def fetch(c: httpx.Client, mid: str, sec: str) -> tuple[int, dict]:
    r = c.get(path(mid, sec))
    if r.status_code != 202:
        return r.status_code, (r.json() if r.headers.get("content-type", "").startswith("application") else {})
    job = r.json()["job_id"]
    t0 = time.monotonic()
    while time.monotonic() - t0 < 900:
        time.sleep(2)
        j = c.get(f"{API}/jobs/{job}").json()
        if j["status"] in ("done", "failed"):
            break
    r = c.get(path(mid, sec))
    return r.status_code, r.json()


def main() -> None:
    head = subprocess.check_output(["git", "-C", str(HERE.parents[2]), "rev-parse", "--short", "HEAD"], text=True).strip()
    with httpx.Client(timeout=120) as c:
        mids = [m["id"] for m in c.get(f"{API}/missions").json()["items"]]
        summary: dict = {"head": head, "missions": {}}
        for mid in mids:
            row = {}
            for sec in SECTIONS:
                code, body = fetch(c, mid, sec)
                (OUT / "sections" / f"{mid}__{sec.replace('/', '_')}.json").write_text(json.dumps(body, indent=1) + "\n")
                meta = body.get("meta") or {}
                row[sec] = {"code": code, "compute_ms": meta.get("compute_ms"), "engines": meta.get("engines"),
                            "stale": meta.get("stale"), "detail": (body.get("detail") if code >= 400 else None)}
            summary["missions"][mid] = row
            print(mid, {k: v["code"] for k, v in row.items()}, flush=True)
        (OUT / "sections.json").write_text(json.dumps(summary, indent=1) + "\n")
        if "--timing" in sys.argv:
            rows = [["section", "missions", "n", "median_ms", "p95_ms"]]
            for sec in SECTIONS:
                ts = []
                for mid in TIMED:
                    c.get(path(mid, sec))
                    for _ in range(20):
                        t = time.perf_counter()
                        r = c.get(path(mid, sec))
                        ts.append((time.perf_counter() - t) * 1000)
                        assert r.status_code == 200, (mid, sec, r.status_code)
                rows.append([sec, "+".join(TIMED), len(ts), round(statistics.median(ts), 1), round(p95(ts), 1)])
                print(rows[-1], flush=True)
            with (OUT / "section_latency.csv").open("w", newline="") as fh:
                csv.writer(fh).writerows(rows + [["# head", head, "", "", ""]])


if __name__ == "__main__":
    main()
