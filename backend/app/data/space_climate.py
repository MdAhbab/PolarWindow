"""Records of the Sun's activity used by the radiation estimates (plan track E).

* The Oulu neutron monitor's corrected count rate, month by month, which sets
  the cosmic-ray modulation parameter W (Matthiä et al. 2013). Fetched once by
  ``make space-climate`` from the NMDB database (www.nmdb.eu) and kept in
  ``data/radiation/oulu_nm_monthly.json``. NMDB's terms: free for
  non-commercial use, acknowledged as "We acknowledge the NMDB database
  (www.nmdb.eu), founded under the European Union's FP7 programme (contract no.
  213007), and the PIs of individual neutron monitors at: Oulu (Sodankyla
  Geophysical Observatory of the University of Oulu, Finland)".
* OMNI's hourly record (NASA SPDF, on disk from HelioCloud): the proton flux
  above 10, 30 and 60 MeV at 1 AU (from the GOES satellites) and the daily
  sunspot number.

* Past solar particle events, for "if an event like this happened during the
  trip": the October 1989 series and the late-October 2003 event integrated from
  the GOES proton detectors' 5-minute averages (NOAA NCEI), and the August 1972
  event from King's (1974) fitted spectrum as SPENVIS gives it. Their peaks are
  checked against NOAA SWPC's list of solar proton events.
* NASA DONKI's solar particle events seen by the GOES >10 MeV detector (NOAA's
  event threshold, 10 pfu), to say which fell during a flown trip.

Run: ``uv run python -m app.data.space_climate`` (rewrites the three tables).
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path

import cdflib
import httpx
import numpy as np
import numpy.typing as npt

from app.config import get_settings
from app.data.download import USER_AGENT

NEST = "https://www.nmdb.eu/nest/draw_graph.php"
NMDB_ACK = (
    "We acknowledge the NMDB database (www.nmdb.eu), founded under the European Union's FP7 "
    "programme (contract no. 213007), and the PIs of individual neutron monitors at: Oulu "
    "(Sodankyla Geophysical Observatory of the University of Oulu, Finland)."
)
OULU_URL = "https://cosmicrays.oulu.fi/"
OMNI_URL = "https://spdf.gsfc.nasa.gov/pub/data/omni/omni_cdaweb/hourly/"
FIRST_YEAR = 2009
OMNI_FILL = 99999.0


def sep_path() -> Path:
    return get_settings().data_dir / "radiation" / "sep_scenarios.json"


def donki_path() -> Path:
    return get_settings().data_dir / "radiation" / "donki_sep_goes.json"


def oulu_path() -> Path:
    return get_settings().data_dir / "radiation" / "oulu_nm_monthly.json"


def omni_dir() -> Path:
    return get_settings().data_dir / "spaceweather" / "omni_hourly"


# --- Oulu neutron monitor -----------------------------------------------------------


@lru_cache(maxsize=1)
def oulu_monthly() -> dict[str, float]:
    """``{"YYYY-MM": counts per minute}`` (monthly means of the daily values), or {}."""
    p = oulu_path()
    if not p.exists():
        return {}
    return {k: float(v) for k, v in json.loads(p.read_text())["monthly_counts_per_min"].items()}


def oulu_at(t: datetime) -> tuple[float, str] | None:
    """The monthly mean count rate of ``t``'s month (or the latest month before it)."""
    table = oulu_monthly()
    key = f"{t:%Y-%m}"
    if key in table:
        return table[key], key
    earlier = sorted(k for k in table if k < key)
    return (table[earlier[-1]], earlier[-1]) if earlier else None


def parse_nest(text: str) -> dict[str, float]:
    """Daily ``YYYY-MM-DD HH:MM:SS; value`` rows of a NEST ASCII answer (counts per s)."""
    out: dict[str, float] = {}
    for m in re.finditer(r"^(\d{4}-\d{2}-\d{2}) \d{2}:\d{2}:\d{2};\s*([-\d.]+|null)", text, re.M):
        if m.group(2) != "null":
            out[m.group(1)] = float(m.group(2))
    return out


