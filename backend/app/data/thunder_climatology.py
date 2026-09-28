"""Lightning climatology at the launch pads: how often, in a given month and UTC hour,
thunder could be heard at the pad (T4 B1, "beyond ensemble range").

Built by ``make thunder-climatology`` from NASA MSFC's Combined GLM Hourly Thunder
Hour data (GHRC DAAC, doi:10.5067/GLM/HTH/DATA301): for every hour since
1 January 2019, on a 0.05-degree grid, 1 when thunder could be heard at the grid
point in that hour (from the GOES lightning mappers), 0 when not, -1 outside
their view. A day's file is 600 MB, so only the grid cells holding each region's
pads are read, through NASA Earthdata's OPeNDAP service (needs the Earthdata
token, ``PW_EARTHDATA_TOKEN``). Each day read is kept in a cache so a stopped
run carries on where it left off.

Stored per pad as, for each month and UTC hour, the hours seen and the hours
with thunder, so the share is read directly.

Run: ``uv run python -m app.data.thunder_climatology`` (writes ``data/climatology/``).
"""

from __future__ import annotations

import asyncio
import json
import sys
import urllib.parse
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx

from app.config import get_settings
from app.data import catalogues
from app.data.download import USER_AGENT

COLLECTION = "C3894650367-GHRC_DAAC"
DOI_URL = "https://doi.org/10.5067/GLM/HTH/DATA301"
CMR = "https://cmr.earthdata.nasa.gov/search/granules.json"
OPENDAP = f"https://opendap.earthdata.nasa.gov/collections/{COLLECTION}/granules"
FIRST_YEAR = 2019
LAST_YEAR = 2025
#: The grid: 0.05 degree, cell centres from -179.975 east and 89.975 north.
STEP_DEG = 0.05
LON0 = -179.975
LAT0 = 89.975
N_LON = 7200
N_LAT = 3600
#: The pads each region's climatology is read at.
REGION_PADS = {
    "florida": ("ksc-lc-39a", "ccsfs-slc-40", "ccsfs-slc-41", "ccsfs-lc-36"),
    "vandenberg": ("vsfb-slc-4e",),
}
CONCURRENCY = 16


def path_for(region: str) -> Path:
    return get_settings().data_dir / "climatology" / f"glm_thunder_{region}.json"


def cache_for(region: str) -> Path:
    return get_settings().data_dir / "climatology" / f"glm_thunder_{region}.cache.jsonl"


def cell_of(lat_deg: float, lon_deg: float) -> tuple[int, int]:
    """The grid cell (longitude index, latitude index) holding a point."""
    i = round((lon_deg - LON0) / STEP_DEG)
    j = round((LAT0 - lat_deg) / STEP_DEG)
    return min(max(i, 0), N_LON - 1), min(max(j, 0), N_LAT - 1)


def parse_csv(text: str, i0: int, j0: int) -> dict[tuple[int, int], list[int]]:
    """OPeNDAP's CSV answer for ``thunder_hours[i0:i1][j0:j1][0:23]`` → 24 values per cell."""
    out: dict[tuple[int, int], list[int]] = {}
    for line in text.splitlines():
        if not line.startswith("/thunder_hours["):
            continue
        head, _, rest = line.partition(",")
        idx = [int(x) for x in head[len("/thunder_hours[") : -1].split("][")]
        vals = [int(v) for v in rest.split(",")]
        if len(idx) != 2 or len(vals) != 24:
            raise ValueError(f"unexpected row: {line[:80]}")
        out[(i0 + idx[0], j0 + idx[1])] = vals
    return out


def tally(
    days: list[dict[str, Any]], pads: list[str]
) -> dict[str, dict[str, dict[str, list[int]]]]:
    """Per pad, month and UTC hour: [hours seen, hours with thunder]."""
    out: dict[str, dict[str, dict[str, list[int]]]] = {
        p: {f"{m:02d}": {f"{h:02d}": [0, 0] for h in range(24)} for m in range(1, 13)} for p in pads
    }
    for d in days:
        month = d["day"][4:6]
        for p in pads:
            for h, v in enumerate(d["pads"].get(p) or []):
                if v < 0:
                    continue
                row = out[p][month][f"{h:02d}"]
                row[0] += 1
                row[1] += 1 if v > 0 else 0
    return out


@dataclass(frozen=True, slots=True)
class ThunderClimatology:
    region: str
    years: str
    source_url: str
    counts: dict[str, dict[str, dict[str, list[int]]]]

    def share(self, pad_id: str, month: int, hour: int) -> tuple[float, int, int] | None:
        """Share of the hours in that month and UTC hour with thunder at the pad, with the
        hours with thunder and the hours seen."""
        row = self.counts.get(pad_id, {}).get(f"{month:02d}", {}).get(f"{hour:02d}")
        if not row or row[0] == 0:
            return None
        return row[1] / row[0], row[1], row[0]


@lru_cache(maxsize=8)
def load(region: str) -> ThunderClimatology | None:
    p = path_for(region)
    if not p.exists():
        return None
    d = json.loads(p.read_text())
    return ThunderClimatology(
        region=region, years=str(d["years"]), source_url=str(d["source_url"]), counts=d["counts"]
    )


