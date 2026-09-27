"""Wind climatology at the launch pads: how often, in a given month and hour, the wind at
50 m has been above a limit (T4 B1, "beyond ensemble range").

Built by ``make climatology`` from NASA POWER's hourly wind at 50 m above the
surface (``WS50M``), which POWER takes from the MERRA-2 reanalysis (a cell of
0.5 by 0.625 degrees), for whole years from 2001. The rule's height, 162 ft,
is 49 m. Stored per model region as a histogram of hourly winds (0.25 m/s
bins, empty ones at the top left out) for each month and UTC hour, so any
limit can be read from it.

Run: ``uv run python -m app.data.climatology`` (writes ``data/climatology/``).
"""

from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx

from app.config import get_settings
from app.data import catalogues
from app.data.download import USER_AGENT

API = "https://power.larc.nasa.gov/api/temporal/hourly/point"
DOCS = "https://power.larc.nasa.gov/docs/services/api/temporal/hourly/"
FIRST_YEAR = 2001
LAST_YEAR = 2024
BIN_M_S = 0.25
N_BINS = 200  # 0 to 50 m/s
FILL = -999.0
#: The pad each model region's climatology is read at (one MERRA-2 cell holds them all).
REGION_PAD = {"florida": "ksc-lc-39a", "vandenberg": "vsfb-slc-4e"}


def path_for(region: str) -> Path:
    return get_settings().data_dir / "climatology" / f"power_ws50m_{region}.json"


def histogram(series: dict[str, float]) -> dict[str, dict[str, list[int]]]:
    """``{"MM": {"HH": counts}}`` from POWER's ``{"YYYYMMDDHH": m/s}``; fill values skipped."""
    out: dict[str, dict[str, list[int]]] = {}
    for stamp, v in series.items():
        if v is None or v == FILL or not math.isfinite(v) or v < 0:
            continue
        mm, hh = stamp[4:6], stamp[8:10]
        row = out.setdefault(mm, {}).setdefault(hh, [0] * N_BINS)
        row[min(N_BINS - 1, int(v / BIN_M_S))] += 1
    for rows in out.values():  # trailing empty bins are left out
        for hh, row in rows.items():
            while row and row[-1] == 0:
                row.pop()
            rows[hh] = row
    return out


@dataclass(frozen=True, slots=True)
class Climatology:
    region: str
    lat_deg: float
    lon_deg: float
    years: str
    source_url: str
    hist: dict[str, dict[str, list[int]]]

    def share_above(self, month: int, hour: int, limit_m_s: float) -> tuple[float, int] | None:
        """Share of the hours in that month and UTC hour above the limit, and how many
        hours were counted. Within a bin the hours are taken as spread evenly."""
        row = self.hist.get(f"{month:02d}", {}).get(f"{hour:02d}")
        if not row:
            return None
        n = sum(row)
        if n == 0:
            return None
        pos = limit_m_s / BIN_M_S
        k = int(math.floor(pos))
        if k >= len(row):
            return 0.0, n
        above = sum(row[k + 1 :]) + row[k] * (1.0 - (pos - k)) if k >= 0 else float(n)
        return above / n, n


@lru_cache(maxsize=8)
def load(region: str) -> Climatology | None:
    p = path_for(region)
    if not p.exists():
        return None
    d = json.loads(p.read_text())
    return Climatology(
        region=region,
        lat_deg=float(d["point"][0]),
        lon_deg=float(d["point"][1]),
        years=str(d["years"]),
        source_url=str(d["source_url"]),
        hist=d["hist"],
    )


def build(region: str, *, first: int = FIRST_YEAR, last: int = LAST_YEAR) -> Path:
    site = catalogues.load("launch_sites").get(REGION_PAD[region])
    assert site.lat_deg is not None and site.lon_deg is not None
    series: dict[str, float] = {}
    with httpx.Client(timeout=180, headers={"User-Agent": USER_AGENT}) as client:
        for y0 in range(first, last + 1, 4):
            y1 = min(last, y0 + 3)
            r = client.get(
                API,
                params={
                    "parameters": "WS50M",
                    "community": "RE",
                    "latitude": f"{site.lat_deg:.4f}",
                    "longitude": f"{site.lon_deg:.4f}",
                    "start": f"{y0}0101",
                    "end": f"{y1}1231",
                    "format": "JSON",
                    "time-standard": "UTC",
                },
            )
            r.raise_for_status()
            body: dict[str, Any] = r.json()
            series.update(body["properties"]["parameter"]["WS50M"])
            print(f"{region}: {y0}-{y1} {len(series)} hours", file=sys.stderr)
    out = {
        "what": "Hourly wind speed at 50 m (WS50M), NASA POWER from MERRA-2, as a histogram "
        "per month and UTC hour",
        "source_url": f"{API}?parameters=WS50M&community=RE&latitude={site.lat_deg:.4f}"
        f"&longitude={site.lon_deg:.4f}&time-standard=UTC",
        "docs": DOCS,
        "point": [site.lat_deg, site.lon_deg],
        "pad": site.id,
        "years": f"{first}-{last}",
        "hours": len(series),
        "bin_m_s": BIN_M_S,
        "built": datetime.now(UTC).isoformat(timespec="seconds"),
        "hist": histogram(series),
    }
    p = path_for(region)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, separators=(",", ":")))
    load.cache_clear()
    return p


if __name__ == "__main__":
    for reg in sys.argv[1:] or list(REGION_PAD):
        print(build(reg))