def build_oulu(first: int = FIRST_YEAR, last: int | None = None) -> Path:
    last = last or datetime.now(UTC).year
    daily: dict[str, float] = {}
    with httpx.Client(timeout=120.0, headers={"User-Agent": USER_AGENT}) as c:
        for y in range(first, last + 1):
            params = {
                "formchk": "1",
                "stations[]": "OULU",
                "output": "ascii",
                "tabchoice": "revori",
                "dtype": "corr_for_efficiency",
                "date_choice": "bydate",
                "start_year": str(y),
                "start_month": "1",
                "start_day": "1",
                "start_hour": "0",
                "start_min": "0",
                "end_year": str(y),
                "end_month": "12",
                "end_day": "31",
                "end_hour": "23",
                "end_min": "59",
                "yunits": "0",
                "tresolution": "1440",
            }
            r = c.get(NEST, params=params)
            r.raise_for_status()
            got = parse_nest(r.text)
            daily.update(got)
            print(f"Oulu {y}: {len(got)} days", file=sys.stderr)
    months: dict[str, list[float]] = {}
    for day, cps in daily.items():
        months.setdefault(day[:7], []).append(cps * 60.0)
    out = {
        "what": "Oulu neutron monitor, corrected for pressure and efficiency (NMDB 1HCOR_E), "
        "monthly means of daily means, counts per minute",
        "source_url": OULU_URL,
        "via": NEST,
        "acknowledgement": NMDB_ACK,
        "built": datetime.now(UTC).isoformat(timespec="seconds"),
        "days": {k: len(v) for k, v in sorted(months.items())},
        "monthly_counts_per_min": {
            k: round(float(np.mean(v)), 1) for k, v in sorted(months.items())
        },
    }
    p = oulu_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, indent=1))
    oulu_monthly.cache_clear()
    return p


# --- OMNI -----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class OmniHours:
    t: list[datetime]
    #: Proton flux above 10, 30 and 60 MeV at 1 AU, per (cm² s sr); NaN when missing.
    p10: npt.NDArray[np.float64]
    p30: npt.NDArray[np.float64]
    p60: npt.NDArray[np.float64]
    #: Daily sunspot number (version 2); NaN when missing.
    sunspots: npt.NDArray[np.float64]
    files: list[str]


def _files(start: datetime, end: datetime) -> list[Path]:
    out = []
    for p in sorted(omni_dir().glob("omni2_h0_mrg1hr_*_v01.cdf")):
        d = datetime.strptime(p.name[16:24], "%Y%m%d").replace(tzinfo=UTC)
        if d <= end and d + timedelta(days=186) >= start:
            out.append(p)
    return out


def omni(start: datetime, end: datetime) -> OmniHours | None:
    """OMNI's hours from ``start`` to ``end``, or None when no file covers them."""
    ts: list[datetime] = []
    cols: dict[str, list[float]] = {"PR-FLX_10": [], "PR-FLX_30": [], "PR-FLX_60": [], "R": []}
    used = []
    for p in _files(start, end):
        c = cdflib.CDF(str(p))
        epoch = cdflib.cdfepoch.to_datetime(c.varget("Epoch"))
        times = [datetime.fromisoformat(str(x)[:19]).replace(tzinfo=UTC) for x in epoch]
        keep = [i for i, t in enumerate(times) if start <= t <= end]
        if not keep:
            continue
        used.append(p.name)
        ts += [times[i] for i in keep]
        for k in cols:
            v = np.asarray(c.varget(k), dtype=np.float64)[keep]
            fill = 999.0 if k == "R" else OMNI_FILL
            cols[k] += list(np.where(v >= fill * 0.999, np.nan, v))
    if not ts:
        return None
    return OmniHours(
        t=ts,
        p10=np.asarray(cols["PR-FLX_10"]),
        p30=np.asarray(cols["PR-FLX_30"]),
        p60=np.asarray(cols["PR-FLX_60"]),
        sunspots=np.asarray(cols["R"]),
        files=used,
    )


# --- past solar particle events ------------------------------------------------------

NCEI_AVG = "https://www.ncei.noaa.gov/data/goes-space-environment-monitor/access/avg"
SWPC_LIST = "https://umbra.nascom.nasa.gov/SEP/"
SPENVIS_SEP = "https://www.spenvis.oma.be/help/background/flare/flare.html"
#: (id, name, satellite file, start, end, SWPC list peak pfu and time)
GOES_EVENTS = (
    (
        "oct-1989",
        "October 1989 (three events, 19-31 October)",
        "1989/10/goes07/csv/g07_eps_5m_19891001_19891031.csv",
        "1989-10-19 12:00",
        "1989-11-01 00:00",
        40000.0,
        "1989-10-20 16:00",
    ),
    (
        "oct-2003",
        "Late October 2003 (28-31 October)",
        "2003/10/goes11/csv/g11_eps_5m_20031001_20031031.csv",
        "2003-10-28 11:00",
        "2003-11-01 00:00",
        29500.0,
        "2003-10-29 06:15",
    ),
)
#: King (1974), as SPENVIS gives it: J(>E) = J0 exp((30 - E) / E0), per cm².
KING_1972 = {"j0_cm2": 7.9e9, "e0_mev": 26.5}
CHANNELS = {10: "p3_flux_ic", 30: "p4_flux_ic", 60: "p6_flux_ic"}