# --- building ------------------------------------------------------------------------


def _granules(first: int, last: int) -> list[str]:
    """Granule file names of whole days in the years asked, listed through CMR."""
    names: list[str] = []
    after: str | None = None
    with httpx.Client(timeout=60.0, headers={"User-Agent": USER_AGENT}) as c:
        while True:
            r = c.get(
                CMR,
                params={
                    "collection_concept_id": COLLECTION,
                    "page_size": 2000,
                    "temporal": f"{first}-01-01T00:00:00Z,{last}-12-31T23:59:59Z",
                },
                headers={"CMR-Search-After": after} if after else {},
            )
            r.raise_for_status()
            entries = r.json()["feed"]["entry"]
            names += [g["title"] for g in entries if g["title"].startswith("GLMc_hth_")]
            after = r.headers.get("CMR-Search-After")
            if not entries or not after:
                break
    return sorted({n for n in names if first <= int(n[9:13]) <= last})


def _box(pads: list[tuple[str, tuple[int, int]]]) -> tuple[int, int, int, int]:
    i = [c[0] for _, c in pads]
    j = [c[1] for _, c in pads]
    return min(i), max(i), min(j), max(j)


async def _one(
    c: httpx.AsyncClient, name: str, box: tuple[int, int, int, int]
) -> dict[tuple[int, int], list[int]]:
    i0, i1, j0, j1 = box
    ce = urllib.parse.quote(f"/thunder_hours[{i0}:1:{i1}][{j0}:1:{j1}][0:1:23]", safe="/:")
    url = f"{OPENDAP}/{name}.dap.csv?dap4.ce={ce}"
    for attempt in range(6):
        try:
            r = await c.get(url)
            if r.status_code == 200:
                return parse_csv(r.text, i0, j0)
            if r.status_code in (401, 403):
                raise RuntimeError(f"Earthdata refused the token ({r.status_code})")
        except httpx.TransportError:
            pass
        await asyncio.sleep(2.0 * (attempt + 1))
    raise RuntimeError(f"{name}: no answer after 6 tries")


async def _fetch(region: str, names: list[str], pads: list[tuple[str, tuple[int, int]]]) -> None:
    token = get_settings().earthdata_token
    if not token:
        raise SystemExit("needs PW_EARTHDATA_TOKEN (NASA Earthdata Login, free)")
    cache = cache_for(region)
    cache.parent.mkdir(parents=True, exist_ok=True)
    done = (
        {json.loads(x)["day"] for x in cache.read_text().splitlines()} if cache.exists() else set()
    )
    todo = [n for n in names if n[9:17] not in done]
    box = _box(pads)
    sem = asyncio.Semaphore(CONCURRENCY)
    headers = {"Authorization": f"Bearer {token}", "User-Agent": USER_AGENT}
    n_done = 0
    async with httpx.AsyncClient(follow_redirects=True, timeout=300.0, headers=headers) as c:

        async def job(name: str) -> None:
            nonlocal n_done
            async with sem:
                cells = await _one(c, name, box)
            row = {"day": name[9:17], "pads": {p: cells.get(cell) for p, cell in pads}}
            with cache.open("a") as f:
                f.write(json.dumps(row, separators=(",", ":")) + "\n")
            n_done += 1
            if n_done % 100 == 0:
                print(f"{region}: {n_done}/{len(todo)} days", file=sys.stderr)

        await asyncio.gather(*(job(n) for n in todo))


def build(region: str, *, first: int = FIRST_YEAR, last: int = LAST_YEAR) -> Path:
    sites = catalogues.load("launch_sites")
    pads = []
    for pid in REGION_PADS[region]:
        s = sites.get(pid)
        assert s.lat_deg is not None and s.lon_deg is not None
        pads.append((pid, cell_of(s.lat_deg, s.lon_deg)))
    names = _granules(first, last)
    asyncio.run(_fetch(region, names, pads))
    wanted = {n[9:17] for n in names}
    days = [
        d
        for d in (json.loads(x) for x in cache_for(region).read_text().splitlines())
        if d["day"] in wanted
    ]
    days = list({d["day"]: d for d in days}.values())
    out = {
        "what": "Hours in which thunder could be heard at each pad's grid cell, per month and "
        "UTC hour: [hours seen by a lightning mapper, hours with thunder]",
        "source_url": DOI_URL,
        "dataset": "Combined GLM Hourly Thunder Hour data (NASA MSFC, GHRC DAAC)",
        "grid_deg": STEP_DEG,
        "cells": {p: list(cell) for p, cell in pads},
        "years": f"{first}-{last}",
        "days": len(days),
        "days_listed": len(names),
        "built": datetime.now(UTC).isoformat(timespec="seconds"),
        "counts": tally(days, [p for p, _ in pads]),
    }
    p = path_for(region)
    p.write_text(json.dumps(out, separators=(",", ":")))
    load.cache_clear()
    return p


if __name__ == "__main__":
    for reg in sys.argv[1:] or list(REGION_PADS):
        print(build(reg))