def goes_fluence(text: str, start: str, end: str) -> dict[str, object]:
    """Fluence above 10, 30 and 60 MeV (omnidirectional: 4 pi times the per-steradian
    flux, taken as isotropic) and the >10 MeV peak, from a GOES EPS 5-minute CSV."""
    import csv

    body = text.split("data: \n", 1)[1] if "data: \n" in text else text.split("data:", 1)[1]
    rows = [
        r for r in csv.DictReader(body.strip().splitlines()) if start <= r["time_tag"][:16] <= end
    ]
    out: dict[str, object] = {"samples": len(rows)}
    for e, col in CHANNELS.items():
        v = np.array([float(r[col]) for r in rows])
        ok = v > 0
        out[f"fluence_gt{e}_cm2"] = float(np.sum(v[ok]) * 300.0 * 4.0 * np.pi)
        out[f"missing_gt{e}"] = int(np.sum(~ok))
        if e == 10:
            k = int(np.argmax(np.where(ok, v, -1.0)))
            out["peak_gt10_pfu"] = float(v[k])
            out["peak_at"] = rows[k]["time_tag"][:16]
    return out


def build_sep() -> Path:
    events = []
    with httpx.Client(timeout=180.0, headers={"User-Agent": USER_AGENT}) as c:
        for eid, name, path, a, b, swpc_pfu, swpc_at in GOES_EVENTS:
            r = c.get(f"{NCEI_AVG}/{path}")
            r.raise_for_status()
            got = goes_fluence(r.text, a, b)
            events.append(
                {
                    "id": eid,
                    "name": name,
                    "source": "GOES proton detector, 5-minute averages (NOAA NCEI)",
                    "source_url": f"{NCEI_AVG}/{path}",
                    "start": a,
                    "end": b,
                    **got,
                    "swpc_list_peak_pfu": swpc_pfu,
                    "swpc_list_peak_at": swpc_at,
                    "swpc_list_url": SWPC_LIST,
                }
            )
            print(f"{eid}: {got}", file=sys.stderr)

    def king(e: float) -> float:
        return KING_1972["j0_cm2"] * float(np.exp((30.0 - e) / KING_1972["e0_mev"]))

    events.append(
        {
            "id": "aug-1972",
            "name": "August 1972",
            "source": "King (1974), J. Spacecraft Rockets 11, 401: fitted spectrum "
            "J(>E) = 7.9e9 exp((30 - E)/26.5) per cm², as SPENVIS gives it",
            "source_url": SPENVIS_SEP,
            **{f"fluence_gt{e}_cm2": king(e) for e in CHANNELS},
        }
    )
    out = {
        "what": "Past solar particle events: fluence above 10, 30 and 60 MeV, protons per cm² "
        "(omnidirectional, isotropic), at 1 AU outside Earth's magnetic field",
        "built": datetime.now(UTC).isoformat(timespec="seconds"),
        "events": events,
    }
    p = sep_path()
    p.write_text(json.dumps(out, indent=1))
    sep_scenarios.cache_clear()
    return p


@lru_cache(maxsize=1)
def sep_scenarios() -> list[dict[str, object]]:
    p = sep_path()
    return list(json.loads(p.read_text())["events"]) if p.exists() else []


# --- DONKI ------------------------------------------------------------------------------

DONKI = "https://api.nasa.gov/DONKI/SEP"
DONKI_FIRST = "2019-01-01"


def goes_events(rows: list[dict[str, object]]) -> list[dict[str, str]]:
    """DONKI events whose instrument is a GOES >10 MeV detector (NOAA's threshold)."""
    out = []
    for e in rows:
        names = [str(i.get("displayName", "")) for i in e.get("instruments") or []]  # type: ignore[attr-defined]
        if any("GOES" in n and ">10 MeV" in n for n in names):
            out.append({"id": str(e["sepID"]), "t": str(e["eventTime"]), "link": str(e["link"])})
    return out


def build_donki(first: str = DONKI_FIRST) -> Path:
    key = get_settings().nasa_api_key or "DEMO_KEY"
    now = datetime.now(UTC).date()
    rows: list[dict[str, object]] = []
    start = datetime.fromisoformat(first).date()
    with httpx.Client(timeout=120.0, headers={"User-Agent": USER_AGENT}) as c:
        while start <= now:
            end = min(now, start.replace(year=start.year + 1) - timedelta(days=1))
            r = c.get(DONKI, params={"startDate": str(start), "endDate": str(end), "api_key": key})
            r.raise_for_status()
            rows += r.json() or []
            start = end + timedelta(days=1)
    out = {
        "what": "NASA DONKI solar particle events seen by a GOES >10 MeV detector",
        "source_url": "https://kauai.ccmc.gsfc.nasa.gov/DONKI/",
        "built": datetime.now(UTC).isoformat(timespec="seconds"),
        "from": first,
        "events": goes_events(rows),
    }
    p = donki_path()
    p.write_text(json.dumps(out, indent=1))
    donki_goes.cache_clear()
    return p


@lru_cache(maxsize=1)
def donki_goes() -> tuple[str | None, list[dict[str, str]]]:
    """(built, events) or (None, []) when the table is not on disk."""
    p = donki_path()
    if not p.exists():
        return None, []
    d = json.loads(p.read_text())
    return str(d["built"]), list(d["events"])


if __name__ == "__main__":
    print(build_oulu())
    print(build_sep())
    print(build_donki())
